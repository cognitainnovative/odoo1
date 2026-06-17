from odoo.tests.common import TransactionCase


class TestGdpr(TransactionCase):
    """Tests for GDPR consent and anonymization."""

    def _make_lead(self, email="gdpr@test.com", name="GDPR Lead"):
        stage = self.env["crm.stage"].search([], limit=1)
        return self.env["crm.lead"].create(
            {
                "name": name,
                "type": "lead",
                "email_from": email,
                "partner_name": "GDPR Test Corp",
                "phone": "+31201234567",
                "stage_id": stage.id if stage else False,
            }
        )

    def test_gdpr_consent_default_false(self):
        """New leads have no GDPR consent by default."""
        lead = self._make_lead()
        self.assertFalse(lead.gdpr_consent)
        self.assertFalse(lead.gdpr_anonymized)

    def test_record_gdpr_consent(self):
        """action_record_gdpr_consent sets consent fields."""
        lead = self._make_lead()
        lead.action_record_gdpr_consent()
        self.assertTrue(lead.gdpr_consent)
        self.assertTrue(lead.gdpr_consent_date)

    def test_anonymize_lead(self):
        """action_anonymize removes personal data."""
        lead = self._make_lead(email="personal@secret.com", name="Real Person Lead")
        lead.action_anonymize()
        self.assertTrue(lead.gdpr_anonymized)
        self.assertNotIn("personal@secret.com", lead.email_from)
        self.assertNotIn("Real Person", lead.partner_name)
        self.assertFalse(lead.phone)

    def test_anonymize_is_idempotent(self):
        """Anonymizing an already-anonymized lead does nothing."""
        lead = self._make_lead()
        lead.action_anonymize()
        name_after_first = lead.partner_name
        lead.action_anonymize()
        self.assertEqual(lead.partner_name, name_after_first)

    def test_gdpr_export_data(self):
        """action_export_gdpr_data returns a dict with personal data."""
        lead = self._make_lead()
        data = lead.action_export_gdpr_data()
        self.assertIn("email", data)
        self.assertIn("name", data)
        self.assertIn("gdpr_consent", data)
        self.assertEqual(data["email"], "gdpr@test.com")

    def test_partner_gdpr_consent(self):
        """GDPR consent propagates to partner when recording on lead."""
        partner = self.env["res.partner"].create(
            {
                "name": "GDPR Partner",
                "email": "partner@gdpr.com",
            }
        )
        stage = self.env["crm.stage"].search([], limit=1)
        lead = self.env["crm.lead"].create(
            {
                "name": "Partner GDPR Lead",
                "type": "lead",
                "partner_id": partner.id,
                "stage_id": stage.id if stage else False,
            }
        )
        lead.action_record_gdpr_consent()
        self.assertTrue(partner.gdpr_consent)

    def test_partner_anonymize(self):
        """Anonymizing a partner clears personal data."""
        partner = self.env["res.partner"].create(
            {
                "name": "Real Name",
                "email": "real@email.com",
                "phone": "+31201234567",
            }
        )
        partner.action_anonymize_partner()
        self.assertTrue(partner.gdpr_anonymized)
        self.assertNotIn("Real Name", partner.name)
        self.assertFalse(partner.phone)
