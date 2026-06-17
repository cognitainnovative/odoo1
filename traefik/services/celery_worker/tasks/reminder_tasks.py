"""Reminder background tasks — payment, contract, and planning job reminders."""
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
    name="tasks.reminder_tasks.send_payment_reminders",
    queue="reminders",
)
def send_payment_reminders():
    """Send payment reminders for all overdue customer invoices.

    Calls account.move.action_send_payment_reminder() on every posted
    invoice with days_overdue > 0.
    """
    try:
        db, uid, models = _odoo()
        overdue_ids = models.execute_kw(
            db, uid, ODOO_PASS,
            "account.move", "search",
            [[
                ["move_type", "=", "out_invoice"],
                ["state", "=", "posted"],
                ["payment_state", "not in", ["paid", "in_payment"]],
                ["invoice_date_due", "<", _today()],
            ]],
        )
        if overdue_ids:
            _logger.info("send_payment_reminders: %d overdue invoices", len(overdue_ids))
            models.execute_kw(
                db, uid, ODOO_PASS,
                "account.move", "action_send_payment_reminder", [overdue_ids],
            )
    except Exception as exc:
        _logger.error("send_payment_reminders error: %s", exc)


@app.task(
    name="tasks.reminder_tasks.send_contract_reminders",
    queue="reminders",
)
def send_contract_reminders():
    """Notify HR about employee contracts expiring within 60 days.

    Delegates to hr.employee.cron_contract_reminders() which already
    handles the 60-day look-ahead window.
    """
    try:
        db, uid, models = _odoo()
        models.execute_kw(
            db, uid, ODOO_PASS,
            "hr.employee", "cron_contract_reminders", [[]],
        )
        _logger.info("send_contract_reminders: done")
    except Exception as exc:
        _logger.error("send_contract_reminders error: %s", exc)


@app.task(
    name="tasks.reminder_tasks.send_planning_reminder",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="reminders",
)
def send_planning_reminder(self, db_name, job_id):
    """Send a reminder to the employee assigned to a planning job."""
    try:
        db, uid, models = _odoo(db_name)
        models.execute_kw(
            db, uid, ODOO_PASS,
            "planning.job", "action_send_reminder", [[job_id]],
        )
        _logger.info("send_planning_reminder: job %s notified", job_id)
    except Exception as exc:
        _logger.error("send_planning_reminder failed for job %s: %s", job_id, exc)
        raise self.retry(exc=exc)


def _today():
    import datetime
    return datetime.date.today().isoformat()
