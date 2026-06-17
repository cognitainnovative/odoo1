# Deployment

Covers local dev, the opt-in monitoring stack, production via Docker Compose, and the
Kubernetes/Helm path. For first-run setup see `installation.md`; for env vars see
`api_keys.md` and `.env.example`.

## 1. Local development

```bash
cp .env.example .env            # boots fine with no keys filled in
docker compose up -d            # auto-merges docker-compose.override.yml (dev conveniences)
docker compose logs -f odoo
```

> **First run only — initialise the database.** Odoo does not auto-initialise an
> empty database, so the very first `docker compose up` will serve HTTP 500 until
> the addons are installed once. Run:
>
> ```bash
> ./scripts/docker_init.sh
> ```
>
> This installs all custom addons and restarts Odoo. It is safe to re-run — on an
> already-initialised database it does nothing. Verify with
> `curl -s localhost:8069/web/health` → `{"status": "pass"}`. (Equivalent manual
> command, if you prefer: `docker compose exec odoo odoo -d "$POSTGRES_DB" -i
> <comma-separated custom_* modules> --stop-after-init --no-http`, then
> `docker compose restart odoo`.)

The override file adds: live addon reload (`--dev=reload,qweb,xml`), `--reload` on both
FastAPI gateways with their source mounted, the Vite dev server (HMR) for the support app,
and direct host ports (Odoo 8069, ai 8000, hooks 8001, support 5173).

Access via Traefik: `platform.localhost`, `support.localhost`, `ai.localhost`,
`hooks.localhost`, `minio.localhost`, `traefik.localhost:8080`.

Host ports: container Postgres on **5433** (native Postgres keeps 5432), Redis 6379,
MinIO 9000/9001.

## 2. Observability (opt-in)

Not started by default. Bring up Prometheus + Grafana + Loki + Promtail + exporters:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  --profile monitoring up -d
```

Grafana → `grafana.localhost` (admin/admin first login), Prometheus →
`prometheus.localhost`. Configs live in `deploy/monitoring/`. Loki retains 7 days of logs;
Prometheus retains 15 days of metrics. The gateways are pre-registered as scrape targets —
add `prometheus-fastapi-instrumentator` to expose `/metrics` and they light up.

> The monitoring file joins the existing `platform_net` network as external, so start the
> main stack first.

## 3. Production (Docker Compose)

Run **without** the override file so dev conveniences don't leak into prod:

```bash
docker compose -f docker-compose.yml up -d
```

Production checklist:
- Disable the Traefik dashboard (`8080`) and switch Traefik to the TLS/Let's Encrypt
  resolver (see `deploy/traefik/traefik.yml`); serve everything over 443.
- Set strong values for `POSTGRES_PASSWORD`, `ODOO_ADMIN_PASSWORD`, `MINIO_ROOT_PASSWORD`,
  `AI_GATEWAY_SECRET`, and provider secrets. Never commit a real `.env`.
- Use real DNS hostnames in place of the `*.localhost` Traefik rules.
- Point object storage at S3/R2 in prod (the addons speak S3); MinIO is the dev default.
- Encrypt provider keys at rest (Fernet via `APP_SECRET_ENCRYPTION_KEY`); manage manifests
  with SOPS+age. `.env` is for dev only.

## 4. Kubernetes / Helm

A Helm chart is in `deploy/k8s/` (Chart.yaml, values.yaml, templates/). It provisions Odoo,
both gateways, Celery worker + beat, the support app, Postgres, Redis, MinIO, plus services,
ingresses, a configmap and a secret. Install:

```bash
helm install platform deploy/k8s -f deploy/k8s/values.yaml
```

Set image registries/tags, hostnames, resource requests, and storage classes in
`values.yaml` before installing. For hard multi-tenant isolation, deploy one release (and
one Postgres database) per tenant.

## 5. Operational scripts

`scripts/` provides: `init.sh` (create DB + install base), `backup.sh` and `restore.sh`
(DB + filestore), `run_tests.sh` (Odoo addon test runner with bootstrap connectivity
checks), `seed_data.sh` (demo tenant), and `run.sh`. Equivalent `make` targets exist
(`make up|down|logs|shell|test|lint|backup|restore|init|seed`).

### Backup / restore drill
Run a restore drill before go-live: `scripts/backup.sh` then `scripts/restore.sh` into a
scratch database, and verify the platform boots and core CRM works. Document the resulting
RPO/RTO in your runbook.

## 6. CI/CD

`.github/workflows/ci.yml` runs on push/PR: Python + XML syntax check, ruff + black lint,
then a test job that spins up `pgvector/pgvector:pg16`, checks out Odoo 19, installs deps,
enables pgvector, runs a bootstrap connectivity assertion, runs every addon's Odoo tests,
and runs the FastAPI gateway test suites. A milestone tag must sit on a green run.
