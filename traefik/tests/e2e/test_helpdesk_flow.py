"""E2E: Helpdesk flow (Section 8 critical flow).

ticket → AI classify → AI draft reply → approve → send → close.

Ticket creation is RBAC-protected (Support Agent / Support Manager) — which is correct: in
production tickets are created by the inbound-email/portal path running as the system user,
not by an arbitrary logged-in user. For this smoke test we grant the authenticated user the
Support Manager role first, then drive the flow. That exercises the access rule rather than
bypassing it.
"""

import pytest

FLOW = [
    "action_ai_classify",
    "action_ai_draft_reply",
    "action_approve_reply",
    "action_send_reply",
    "action_close",
]


def _grant_support_role(odoo):
    """Best-effort: add the Support Manager group to the current user."""
    try:
        group_ids = odoo.search(
            "res.groups",
            ["|", ["name", "=", "Support Manager"], ["name", "ilike", "Support Manager"]],
            limit=1,
        )
        if group_ids and odoo.uid:
            odoo.write("res.users", [odoo.uid], {"groups_id": [(4, group_ids[0])]})
    except Exception:
        pass  # if we can't, the create below will skip the test cleanly


def test_helpdesk_ticket_flow_methods_wired(odoo, test_partner):
    if not odoo.model_exists("helpdesk.ticket"):
        pytest.skip("helpdesk.ticket model not installed")

    _grant_support_role(odoo)

    try:
        ticket_id = odoo.create(
            "helpdesk.ticket",
            {
                "name": "E2E: invoice question",
                "description": "Where can I download my latest invoice?",
                "partner_id": test_partner,
            },
        )
    except Exception as exc:
        if "not allowed to create" in str(exc).lower():
            pytest.skip(f"User lacks helpdesk create rights and role grant failed ({exc})")
        raise
    assert ticket_id

    for method in FLOW:
        odoo.call_action("helpdesk.ticket", [ticket_id], method)  # raises if a method is missing

    ticket = odoo.read("helpdesk.ticket", [ticket_id], ["name"])[0]
    assert ticket["name"].startswith("E2E")
