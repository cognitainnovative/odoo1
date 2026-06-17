"""Celery task dispatch bridge for Odoo addons.

Sends tasks to the Celery worker via Redis broker.
Falls back to returning False when Celery/Redis is unavailable so callers
can run the operation synchronously instead.

Usage:
    from odoo.addons.custom_ai_core.lib.task_bridge import dispatch

    dispatched = dispatch("tasks.ai_tasks.embed_document", args=[env.cr.dbname, doc.id])
    if not dispatched:
        doc._do_index()   # sync fallback
"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_celery_app = None
_celery_checked = False


def _get_celery():
    global _celery_app, _celery_checked
    if _celery_checked:
        return _celery_app
    _celery_checked = True
    try:
        from celery import Celery  # noqa: PLC0415

        _celery_app = Celery(broker=REDIS_URL)
        _celery_app.config_from_object({"task_serializer": "json", "accept_content": ["json"]})
        _logger.info("task_bridge: Celery broker connected at %s", REDIS_URL)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("task_bridge: Celery unavailable (%s) — sync fallback active", exc)
        _celery_app = None
    return _celery_app


# Opt-in: async is only used when explicitly enabled AND a worker is live.
# Default is sync execution, so indexing works out of the box without a worker.
_ASYNC_ENABLED = os.environ.get("AI_TASKS_ASYNC", "0") in ("1", "true", "True")


def _worker_is_live(app) -> bool:
    """Return True only if at least one Celery worker is actually responding.

    send_task() succeeds even with no worker (it just buffers to the broker),
    so we must actively ping workers before trusting async dispatch — otherwise
    tasks vanish into a queue nobody consumes.
    """
    try:
        replies = app.control.ping(timeout=1.0)
        return bool(replies)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("task_bridge: worker ping failed (%s)", exc)
        return False


def dispatch(
    task_name: str, args: tuple | list = (), kwargs: dict | None = None, countdown: int = 0
) -> bool:
    """Send a task to the Celery queue IF async is enabled and a worker is live.

    Returns True only when the task was handed to a confirmed-live worker.
    Returns False otherwise, so the caller runs the operation synchronously.
    This guarantees work never disappears into a queue with no consumer.
    """
    if not _ASYNC_ENABLED:
        return False  # sync mode (default) — caller does the work inline
    app = _get_celery()
    if app is None:
        return False
    if not _worker_is_live(app):
        _logger.warning("task_bridge: no live Celery worker — sync fallback for %s", task_name)
        return False
    try:
        app.send_task(task_name, args=list(args), kwargs=kwargs or {}, countdown=countdown)
        _logger.debug("task_bridge: dispatched %s args=%s", task_name, args)
        return True
    except Exception as exc:  # noqa: BLE001
        _logger.warning("task_bridge: dispatch failed (%s) — sync fallback", exc)
        return False
