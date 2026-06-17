"""Social media background tasks — scheduled post publishing."""
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
    name="tasks.social_tasks.publish_scheduled_posts",
    queue="social",
)
def publish_scheduled_posts():
    """Publish all social.post records whose scheduled_at is due and state='scheduled'."""
    import datetime

    try:
        db, uid, models = _odoo()
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        due_posts = models.execute_kw(
            db, uid, ODOO_PASS,
            "social.post", "search",
            [[
                ["state", "=", "scheduled"],
                ["scheduled_at", "<=", now],
            ]],
        )
        if not due_posts:
            return

        _logger.info("publish_scheduled_posts: publishing %d posts", len(due_posts))
        for post_id in due_posts:
            publish_single_post.delay(db, post_id)
    except Exception as exc:
        _logger.error("publish_scheduled_posts error: %s", exc)


@app.task(
    name="tasks.social_tasks.publish_single_post",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    queue="social",
)
def publish_single_post(self, db_name, post_id):
    """Publish a single social.post (calls action_publish on the Odoo record)."""
    try:
        db, uid, models = _odoo(db_name)
        models.execute_kw(
            db, uid, ODOO_PASS,
            "social.post", "action_publish", [[post_id]],
        )
        _logger.info("publish_single_post: post %s published", post_id)
    except Exception as exc:
        _logger.error("publish_single_post failed for post %s: %s", post_id, exc)
        raise self.retry(exc=exc)
