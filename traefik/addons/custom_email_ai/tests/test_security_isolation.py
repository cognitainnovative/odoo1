"""M16 security review: company-isolation regression tests for email_ai.

Proves the company record rules actually filter cross-company data — not just
that the field exists. Uses with_user + a second company to verify a user in
company A cannot see company B's mailbox/outbox.
"""

from odoo.tests.common import TransactionCase


class TestEmailAiCompanyIsolation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company_a = self.env.company
        self.company_b = self.env["res.company"].create({"name": "M16 Co B"})
        # a user who belongs ONLY to company A
        self.user_a = self.env["res.users"].create(
            {
                "name": "M16 User A",
                "login": "m16_user_a@test.local",
                "company_id": self.company_a.id,
                "company_ids": [(6, 0, [self.company_a.id])],
                "group_ids": [
                    (4, self.env.ref("base.group_user").id),
                    (4, self.env.ref("custom_platform_security.group_support_agent").id),
                ],
            }
        )
        # mailboxes in each company
        self.mb_a = self.env["email.ai.mailbox"].create(
            {"name": "MB A", "email_address": "a@test.local", "company_id": self.company_a.id}
        )
        self.mb_b = self.env["email.ai.mailbox"].create(
            {"name": "MB B", "email_address": "b@test.local", "company_id": self.company_b.id}
        )

    def test_user_a_cannot_see_company_b_mailbox(self):
        visible = self.env["email.ai.mailbox"].with_user(self.user_a).search([])
        self.assertIn(self.mb_a, visible)
        self.assertNotIn(
            self.mb_b,
            visible,
            "COMPANY ISOLATION FAILURE: user in company A can see company B's mailbox.",
        )

    def test_user_a_cannot_read_company_b_mailbox_direct(self):
        from odoo.exceptions import AccessError

        with self.assertRaises(AccessError):
            self.mb_b.with_user(self.user_a).read(["name", "email_address"])
