"""Extend hr.employee with certifications, equipment, onboarding checklists, portal."""

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # ── Emergency contact ─────────────────────────────────────────────────────
    emergency_contact_name = fields.Char("Emergency Contact Name")
    emergency_contact_phone = fields.Char("Emergency Contact Phone")
    emergency_contact_relation = fields.Char("Relation")

    # ── Contract & working conditions ─────────────────────────────────────────
    weekly_hours = fields.Float("Weekly Hours", default=40.0)
    contract_type = fields.Selection(
        [
            ("permanent", "Permanent"),
            ("temporary", "Temporary / Fixed-term"),
            ("freelance", "Freelance"),
            ("intern", "Internship"),
            ("on_call", "On-call"),
        ],
        default="permanent",
    )
    probation_end_date = fields.Date("Probation End Date")
    contract_renewal_date = fields.Date("Contract Renewal Date")

    # ── Documents & certifications ────────────────────────────────────────────
    platform_certification_ids = fields.One2many(
        "hr.employee.certification", "employee_id", "Certifications"
    )
    certification_count = fields.Integer(compute="_compute_cert_count")

    # ── Equipment ─────────────────────────────────────────────────────────────
    equipment_ids = fields.One2many("hr.employee.equipment", "employee_id", "Assigned Equipment")

    # ── Onboarding / offboarding ──────────────────────────────────────────────
    onboarding_completed = fields.Boolean("Onboarding Completed", default=False)
    offboarding_started = fields.Boolean("Offboarding Started", default=False)
    onboarding_checklist_ids = fields.One2many(
        "hr.onboarding.checklist.item", "employee_id", "Onboarding Checklist"
    )

    # ── Payslips ──────────────────────────────────────────────────────────────
    payslip_ids = fields.One2many("hr.employee.payslip", "employee_id", "Payslips")

    # ── Notes & roles ─────────────────────────────────────────────────────────
    hr_notes = fields.Text("HR Internal Notes")
    portal_access = fields.Boolean(
        "Portal Access Enabled",
        compute="_compute_portal_access",
        store=True,
    )

    # ── Performance review ────────────────────────────────────────────────────
    next_performance_review = fields.Date("Next Performance Review")
    last_performance_review = fields.Date("Last Performance Review")

    @api.depends("platform_certification_ids")
    def _compute_cert_count(self):
        for emp in self:
            emp.certification_count = len(emp.platform_certification_ids)

    @api.depends("user_id")
    def _compute_portal_access(self):
        for emp in self:
            emp.portal_access = bool(emp.user_id)

    def action_initiate_onboarding(self):
        """Create default onboarding checklist items."""
        self.ensure_one()
        default_tasks = [
            "Welcome meeting with manager",
            "IT equipment setup",
            "System access and credentials",
            "HR documentation signed",
            "Company policy review",
            "Introduction to team",
            "First-month check-in scheduled",
        ]
        existing = set(self.onboarding_checklist_ids.mapped("name"))
        for task in default_tasks:
            if task not in existing:
                self.env["hr.onboarding.checklist.item"].create(
                    {"employee_id": self.id, "name": task}
                )

    def action_initiate_offboarding(self):
        """Mark offboarding started and create offboarding tasks."""
        self.offboarding_started = True
        offboarding_tasks = [
            "Return IT equipment",
            "Access revocation — IT systems",
            "Final payroll processing",
            "Exit interview",
            "Knowledge transfer completed",
            "Badge / key card returned",
        ]
        existing_off = {
            c.name for c in self.onboarding_checklist_ids if c.checklist_type == "offboarding"
        }
        for task in offboarding_tasks:
            if task not in existing_off:
                self.env["hr.onboarding.checklist.item"].create(
                    {
                        "employee_id": self.id,
                        "name": task,
                        "checklist_type": "offboarding",
                    }
                )

    @api.model
    def cron_contract_reminders(self):
        """Send reminders for probation ends, contract renewals, document expiries."""
        from datetime import date, timedelta

        today = date.today()
        warning_days = 30

        # Probation ending soon
        prob_ending = self.search(
            [
                ("probation_end_date", ">=", today),
                ("probation_end_date", "<=", today + timedelta(days=warning_days)),
            ]
        )
        for emp in prob_ending:
            emp.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=f"Probation ending: {emp.name}",
                note=f"Probation period ends on {emp.probation_end_date}. "
                "Please arrange a performance review.",
                user_id=emp.parent_id.user_id.id if emp.parent_id else False,
            )

        # Contract renewal soon
        renewal_due = self.search(
            [
                ("contract_renewal_date", ">=", today),
                ("contract_renewal_date", "<=", today + timedelta(days=warning_days)),
            ]
        )
        for emp in renewal_due:
            emp.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=f"Contract renewal: {emp.name}",
                note=f"Contract renewal date: {emp.contract_renewal_date}.",
                user_id=emp.parent_id.user_id.id if emp.parent_id else False,
            )

        # Certification expiry soon
        expiring_certs = self.env["hr.employee.certification"].search(
            [
                ("expiry_date", ">=", today),
                ("expiry_date", "<=", today + timedelta(days=warning_days)),
                ("status", "=", "active"),
            ]
        )
        for cert in expiring_certs:
            cert.employee_id.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=f"Certification expiring: {cert.name} ({cert.employee_id.name})",
                note=(
                    f"Certification '{cert.name}' for {cert.employee_id.name} "
                    f"expires on {cert.expiry_date}. Please arrange renewal."
                ),
                user_id=(
                    cert.employee_id.parent_id.user_id.id if cert.employee_id.parent_id else False
                ),
            )

        # Performance review due soon
        review_due = self.search(
            [
                ("next_performance_review", ">=", today),
                ("next_performance_review", "<=", today + timedelta(days=warning_days)),
            ]
        )
        for emp in review_due:
            emp.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=f"Performance review due: {emp.name}",
                note=(
                    f"Performance review for {emp.name} is scheduled on "
                    f"{emp.next_performance_review}. Please arrange the review session."
                ),
                user_id=emp.parent_id.user_id.id if emp.parent_id else False,
            )


class HrEmployeePayslip(models.Model):
    """Payslip document reference — stored payslip PDFs scoped per employee."""

    _name = "hr.employee.payslip"
    _description = "Employee Payslip"
    _order = "period_start desc"
    _rec_name = "name"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", related="employee_id.company_id", store=True)
    name = fields.Char("Reference", required=True)
    period_start = fields.Date("Period Start", required=True)
    period_end = fields.Date("Period End", required=True)
    gross_amount = fields.Float("Gross (€)", digits=(12, 2))
    net_amount = fields.Float("Net (€)", digits=(12, 2))
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.company.currency_id)
    attachment_id = fields.Many2one("ir.attachment", "PDF Attachment", ondelete="set null")


class HrAnnouncement(models.Model):
    """HR announcements displayed in the employee self-service portal."""

    _name = "hr.announcement"
    _description = "HR Announcement"
    _order = "publish_date desc"

    name = fields.Char("Title", required=True)
    body = fields.Html("Content", required=True)
    publish_date = fields.Date("Publish Date", default=fields.Date.today)
    expiry_date = fields.Date("Expires On")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)

    @api.model
    def get_active_announcements(self):
        today = fields.Date.today()
        domain = [
            ("active", "=", True),
            ("publish_date", "<=", today),
            "|",
            ("expiry_date", "=", False),
            ("expiry_date", ">=", today),
        ]
        return self.search(domain, order="publish_date desc")


class HrEmployeeCertification(models.Model):
    _name = "hr.employee.certification"
    _description = "Employee Certification"
    _order = "expiry_date"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char("Certification / Qualification", required=True)
    issuer = fields.Char("Issuing Body")
    issue_date = fields.Date("Issue Date")
    expiry_date = fields.Date("Expiry Date")
    status = fields.Selection(
        [("active", "Active"), ("expired", "Expired"), ("pending", "Pending Renewal")],
        default="active",
    )
    notes = fields.Text()


class HrEmployeeEquipment(models.Model):
    _name = "hr.employee.equipment"
    _description = "Employee Equipment Assignment"
    _order = "name"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char("Equipment", required=True)
    serial_number = fields.Char("Serial / Asset Number")
    assigned_date = fields.Date("Assigned On", default=fields.Date.today)
    return_date = fields.Date("Returned On")
    returned = fields.Boolean("Returned", default=False)
    notes = fields.Text()

    def action_mark_returned(self):
        self.write({"returned": True, "return_date": fields.Date.today()})


class HrOnboardingChecklistItem(models.Model):
    _name = "hr.onboarding.checklist.item"
    _description = "Onboarding / Offboarding Checklist Item"
    _order = "sequence, name"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    checklist_type = fields.Selection(
        [("onboarding", "Onboarding"), ("offboarding", "Offboarding")],
        default="onboarding",
    )
    done = fields.Boolean("Completed", default=False)
    done_date = fields.Datetime("Completed On", readonly=True)
    done_by_id = fields.Many2one("res.users", "Completed By", readonly=True)
    notes = fields.Text()

    def action_mark_done(self):
        self.write(
            {
                "done": True,
                "done_date": fields.Datetime.now(),
                "done_by_id": self.env.user.id,
            }
        )

    def action_mark_undone(self):
        self.write({"done": False, "done_date": False, "done_by_id": False})
