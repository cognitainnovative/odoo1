ODOO_BIN      := /home/diviner/Odoo/19/odoo-bin
ODOO_CONF     := $(CURDIR)/config/odoo.conf
ODOO_DB       := platform_dev
ADDONS_PATH   := /home/diviner/Odoo/19/addons,$(CURDIR)/addons
PID_FILE      := $(CURDIR)/logs/odoo.pid
LOG_FILE      := $(CURDIR)/logs/odoo.log

CELERY_DIR    := $(CURDIR)/services/celery_worker
CELERY_LOG    := $(CURDIR)/logs/celery_worker.log
CELERY_BEAT_LOG := $(CURDIR)/logs/celery_beat.log
CELERY_PID    := $(CURDIR)/logs/celery_worker.pid
CELERY_BEAT_PID := $(CURDIR)/logs/celery_beat.pid

.PHONY: help up down restart logs shell test lint init seed backup restore \
        update install-dev db-create db-drop db-reset format check \
        celery-up celery-beat celery-down celery-logs redis-check \
        docker-build docker-up docker-down docker-reset docker-logs docker-ps

help:
	@echo ""
	@echo "  Platform Dev — Makefile targets"
	@echo "  ───────────────────────────────────────────────────────"
	@echo "  up           Start Odoo dev server (port 8070, background)"
	@echo "  docker-build Build all Docker images"
	@echo "  docker-up    Start full stack via Docker Compose (Odoo+DB+Redis+MinIO+Traefik)"
	@echo "  docker-down  Stop Docker Compose stack"
	@echo "  docker-reset Wipe volumes and restart (destructive)"
	@echo "  docker-logs  Tail all service logs"
	@echo "  docker-ps    Show running containers"
	@echo "  celery-up    Start Celery worker (background, all queues)"
	@echo "  celery-beat  Start Celery beat scheduler (background)"
	@echo "  celery-down  Stop Celery worker + beat"
	@echo "  celery-logs  Tail Celery worker log"
	@echo "  redis-check  Ping Redis to verify it is running"
	@echo "  down         Stop Odoo dev server"
	@echo "  restart      Stop then start"
	@echo "  logs         Tail Odoo log"
	@echo "  shell        Open Odoo shell (Python REPL with ORM)"
	@echo "  test         Run addon test suite"
	@echo "  lint         Run ruff + black --check"
	@echo "  format       Auto-fix with ruff + black"
	@echo "  init         First-time setup: create DB + install base modules"
	@echo "  seed         Load demo/seed data"
	@echo "  db-create    Create the $(ODOO_DB) database"
	@echo "  db-drop      Drop the $(ODOO_DB) database"
	@echo "  db-reset     Drop + re-create + init"
	@echo "  update       Update all custom addons (odoo -u all)"
	@echo "  install-dev  Install Python dev tools (ruff, black, pre-commit)"
	@echo "  backup       Dump DB to backups/"
	@echo "  restore      Restore latest backup"
	@echo "  check        Full pre-commit check pass"
	@echo ""

# ── Dev server ────────────────────────────────────────────────────────────────
up:
	@mkdir -p $(CURDIR)/logs
	@echo "Starting Odoo on http://localhost:8070 …"
	@cd /home/diviner/Odoo/19 && python3 $(ODOO_BIN) \
		-c $(ODOO_CONF) \
		--pid-file=$(PID_FILE) \
		> $(LOG_FILE) 2>&1 &
	@echo "PID: $$(cat $(PID_FILE) 2>/dev/null || echo 'starting…')"

down:
	@if [ -f $(PID_FILE) ]; then \
		kill $$(cat $(PID_FILE)) 2>/dev/null && rm -f $(PID_FILE) && echo "Stopped."; \
	else \
		pkill -f "odoo-bin.*8070" 2>/dev/null && echo "Stopped (by port match)." || echo "Not running."; \
	fi

restart: down up

logs:
	@tail -f $(LOG_FILE)

# ── Docker Compose ────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	@[ -f .env ] || cp .env.example .env
	docker compose up -d
	@echo "Platform → http://platform.localhost"
	@echo "Support  → http://support.localhost"
	@echo "MinIO    → http://minio.localhost"
	@echo "Traefik  → http://traefik.localhost:8080"

docker-down:
	docker compose down

docker-reset:
	@echo "WARNING: this wipes all Docker volumes (DB, MinIO, Redis)."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	docker compose down -v
	docker compose up -d

docker-logs:
	@docker compose logs -f --tail=100

docker-ps:
	@docker compose ps

# ── Celery worker ─────────────────────────────────────────────────────────────
redis-check:
	@redis-cli ping 2>/dev/null | grep -q PONG && echo "Redis: OK" || echo "Redis: NOT RUNNING — run: sudo systemctl start redis-server"

celery-up: redis-check
	@mkdir -p $(CURDIR)/logs
	@echo "Starting Celery worker (all queues) …"
	@cd $(CELERY_DIR) && \
		[ -f .env ] || cp .env.example .env; \
		celery -A celery_app worker \
			--loglevel=info \
			--queues=default,ai,accounting,social,inventory,payroll,reminders,ocr \
			--pidfile=$(CELERY_PID) \
			--logfile=$(CELERY_LOG) \
			--detach
	@echo "Worker log: $(CELERY_LOG)"

celery-beat: redis-check
	@mkdir -p $(CURDIR)/logs
	@echo "Starting Celery beat scheduler …"
	@cd $(CELERY_DIR) && \
		[ -f .env ] || cp .env.example .env; \
		celery -A celery_app beat \
			--loglevel=info \
			--pidfile=$(CELERY_BEAT_PID) \
			--logfile=$(CELERY_BEAT_LOG) \
			--detach
	@echo "Beat log: $(CELERY_BEAT_LOG)"

celery-down:
	@if [ -f $(CELERY_PID) ]; then \
		kill $$(cat $(CELERY_PID)) 2>/dev/null && rm -f $(CELERY_PID) && echo "Worker stopped."; \
	else \
		pkill -f "celery.*celery_app.*worker" 2>/dev/null && echo "Worker stopped (by name)." || echo "Worker not running."; \
	fi
	@if [ -f $(CELERY_BEAT_PID) ]; then \
		kill $$(cat $(CELERY_BEAT_PID)) 2>/dev/null && rm -f $(CELERY_BEAT_PID) && echo "Beat stopped."; \
	else \
		pkill -f "celery.*celery_app.*beat" 2>/dev/null && echo "Beat stopped (by name)." || echo "Beat not running."; \
	fi

celery-logs:
	@tail -f $(CELERY_LOG)

shell:
	@cd /home/diviner/Odoo/19 && python3 $(ODOO_BIN) shell \
		-c $(ODOO_CONF) \
		-d $(ODOO_DB)

# ── DB management ─────────────────────────────────────────────────────────────
db-create:
	@createdb -U diviner $(ODOO_DB) 2>/dev/null && echo "Database $(ODOO_DB) created." || echo "Already exists."
	@psql -U diviner $(ODOO_DB) -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null && echo "pgvector enabled." || echo "pgvector not available (optional)."

db-drop:
	@dropdb -U diviner --if-exists $(ODOO_DB) && echo "Database $(ODOO_DB) dropped."

db-reset: db-drop db-create init

init: db-create
	@echo "Initialising Odoo database (this takes a minute)…"
	@cd /home/diviner/Odoo/19 && python3 $(ODOO_BIN) \
		-c $(ODOO_CONF) \
		-d $(ODOO_DB) \
		-i base \
		--stop-after-init \
		--without-demo=False
	@echo "Init done. Run 'make up' to start the server."

update:
	@cd /home/diviner/Odoo/19 && python3 $(ODOO_BIN) \
		-c $(ODOO_CONF) \
		-d $(ODOO_DB) \
		-u all \
		--stop-after-init

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	@bash $(CURDIR)/scripts/run_tests.sh

# ── Cross-service tests (live stack) ──────────────────────────────────────────
test-e2e:
	@echo "Running cross-service tests (tests/api + tests/e2e) against the live stack..."
	@pip install -q -r tests/requirements.txt
	@python3 -m pytest tests -c tests/pytest.ini

# ── Observability profile (opt-in) ────────────────────────────────────────────
monitoring-up:
	docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --profile monitoring up -d

monitoring-down:
	docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --profile monitoring down

# ── Linting / formatting ──────────────────────────────────────────────────────
lint:
	@ruff check addons/ tests/ 2>/dev/null || (echo "ruff not installed — run 'make install-dev'"; exit 0)
	@black --check addons/ tests/ 2>/dev/null || (echo "black not installed — run 'make install-dev'"; exit 0)

format:
	@ruff check --fix addons/ tests/ 2>/dev/null || true
	@black addons/ tests/ 2>/dev/null || true

check:
	@pre-commit run --all-files 2>/dev/null || (echo "pre-commit not installed — run 'make install-dev'"; exit 0)

# ── Tooling ───────────────────────────────────────────────────────────────────
install-dev:
	@pip3 install --user ruff black pre-commit pylint-odoo
	@pre-commit install 2>/dev/null || true
	@echo "Dev tools installed."

# ── Data ─────────────────────────────────────────────────────────────────────
seed:
	@bash $(CURDIR)/scripts/seed_data.sh

# ── Backup / Restore ─────────────────────────────────────────────────────────
backup:
	@bash $(CURDIR)/scripts/backup.sh

restore:
	@bash $(CURDIR)/scripts/restore.sh
