from odoo.tests.common import TransactionCase


class TestCrmLead(TransactionCase):
    """Tests for custom crm.lead extensions."""

    def setUp(self):
        super().setUp()
        self.stage = self.env["crm.stage"].search([], limit=1)
        self.lead = self.env["crm.lead"].create(
            {
                "name": "Test Platform Lead",
                "type": "lead",
                "email_from": "prospect@example.com",
                "partner_name": "Test Corp",
                "expected_revenue": 5000,
                "probability": 30,
                "stage_id": self.stage.id if self.stage else False,
            }
        )

    def test_lead_score_computed(self):
        """Lead score is computed based on available data."""
        self.assertGreater(self.lead.lead_score, 0, "Lead with email should have score > 0")
        self.assertLessEqual(self.lead.lead_score, 100)

    def test_lead_score_email_only(self):
        """Minimum score for a lead with email only."""
        lead = self.env["crm.lead"].create(
            {
                "name": "Bare Lead",
                "type": "lead",
                "email_from": "test@test.com",
            }
        )
        self.assertGreaterEqual(lead.lead_score, 20)

    def test_lead_score_full_data_higher(self):
        """Lead with more data scores higher."""
        rich_lead = self.env["crm.lead"].create(
            {
                "name": "Rich Lead",
                "type": "opportunity",
                "email_from": "rich@example.com",
                "phone": "+31201234567",
                "expected_revenue": 50000,
                "probability": 70,
                "stage_id": self.stage.id if self.stage else False,
            }
        )
        self.assertGreater(rich_lead.lead_score, self.lead.lead_score)

    def test_duplicate_detection_by_email(self):
        """Leads with the same email are detected as duplicates."""
        dupe = self.env["crm.lead"].create(
            {
                "name": "Duplicate Lead",
                "type": "lead",
                "email_from": "prospect@example.com",
            }
        )
        # Force recompute
        self.lead._compute_duplicates()
        self.assertGreater(self.lead.duplicate_count, 0, "Should detect email duplicate.")
        self.assertIn(dupe.id, self.lead.duplicate_lead_ids.ids)

    def test_campaign_assignment(self):
        """Lead can be linked to a campaign."""
        campaign = self.env["crm.campaign"].create(
            {
                "name": "Q1 Outreach",
                "channel": "email",
            }
        )
        self.lead.platform_campaign_id = campaign
        self.assertEqual(self.lead.platform_campaign_id.name, "Q1 Outreach")
        self.assertIn(self.lead, campaign.lead_ids)

    def test_ai_summary_with_mock(self):
        """AI summary is generated using the mock provider."""
        self.lead.action_generate_ai_summary()
        self.assertTrue(self.lead.ai_summary, "AI summary should be set after generation.")
        self.assertTrue(self.lead.ai_summary_date)
        self.assertIn("MOCK", self.lead.ai_summary)

    def test_mark_contacted(self):
        """action_mark_contacted increments contact_count."""
        self.lead.action_mark_contacted()
        self.assertEqual(self.lead.contact_count, 1)
        self.assertTrue(self.lead.last_contacted_date)


class TestCrmCampaign(TransactionCase):
    """Tests for crm.campaign model."""

    def _make_campaign(self, **kwargs):
        vals = {"name": "Test Campaign", "channel": "email"}
        vals.update(kwargs)
        return self.env["crm.campaign"].create(vals)

    def test_create_campaign(self):
        campaign = self._make_campaign()
        self.assertEqual(campaign.state, "draft")
        self.assertEqual(campaign.lead_count, 0)

    def test_activate_campaign(self):
        campaign = self._make_campaign()
        campaign.action_activate()
        self.assertEqual(campaign.state, "active")

    def test_campaign_lead_count(self):
        """lead_count reflects linked leads."""
        campaign = self._make_campaign()
        stage = self.env["crm.stage"].search([], limit=1)
        self.env["crm.lead"].create(
            {
                "name": "Campaign Lead",
                "type": "lead",
                "platform_campaign_id": campaign.id,
                "stage_id": stage.id if stage else False,
            }
        )
        campaign._compute_lead_stats()
        self.assertEqual(campaign.lead_count, 1)


class TestCrmCampaignRBAC(TransactionCase):
    """Tests for CRM campaign access control matrix."""

    def setUp(self):
        super().setUp()
        self.campaign = self.env["crm.campaign"].create(
            {"name": "RBAC Test Campaign", "channel": "email"}
        )

    def test_sales_manager_has_full_access(self):
        """Sales manager can create, write, read, and delete campaigns."""
        manager = self.env["res.users"].create(
            {
                "name": "RBAC Sales Manager",
                "login": "rbac_mgr@campaign.test",
                "group_ids": [(4, self.env.ref("sales_team.group_sale_manager").id)],
            }
        )
        env = self.env(user=manager)
        c = env["crm.campaign"].create({"name": "Manager Campaign", "channel": "email"})
        c.write({"name": "Manager Campaign Updated"})
        self.assertEqual(c.name, "Manager Campaign Updated")
        c.unlink()

    def test_salesman_cannot_delete_campaign(self):
        """Sales salesman cannot delete campaigns (perm_unlink=0)."""
        from odoo.exceptions import AccessError

        salesman = self.env["res.users"].create(
            {
                "name": "RBAC Salesman",
                "login": "rbac_salesman@campaign.test",
                "group_ids": [(4, self.env.ref("sales_team.group_sale_salesman").id)],
            }
        )
        env = self.env(user=salesman)
        with self.assertRaises(AccessError):
            env["crm.campaign"].browse(self.campaign.id).unlink()

    def test_regular_user_cannot_create_campaign(self):
        """Regular users cannot create campaigns (perm_create=0)."""
        from odoo.exceptions import AccessError

        user = self.env["res.users"].create(
            {
                "name": "RBAC Regular",
                "login": "rbac_regular@campaign.test",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        env = self.env(user=user)
        with self.assertRaises(AccessError):
            env["crm.campaign"].create({"name": "Unauthorized", "channel": "email"})

    def test_regular_user_cannot_write_campaign(self):
        """Regular users cannot modify campaigns (perm_write=0)."""
        from odoo.exceptions import AccessError

        user = self.env["res.users"].create(
            {
                "name": "RBAC Regular Write",
                "login": "rbac_regular_w@campaign.test",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        env = self.env(user=user)
        with self.assertRaises(AccessError):
            env["crm.campaign"].browse(self.campaign.id).write({"name": "Tamper"})

    def test_regular_user_can_read_campaign(self):
        """Regular users can read campaigns (perm_read=1)."""
        user = self.env["res.users"].create(
            {
                "name": "RBAC Regular Read",
                "login": "rbac_regular_r@campaign.test",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        env = self.env(user=user)
        results = env["crm.campaign"].search([("id", "=", self.campaign.id)])
        self.assertEqual(len(results), 1)


class TestLeadDealQuoteFlow(TransactionCase):
    """Integration test: Lead → Opportunity → Sale Order (quote) → Confirmed."""

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create(
            {
                "name": "E2E Test Corp",
                "email": "e2e@testcorp.example",
            }
        )
        self.stage = self.env["crm.stage"].search([], limit=1)
        self.product = self.env["product.product"].create(
            {
                "name": "Consulting Service",
                "type": "service",
                "list_price": 1500.0,
            }
        )

    def test_lead_to_opportunity(self):
        """A lead can be converted to an opportunity."""
        lead = self.env["crm.lead"].create(
            {
                "name": "Prospect: E2E Test Corp",
                "type": "lead",
                "email_from": "e2e@testcorp.example",
                "partner_name": "E2E Test Corp",
                "expected_revenue": 10000,
                "stage_id": self.stage.id if self.stage else False,
            }
        )
        self.assertEqual(lead.type, "lead")
        lead.write({"type": "opportunity", "partner_id": self.partner.id})
        self.assertEqual(lead.type, "opportunity")
        self.assertEqual(lead.partner_id, self.partner)

    def test_opportunity_to_sale_order(self):
        """A sale order (quote) can be created and linked to an opportunity."""
        opp = self.env["crm.lead"].create(
            {
                "name": "Deal: E2E Platform",
                "type": "opportunity",
                "partner_id": self.partner.id,
                "expected_revenue": 10000,
                "probability": 60,
                "stage_id": self.stage.id if self.stage else False,
            }
        )
        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "opportunity_id": opp.id,
            }
        )
        self.assertEqual(so.opportunity_id, opp)
        self.assertEqual(so.state, "draft")

    def test_sale_order_confirmation(self):
        """A sale order linked to an opportunity can be confirmed."""
        opp = self.env["crm.lead"].create(
            {
                "name": "Deal: Confirmed Platform",
                "type": "opportunity",
                "partner_id": self.partner.id,
                "stage_id": self.stage.id if self.stage else False,
            }
        )
        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "opportunity_id": opp.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "price_unit": 1500.0,
                        },
                    )
                ],
            }
        )
        so.action_confirm()
        self.assertEqual(so.state, "sale")

    def test_full_lead_deal_quote_flow(self):
        """Full flow: lead → opportunity → confirmed sale order."""
        # 1. Create lead
        lead = self.env["crm.lead"].create(
            {
                "name": "Full Flow Lead",
                "type": "lead",
                "email_from": "full@flow.example",
                "partner_name": "Full Flow Corp",
                "expected_revenue": 5000,
                "stage_id": self.stage.id if self.stage else False,
            }
        )
        self.assertGreater(lead.lead_score, 0)

        # 2. Convert to opportunity
        lead.write({"type": "opportunity", "partner_id": self.partner.id})
        self.assertEqual(lead.type, "opportunity")

        # 3. Create sale order (quote) linked to the opportunity
        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "opportunity_id": lead.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "price_unit": 5000.0,
                        },
                    )
                ],
            }
        )
        self.assertEqual(so.opportunity_id, lead)
        self.assertEqual(so.state, "draft")

        # 4. Confirm the quote → sale order
        so.action_confirm()
        self.assertEqual(so.state, "sale")

        # 5. Mark opportunity won
        lead.write({"probability": 100})
        self.assertEqual(lead.probability, 100)
