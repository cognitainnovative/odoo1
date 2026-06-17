"""Celery application — broker: Redis, backend: Redis.

Start worker:   celery -A celery_app worker -l info -Q default,ai,accounting,social,inventory
Start beat:     celery -A celery_app beat  -l info
"""
import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "platform_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.ai_tasks",
        "tasks.accounting_tasks",
        "tasks.social_tasks",
        "tasks.inventory_tasks",
        "tasks.payroll_tasks",
        "tasks.reminder_tasks",
        "tasks.ocr_tasks",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Amsterdam",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.ai_tasks.*": {"queue": "ai"},
        "tasks.accounting_tasks.*": {"queue": "accounting"},
        "tasks.social_tasks.*": {"queue": "social"},
        "tasks.inventory_tasks.*": {"queue": "inventory"},
        "tasks.payroll_tasks.*": {"queue": "payroll"},
        "tasks.reminder_tasks.*": {"queue": "reminders"},
        "tasks.ocr_tasks.*": {"queue": "ocr"},
    },
    beat_schedule={
        # Publish any social posts whose scheduled_at <= now
        "publish-scheduled-posts": {
            "task": "tasks.social_tasks.publish_scheduled_posts",
            "schedule": crontab(minute="*/5"),
        },
        # Check reorder levels every morning at 07:00
        "check-reorder-levels": {
            "task": "tasks.inventory_tasks.check_reorder_levels",
            "schedule": crontab(hour=7, minute=0),
        },
        # Re-index documents stuck in 'pending' for > 30 min (recovery)
        "recover-pending-docs": {
            "task": "tasks.ai_tasks.recover_pending_documents",
            "schedule": crontab(minute="*/30"),
        },
        # Send payment reminders for overdue invoices every weekday at 09:00
        "payment-reminders": {
            "task": "tasks.reminder_tasks.send_payment_reminders",
            "schedule": crontab(hour=9, minute=0, day_of_week="1-5"),
        },
        # Check employee contract expiry every Monday at 08:00
        "contract-reminders": {
            "task": "tasks.reminder_tasks.send_contract_reminders",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),
        },
    },
)
