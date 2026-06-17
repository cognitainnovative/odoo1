from unittest.mock import MagicMock, patch

import psycopg2.errors
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestPlatformPackage(TransactionCase):
    """Tests for platform.package model."""

    def test_packages_seeded(self):
        """Verify all 13 predefined packages exist."""
        packages = self.env["platform.package"].search([])
        codes = packages.mapped("code")
        expected = {
            "crm_base",
            "finance_basic",
            "finance_advanced",
            "hrm",
            "payroll_nl",
            "inventory",
            "rental",
            "helpdesk",
            "planning",
            "ai_chat",
            "ai_voice",
            "social_media",
            "full_suite",
        }
        self.assertEqual(set(codes), expected, "All 13 predefined packages must exist.")

    def test_package_code_unique(self):
        """Package codes must be unique — raises UniqueViolation on duplicate."""
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.env["platform.package"].create({"name": "Duplicate", "code": "crm_base"})


class TestPlatformSubscription(TransactionCase):
    """Tests for platform.subscription state machine and access check."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.package = self.env["platform.package"].search([("code", "=", "crm_base")], limit=1)
        # Clean slate: platform.subscription.create() calls registry.clear_cache(),
        # which under the full-suite runner can let a subscription created by a
        # prior test survive the per-test rollback. Remove ALL subscriptions for
        # this company so every test is deterministic regardless of ordering.
        # (The other test classes in this file already do this.)
        self.env["platform.subscription"].search([("company_id", "=", self.company.id)]).unlink()

    def _make_sub(self, state="trial", **kwargs):
        vals = {
            "company_id": self.company.id,
            "package_id": self.package.id,
            "state": state,
        }
        vals.update(kwargs)
        return self.env["platform.subscription"].create(vals)

    def test_trial_is_active(self):
        """A new trial subscription is active."""
        sub = self._make_sub(state="trial")
        self.assertTrue(sub.is_active, "Trial subscription should be active.")

    def test_activate_transition(self):
        """Trial → Active via action_activate."""
        sub = self._make_sub(state="trial")
        sub.action_activate()
        self.assertEqual(sub.state, "active")
        self.assertTrue(sub.is_active)

    def test_expire_transition(self):
        """Active → Expired via action_expire."""
        sub = self._make_sub(state="active")
        sub.action_expire()
        self.assertEqual(sub.state, "expired")
        self.assertFalse(sub.is_active)

    def test_cancel_transition(self):
        """Active → Cancelled via action_cancel."""
        sub = self._make_sub(state="active")
        sub.action_cancel()
        self.assertEqual(sub.state, "cancelled")
        self.assertFalse(sub.is_active)

    def test_reactivate_from_cancelled(self):
        """Cancelled → Active via action_reactivate."""
        sub = self._make_sub(state="cancelled")
        sub.action_reactivate()
        self.assertEqual(sub.state, "active")
        self.assertTrue(sub.is_active)

    def test_is_module_active_no_subscriptions(self):
        """When no subscriptions exist, is_module_active returns True (graceful default)."""
        # Delete any existing subs for this company
        self.env["platform.subscription"].search([("company_id", "=", self.company.id)]).unlink()
        result = self.env["platform.subscription"].is_module_active("crm")
        self.assertTrue(result, "No subscriptions → all modules accessible (graceful default).")

    def test_is_module_active_with_active_sub(self):
        """Active subscription for a package grants access to its module codes."""
        self._make_sub(state="active")
        self.package.module_codes = "crm"
        result = self.env["platform.subscription"].is_module_active("crm")
        self.assertTrue(result)

    def test_is_module_active_expired_denies_access(self):
        """Expired subscription denies access."""
        self._make_sub(state="expired")
        self.package.module_codes = "crm"
        result = self.env["platform.subscription"].is_module_active("crm")
        self.assertFalse(result, "Expired subscription should deny access.")

    def test_full_suite_grants_any_module(self):
        """Full Suite subscription grants access to any module code."""
        full = self.env["platform.package"].search([("code", "=", "full_suite")], limit=1)
        self.env["platform.subscription"].create(
            {
                "company_id": self.company.id,
                "package_id": full.id,
                "state": "active",
            }
        )
        for code in ("crm", "payroll_nl", "inventory", "ai_voice"):
            self.assertTrue(
                self.env["platform.subscription"].is_module_active(code),
                f"Full Suite should grant access to '{code}'.",
            )

    def test_company_package_unique_constraint(self):
        """Cannot create two subscriptions for the same company+package."""
        self._make_sub(state="trial")
        with self.assertRaises(psycopg2.errors.UniqueViolation), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self._make_sub(state="trial")

    def test_license_key_generated_on_activation(self):
        """License key is auto-generated when a subscription is activated."""
        sub = self._make_sub(state="trial")
        self.assertFalse(sub.license_key, "License key should not exist before activation.")
        sub.action_activate()
        self.assertTrue(sub.license_key, "License key must be set after activation.")
        self.assertTrue(sub.license_key.startswith("PLT-"), "License key must start with 'PLT-'.")

    def test_license_key_stable_on_reactivation(self):
        """License key generated on first activation is kept on reactivation."""
        sub = self._make_sub(state="trial")
        sub.action_activate()
        first_key = sub.license_key
        sub.action_cancel()
        sub.action_reactivate()
        self.assertEqual(sub.license_key, first_key, "License key must not change on reactivation.")

    def test_data_retention_on_deactivation(self):
        """Transitioning to inactive triggers _on_module_deactivated — no data deleted."""
        sub = self._make_sub(state="active")
        self.package.module_codes = "crm"
        # Expire the subscription — data retention hook must fire without error
        sub.action_expire()
        self.assertFalse(sub.is_active)
        # The subscription record itself must still exist (archived, not deleted)
        still_exists = self.env["platform.subscription"].search([("id", "=", sub.id)], limit=1)
        self.assertTrue(still_exists, "Subscription record must be retained after expiry.")


class TestMenuGating(TransactionCase):
    """Tests proving inactive-module menus are excluded from visible menu set."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.package = self.env["platform.package"].search([("code", "=", "crm_base")], limit=1)
        # Ensure a clean slate: remove any pre-existing subs for this company
        self.env["platform.subscription"].search([("company_id", "=", self.company.id)]).unlink()

    def _make_sub(self, state="active"):
        sub = self.env["platform.subscription"].create(
            {
                "company_id": self.company.id,
                "package_id": self.package.id,
                "state": state,
            }
        )
        self.package.module_codes = "crm"
        return sub

    def _make_gate(self, module_code, menu):
        return self.env["platform.menu.gate"].create(
            {
                "module_code": module_code,
                "menu_id": menu.id,
            }
        )

    def _dummy_menu(self):
        act = self.env["ir.actions.act_url"].create({"name": "Test", "url": "#"})
        return self.env["ir.ui.menu"].create(
            {
                "name": "Test Gated Menu",
                "sequence": 999,
                "action": f"ir.actions.act_url,{act.id}",
            }
        )

    def test_active_subscription_menu_visible(self):
        """Menu linked to an active subscription's module is in the visible set."""
        menu = self._dummy_menu()
        self._make_sub(state="active")
        self._make_gate("crm", menu)
        visible = self.env["ir.ui.menu"]._visible_menu_ids()
        self.assertIn(menu.id, visible, "Menu must be visible when subscription is active.")

    def test_expired_subscription_menu_hidden(self):
        """Menu linked to an expired subscription's module is excluded from visible set."""
        menu = self._dummy_menu()
        self._make_sub(state="expired")
        self._make_gate("crm", menu)
        visible = self.env["ir.ui.menu"]._visible_menu_ids()
        self.assertNotIn(menu.id, visible, "Menu must be hidden when subscription is expired.")

    def test_cancelled_subscription_menu_hidden(self):
        """Menu linked to a cancelled subscription is excluded."""
        menu = self._dummy_menu()
        self._make_sub(state="cancelled")
        self._make_gate("crm", menu)
        visible = self.env["ir.ui.menu"]._visible_menu_ids()
        self.assertNotIn(menu.id, visible, "Menu must be hidden when subscription is cancelled.")

    def test_no_subscriptions_all_menus_visible(self):
        """Graceful default: no subscriptions → gated menu still visible."""
        menu = self._dummy_menu()
        self._make_gate("crm", menu)
        # No subscription created → graceful default returns True
        visible = self.env["ir.ui.menu"]._visible_menu_ids()
        self.assertIn(menu.id, visible, "With no subscriptions, menus must default to visible.")


class TestRouteGating(TransactionCase):
    """Tests proving require_module decorator returns 403 when module inactive."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.package = self.env["platform.package"].search([("code", "=", "crm_base")], limit=1)
        self.env["platform.subscription"].search([("company_id", "=", self.company.id)]).unlink()

    def _make_sub(self, state):
        sub = self.env["platform.subscription"].create(
            {
                "company_id": self.company.id,
                "package_id": self.package.id,
                "state": state,
            }
        )
        self.package.module_codes = "crm"
        return sub

    def test_require_module_passes_when_active(self):
        """require_module allows through when subscription is active."""
        from odoo.addons.custom_subscription_modules.controllers.gate import require_module

        self._make_sub(state="active")
        call_log = []

        @require_module("crm")
        def fake_handler(*args, **kwargs):
            call_log.append("called")
            return "ok"

        mock_env = self.env
        mock_req = MagicMock()
        mock_req.env = mock_env
        with patch(
            "odoo.addons.custom_subscription_modules.controllers.gate.request",
            new=mock_req,
        ):
            result = fake_handler()

        self.assertEqual(result, "ok", "Handler must be called when module is active.")
        self.assertEqual(call_log, ["called"])

    def test_require_module_blocks_when_expired(self):
        """require_module returns 403 when subscription is expired."""
        from odoo.addons.custom_subscription_modules.controllers.gate import require_module

        self._make_sub(state="expired")
        call_log = []

        @require_module("crm")
        def fake_handler(*args, **kwargs):
            call_log.append("called")
            return "ok"

        mock_env = self.env
        mock_req = MagicMock()
        mock_req.env = mock_env
        mock_req.make_json_response.return_value = {"status": 403}
        with patch(
            "odoo.addons.custom_subscription_modules.controllers.gate.request",
            new=mock_req,
        ):
            fake_handler()

        self.assertEqual(call_log, [], "Handler must NOT be called when module is inactive.")
        mock_req.make_json_response.assert_called_once()
        call_kwargs = mock_req.make_json_response.call_args
        self.assertEqual(call_kwargs.kwargs.get("status") or call_kwargs.args[1], 403)
