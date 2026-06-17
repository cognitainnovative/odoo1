"""AI Gateway — FastAPI service entry point.

Exposes:
  GET  /health
  POST /chat                — sync completion
  POST /chat/stream         — SSE streaming
  POST /embed               — embeddings
  POST /rag/ingest          — document ingest (chunk + embed + pgvector)
  POST /rag/query           — RAG semantic search + cited answer
  GET  /audit/logs          — immutable AI audit log
"""

import logging

from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from routers.audit_router import router as audit_router
from routers.chat import router as chat_router
from routers.embed import router as embed_router
from routers.health import router as health_router
from routers.rag import router as rag_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Gateway",
    description="Provider abstraction, RAG pipeline, streaming chat, redaction, audit.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(embed_router)
app.include_router(rag_router)
app.include_router(audit_router)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Optional Bearer token auth. Skipped when API_SECRET is empty (dev)."""
    from config import get_settings

    settings = get_settings()
    if settings.api_secret and request.url.path not in ("/health", "/docs", "/openapi.json"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != settings.api_secret:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.on_event("startup")
async def startup():
    from audit import ensure_audit_schema
    from config import get_settings
    from rag.db import ensure_schema

    settings = get_settings()
    try:
        ensure_schema(settings.database_url)
        ensure_audit_schema(settings.database_url)
        logger.info("AI Gateway started — provider=%s", settings.default_provider)
    except Exception as exc:
        logger.warning("DB schema init skipped (DB may not be ready yet): %s", exc)


if __name__ == "__main__":
    import uvicorn
    from config import get_settings

    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, log_level=s.log_level, reload=False)
