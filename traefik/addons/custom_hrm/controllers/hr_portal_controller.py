"""Employee self-service portal controller and model hooks."""

import base64
import calendar as _cal
import logging
from datetime import date, datetime, timedelta

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class EmployeePortalController(http.Controller):
    """Portal endpoints for employee self-service."""

    @http.route("/my/profile", type="http", auth="user", website=True)
    def employee_profile(self, **kwargs):
        """Show employee's own profile."""
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )
        if not employee:
            return request.redirect("/web")
        return request.render(
            "custom_hrm.portal_employee_profile",
            {"employee": employee, "user": request.env.user},
        )

    @http.route("/my/leaves", type="http", auth="user", website=True)
    def employee_leaves(self, **kwargs):
        """Show employee's leave allocations and requests."""
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )
        if not employee:
            return request.redirect("/web")

        leaves = (
            request.env["hr.leave"]
            .sudo()
            .search(
                [("employee_id", "=", employee.id)],
                order="date_from desc",
                limit=20,
            )
        )
        allocations = (
            request.env["hr.leave.allocation"]
            .sudo()
            .search(
                [("employee_id", "=", employee.id), ("state", "=", "validate")],
            )
        )
        # Sick leaves are a separate model (hr.sick.leave) and are what the
        # website self-report form creates; include them so records added from
        # the portal are visible here too.
        sick_leaves = (
            request.env["hr.sick.leave"]
            .sudo()
            .search(
                [("employee_id", "=", employee.id)],
                order="start_date desc",
                limit=20,
            )
        )
        return request.render(
            "custom_hrm.portal_employee_leaves",
            {
                "employee": employee,
                "leaves": leaves,
                "allocations": allocations,
                "sick_leaves": sick_leaves,
            },
        )

    @http.route("/my/payslips", type="http", auth="user", website=True)
    def employee_payslips(self, **kwargs):
        """Show employee's own payslips — scoped by record rule to self."""
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )
        if not employee:
            return request.redirect("/web")
        # Record rule on hr.employee.payslip enforces employee_id.user_id == user
        payslips = (
            request.env["hr.employee.payslip"]
            .sudo()
            .search(
                [("employee_id", "=", employee.id)],
                order="period_start desc",
                limit=36,
            )
        )
        return request.render(
            "custom_hrm.portal_employee_payslips",
            {"employee": employee, "payslips": payslips},
        )

    @http.route(
        "/my/documents", type="http", auth="user", methods=["GET", "POST"], website=True, csrf=True
    )
    def employee_documents(self, **kwargs):
        """HR document viewer + upload for the logged-in employee."""
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )
        if not employee:
            return request.redirect("/web")

        if request.httprequest.method == "POST":
            uploaded = request.httprequest.files.get("document")
            if uploaded and uploaded.filename:
                file_data = base64.b64encode(uploaded.stream.read()).decode()
                request.env["ir.attachment"].sudo().create(
                    {
                        "name": uploaded.filename,
                        "res_model": "hr.employee",
                        "res_id": employee.id,
                        "datas": file_data,
                        "type": "binary",
                    }
                )

        docs = (
            request.env["ir.attachment"]
            .sudo()
            .search(
                [("res_model", "=", "hr.employee"), ("res_id", "=", employee.id)],
                order="create_date desc",
                limit=50,
            )
        )
        announcements = request.env["hr.announcement"].sudo().get_active_announcements()
        return request.render(
            "custom_hrm.portal_employee_documents",
            {"employee": employee, "docs": docs, "announcements": announcements},
        )

    @http.route("/my/planning", type="http", auth="user", website=True)
    def employee_planning(self, year=None, month=None, **kwargs):
        """Monthly leave + sick-leave calendar for the logged-in employee."""
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )
        if not employee:
            return request.redirect("/web")

        today = date.today()
        try:
            year = int(year) if year else today.year
            month = int(month) if month else today.month
        except (ValueError, TypeError):
            year, month = today.year, today.month
        year = max(2000, min(2099, year))
        month = max(1, min(12, month))

        last_day = _cal.monthrange(year, month)[1]
        month_start_str = f"{year}-{month:02d}-01"
        month_end_str = f"{year}-{month:02d}-{last_day:02d}"
        # Datetime boundaries for hr.leave (Datetime fields)
        month_start_dt = datetime(year, month, 1, 0, 0, 0)
        month_end_dt = datetime(year, month, last_day, 23, 59, 59)

        # ── Fetch leave requests overlapping this month ───────────────────────
        leaves = (
            request.env["hr.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("date_from", "<=", month_end_dt),
                    ("date_to", ">=", month_start_dt),
                    ("state", "not in", ("refuse",)),
                ]
            )
        )

        # ── Fetch sick leaves overlapping this month ──────────────────────────
        sick_leaves = (
            request.env["hr.sick.leave"]
            .sudo()
            .search(
                [
                    ("employee_id", "=", employee.id),
                    ("start_date", "<=", month_end_str),
                    "|",
                    ("expected_end_date", ">=", month_start_str),
                    ("expected_end_date", "=", False),
                ]
            )
        )

        # ── Build date → events map ───────────────────────────────────────────
        _STATE_LABELS = {
            "draft": "Draft",
            "confirm": "Pending",
            "validate1": "Approved (1st)",
            "validate": "Approved",
            "refuse": "Refused",
        }
        _STATE_CSS = {
            "draft": "secondary",
            "confirm": "warning",
            "validate1": "info",
            "validate": "success",
            "refuse": "danger",
        }
        events_by_date = {}

        for leave in leaves:
            if not leave.date_from:
                continue
            cur = leave.date_from.date()
            end = leave.date_to.date() if leave.date_to else cur
            while cur <= end:
                if cur.year == year and cur.month == month:
                    events_by_date.setdefault(cur, []).append(
                        {
                            "label": leave.holiday_status_id.name or "Leave",
                            "css": _STATE_CSS.get(leave.state, "secondary"),
                            "type": "leave",
                        }
                    )
                cur += timedelta(days=1)

        for sl in sick_leaves:
            if not sl.start_date:
                continue
            cur = sl.start_date
            end = sl.expected_end_date or sl.actual_end_date or cur
            while cur <= end:
                if cur.year == year and cur.month == month:
                    events_by_date.setdefault(cur, []).append(
                        {
                            "label": "Sick Leave",
                            "css": "danger",
                            "type": "sick",
                        }
                    )
                cur += timedelta(days=1)

        # ── Build calendar grid ───────────────────────────────────────────────
        weeks = []
        for week in _cal.monthcalendar(year, month):
            days = []
            for day_num in week:
                if day_num == 0:
                    days.append({"date": None, "current_month": False, "events": []})
                else:
                    d = date(year, month, day_num)
                    days.append(
                        {
                            "date": d,
                            "day_num": day_num,
                            "current_month": True,
                            "today": d == today,
                            "weekend": d.isoweekday() in (6, 7),
                            "events": events_by_date.get(d, []),
                        }
                    )
            weeks.append(days)

        # ── Prev / next month links ───────────────────────────────────────────
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

        _MONTH_NAMES = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]

        return request.render(
            "custom_hrm.portal_employee_planning",
            {
                "employee": employee,
                "year": year,
                "month": month,
                "month_name": _MONTH_NAMES[month - 1],
                "weeks": weeks,
                "prev_year": prev_year,
                "prev_month": prev_month,
                "next_year": next_year,
                "next_month": next_month,
                "today": today,
            },
        )

    @http.route(
        "/my/sick-leave/report",
        type="http",
        auth="user",
        methods=["GET", "POST"],
        website=True,
        csrf=True,
    )
    def report_sick_leave(self, **kwargs):
        """Employee can self-report sick leave."""
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )
        if not employee:
            return request.redirect("/web")

        if request.httprequest.method == "POST":
            start_date = kwargs.get("start_date")
            expected_end = kwargs.get("expected_end_date") or None
            if start_date:
                request.env["hr.sick.leave"].sudo().create(
                    {
                        "employee_id": employee.id,
                        "start_date": start_date,
                        "expected_end_date": expected_end,
                    }
                )
                return request.render(
                    "custom_hrm.portal_sick_leave_submitted",
                    {"employee": employee},
                )

        return request.render(
            "custom_hrm.portal_sick_leave_form",
            {"employee": employee},
        )
