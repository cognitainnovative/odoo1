"""Chat widget HTTP controller."""

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ChatController(http.Controller):

    @http.route("/chatbot/config", type="jsonrpc", auth="public", methods=["POST"])
    def get_config(self, **kwargs):
        """Return chatbot config for the current company."""
        config = (
            request.env["chat.config"]
            .sudo()
            .search([("company_id", "=", request.env.company.id)], limit=1)
        )
        if not config or not config.is_enabled:
            return {"enabled": False}
        return {
            "enabled": True,
            "greeting": config.greeting_message,
            "offline_message": config.offline_message,
            "collect_email": config.collect_email,
            "collect_company": config.collect_company,
            "primary_color": config.primary_color,
        }

    @http.route("/chatbot/start", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def start_session(self, visitor_token=None, **kwargs):
        """Start or resume a chat session."""
        visitor = request.env["chat.visitor"].sudo().get_or_create_visitor(visitor_token)
        # Check if there's an open session for this visitor
        session = (
            request.env["chat.session"]
            .sudo()
            .search(
                [
                    ("visitor_id", "=", visitor.id),
                    ("state", "in", ("open", "escalated", "assigned")),
                ],
                limit=1,
            )
        )
        if not session:
            session = (
                request.env["chat.session"]
                .sudo()
                .create(
                    {
                        "visitor_id": visitor.id,
                        "language_code": kwargs.get("language", "en"),
                    }
                )
            )
        return {
            "visitor_token": visitor.token,
            "session_id": session.id,
            "state": session.state,
        }

    @http.route("/chatbot/message", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def send_message(self, session_id, message, visitor_name="", visitor_email="", **kwargs):
        """Send a message and get AI response."""
        if not session_id or not message:
            return {"error": "Missing session_id or message"}

        try:
            result = (
                request.env["chat.session"]
                .sudo()
                .process_message(
                    session_id=int(session_id),
                    user_message=str(message)[:2000],
                    visitor_name=str(visitor_name)[:100],
                    visitor_email=str(visitor_email)[:200],
                )
            )
            return result
        except Exception as exc:
            _logger.error("Chat message processing error: %s", exc)
            return {
                "reply": "Sorry, something went wrong. Please try again.",
                "escalated": False,
                "citations": [],
                "session_id": session_id,
            }

    @http.route("/chatbot/consent", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def record_consent(self, visitor_token=None, **kwargs):
        """Record visitor tracking consent."""
        if not visitor_token:
            return {"ok": False}
        visitor = (
            request.env["chat.visitor"].sudo().search([("token", "=", visitor_token)], limit=1)
        )
        if visitor:
            visitor.record_consent()
        return {"ok": True}

    @http.route(
        "/chatbot/consent/revoke", type="jsonrpc", auth="public", methods=["POST"], csrf=False
    )
    def revoke_consent(self, visitor_token=None, **kwargs):
        """Withdraw visitor tracking consent (GDPR Art. 7(3) right to withdraw)."""
        if not visitor_token:
            return {"ok": False, "error": "visitor_token required"}
        visitor = (
            request.env["chat.visitor"].sudo().search([("token", "=", visitor_token)], limit=1)
        )
        if visitor:
            visitor.revoke_consent()
        return {"ok": True}

    @http.route("/chatbot/email", type="jsonrpc", auth="public", methods=["POST"], csrf=False)
    def capture_email(self, session_id, email, name="", company="", **kwargs):
        """Capture visitor email and create a lead."""
        session = request.env["chat.session"].sudo().search([("id", "=", session_id)], limit=1)
        if not session:
            return {"ok": False}
        session.write({"visitor_email": email, "visitor_name": name, "visitor_company": company})
        if session.visitor_id:
            session.visitor_id.write({"email": email, "company_name": company})
        return {"ok": True}

    # ── Agent-side endpoints (auth="user" — internal staff only) ──────────────

    @http.route("/chatbot/suggest_reply", type="jsonrpc", auth="user", methods=["POST"], csrf=False)
    def suggest_reply(self, session_id, **kwargs):
        """Return an AI-suggested reply for the agent based on session transcript."""
        session = request.env["chat.session"].browse(int(session_id))
        if not session.exists():
            return {"suggestion": ""}
        return session.action_suggest_reply()

    @http.route(
        "/chatbot/canned_replies", type="jsonrpc", auth="user", methods=["POST"], csrf=False
    )
    def canned_replies(self, query="", **kwargs):
        """Return canned replies matching the query shortcut or label."""
        domain = [("company_id", "=", request.env.company.id), ("active", "=", True)]
        if query:
            domain += ["|", ("shortcut", "ilike", query), ("name", "ilike", query)]
        replies = request.env["chat.canned.reply"].search(domain, limit=20)
        return [
            {"id": r.id, "shortcut": r.shortcut, "name": r.name, "message": r.message}
            for r in replies
        ]

    @http.route(
        "/chatbot/product_suggestions", type="jsonrpc", auth="public", methods=["POST"], csrf=False
    )
    def product_suggestions(self, query="", **kwargs):
        """Return published products matching a query for use as chat suggestions."""
        if not query or len(query.strip()) < 2:
            return []
        products = (
            request.env["product.template"]
            .sudo()
            .search(
                [("name", "ilike", query[:80]), ("sale_ok", "=", True)],
                limit=5,
            )
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "price": p.list_price,
                "description": (p.description_sale or "")[:120],
            }
            for p in products
        ]

    @http.route("/chatbot/transfer", type="jsonrpc", auth="user", methods=["POST"], csrf=False)
    def transfer_session(self, session_id, agent_id, **kwargs):
        """Transfer a chat session to another agent."""
        session = request.env["chat.session"].browse(int(session_id))
        if not session.exists():
            return {"ok": False, "error": "Session not found"}
        try:
            session.action_transfer_to_agent(int(agent_id))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
