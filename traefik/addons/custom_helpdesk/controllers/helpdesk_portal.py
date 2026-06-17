"""Customer portal routes for helpdesk tickets."""

from odoo import http
from odoo.http import request


class HelpdeskPortal(http.Controller):

    @http.route("/my/tickets", auth="user", website=True)
    def my_tickets(self, **kwargs):
        partner = request.env.user.partner_id
        tickets = (
            request.env["helpdesk.ticket"]
            .sudo()
            .search([("partner_id", "=", partner.id)], order="create_date desc", limit=50)
        )
        return request.render(
            "custom_helpdesk.portal_my_tickets",
            {"tickets": tickets, "page_name": "tickets"},
        )

    @http.route("/helpdesk/ticket/<int:ticket_id>", auth="user", website=True)
    def ticket_detail(self, ticket_id, **kwargs):
        partner = request.env.user.partner_id
        ticket = (
            request.env["helpdesk.ticket"]
            .sudo()
            .search([("id", "=", ticket_id), ("partner_id", "=", partner.id)], limit=1)
        )
        if not ticket:
            return request.not_found()
        return request.render(
            "custom_helpdesk.portal_ticket_detail",
            {"ticket": ticket, "page_name": "ticket_detail"},
        )

    @http.route(
        "/helpdesk/ticket/<int:ticket_id>/reply",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def ticket_reply(self, ticket_id, message="", **kwargs):
        partner = request.env.user.partner_id
        ticket = (
            request.env["helpdesk.ticket"]
            .sudo()
            .search([("id", "=", ticket_id), ("partner_id", "=", partner.id)], limit=1)
        )
        if ticket and message:
            ticket.message_post(
                body=message[:4000],
                author_id=partner.id,
                subtype_id=request.env.ref("mail.mt_comment").id,
            )
        return request.redirect(f"/helpdesk/ticket/{ticket_id}")
