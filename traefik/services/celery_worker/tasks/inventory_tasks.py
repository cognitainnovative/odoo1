"""Inventory background tasks — AI reorder suggestions."""
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
    name="tasks.inventory_tasks.check_reorder_levels",
    queue="inventory",
)
def check_reorder_levels():
    """Run AI reorder suggestions across all active stock alert rules."""
    try:
        db, uid, models = _odoo()
        alert_ids = models.execute_kw(
            db, uid, ODOO_PASS,
            "stock.alert", "search",
            [[["active", "=", True]]],
        )
        if not alert_ids:
            return
        _logger.info("check_reorder_levels: checking %d alert rules", len(alert_ids))
        models.execute_kw(
            db, uid, ODOO_PASS,
            "stock.alert", "action_ai_suggest_reorder", [alert_ids],
        )
    except Exception as exc:
        _logger.error("check_reorder_levels error: %s", exc)
