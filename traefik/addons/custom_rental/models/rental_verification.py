"""Customer verification record — minimal PII, configurable retention."""

from odoo import api, fields, models


class RentalVerification(models.Model):
    _name = "rental.verification"
    _description = "Rental Customer Verification"
    _order = "create_date desc"

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)

    # Verification type
    verification_type = fields.Selection(
        [
            ("id_document", "ID Document"),
            ("kvk", "KVK / Chamber of Commerce"),
            ("passport", "Passport"),
            ("driving_license", "Driving Licence"),
            ("other", "Other"),
        ],
        default="id_document",
        required=True,
    )

    # Status — store status + expiry, NOT the document itself
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("verified", "Verified"),
            ("expired", "Expired"),
            ("rejected", "Rejected"),
        ],
        default="pending",
    )
    verified_by_id = fields.Many2one("res.users", "Verified By", readonly=True)
    verified_date = fields.Datetime("Verified On", readonly=True)
    expiry_date = fields.Date("Document Expiry")
    reference = fields.Char(
        "Reference (last 4 chars only)",
        help="Store only the last 4 characters of the document number for traceability."
        " Do not store the full document number.",
    )
    risk_flag = fields.Selection(
        [("low", "Low Risk"), ("medium", "Medium Risk"), ("high", "High Risk")],
        default="low",
    )
    notes = fields.Text("Internal Notes")

    # Configurable retention
    retain_until = fields.Date(
        "Retain Until",
        help="After this date, this record should be purged per retention policy.",
    )

    def action_verify(self):
        self.write(
            {
                "status": "verified",
                "verified_by_id": self.env.user.id,
                "verified_date": fields.Datetime.now(),
            }
        )

    def action_reject(self):
        self.write({"status": "rejected"})

    def action_expire(self):
        self.write({"status": "expired"})

    @api.model
    def cron_expire_verifications(self):
        """Mark verifications with passed expiry dates as expired."""
        today = fields.Date.today()
        expired = self.search([("expiry_date", "<", today), ("status", "=", "verified")])
        expired.write({"status": "expired"})
