"""E2E: Payroll flow (Section 8 critical flow).

payroll run → calculate → confirm → approve → publish payslips → post journal.

Asserts the documented `hr.payroll.run` action methods are wired and that the immutable
payroll access-log model exists (a security requirement from the brief). Business guards
(e.g. no employees in the run) are tolerated.
"""

import pytest

RUN_FLOW = [
    "action_calculate",
    "action_confirm",
    "action_approve",
    "action_publish_payslips",
    "action_post_journal",
]


def test_payroll_run_methods_wired(odoo):
    if not odoo.model_exists("hr.payroll.run"):
        pytest.skip("hr.payroll.run model not installed")

    # Audit requirement: payroll access must be logged.
    assert odoo.model_exists("hr.payroll.access.log"), "payroll access-log model missing"

    run_id = odoo.create(
        "hr.payroll.run",
        {"name": "E2E Run", "period_start": "2026-05-01", "period_end": "2026-05-31"},
    )
    assert run_id

    for method in RUN_FLOW:
        odoo.call_action("hr.payroll.run", [run_id], method)  # raises if a method is missing

    state = odoo.read("hr.payroll.run", [run_id], ["state"])[0].get("state")
    assert state is not None
