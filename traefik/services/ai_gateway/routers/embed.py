from fastapi import APIRouter, HTTPException
from providers.base import EmbedResponse
from pydantic import BaseModel

router = APIRouter(prefix="/embed", tags=["embed"])


class EmbedRequest(BaseModel):
    text: str
    model: str = ""
    company_id: int = 0


@router.post("", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    from config import get_settings
    from providers.factory import get_embed_provider

    settings = get_settings()
    provider = get_embed_provider(settings)
    try:
        return await provider.embed(req.text, model=req.model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
