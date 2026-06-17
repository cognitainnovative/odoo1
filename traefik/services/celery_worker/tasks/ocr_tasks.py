"""OCR background tasks — invoice / document extraction.

The Odoo-side method (account.move.action_ocr_extract) is a planned
deliverable in custom_accounting_basic. This task handles the async
dispatch so the architecture is wired; swap the execute_kw call for
the real method name when the addon method is implemented.

Supported providers (set OCR_PROVIDER env var):
  mindee   — Mindee API (MINDEE_API_KEY required)
  azure    — Azure Document Intelligence (AZURE_DOCAI_ENDPOINT + AZURE_DOCAI_KEY)
  mock     — Returns dummy data; used when no key is configured
"""
import logging
import os
import xmlrpc.client

from celery_app import app

_logger = logging.getLogger(__name__)

ODOO_URL = os.environ.get("ODOO_URL", "http://localhost:8070")
ODOO_DB = os.environ.get("ODOO_DB", "v19_platform_dev")
ODOO_USER = os.environ.get("ODOO_ADMIN_USER", "admin")
ODOO_PASS = os.environ.get("ODOO_ADMIN_PASSWORD", "admin")
OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "mock")


def _odoo(db=None):
    db = db or ODOO_DB
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(db, ODOO_USER, ODOO_PASS, {})
    if not uid:
        raise RuntimeError(f"Odoo auth failed for user '{ODOO_USER}' on db '{db}'")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return db, uid, models


@app.task(
    name="tasks.ocr_tasks.extract_invoice",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="ocr",
)
def extract_invoice(self, db_name, attachment_id):
    """Run OCR on an uploaded invoice attachment and write extracted fields back.

    Calls account.move.action_ocr_extract() on the move linked to the
    attachment. That method (in custom_accounting_basic) reads OCR_PROVIDER
    and populates partner, amount, due date, VAT lines, etc.

    TODO: implement action_ocr_extract in custom_accounting_basic once
    Mindee / Azure Document Intelligence credentials are available.
    """
    try:
        db, uid, models = _odoo(db_name)

        # Find the account.move linked to this attachment
        moves = models.execute_kw(
            db, uid, ODOO_PASS,
            "account.move", "search",
            [[["attachment_ids", "in", [attachment_id]]]],
            {"limit": 1},
        )
        if not moves:
            _logger.warning("extract_invoice: no move found for attachment %s", attachment_id)
            return

        move_id = moves[0]
        models.execute_kw(
            db, uid, ODOO_PASS,
            "account.move", "action_ocr_extract", [[move_id]],
            {"attachment_id": attachment_id, "provider": OCR_PROVIDER},
        )
        _logger.info("extract_invoice: attachment %s → move %s extracted OK", attachment_id, move_id)
    except Exception as exc:
        _logger.error("extract_invoice failed for attachment %s: %s", attachment_id, exc)
        raise self.retry(exc=exc)


@app.task(
    name="tasks.ocr_tasks.extract_batch",
    queue="ocr",
)
def extract_batch(db_name, attachment_ids):
    """Fan out OCR extraction for a list of attachment IDs."""
    _logger.info("extract_batch: queuing %d attachments", len(attachment_ids))
    for att_id in attachment_ids:
        extract_invoice.delay(db_name, att_id)
