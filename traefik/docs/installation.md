# Installation (Dev — Native)

> **Deploying with Docker?** This page covers the *native* dev setup (Postgres +
> Odoo installed directly on the host). For the containerised stack — the
> supported deployment path — follow `deployment.md`: `cp .env.example .env` →
> `docker compose up -d` → `./scripts/docker_init.sh`.

## Prerequisites
- Ubuntu 22.04 / 24.04
- Python 3.11+
- PostgreSQL 16 (with `diviner` superuser)
- Odoo 19 Community at `/home/diviner/Odoo/19/`

## Quick start

```bash
cd /home/diviner/Odoo/custom/traefik

# 1. Install dev tools
make install-dev

# 2. Create DB + install Odoo base (takes ~2 min)
make init

# 3. Start dev server
make up

# 4. Open browser
open http://localhost:8070
```

## Optional services

```bash
# Redis (needed for Celery, chat, rate-limiting)
sudo apt install redis

# pgvector (needed for RAG / AI embeddings)
sudo apt install postgresql-16-pgvector

# Ollama (local LLM / embeddings)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull nomic-embed-text
```

## Environment variables
Copy `.env.example` to `.env` and fill in keys as needed.
All keys are optional for the core platform to run.
