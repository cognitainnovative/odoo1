from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    provider: str


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health():
    from config import get_settings
    from providers.factory import get_provider

    settings = get_settings()
    provider = get_provider(settings=settings)
    return HealthResponse(status="ok", provider=provider.name)
