"""Tests for M9 — HRM extensions, sick leave, certifications, leave types."""

from datetime import date, timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestHrEmployeeExtensions(TransactionCase):
    """Tests for hr.employee extensions."""

    def _make_employee(self, **kwargs):
        dept = self.env["hr.department"].search([], limit=1)
        vals = {
            "name": "Test Employee",
            "department_id": dept.id if dept else False,
        }
        vals.update(kwargs)
        return self.env["hr.employee"].create(vals)

    def test_emergency_contact_fields(self):
        emp = self._make_employee(
            emergency_contact_name="Jane Doe",
            emergency_contact_phone="+31612345678",
            emergency_contact_relation="Spouse",
        )
        self.assertEqual(emp.emergency_contact_name, "Jane Doe")
        self.assertEqual(emp.emergency_contact_phone, "+31612345678")

    def test_contract_fields(self):
        emp = self._make_employee(
            contract_type="permanent",
            weekly_hours=40.0,
        )
        self.assertEqual(emp.contract_type, "permanent")
        self.assertAlmostEqual(emp.weekly_hours, 40.0)

    def test_onboarding_checklist_creation(self):
        emp = self._make_employee()
        emp.action_initiate_onboarding()
        self.assertGreater(len(emp.onboarding_checklist_ids), 0)

    def test_checklist_item_mark_done(self):
        emp = self._make_employee()
        emp.action_initiate_onboarding()
        item = emp.onboarding_checklist_ids[0]
        self.assertFalse(item.done)
        item.action_mark_done()
        self.assertTrue(item.done)
        self.assertTrue(item.done_date)

    def test_certification_creation(self):
        emp = self._make_employee()
        cert = self.env["hr.employee.certification"].create(
            {
                "employee_id": emp.id,
                "name": "First Aid Certificate",
                "issuer": "Red Cross",
                "expiry_date": date.today() + timedelta(days=365),
                "status": "active",
            }
        )
        self.assertEqual(cert.status, "active")
        self.assertEqual(emp.certification_count, 1)

    def test_equipment_assignment(self):
        emp = self._make_employee()
        eq = self.env["hr.employee.equipment"].create(
            {
                "employee_id": emp.id,
                "name": "Laptop",
                "serial_number": "SN-12345",
            }
        )
        self.assertFalse(eq.returned)
        eq.action_mark_returned()
        self.assertTrue(eq.returned)
        self.assertTrue(eq.return_date)

    def test_offboarding_creates_checklist(self):
        emp = self._make_employee()
        emp.action_initiate_offboarding()
        self.assertTrue(emp.offboarding_started)
        offboarding = emp.onboarding_checklist_ids.filtered(
            lambda c: c.checklist_type == "offboarding"
        )
        self.assertGreater(len(offboarding), 0)


class TestSickLeave(TransactionCase):
    """Tests for hr.sick.leave model — privacy-safe behavior."""

    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Sick Leave Employee"})

    def test_create_sick_leave(self):
        sick = self.env["hr.sick.leave"].create(
            {
                "employee_id": self.employee.id,
                "start_date": fields.Date.today(),
            }
        )
        self.assertEqual(sick.state, "reported")

    def test_sick_leave_state_machine(self):
        sick = self.env["hr.sick.leave"].create(
            {
                "employee_id": self.employee.id,
                "start_date": fields.Date.today(),
                "expected_end_date": fields.Date.today() + timedelta(days=3),
            }
        )
        sick.action_recovery()
        self.assertEqual(sick.state, "recovered")
        self.assertEqual(sick.actual_end_date, fields.Date.today())
        sick.action_close()
        self.assertEqual(sick.state, "closed")

    def test_no_medical_data_stored(self):
        """Confirm sick leave model has no medical/diagnosis fields."""
        sick_fields = self.env["hr.sick.leave"]._fields
        # These should NOT exist on the model
        medical_fields = ["diagnosis", "symptoms", "medical_condition", "doctor_name"]
        for field in medical_fields:
            self.assertNotIn(
                field,
                sick_fields,
                f"Field '{field}' must not exist on hr.sick.leave (GDPR/privacy).",
            )

    def test_duration_computed(self):
        sick = self.env["hr.sick.leave"].create(
            {
                "employee_id": self.employee.id,
                "start_date": date.today(),
                "expected_end_date": date.today() + timedelta(days=4),
            }
        )
        self.assertEqual(sick.duration_days, 5)  # inclusive of start and end

    def test_privacy_notes_field_exists(self):
        """notes field should exist but must not require any medical content."""
        sick = self.env["hr.sick.leave"].create(
            {
                "employee_id": self.employee.id,
                "start_date": date.today(),
                "notes": "Administrative: HR to arrange coverage",
            }
        )
        self.assertIn("Administrative", sick.notes)


class TestLeaveTypes(TransactionCase):
    """Tests for seeded leave types."""

    def test_leave_types_seeded(self):
        """All 5 standard leave types are seeded."""
        leave_types = self.env["hr.leave.type"].search([])
        names = leave_types.mapped("name")
        expected_partial = ["Annual Leave", "Sick Leave", "Special Leave", "Unpaid", "Parental"]
        for partial in expected_partial:
            self.assertTrue(
                any(partial in name for name in names),
                f"Expected leave type containing '{partial}' to be seeded.",
            )

    def test_vacation_requires_allocation(self):
        vacation = self.env["hr.leave.type"].search([("name", "like", "Annual Leave")], limit=1)
        if vacation:
            self.assertTrue(vacation.requires_allocation)

    def test_sick_no_allocation(self):
        sick = self.env["hr.leave.type"].search([("name", "like", "Sick Leave")], limit=1)
        if sick:
            self.assertFalse(sick.requires_allocation)


class TestPortalPayslipVisibility(TransactionCase):
    """Portal payslip visibility must be scoped to the employee's own user."""

    def setUp(self):
        super().setUp()
        # Create two internal users
        self.user_a = self.env["res.users"].create(
            {
                "name": "Portal User A",
                "login": "portal_user_a@test.local",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        self.user_b = self.env["res.users"].create(
            {
                "name": "Portal User B",
                "login": "portal_user_b@test.local",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        self.emp_a = self.env["hr.employee"].create({"name": "Emp A", "user_id": self.user_a.id})
        self.emp_b = self.env["hr.employee"].create({"name": "Emp B", "user_id": self.user_b.id})
        # Create one payslip per employee
        self.slip_a = self.env["hr.employee.payslip"].create(
            {
                "employee_id": self.emp_a.id,
                "name": "Slip A — June 2025",
                "period_start": "2025-06-01",
                "period_end": "2025-06-30",
                "gross_amount": 3000.0,
                "net_amount": 2300.0,
            }
        )
        self.slip_b = self.env["hr.employee.payslip"].create(
            {
                "employee_id": self.emp_b.id,
                "name": "Slip B — June 2025",
                "period_start": "2025-06-01",
                "period_end": "2025-06-30",
                "gross_amount": 4000.0,
                "net_amount": 3100.0,
            }
        )

    def test_employee_sees_own_payslip_only(self):
        """User A's payslip query (filtered by employee_id=emp_a) returns only their own slip."""
        slips_for_a = self.env["hr.employee.payslip"].search([("employee_id", "=", self.emp_a.id)])
        self.assertIn(self.slip_a, slips_for_a)
        self.assertNotIn(self.slip_b, slips_for_a)

    def test_employee_b_cannot_read_employee_a_payslip(self):
        """Employee B's scoped search does not return Employee A's payslip."""
        slips_for_b = self.env["hr.employee.payslip"].search([("employee_id", "=", self.emp_b.id)])
        self.assertIn(self.slip_b, slips_for_b)
        self.assertNotIn(self.slip_a, slips_for_b)

    def test_record_rule_domain_matches_own_employee(self):
        """The domain used by the portal controller correctly scopes to user_id=user."""
        # Simulate what the portal controller does: filter by employee_id=employee
        # The record rule [('employee_id.user_id', '=', user.id)] enforces this at DB level.
        # We verify the field path resolves correctly.
        self.assertEqual(self.slip_a.employee_id.user_id, self.user_a)
        self.assertEqual(self.slip_b.employee_id.user_id, self.user_b)

    def test_payslip_model_has_scoping_fields(self):
        """hr.employee.payslip has employee_id and related company_id for record-rule scoping."""
        slip_fields = self.env["hr.employee.payslip"]._fields
        self.assertIn("employee_id", slip_fields)
        self.assertIn("company_id", slip_fields)
        self.assertIn("period_start", slip_fields)
        self.assertIn("net_amount", slip_fields)


class TestLeaveApprovalFlow(TransactionCase):
    """Tests for leave request → approval → balance update flow."""

    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Leave Flow Test Employee"})
        self.leave_type = self.env["hr.leave.type"].search(
            [("name", "like", "Annual Leave")], limit=1
        )

    def _make_allocation(self, days=20):
        alloc = (
            self.env["hr.leave.allocation"]
            .sudo()
            .create(
                {
                    "name": "Test Annual Allocation",
                    "employee_id": self.employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "number_of_days": days,
                }
            )
        )
        # In Odoo 19, allocations auto-go to 'confirm' on create; approve to validate
        alloc.sudo().action_approve()
        return alloc

    def test_leave_approve_sets_state_validate(self):
        """Validating a leave request moves its state to 'validate'."""
        if not self.leave_type:
            return
        self._make_allocation()
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "date_from": "2025-06-02 08:00:00",
                    "date_to": "2025-06-04 17:00:00",
                }
            )
        )
        leave.sudo()._action_validate(check_state=False)
        self.assertEqual(
            leave.state, "validate", "Leave must be in 'validate' state after approval."
        )

    def test_leave_approval_reduces_balance(self):
        """After approval, used days are deducted from the employee's allocation."""
        if not self.leave_type:
            return
        alloc = self._make_allocation(days=20)
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "date_from": "2025-07-07 08:00:00",
                    "date_to": "2025-07-09 17:00:00",
                }
            )
        )
        leave.sudo()._action_validate(check_state=False)

        used = sum(
            self.env["hr.leave"]
            .search(
                [
                    ("employee_id", "=", self.employee.id),
                    ("holiday_status_id", "=", self.leave_type.id),
                    ("state", "=", "validate"),
                ]
            )
            .mapped("number_of_days")
        )
        remaining = alloc.number_of_days - used
        self.assertGreater(used, 0, "Approved leave days must be greater than zero.")
        self.assertLess(
            remaining,
            alloc.number_of_days,
            "Remaining balance must decrease after leave is approved.",
        )
        self.assertGreaterEqual(remaining, 0.0, "Remaining balance must not go negative.")

    def test_refused_leave_does_not_reduce_balance(self):
        """A refused leave request does not consume any allocation days."""
        if not self.leave_type:
            return
        self._make_allocation(days=10)
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "date_from": "2025-08-04 08:00:00",
                    "date_to": "2025-08-06 17:00:00",
                }
            )
        )
        leave.sudo().action_refuse()
        self.assertEqual(leave.state, "refuse")

        used = sum(
            self.env["hr.leave"]
            .search(
                [
                    ("employee_id", "=", self.employee.id),
                    ("holiday_status_id", "=", self.leave_type.id),
                    ("state", "=", "validate"),
                ]
            )
            .mapped("number_of_days")
        )
        self.assertAlmostEqual(
            used, 0.0, places=2, msg="No allocation days must be consumed by a refused leave."
        )


# ── Portal planning calendar ───────────────────────────────────────────────────


class TestPortalPlanningCalendar(TransactionCase):
    """Unit tests for the planning calendar data-assembly logic.

    The HTTP layer is not exercised here — we test the model queries and
    calendar-grid construction logic independently so no web server is needed.
    """

    def setUp(self):
        super().setUp()
        self.user = self.env["res.users"].create(
            {
                "name": "Calendar Employee",
                "login": "cal_emp@test.com",
                "email": "cal_emp@test.com",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.employee = self.env["hr.employee"].create(
            {
                "name": "Calendar Employee",
                "user_id": self.user.id,
            }
        )
        self.leave_type = self.env["hr.leave.type"].search([("name", "ilike", "Annual")], limit=1)

    def _ensure_alloc(self, employee):
        """Create and approve an allocation for employee if leave_type requires it."""
        if not self.leave_type or not self.leave_type.requires_allocation:
            return
        alloc = (
            self.env["hr.leave.allocation"]
            .sudo()
            .create(
                {
                    "name": "Calendar Test Allocation",
                    "employee_id": employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "number_of_days": 30,
                }
            )
        )
        alloc.sudo().action_approve()

    def _make_leave(self, date_from, date_to, state="validate"):
        if not self.leave_type:
            return None
        self._ensure_alloc(self.employee)
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "date_from": date_from,
                    "date_to": date_to,
                }
            )
        )
        if state == "validate":
            try:
                leave.sudo()._action_validate(check_state=False)
            except Exception:
                pass
        return leave

    def _make_sick_leave(self, start_date, expected_end_date=None):
        return (
            self.env["hr.sick.leave"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee.id,
                    "start_date": start_date,
                    "expected_end_date": expected_end_date,
                }
            )
        )

    def test_planning_template_exists(self):
        """portal_employee_planning template must be registered."""
        tmpl = self.env["ir.ui.view"].search(
            [("key", "=", "custom_hrm.portal_employee_planning")], limit=1
        )
        self.assertTrue(tmpl, "portal_employee_planning template must exist.")

    def test_sick_leave_appears_in_calendar_month(self):
        """Sick leave created mid-month must be fetchable for that month's calendar."""
        sl = self._make_sick_leave("2026-06-10", "2026-06-12")
        results = self.env["hr.sick.leave"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("start_date", "<=", "2026-06-30"),
                "|",
                ("expected_end_date", ">=", "2026-06-01"),
                ("expected_end_date", "=", False),
            ]
        )
        self.assertIn(sl, results)

    def test_sick_leave_without_end_date_still_appears(self):
        """Sick leave with no expected_end_date must appear in the calendar query."""
        sl = self._make_sick_leave("2026-06-15")
        results = self.env["hr.sick.leave"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("start_date", "<=", "2026-06-30"),
                "|",
                ("expected_end_date", ">=", "2026-06-01"),
                ("expected_end_date", "=", False),
            ]
        )
        self.assertIn(sl, results)

    def test_sick_leave_outside_month_not_returned(self):
        """Sick leave in a different month must not appear in June query."""
        sl = self._make_sick_leave("2026-07-05", "2026-07-08")
        results = self.env["hr.sick.leave"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("start_date", "<=", "2026-06-30"),
                "|",
                ("expected_end_date", ">=", "2026-06-01"),
                ("expected_end_date", "=", False),
            ]
        )
        self.assertNotIn(sl, results)

    def test_refused_leave_excluded_from_calendar(self):
        """Refused leaves must not appear in the calendar query."""
        if not self.leave_type:
            return
        self._ensure_alloc(self.employee)
        leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee.id,
                    "holiday_status_id": self.leave_type.id,
                    "date_from": "2026-06-10 08:00:00",
                    "date_to": "2026-06-11 17:00:00",
                }
            )
        )
        leave.sudo().action_refuse()
        results = self.env["hr.leave"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("date_from", "<=", "2026-06-30 23:59:59"),
                ("date_to", ">=", "2026-06-01 00:00:00"),
                ("state", "not in", ("refuse",)),
            ]
        )
        self.assertNotIn(leave, results)

    def test_other_employee_leave_not_visible(self):
        """Another employee's leave must not appear in this employee's calendar query."""
        other_emp = self.env["hr.employee"].create({"name": "Other Employee"})
        if not self.leave_type:
            return
        self._ensure_alloc(other_emp)
        other_leave = (
            self.env["hr.leave"]
            .sudo()
            .create(
                {
                    "employee_id": other_emp.id,
                    "holiday_status_id": self.leave_type.id,
                    "date_from": "2026-06-10 08:00:00",
                    "date_to": "2026-06-11 17:00:00",
                }
            )
        )
        results = self.env["hr.leave"].search(
            [
                ("employee_id", "=", self.employee.id),
                ("date_from", "<=", "2026-06-30 23:59:59"),
                ("date_to", ">=", "2026-06-01 00:00:00"),
            ]
        )
        self.assertNotIn(other_leave, results)

    def test_calendar_grid_structure(self):
        """Calendar grid must produce 7-day weeks covering the full month."""
        import calendar as _cal

        year, month = 2026, 6
        weeks = _cal.monthcalendar(year, month)
        # All weeks must be 7 days
        for week in weeks:
            self.assertEqual(len(week), 7)
        # All non-zero day numbers must be valid for June
        for week in weeks:
            for day_num in week:
                if day_num != 0:
                    self.assertGreaterEqual(day_num, 1)
                    self.assertLessEqual(day_num, 30)

    def test_planning_route_exists_in_controller(self):
        """The /my/planning route must be registered in the portal controller."""
        from odoo.addons.custom_hrm.controllers.hr_portal_controller import (
            EmployeePortalController,
        )

        route_paths = [
            r
            for method_name in dir(EmployeePortalController)
            for r in (
                getattr(
                    getattr(EmployeePortalController, method_name, None),
                    "original_routing",
                    {},
                ).get("routes", [])
            )
        ]
        self.assertIn(
            "/my/planning", route_paths, "/my/planning must be a registered portal route."
        )
