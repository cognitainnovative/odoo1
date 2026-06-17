"""Bank statement parsers for CSV, MT940, and CAMT.053 formats.

Each parser returns a list of transaction dicts:
  {
    "date": date | str,
    "amount": float,
    "payment_ref": str,       # label / description
    "partner_name": str,
    "account_number": str,    # counterparty IBAN/account
    "ref": str,               # reference number
    "unique_import_id": str,  # de-duplication key
  }
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


def parse_csv(content: bytes | str, delimiter: str = ",") -> list[dict]:
    """Parse a CSV bank export.

    Tries to auto-detect common column layouts:
    - Date, Description, Amount  (3-column minimal)
    - Date, Description, Debit, Credit, Balance
    - Date, Ref, Amount, Counterparty, IBAN
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    transactions = []

    for i, row in enumerate(rows):
        row_lower = {k.strip().lower(): v.strip() for k, v in row.items() if k}

        txn_date = _find_field(
            row_lower, ["date", "datum", "valuedate", "boekingsdatum", "booking date"]
        )
        amount_raw = _find_field(row_lower, ["amount", "bedrag", "amount (eur)", "credit", "debit"])
        if not amount_raw:
            debit = _parse_amount(_find_field(row_lower, ["debit", "af", "debit amount"]) or "0")
            credit = _parse_amount(
                _find_field(row_lower, ["credit", "bij", "credit amount"]) or "0"
            )
            amount_raw = str(credit - debit) if (debit or credit) else "0"
        description = _find_field(
            row_lower, ["description", "omschrijving", "label", "memo", "reference", "ref"]
        )
        partner = _find_field(
            row_lower, ["counterparty", "name", "tegenpartij", "partner", "payee"]
        )
        iban = _find_field(row_lower, ["iban", "account", "counterparty iban", "rekening"])
        ref = _find_field(row_lower, ["reference", "referentie", "payment reference", "ref"])

        amount = _parse_amount(amount_raw or "0")
        if amount == 0:
            continue

        unique_id = hashlib.md5(f"{txn_date}{amount}{description}{i}".encode()).hexdigest()

        transactions.append(
            {
                "date": _parse_date(txn_date or "") or date.today(),
                "amount": amount,
                "payment_ref": description or "",
                "partner_name": partner or "",
                "account_number": iban or "",
                "ref": ref or "",
                "unique_import_id": unique_id,
            }
        )

    return transactions


def parse_mt940(content: bytes | str) -> list[dict]:
    """Parse an MT940 SWIFT bank statement.

    Handles the most common MT940 structure used by Dutch/EU banks.
    Fields: :20: (reference), :25: (account), :61: (transaction), :86: (info)
    """
    if isinstance(content, bytes):
        content = content.decode("latin-1", errors="replace")

    transactions = []
    account_number = ""

    # Extract account number from :25: field
    m = re.search(r":25:([^\r\n]+)", content)
    if m:
        account_number = m.group(1).strip()

    # Split into transaction blocks — each starts with :61:
    blocks = re.split(r"(?=:61:)", content)
    for block in blocks:
        m61 = re.match(
            r":61:(\d{6})(\d{4})?(C|D|RD|RC|CR|DR)([A-Z]?)(\d+[,.]?\d*)([A-Z]{4})?(.+)?",
            block.strip(),
            re.DOTALL,
        )
        if not m61:
            continue

        date_str = m61.group(1)
        cd = m61.group(3)  # C = credit, D = debit
        amount_str = m61.group(5).replace(",", ".")
        ref_raw = m61.group(7) or ""

        txn_date = _parse_date(date_str) or date.today()
        amount = _parse_amount(amount_str)
        if "D" in cd.upper():
            amount = -amount

        # :86: info field
        info_match = re.search(r":86:(.+?)(?=:6[01]:|$)", block, re.DOTALL)
        info = info_match.group(1).strip().replace("\n", " ") if info_match else ""

        # Extract IBAN and partner from /IBAN/ or /NAME/ tags common in Dutch MT940
        partner = re.search(r"/NAME/([^/\r\n]+)", info)
        iban = re.search(r"/IBAN/([A-Z]{2}\d{2}[A-Z0-9]+)", info)

        ref_clean = re.sub(r"[^A-Za-z0-9 \-]", " ", ref_raw.strip())[:40]
        unique_id = hashlib.md5(f"{txn_date}{amount}{ref_clean}".encode()).hexdigest()

        transactions.append(
            {
                "date": txn_date,
                "amount": amount,
                "payment_ref": info[:140] or ref_clean,
                "partner_name": partner.group(1).strip() if partner else "",
                "account_number": iban.group(1) if iban else account_number,
                "ref": ref_clean,
                "unique_import_id": unique_id,
            }
        )

    return transactions


def parse_camt053(content: bytes | str) -> list[dict]:
    """Parse a CAMT.053 (ISO 20022) XML bank statement.

    Standard used by most EU banks for electronic account statements.
    """
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    # Strip namespace
    ns_match = re.match(r"\{(.+?)\}", root.tag)
    ns = ns_match.group(1) if ns_match else ""
    pfx = f"{{{ns}}}" if ns else ""

    transactions = []

    for stmt in root.iter(f"{pfx}Stmt"):
        for ntry in stmt.iter(f"{pfx}Ntry"):
            amount_el = ntry.find(f"{pfx}Amt")
            cdt_dbt_el = ntry.find(f"{pfx}CdtDbtInd")
            val_date_el = ntry.find(f".//{pfx}Dt") or ntry.find(f".//{pfx}DtTm")
            info_el = ntry.find(f".//{pfx}AddtlNtryInf") or ntry.find(f".//{pfx}Rmtinf")

            if amount_el is None:
                continue

            amount = _parse_amount(amount_el.text or "0")
            if cdt_dbt_el is not None and cdt_dbt_el.text in ("DBIT", "D"):
                amount = -amount

            txn_date = (
                _parse_date(val_date_el.text or "") if val_date_el is not None else date.today()
            )
            payment_ref = info_el.text.strip() if info_el is not None and info_el.text else ""

            # Try to find counterparty
            partner_el = ntry.find(f".//{pfx}Nm")
            iban_el = ntry.find(f".//{pfx}IBAN")
            end_to_end = ntry.find(f".//{pfx}EndToEndId")

            ref = end_to_end.text.strip() if end_to_end is not None and end_to_end.text else ""
            unique_id = hashlib.md5(f"{txn_date}{amount}{ref}{payment_ref}".encode()).hexdigest()

            transactions.append(
                {
                    "date": txn_date,
                    "amount": amount,
                    "payment_ref": payment_ref or ref,
                    "partner_name": (
                        partner_el.text.strip()
                        if partner_el is not None and partner_el.text
                        else ""
                    ),
                    "account_number": (
                        iban_el.text.strip() if iban_el is not None and iban_el.text else ""
                    ),
                    "ref": ref,
                    "unique_import_id": unique_id,
                }
            )

    return transactions


# ── Helpers ────────────────────────────────────────────────────────────────────


def _find_field(row: dict, keys: list[str]) -> str | None:
    for k in keys:
        v = row.get(k)
        if v:
            return v
    return None


def _parse_amount(raw: str) -> float:
    if not raw:
        return 0.0
    # Remove currency symbols and whitespace.
    cleaned = re.sub(r"[€$£\s]", "", raw).strip()
    if not cleaned:
        return 0.0

    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        # Both separators present — the LAST one is the decimal separator.
        if cleaned.rfind(",") > cleaned.rfind("."):
            # European: 1.234,56 -> dot=thousands, comma=decimal
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: 1,234.56 -> comma=thousands, dot=decimal
            cleaned = cleaned.replace(",", "")
    elif has_comma:
        # Only comma: treat as decimal separator (European "99,95").
        # If it looks like a thousands group (e.g. "1,234" with exactly 3 digits
        # after and no decimals), it's ambiguous; default to decimal which is the
        # common SEPA/Dutch case.
        cleaned = cleaned.replace(",", ".")
    # else: only dot or plain integer — already valid.

    try:
        return float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return 0.0


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    raw = raw.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d", "%d%m%y", "%y%m%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
