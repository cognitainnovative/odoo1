"""AI-assisted reconciliation suggestion logic.

Called by the Odoo model — returns a ranked list of match candidates
with confidence scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date


@dataclass
class MatchCandidate:
    move_id: int
    move_name: str
    partner_name: str
    amount: float
    due_date: date | None
    confidence: float
    reasons: list[str] = field(default_factory=list)
    payment_type: str = "full"  # full | partial | overpayment | underpayment


def score_candidates(
    stmt_amount: float,
    stmt_ref: str,
    stmt_partner: str,
    stmt_date: date,
    candidates: list[dict],
    tolerance: float = 0.01,
) -> list[MatchCandidate]:
    """Score each candidate move against a bank statement line.

    Args:
        stmt_amount: Bank statement line amount (positive = credit to our account).
        stmt_ref: Payment reference on the bank line.
        stmt_partner: Counterparty name from bank line.
        stmt_date: Value date of the bank line.
        candidates: List of open invoice/payment dicts from the DB.
        tolerance: Allowed rounding difference for amount matching.

    Returns:
        Sorted list of MatchCandidates (highest confidence first).
    """
    results = []

    for cand in candidates:
        confidence = 0.0
        reasons: list[str] = []

        cand_amount = float(cand.get("amount_residual", 0))
        cand_name = str(cand.get("name", ""))
        cand_partner = str(cand.get("partner_name", ""))
        cand_ref = str(cand.get("ref", "") or "")
        cand_iban = str(cand.get("partner_iban", "") or "")
        cand_due = cand.get("invoice_date_due")

        # ── Amount match ───────────────────────────────────────────────────────
        ptype = detect_payment_type(stmt_amount, cand_amount, tolerance)
        if ptype == "full":
            confidence += 0.40
            reasons.append("Exact amount match")
        elif ptype == "overpayment":
            confidence += 0.25
            reasons.append("Overpayment — amount exceeds invoice total")
        elif ptype == "partial":
            # Partial payment still scores if reference or partner matches
            confidence += 0.15
            reasons.append(f"Partial payment — {abs(stmt_amount):.2f} of {abs(cand_amount):.2f}")
        elif abs(abs(stmt_amount) - abs(cand_amount)) / max(abs(cand_amount), 0.01) < 0.02:
            confidence += 0.25
            reasons.append("Near-exact amount (within 2%)")

        # ── Reference match ────────────────────────────────────────────────────
        if stmt_ref and cand_name:
            if cand_name.lower() in stmt_ref.lower() or stmt_ref.lower() in cand_name.lower():
                confidence += 0.30
                reasons.append(f"Invoice number '{cand_name}' in payment reference")
            elif cand_ref and (
                cand_ref.lower() in stmt_ref.lower() or stmt_ref.lower() in cand_ref.lower()
            ):
                confidence += 0.20
                reasons.append("Reference field match")

        # ── Partner match ──────────────────────────────────────────────────────
        if stmt_partner and cand_partner:
            if _name_similarity(stmt_partner, cand_partner) > 0.8:
                confidence += 0.20
                reasons.append("Partner name match")
            elif _name_similarity(stmt_partner, cand_partner) > 0.5:
                confidence += 0.10
                reasons.append("Partial partner name match")

        # ── IBAN match ─────────────────────────────────────────────────────────
        if cand_iban and stmt_partner:
            if cand_iban.replace(" ", "").upper() in stmt_ref.upper():
                confidence += 0.15
                reasons.append("IBAN matched in reference")

        # ── Date proximity ─────────────────────────────────────────────────────
        if cand_due and isinstance(cand_due, date):
            days_diff = abs((stmt_date - cand_due).days)
            if days_diff <= 3:
                confidence += 0.05
                reasons.append("Payment within 3 days of due date")
            elif days_diff <= 14:
                confidence += 0.02
                reasons.append("Payment within 2 weeks of due date")

        if confidence > 0.05:
            results.append(
                MatchCandidate(
                    move_id=cand.get("id", 0),
                    move_name=cand_name,
                    partner_name=cand_partner,
                    amount=cand_amount,
                    due_date=cand_due,
                    confidence=min(confidence, 1.0),
                    reasons=reasons,
                    payment_type=detect_payment_type(stmt_amount, cand_amount, tolerance),
                )
            )

    return sorted(results, key=lambda c: c.confidence, reverse=True)


def build_ai_reconciliation_prompt(
    stmt_amount: float,
    stmt_ref: str,
    stmt_partner: str,
    stmt_date: date,
    top_candidates: list[MatchCandidate],
) -> str:
    """Build a prompt for the AI to refine reconciliation suggestions."""
    candidates_text = "\n".join(
        f"  [{i+1}] Invoice {c.move_name} — €{c.amount:.2f} from {c.partner_name}"
        f" (confidence: {c.confidence:.0%}, reasons: {', '.join(c.reasons)})"
        for i, c in enumerate(top_candidates[:5])
    )
    return (
        f"A bank transaction needs reconciliation:\n"
        f"  Amount: €{stmt_amount:.2f}\n"
        f"  Reference: {stmt_ref}\n"
        f"  Counterparty: {stmt_partner}\n"
        f"  Date: {stmt_date}\n\n"
        f"Top candidates from the ledger:\n{candidates_text}\n\n"
        f"Which invoice number (if any) best matches this payment? "
        f"Reply with just the invoice number (e.g. 'INV/2025/00123') or 'UNKNOWN'."
    )


def detect_payment_type(
    stmt_amount: float,
    cand_amount: float,
    tolerance: float = 0.01,
) -> str:
    """Classify a bank payment relative to the open invoice amount.

    Returns one of: 'full', 'partial', 'overpayment', 'underpayment'.
    """
    stmt_abs = abs(stmt_amount)
    cand_abs = abs(cand_amount)
    if cand_abs < tolerance:
        return "full"
    diff = stmt_abs - cand_abs
    if abs(diff) <= tolerance:
        return "full"
    if diff > tolerance:
        return "overpayment"
    # stmt_abs < cand_abs — either partial or underpayment
    ratio = stmt_abs / cand_abs
    if ratio >= 0.10:
        return "partial"
    return "underpayment"


def find_split_match(
    stmt_amounts: list[float],
    candidates: list[dict],
    tolerance: float = 0.01,
) -> list[dict]:
    """Detect invoices whose residual equals the sum of multiple bank line amounts.

    Used when one invoice is paid across several transactions (split payment).
    Returns a list of dicts with move_id, move_name, total, matched_amounts, confidence.
    """
    if not stmt_amounts or not candidates:
        return []

    stmt_total = sum(abs(a) for a in stmt_amounts)
    results = []
    for cand in candidates:
        cand_amount = abs(float(cand.get("amount_residual", 0)))
        if cand_amount < tolerance:
            continue
        if abs(stmt_total - cand_amount) <= tolerance:
            results.append(
                {
                    "move_id": cand.get("id"),
                    "move_name": cand.get("name", ""),
                    "partner_name": cand.get("partner_name", ""),
                    "total": cand_amount,
                    "matched_amounts": list(stmt_amounts),
                    "confidence": 0.85,
                    "payment_type": "split",
                }
            )
    return results


def _name_similarity(a: str, b: str) -> float:
    """Simple token overlap similarity (0–1)."""
    a_tokens = set(re.split(r"[\s\-,./]+", a.lower()))
    b_tokens = set(re.split(r"[\s\-,./]+", b.lower()))
    a_tokens -= {"", "bv", "nv", "de", "the", "and", "en"}
    b_tokens -= {"", "bv", "nv", "de", "the", "and", "en"}
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    return len(intersection) / max(len(a_tokens), len(b_tokens))
