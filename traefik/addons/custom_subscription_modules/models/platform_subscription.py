import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PlatformSubscription(models.Model):
    _name = "platform.subscription"
    _description = "Platform Subscription"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, package_id"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
        index=True,
    )
    package_id = fields.Many2one(
        "platform.package", required=True, ondelete="restrict", string="Package"
    )
    state = fields.Selection(
        [
            ("trial", "Trial"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        default="trial",
        required=True,
        tracking=True,
        index=True,
    )
    trial_days = fields.Integer("Trial Days", default=14)
    trial_start = fields.Datetime("Trial Start", default=fields.Datetime.now, tracking=True)
    trial_end = fields.Datetime("Trial End", compute="_compute_trial_end", store=True)

    start_date = fields.Date("Activation Date", tracking=True)
    end_date = fields.Date("Expiry Date", tracking=True)

    license_key = fields.Char(
        "License Key",
        copy=False,
        readonly=True,
        help="Auto-generated opaque key. Used to verify entitlement via API.",
    )
    notes = fields.Text()
    is_active = fields.Boolean("Currently Active", compute="_compute_is_active", store=True)
    days_remaining = fields.Integer("Days Remaining", compute="_compute_days_remaining")

    display_name = fields.Char(compute="_compute_display_name", store=True)

    _company_package_uniq = models.Constraint(
        "UNIQUE(company_id, package_id)",
        "A company can only have one subscription per package.",
    )

    @api.depends("company_id", "package_id")
    def _compute_display_name(self):
        for rec in self:
            company = rec.company_id.name or ""
            package = rec.package_id.name or ""
            rec.display_name = (
                f"{company} — {package}" if company or package else "New Subscription"
            )

    @api.depends("trial_start", "trial_days")
    def _compute_trial_end(self):
        for rec in self:
            if rec.trial_start and rec.trial_days:
                rec.trial_end = rec.trial_start + timedelta(days=rec.trial_days)
            else:
                rec.trial_end = False

    @api.depends("state", "end_date", "trial_end")
    def _compute_is_active(self):
        now = fields.Datetime.now()
        today = fields.Date.today()
        for rec in self:
            if rec.state == "active":
                rec.is_active = not rec.end_date or rec.end_date >= today
            elif rec.state == "trial":
                rec.is_active = not rec.trial_end or rec.trial_end >= now
            else:
                rec.is_active = False

    @api.depends("state", "end_date", "trial_end")
    def _compute_days_remaining(self):
        today = fields.Date.today()
        for rec in self:
            if rec.state == "active" and rec.end_date:
                rec.days_remaining = max(0, (rec.end_date - today).days)
            elif rec.state == "trial" and rec.trial_end:
                trial_date = rec.trial_end.date()
                rec.days_remaining = max(0, (trial_date - today).days)
            else:
                rec.days_remaining = 0

    # ── State transitions ──────────────────────────────────────────────────────

    def _generate_license_key(self):
        return "PLT-" + secrets.token_urlsafe(24)

    def action_activate(self):
        for rec in self:
            if rec.state in ("cancelled",):
                raise UserError("Cannot activate a cancelled subscription. Use Reactivate.")
            vals = {"state": "active", "start_date": fields.Date.today()}
            if not rec.license_key:
                vals["license_key"] = self._generate_license_key()
            rec.write(vals)
        return True

    def action_expire(self):
        self.write({"state": "expired"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_reactivate(self):
        self.write({"state": "active", "start_date": fields.Date.today()})

    def action_reset_trial(self):
        self.write(
            {
                "state": "trial",
                "trial_start": fields.Datetime.now(),
                "start_date": False,
                "end_date": False,
            }
        )

    # ── Data retention on disable ──────────────────────────────────────────────

    def _invalidate_menu_cache(self):
        """Invalidate the cached visible-menu set so gating takes effect
        immediately. Odoo 19 deprecated ir.ui.menu.clear_caches() in favour of
        registry.clear_cache(); call whichever this build exposes."""
        try:
            self.env.registry.clear_cache()
        except AttributeError:
            self.env["ir.ui.menu"].clear_caches()

    def write(self, vals):
        previously_active = {r.id: r.is_active for r in self}
        result = super().write(vals)
        for rec in self:
            was_active = previously_active.get(rec.id, False)
            if was_active and not rec.is_active:
                self._on_module_deactivated(rec)
        # Menu visibility is gated on is_module_active(), and the web client
        # caches the visible-menu set. Any change to state/dates that could flip
        # is_active must invalidate that cache so gated menus appear/disappear on
        # the next menu load instead of requiring a manual hard refresh.
        if {"state", "end_date", "trial_end", "trial_start", "trial_days"} & set(vals):
            self._invalidate_menu_cache()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # A newly-created subscription flips the company from fail-open (no subs)
        # to gated, which changes which menus are visible — invalidate the cache.
        records._invalidate_menu_cache()
        return records

    def unlink(self):
        result = super().unlink()
        self._invalidate_menu_cache()
        return result

    def _on_module_deactivated(self, subscription):
        """Called when a subscription transitions from active/trial to inactive.

        Data is NEVER deleted — records are archived (active=False) so they
        survive a subscription lapse and are restored on reactivation.
        Extend this method in other addons to archive module-specific records.
        """
        module_code = subscription.package_id.code or ""
        _logger.info(
            "Platform: subscription %s for company %s deactivated (module_code=%s). "
            "Data retained via archival.",
            subscription.display_name,
            subscription.company_id.name,
            module_code,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    @api.model
    def is_module_active(self, module_code, company_id=None):
        """Return True if the given module code is accessible for the company.

        If no subscriptions are configured for the company at all, access is
        granted (graceful default so a fresh install works out of the box).
        """
        cid = company_id or self.env.company.id
        subs = self.search([("company_id", "=", cid)])

        if not subs:
            return True

        active_subs = subs.filtered("is_active")
        for sub in active_subs:
            codes = [c.strip() for c in (sub.package_id.module_codes or "").split(",") if c.strip()]
            if module_code in codes or sub.package_id.code == "full_suite":
                return True
        return False
