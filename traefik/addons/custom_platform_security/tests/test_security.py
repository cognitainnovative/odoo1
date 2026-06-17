from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestApiToken(TransactionCase):
    """Token issuance, hashing, verification, revocation."""

    def setUp(self):
        super().setUp()
        self.Token = self.env["platform.api.token"]
        self.Wizard = self.env["platform.api.token.generate"]

    def test_wizard_shows_raw_token_once_and_stores_only_hash(self):
        """The generate wizard surfaces the raw token; the record stores only its hash."""
        wiz = self.Wizard.create(
            {
                "name": "React App",
                "user_id": self.env.user.id,
                "service": "react_app",
                "scope": "read",
            }
        )
        wiz.action_generate()
        self.assertTrue(wiz.raw_token, "Wizard must expose the raw token once.")
        self.assertTrue(wiz.token_id, "Wizard must link the created token record.")
        token = wiz.token_id
        self.assertNotEqual(
            token.token_hash, wiz.raw_token, "Record must store the hash, never the raw token."
        )
        self.assertEqual(token.token_hash, self.Token._hash_token(wiz.raw_token))
        # No field on the token record contains the raw value
        for fname in token._fields:
            val = token[fname]
            if isinstance(val, str):
                self.assertNotEqual(val, wiz.raw_token, f"Raw token leaked into field {fname}")

    def test_verify_token_roundtrip(self):
        """A generated token verifies; a revoked one does not."""
        wiz = self.Wizard.create(
            {
                "name": "CI",
                "user_id": self.env.user.id,
                "service": "ci",
                "scope": "read",
            }
        )
        wiz.action_generate()
        raw = wiz.raw_token
        rec = self.Token.verify_token(raw)
        self.assertTrue(rec, "Valid token must verify.")
        self.assertEqual(rec.id, wiz.token_id.id)
        rec.action_revoke()
        self.assertFalse(self.Token.verify_token(raw), "Revoked token must not verify.")

    def test_verify_rejects_garbage(self):
        self.assertFalse(self.Token.verify_token(""))
        self.assertFalse(self.Token.verify_token("not-a-real-token"))

    def test_programmatic_create_generates_hash(self):
        """Direct create without a hash still gets one (raw is discarded)."""
        token = self.Token.create(
            {
                "name": "Direct",
                "user_id": self.env.user.id,
                "service": "other",
                "scope": "read",
            }
        )
        self.assertTrue(token.token_hash)


class TestAuditLogImmutability(TransactionCase):
    def test_write_and_unlink_blocked(self):
        log = self.env["platform.audit.log"].log("admin_config_change", summary="test entry")
        with self.assertRaises(UserError):
            log.write({"summary": "tampered"})
        with self.assertRaises(UserError):
            log.unlink()


class TestGdprPurgeSafeguards(TransactionCase):
    def test_protected_model_policy_is_skipped(self):
        """A retention policy on a protected model must never delete anything."""
        Policy = self.env["platform.gdpr.retention.policy"]
        # Use an existing partner; creating one can trip NOT NULL columns
        # added by other modules (e.g. account.autopost_bills) on some DBs.
        partner = self.env.ref("base.partner_admin")
        Policy.create(
            {
                "model_name": "res.partner",
                "retention_days": 1,  # everything older than yesterday
            }
        )
        Policy.cron_purge_expired_records()
        self.assertTrue(partner.exists(), "Protected model records must survive the purge cron.")

    def test_gdpr_request_audit_event_mapping(self):
        """Portability/rectification requests log their own event types."""
        partner = self.env.ref("base.partner_admin")
        Log = self.env["platform.audit.log"]
        before = Log.search_count([("event_type", "=", "gdpr_portability")])
        self.env["platform.gdpr.request"].create(
            {
                "partner_id": partner.id,
                "request_type": "portability",
            }
        )
        after = Log.search_count([("event_type", "=", "gdpr_portability")])
        self.assertEqual(
            after, before + 1, "Portability request must log gdpr_portability, not gdpr_delete."
        )
