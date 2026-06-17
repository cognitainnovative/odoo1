"""Parse CAMT.053 and MT940 bank statement files into normalised transaction dicts.

These are the formats most Dutch and EU banks export; they feed into
Odoo's bank-import matching pipeline (custom_accounting_basic).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


_CAMT_NS = {"camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"}
# Fallback for older namespace versions
_CAMT_NS_ALT = {"camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"}


def normalise_camt053(xml_bytes: bytes) -> list[dict]:
    """Parse a CAMT.053 XML file and return a list of transaction dicts."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid CAMT.053 XML: {exc}") from exc

    # Detect namespace
    tag = root.tag
    ns_uri = tag[1:tag.index("}")] if tag.startswith("{") else ""
    ns = {"camt": ns_uri} if ns_uri else {}
    prefix = "camt:" if ns else ""

    transactions = []
    for stmt in root.iter(f"{{{ns_uri}}}Stmt" if ns_uri else "Stmt"):
        iban = _text(stmt, f"{prefix}Acct/{prefix}Id/{prefix}IBAN", ns) or ""
        currency = _text(stmt, f"{prefix}Acct/{prefix}Ccy", ns) or "EUR"

        for entry in stmt.iter(f"{{{ns_uri}}}Ntry" if ns_uri else "Ntry"):
            amount_str = _text(entry, f"{prefix}Amt", ns) or "0"
            cdt_dbt = _text(entry, f"{prefix}CdtDbtInd", ns) or "CRDT"
            amount = float(amount_str)
            if cdt_dbt == "DBIT":
                amount = -amount

            booking_date = _text(entry, f"{prefix}BookgDt/{prefix}Dt", ns) or ""
            value_date = _text(entry, f"{prefix}ValDt/{prefix}Dt", ns) or ""

            # Reference / end-to-end ID
            ref = (
                _text(entry, f"{prefix}NtryDtls/{prefix}TxDtls/{prefix}Refs/{prefix}EndToEndId", ns)
                or _text(entry, f"{prefix}AcctSvcrRef", ns)
                or ""
            )

            # Counterparty
            dbtr = entry.find(f".//{{{ns_uri}}}Dbtr" if ns_uri else ".//Dbtr")
            cdtr = entry.find(f".//{{{ns_uri}}}Cdtr" if ns_uri else ".//Cdtr")
            counterparty = ""
            counterparty_iban = ""
            if cdt_dbt == "CRDT" and dbtr is not None:
                counterparty = _text(dbtr, f"{prefix}Nm", ns) or ""
                counterparty_iban = _text(
                    entry, f".//{prefix}DbtrAcct/{prefix}Id/{prefix}IBAN", ns
                ) or ""
            elif cdt_dbt == "DBIT" and cdtr is not None:
                counterparty = _text(cdtr, f"{prefix}Nm", ns) or ""
                counterparty_iban = _text(
                    entry, f".//{prefix}CdtrAcct/{prefix}Id/{prefix}IBAN", ns
                ) or ""

            # Remittance info
            remittance = _text(
                entry,
                f"{prefix}NtryDtls/{prefix}TxDtls/{prefix}RmtInf/{prefix}Ustrd",
                ns,
            ) or _text(entry, f"{prefix}AddtlNtryInf", ns) or ""

            transactions.append({
                "account_iban": iban,
                "currency": currency,
                "amount": amount,
                "credit_debit": cdt_dbt,
                "booking_date": booking_date,
                "value_date": value_date,
                "reference": ref,
                "counterparty_name": counterparty,
                "counterparty_iban": counterparty_iban,
                "remittance_info": remittance,
            })

    return transactions


def normalise_mt940(text: str) -> list[dict]:
    """Parse a MT940 bank statement text and return normalised transaction dicts.

    Supports basic :60F:/:61:/:86: tag structure common in Dutch banks.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    transactions = []
    account_iban = ""
    currency = "EUR"
    current: dict | None = None

    for line in lines:
        if line.startswith(":25:"):
            account_iban = line[4:].strip()
        elif line.startswith(":60F:") or line.startswith(":60M:"):
            currency = line[5:8]
        elif line.startswith(":61:"):
            if current:
                transactions.append(current)
            # Format: YYMMDD[MMDD]C/DAmount[N]Reference
            body = line[4:]
            date_str = body[:6]
            booking_date = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:6]}"
            body = body[6:]
            if len(body) > 4 and body[:4].isdigit():
                body = body[4:]  # optional MMDD
            cdt_dbt = "CRDT" if body[0] in ("C", "R") else "DBIT"
            body = body[1:]
            if body and body[0] in ("D", "C"):
                body = body[1:]  # currency reversal indicator
            amt_match = re.match(r"([\d,]+)", body)
            amount_str = amt_match.group(1).replace(",", ".") if amt_match else "0"
            amount = float(amount_str)
            if cdt_dbt == "DBIT":
                amount = -amount
            current = {
                "account_iban": account_iban,
                "currency": currency,
                "amount": amount,
                "credit_debit": cdt_dbt,
                "booking_date": booking_date,
                "value_date": booking_date,
                "reference": "",
                "counterparty_name": "",
                "counterparty_iban": "",
                "remittance_info": "",
            }
        elif line.startswith(":86:") and current is not None:
            current["remittance_info"] = line[4:].strip()

    if current:
        transactions.append(current)

    return transactions


def _text(element, path: str, ns: dict) -> str | None:
    node = element.find(path, ns)
    return node.text.strip() if node is not None and node.text else None
