"""Bank statement import endpoint.

POST /webhooks/bank/import  — accepts CAMT.053 or MT940, forwards parsed
                              transactions to Odoo's bank import pipeline.

Protected by a shared secret header (X-Bank-Import-Secret).
"""
import logging

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/bank", tags=["bank"])


@router.post("/import")
async def bank_import(
    file: UploadFile = File(...),
    journal_id: int = Form(0),
    x_bank_import_secret: str = Header(""),
):
    from config import get_settings
    from odoo_client import get_odoo_client

    settings = get_settings()
    if settings.bank_import_secret and x_bank_import_secret != settings.bank_import_secret:
        raise HTTPException(status_code=401, detail="Invalid secret")

    content = await file.read()
    filename = file.filename or ""
    mime = file.content_type or ""

    try:
        if filename.endswith(".xml") or "xml" in mime:
            from normalizers.bank import normalise_camt053
            transactions = normalise_camt053(content)
            fmt = "camt053"
        else:
            # Assume MT940
            from normalizers.bank import normalise_mt940
            transactions = normalise_mt940(content.decode("utf-8", errors="replace"))
            fmt = "mt940"
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    client = get_odoo_client()
    try:
        result = await client.call(
            "account.bank.statement",
            "import_transactions_from_gateway",
            [journal_id, transactions, fmt],
        )
    except Exception as exc:
        _logger.error("Odoo bank import failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Odoo import failed: {exc}") from exc

    return {"ok": True, "format": fmt, "transactions": len(transactions), "odoo_result": result}
