"""Prompt template evaluations — run test inputs against a template and verify output."""

import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AiPromptEvaluation(models.Model):
    _name = "ai.prompt.evaluation"
    _description = "Prompt Template Evaluation"
    _order = "template_id, create_date desc"

    template_id = fields.Many2one(
        "ai.prompt.template", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda s: s.env.company, index=True
    )
    name = fields.Char("Test Name", required=True)
    test_input_json = fields.Text(
        "Template Variables (JSON)",
        help="JSON object mapping template placeholders to test values. "
        'E.g. {"name": "Acme", "stage": "New"}',
    )
    test_user_prompt = fields.Text(
        "User Prompt Override",
        help="If set, used as the user prompt instead of the template's user_template.",
    )
    expected_contains = fields.Char(
        "Output Must Contain",
        help="Case-insensitive substring that must appear in the model response to pass.",
    )

    # Results (written by action_run)
    actual_output = fields.Text("Actual Output", readonly=True)
    passed = fields.Boolean("Passed", readonly=True)
    run_date = fields.Datetime("Last Run", readonly=True)
    run_by = fields.Many2one("res.users", "Run By", readonly=True)
    audit_log_id = fields.Many2one("ai.audit.log", "Audit Entry", readonly=True)
    error = fields.Char("Error", readonly=True)
    notes = fields.Text()

    def action_run(self):
        """Execute the evaluation: call ai.service and store pass/fail result."""
        for rec in self:
            vars_dict = {}
            if rec.test_input_json:
                try:
                    vars_dict = json.loads(rec.test_input_json)
                except json.JSONDecodeError as exc:
                    rec.write(
                        {
                            "error": f"Invalid JSON: {exc}",
                            "passed": False,
                            "run_date": fields.Datetime.now(),
                            "run_by": self.env.user.id,
                        }
                    )
                    continue

            user_prompt = rec.test_user_prompt or ""
            try:
                result = self.env["ai.service"].call(
                    user_prompt,
                    template_code=rec.template_id.code,
                    template_vars=vars_dict,
                )
            except Exception as exc:
                rec.write(
                    {
                        "error": str(exc)[:500],
                        "passed": False,
                        "run_date": fields.Datetime.now(),
                        "run_by": self.env.user.id,
                    }
                )
                continue

            actual = result.get("content", "")
            passed = True
            if rec.expected_contains:
                passed = rec.expected_contains.lower() in actual.lower()

            rec.write(
                {
                    "actual_output": actual[:2000],
                    "passed": passed,
                    "run_date": fields.Datetime.now(),
                    "run_by": self.env.user.id,
                    "audit_log_id": result.get("audit_log_id") or False,
                    "error": result.get("error", "")[:500] if not result.get("ok") else "",
                }
            )

    @api.model
    def run_all_for_template(self, template_code: str) -> list[dict]:
        """Run all evaluations for a template and return a summary."""
        template = self.env["ai.prompt.template"].search(
            [
                ("code", "=", template_code),
                ("company_id", "=", self.env.company.id),
                ("is_active", "=", True),
            ],
            limit=1,
        )
        if not template:
            return []
        evals = self.search(
            [("template_id", "=", template.id), ("company_id", "=", self.env.company.id)]
        )
        if evals:
            evals.action_run()
        return [{"name": e.name, "passed": e.passed, "error": e.error} for e in evals]
