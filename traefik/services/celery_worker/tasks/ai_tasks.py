"""AI background tasks — document embedding, RAG indexing, async AI calls."""
import logging
import os
import xmlrpc.client

from celery_app import app

_logger = logging.getLogger(__name__)

ODOO_URL = os.environ.get("ODOO_URL", "http://localhost:8070")
ODOO_DB = os.environ.get("ODOO_DB", "v19_platform_dev")
ODOO_USER = os.environ.get("ODOO_ADMIN_USER", "admin")
ODOO_PASS = os.environ.get("ODOO_ADMIN_PASSWORD", "admin")


def _odoo(db=None):
    """Return (uid, models_proxy) authenticated against Odoo XML-RPC."""
    db = db or ODOO_DB
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(db, ODOO_USER, ODOO_PASS, {})
    if not uid:
        raise RuntimeError(f"Odoo auth failed for user '{ODOO_USER}' on db '{db}'")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return db, uid, models


@app.task(
    name="tasks.ai_tasks.embed_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="ai",
)
def embed_document(self, db_name, document_id):
    """Chunk and embed a single ai.document record (by ID) in Odoo.

    Odoo's _do_index() already handles chunking + embedding + pgvector write.
    We just trigger it from outside so the Odoo worker is not blocked.
    """
    try:
        db, uid, models = _odoo(db_name)
        models.execute_kw(db, uid, ODOO_PASS, "ai.document", "action_index", [[document_id]])
        _logger.info("embed_document: document %s indexed OK", document_id)
    except Exception as exc:
        _logger.error("embed_document failed for doc %s: %s", document_id, exc)
        raise self.retry(exc=exc)


@app.task(
    name="tasks.ai_tasks.recover_pending_documents",
    queue="ai",
)
def recover_pending_documents():
    """Re-trigger indexing for documents stuck in 'pending' > 30 minutes."""
    import datetime

    try:
        db, uid, models = _odoo()
        cutoff = (
            datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
        ).strftime("%Y-%m-%d %H:%M:%S")
        stuck = models.execute_kw(
            db, uid, ODOO_PASS,
            "ai.document", "search",
            [[["status", "=", "pending"], ["write_date", "<", cutoff]]],
        )
        if stuck:
            _logger.info("recover_pending_documents: re-indexing %d stuck docs", len(stuck))
            models.execute_kw(db, uid, ODOO_PASS, "ai.document", "action_index", [stuck])
    except Exception as exc:
        _logger.error("recover_pending_documents error: %s", exc)


@app.task(
    name="tasks.ai_tasks.ai_call_async",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="ai",
)
def ai_call_async(self, db_name, model_name, record_id, method_name, kwargs=None):
    """Call an arbitrary Odoo method asynchronously (for long AI drafts, summaries, etc.)."""
    try:
        db, uid, models = _odoo(db_name)
        result = models.execute_kw(
            db, uid, ODOO_PASS,
            model_name, method_name, [[record_id]],
            kwargs or {},
        )
        _logger.info("ai_call_async %s.%s(%s): OK", model_name, method_name, record_id)
        return result
    except Exception as exc:
        _logger.error("ai_call_async %s.%s(%s) failed: %s", model_name, method_name, record_id, exc)
        raise self.retry(exc=exc)
