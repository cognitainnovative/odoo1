"""Accounting background tasks — reconciliation suggestions, bank statement processing."""
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
    db = db or ODOO_DB
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(db, ODOO_USER, ODOO_PASS, {})
    if not uid:
        raise RuntimeError(f"Odoo auth failed for user '{ODOO_USER}' on db '{db}'")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return db, uid, models


@app.task(
    name="tasks.accounting_tasks.suggest_reconciliation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="accounting",
)
def suggest_reconciliation(self, db_name, statement_line_id):
    """Compute AI reconciliation suggestions for a bank statement line.

    Calls account.bank.statement.line's action_ai_suggest method which
    runs the scoring logic and writes candidates back to the record.
    """
    try:
        db, uid, models = _odoo(db_name)
        models.execute_kw(
            db, uid, ODOO_PASS,
            "account.bank.statement.line",
            "action_ai_suggest",
            [[statement_line_id]],
        )
        _logger.info("suggest_reconciliation: line %s scored OK", statement_line_id)
    except Exception as exc:
        _logger.error("suggest_reconciliation failed for line %s: %s", statement_line_id, exc)
        raise self.retry(exc=exc)


@app.task(
    name="tasks.accounting_tasks.process_bank_statement",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="accounting",
)
def process_bank_statement(self, db_name, statement_id):
    """Fan out reconciliation suggestions for all lines in a bank statement."""
    try:
        db, uid, models = _odoo(db_name)
        lines = models.execute_kw(
            db, uid, ODOO_PASS,
            "account.bank.statement.line",
            "search",
            [[["statement_id", "=", statement_id]]],
        )
        for line_id in lines:
            suggest_reconciliation.delay(db_name, line_id)
        _logger.info("process_bank_statement: queued %d lines for statement %s", len(lines), statement_id)
    except Exception as exc:
        _logger.error("process_bank_statement failed for statement %s: %s", statement_id, exc)
        raise self.retry(exc=exc)
