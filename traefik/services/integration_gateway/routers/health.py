from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    odoo_url: str


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health():
    from config import get_settings
    s = get_settings()
    return HealthResponse(status="ok", odoo_url=s.odoo_url)
