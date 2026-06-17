"""Chat completion endpoints — sync and SSE streaming."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from providers.base import ChatMessage, ChatResponse
from pydantic import BaseModel
from redaction import maybe_redact_messages

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    provider: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    system: str = ""
    company_id: int = 0
    user_id: int = 0


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    from audit import log_ai_event
    from config import get_settings
    from providers.factory import get_provider

    settings = get_settings()
    provider = get_provider(req.provider, settings)
    messages = maybe_redact_messages(req.messages, provider, settings)

    t0 = time.monotonic()
    try:
        resp = await provider.chat(
            messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            system=req.system,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    latency = int((time.monotonic() - t0) * 1000)
    await log_ai_event(
        database_url=settings.database_url,
        event_type="chat",
        provider=resp.provider,
        model=resp.model,
        company_id=req.company_id,
        user_id=req.user_id,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
        latency_ms=latency,
        redacted=messages is not req.messages,
    )
    return resp


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events streaming endpoint.

    Returns `text/event-stream` with `data: <token>` lines.
    Sends `data: [DONE]` when the stream is complete.
    """
    from audit import log_ai_event
    from config import get_settings
    from providers.factory import get_provider

    settings = get_settings()
    provider = get_provider(req.provider, settings)
    messages = maybe_redact_messages(req.messages, provider, settings)

    async def _gen():
        try:
            async for token in await provider.chat_stream(
                messages,
                model=req.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                system=req.system,
            ):
                yield f"data: {token}\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {exc}\n\n"
        yield "data: [DONE]\n\n"
        await log_ai_event(
            database_url=settings.database_url,
            event_type="stream",
            provider=provider.name,
            model=req.model or "",
            company_id=req.company_id,
            user_id=req.user_id,
            redacted=messages is not req.messages,
        )

    return StreamingResponse(_gen(), media_type="text/event-stream")
