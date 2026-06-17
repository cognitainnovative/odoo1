"""Menu gating — hides ir.ui.menu entries when their module subscription is inactive."""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PlatformMenuGate(models.Model):
    """Maps a platform module_code to one or more top-level ir.ui.menu entries.

    When the subscription for module_code is inactive for the current company,
    the linked menus are excluded from the visible menu set.
    """

    _name = "platform.menu.gate"
    _description = "Platform Menu Gate"
    _order = "module_code, sequence"

    module_code = fields.Char("Module Code", required=True, index=True)
    menu_xmlid = fields.Char(
        "Menu XML ID",
        help="XML ID of the top-level menu to gate (e.g. 'crm.crm_menu_root'). "
        "Resolved at runtime so the module does not need to be a hard dependency.",
        index=True,
    )
    menu_id = fields.Many2one(
        "ir.ui.menu",
        string="Menu (direct)",
        ondelete="set null",
        help="Alternative to Menu XML ID — used in tests and manual admin configuration.",
    )
    sequence = fields.Integer(default=10)
    note = fields.Char("Note")


class IrUiMenuGating(models.Model):
    """Extend ir.ui.menu to enforce platform subscription gating."""

    _inherit = "ir.ui.menu"

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = set(super()._visible_menu_ids(debug=debug))

        # Only gate when subscriptions are actually configured (graceful default).
        Sub = self.env["platform.subscription"]
        if not Sub.search_count([("company_id", "=", self.env.company.id)]):
            return visible

        # Fetch all gate rules in one query.
        gates = self.env["platform.menu.gate"].sudo().search([])
        if not gates:
            return visible

        for gate in gates:
            if gate.menu_id:
                target_id = gate.menu_id.id
            elif gate.menu_xmlid:
                menu = self.env.ref(gate.menu_xmlid, raise_if_not_found=False)
                target_id = menu.id if menu else None
            else:
                continue
            if not target_id or target_id not in visible:
                continue
            if not Sub.is_module_active(gate.module_code):
                visible.discard(target_id)

        return visible
