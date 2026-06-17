"""Payroll background tasks — batch payslip calculation."""
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
    name="tasks.payroll_tasks.calculate_payroll_run",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="payroll",
    time_limit=600,  # payroll calc can be slow for large headcounts
)
def calculate_payroll_run(self, db_name, run_id):
    """Trigger payroll.run.action_calculate() asynchronously.

    Calculates all payslips in the run (gross→net, LHK, vakantiegeld,
    employer costs). Can take minutes for large headcounts — must not
    block an Odoo worker thread.
    """
    try:
        db, uid, models = _odoo(db_name)
        models.execute_kw(
            db, uid, ODOO_PASS,
            "payroll.run", "action_calculate", [[run_id]],
        )
        _logger.info("calculate_payroll_run: run %s calculated OK", run_id)
    except Exception as exc:
        _logger.error("calculate_payroll_run failed for run %s: %s", run_id, exc)
        raise self.retry(exc=exc)


@app.task(
    name="tasks.payroll_tasks.publish_payslips",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="payroll",
)
def publish_payslips(self, db_name, run_id):
    """Publish (portal-visible) all payslips in a payroll run after approval."""
    try:
        db, uid, models = _odoo(db_name)
        models.execute_kw(
            db, uid, ODOO_PASS,
            "payroll.run", "action_publish_payslips", [[run_id]],
        )
        _logger.info("publish_payslips: run %s payslips published", run_id)
    except Exception as exc:
        _logger.error("publish_payslips failed for run %s: %s", run_id, exc)
        raise self.retry(exc=exc)
