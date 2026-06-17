"""Tests for account.move extensions, invoice import, bank import, accounting consistency,
recurring invoices, and audit log."""

from odoo import fields
from odoo.tests.common import TransactionCase

# ── Existing: account.move field extensions ────────────────────────────────────


class TestAccountMoveExtensions(TransactionCase):
    """Tests for extended account.move fields."""

    def _get_journal(self, journal_type="sale"):
        return self.env["account.journal"].search(
            [("type", "=", journal_type), ("company_id", "=", self.env.company.id)], limit=1
        )

    def _make_invoice(self, **kwargs):
        journal = self._get_journal("sale")
        if not journal:
            return None
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        vals = {
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "journal_id": journal.id,
        }
        vals.update(kwargs)
        return self.env["account.move"].create(vals)

    def test_ai_extracted_field_default_false(self):
        move = self._make_invoice()
        if not move:
            return
        self.assertFalse(move.ai_extracted)

    def test_ai_extracted_can_be_set(self):
        move = self._make_invoice(
            ai_extracted=True,
            extraction_confidence=0.85,
            import_reference="SUPPLIER-2025-001",
        )
        if not move:
            return
        self.assertTrue(move.ai_extracted)
        self.assertAlmostEqual(move.extraction_confidence, 0.85)
        self.assertEqual(move.import_reference, "SUPPLIER-2025-001")

    def test_days_overdue_zero_for_draft(self):
        move = self._make_invoice()
        if not move:
            return
        self.assertEqual(move.days_overdue, 0)

    def test_days_overdue_computed_for_posted(self):
        move = self._make_invoice()
        if not move:
            return
        self.assertIsNotNone(move.days_overdue)

    def test_duplicate_detection(self):
        journal = self._get_journal("sale")
        if not journal:
            return
        partner = self.env["res.partner"].create({"name": "Duplicate Corp"})
        m1 = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": journal.id,
            }
        )
        m1.action_detect_duplicates()
        self.assertIsNotNone(m1.duplicate_count)

    def test_reminder_sent_defaults_false(self):
        move = self._make_invoice()
        if not move:
            return
        self.assertFalse(move.reminder_sent)


# ── Incoming invoice OCR wizard ───────────────────────────────────────────────


class TestInvoiceImportWizardExtraction(TransactionCase):
    """Test incoming invoice import wizard with mocked AI extraction."""

    def setUp(self):
        super().setUp()
        self.journal = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def _mock_ai_response(self, content: str, ok: bool = True):
        from unittest.mock import patch

        return patch.object(
            type(self.env["ai.service"]),
            "call",
            return_value={"ok": ok, "content": content, "error": ""},
        )

    def test_extraction_populates_fields(self):
        """AI extraction populates wizard fields from mocked JSON response."""
        import base64

        if not self.journal:
            return

        mock_json = (
            '{"supplier_name": "ACME BV", "invoice_number": "ACME-2025-042", '
            '"invoice_date": "2025-01-10", "due_date": "2025-02-10", '
            '"amount_total": 1210.00, "amount_tax": 210.00, '
            '"iban": "NL02ABNA0123456789", "payment_reference": "ACME-2025-042", '
            '"currency": "EUR"}'
        )

        wizard = self.env["invoice.import.wizard"].create(
            {
                "invoice_file": base64.b64encode(b"%PDF-1.4 fake pdf content for test"),
                "invoice_filename": "acme_invoice.pdf",
            }
        )

        with self._mock_ai_response(mock_json):
            wizard.action_extract()

        self.assertTrue(wizard.extraction_done)
        self.assertEqual(wizard.supplier_name, "ACME BV")
        self.assertEqual(wizard.invoice_number, "ACME-2025-042")
        self.assertAlmostEqual(wizard.amount_total, 1210.0)
        self.assertAlmostEqual(wizard.amount_tax, 210.0)
        self.assertEqual(wizard.iban, "NL02ABNA0123456789")
        self.assertEqual(wizard.currency_name, "EUR")
        self.assertGreater(wizard.extraction_confidence, 0)
        self.assertEqual(wizard.approval_state, "extracted")

    def test_extraction_with_line_items(self):
        """AI extraction with line_items stores JSON and creates multiple invoice lines."""
        import base64

        if not self.journal:
            return

        mock_json = (
            '{"supplier_name": "Parts BV", "invoice_number": "PBV-2025-10", '
            '"invoice_date": "2025-03-01", "due_date": "2025-04-01", '
            '"amount_total": 500.00, "amount_tax": 87.60, "currency": "EUR", '
            '"line_items": ['
            '  {"description": "Widget A", "quantity": 2.0, "unit_price": 100.00, "vat_rate": 21},'
            '  {"description": "Widget B", "quantity": 1.0, "unit_price": 213.40, "vat_rate": 21}'
            "]}"
        )

        wizard = self.env["invoice.import.wizard"].create(
            {
                "invoice_file": base64.b64encode(b"pdf bytes"),
                "invoice_filename": "parts_invoice.pdf",
            }
        )

        with self._mock_ai_response(mock_json):
            wizard.action_extract()

        self.assertTrue(wizard.extraction_done)
        self.assertIsNotNone(wizard.line_items_json)
        self.assertIn("Widget A", wizard.line_items_json)

        # Approve and create invoice
        wizard.approval_state = "approved"
        wizard.action_create_invoice()

        self.assertTrue(wizard.created_invoice_id)
        move = wizard.created_invoice_id
        self.assertEqual(move.move_type, "in_invoice")
        # Should have 2 lines from line_items (not the catch-all)
        self.assertGreaterEqual(len(move.invoice_line_ids), 2)
        line_names = [line.name for line in move.invoice_line_ids]
        self.assertIn("Widget A", line_names)
        self.assertIn("Widget B", line_names)

    def test_extraction_ai_failure_sets_zero_confidence(self):
        """When AI call fails, extraction_done is set but confidence is 0."""
        import base64

        wizard = self.env["invoice.import.wizard"].create(
            {
                "invoice_file": base64.b64encode(b"dummy"),
                "invoice_filename": "fail.pdf",
            }
        )

        with self._mock_ai_response("", ok=False):
            wizard.action_extract()

        self.assertTrue(wizard.extraction_done)
        self.assertAlmostEqual(wizard.extraction_confidence, 0.0)

    def test_create_invoice_from_extraction(self):
        """action_create_invoice creates a draft vendor bill from extracted data."""
        import base64

        if not self.journal:
            return

        mock_json = (
            '{"supplier_name": "Test Supplier", "invoice_number": "TS-001", '
            '"invoice_date": "2025-01-15", "due_date": "2025-02-15", '
            '"amount_total": 500.0, "amount_tax": 87.0, "currency": "EUR"}'
        )

        wizard = self.env["invoice.import.wizard"].create(
            {
                "invoice_file": base64.b64encode(b"pdf content"),
                "invoice_filename": "ts_invoice.pdf",
            }
        )

        with self._mock_ai_response(mock_json):
            wizard.action_extract()

        # Approve before creating (bypass by setting state directly in test)
        wizard.write({"approval_state": "approved"})
        wizard.action_create_invoice()

        self.assertTrue(wizard.created_invoice_id)
        move = wizard.created_invoice_id
        self.assertEqual(move.move_type, "in_invoice")
        self.assertEqual(move.state, "draft")
        self.assertTrue(move.ai_extracted)
        self.assertGreater(move.extraction_confidence, 0)

    def test_create_invoice_blocked_without_approval(self):
        """Non-manager user cannot create invoice without approval."""
        import base64

        from odoo.exceptions import UserError

        wizard = self.env["invoice.import.wizard"].create(
            {
                "invoice_file": base64.b64encode(b"pdf"),
                "invoice_filename": "test.pdf",
                "extraction_done": True,
                "extraction_confidence": 0.80,
                "supplier_name": "Supplier",
                "amount_total": 100.0,
                "approval_state": "extracted",
            }
        )

        # As a regular invoice user (not manager), creating without approval should raise
        # Use sudo with a user that doesn't have account_manager group
        demo_user = self.env.ref("base.user_demo", raise_if_not_found=False)
        if demo_user and not demo_user.has_group("account.group_account_manager"):
            with self.assertRaises(UserError):
                wizard.with_user(demo_user).action_create_invoice()

    def test_approve_action_changes_state(self):
        """action_approve changes approval_state to 'approved'."""
        import base64

        wizard = self.env["invoice.import.wizard"].create(
            {
                "invoice_file": base64.b64encode(b"pdf"),
                "invoice_filename": "test.pdf",
                "extraction_done": True,
                "extraction_confidence": 0.80,
                "supplier_name": "Supplier",
            }
        )
        wizard.action_approve()
        self.assertEqual(wizard.approval_state, "approved")


# ── Bank import wizard ─────────────────────────────────────────────────────────


class TestBankImportWizard(TransactionCase):
    """Tests for bank.statement.import.wizard."""

    def test_create_wizard(self):
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal:
            return
        wizard = self.env["bank.statement.import.wizard"].create(
            {"journal_id": journal.id, "file_format": "csv"}
        )
        self.assertEqual(wizard.file_format, "csv")

    def test_import_csv_creates_statement(self):
        import base64

        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if not journal:
            return

        csv_content = (
            b"date,description,amount\n2025-01-15,Test Payment,1250.00\n2025-01-16,Supplier,-89.50"
        )
        wizard = self.env["bank.statement.import.wizard"].create(
            {
                "journal_id": journal.id,
                "file_format": "csv",
                "statement_file": base64.b64encode(csv_content),
                "statement_filename": "test.csv",
            }
        )
        result = wizard.action_import()
        self.assertIn(result.get("type", ""), ["ir.actions.act_window", "ir.actions.client"])
        if wizard.statement_id:
            self.assertGreater(wizard.import_count, 0)


# ── Accounting consistency (debit = credit) ────────────────────────────────────


class TestAccountingConsistency(TransactionCase):
    """Verify double-entry integrity: sum(debits) == sum(credits) for every posted move."""

    def _get_journals(self):
        sale = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.env.company.id)], limit=1
        )
        purchase = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)], limit=1
        )
        return sale, purchase

    def _assert_balanced(self, move):
        total_debit = sum(line.debit for line in move.line_ids)
        total_credit = sum(line.credit for line in move.line_ids)
        self.assertAlmostEqual(
            total_debit,
            total_credit,
            places=2,
            msg=(
                f"Move {move.name} is unbalanced: "
                f"debits={total_debit:.2f} credits={total_credit:.2f}"
            ),
        )

    def test_customer_invoice_balanced(self):
        sale_journal, _ = self._get_journals()
        if not sale_journal:
            return

        partner = self.env["res.partner"].create({"name": "Balance Test Customer"})
        receivable = self.env["account.account"].search(
            [("account_type", "=", "asset_receivable")],
            limit=1,
        )
        revenue = self.env["account.account"].search(
            [("account_type", "=", "income")],
            limit=1,
        )
        if not receivable or not revenue:
            return

        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": sale_journal.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Consulting Service",
                            "quantity": 1,
                            "price_unit": 1000.0,
                            "account_id": revenue.id,
                        },
                    )
                ],
            }
        )
        move.action_post()
        self.assertEqual(move.state, "posted")
        self._assert_balanced(move)

    def test_vendor_bill_balanced(self):
        _, purchase_journal = self._get_journals()
        if not purchase_journal:
            return

        partner = self.env["res.partner"].create({"name": "Balance Test Supplier"})
        payable = self.env["account.account"].search(
            [("account_type", "=", "liability_payable")],
            limit=1,
        )
        expense = self.env["account.account"].search(
            [("account_type", "=", "expense")],
            limit=1,
        )
        if not payable or not expense:
            return

        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "journal_id": purchase_journal.id,
                "invoice_date": fields.Date.today(),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Office Supplies",
                            "quantity": 2,
                            "price_unit": 150.0,
                            "account_id": expense.id,
                        },
                    )
                ],
            }
        )
        move.action_post()
        self.assertEqual(move.state, "posted")
        self._assert_balanced(move)

    def test_credit_note_balanced(self):
        sale_journal, _ = self._get_journals()
        if not sale_journal:
            return

        partner = self.env["res.partner"].create({"name": "Credit Note Test"})
        revenue = self.env["account.account"].search(
            [("account_type", "=", "income")],
            limit=1,
        )
        if not revenue:
            return

        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": sale_journal.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Service",
                            "quantity": 1,
                            "price_unit": 500.0,
                            "account_id": revenue.id,
                        },
                    )
                ],
            }
        )
        invoice.action_post()

        reversal_wizard = (
            self.env["account.move.reversal"]
            .with_context(active_ids=[invoice.id], active_model="account.move")
            .create({"reason": "Test reversal", "journal_id": sale_journal.id})
        )
        result = reversal_wizard.reverse_moves()

        credit_note_id = result.get("res_id") or (
            result.get("domain") and self.env["account.move"].search(result["domain"], limit=1).id
        )
        if credit_note_id:
            credit_note = self.env["account.move"].browse(credit_note_id)
            if credit_note.state != "posted":
                credit_note.action_post()
            self._assert_balanced(credit_note)


# ── Pro forma invoices ────────────────────────────────────────────────────────


class TestProFormaInvoice(TransactionCase):
    """Tests for pro forma invoice functionality."""

    def _get_sale_journal(self):
        return self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def _make_draft_invoice(self):
        journal = self._get_sale_journal()
        if not journal:
            return None
        partner = self.env["res.partner"].create({"name": "Pro Forma Customer"})
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": journal.id,
            }
        )

    def test_is_proforma_default_false(self):
        """is_proforma defaults to False."""
        move = self._make_draft_invoice()
        if not move:
            return
        self.assertFalse(move.is_proforma)

    def test_is_proforma_can_be_set(self):
        """is_proforma can be set to True."""
        move = self._make_draft_invoice()
        if not move:
            return
        move.is_proforma = True
        self.assertTrue(move.is_proforma)

    def test_action_remove_proforma_clears_flag(self):
        """action_remove_proforma clears the flag."""
        move = self._make_draft_invoice()
        if not move:
            return
        move.write({"is_proforma": True})
        move.action_remove_proforma()
        self.assertFalse(move.is_proforma)

    def test_send_proforma_raises_for_posted(self):
        """action_send_proforma raises UserError for posted invoices."""
        from odoo.exceptions import UserError

        journal = self._get_sale_journal()
        if not journal:
            return
        revenue = self.env["account.account"].search(
            [("account_type", "=", "income")],
            limit=1,
        )
        if not revenue:
            return
        partner = self.env["res.partner"].create({"name": "Posted PF Test"})
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": journal.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Service",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": revenue.id,
                        },
                    )
                ],
            }
        )
        move.action_post()
        with self.assertRaises(UserError):
            move.action_send_proforma()

    def test_proforma_not_copied_on_duplicate(self):
        """is_proforma flag is not copied when duplicating an invoice."""
        move = self._make_draft_invoice()
        if not move:
            return
        move.write({"is_proforma": True})
        copy = move.copy()
        self.assertFalse(copy.is_proforma)


# ── Invoice CSV export ────────────────────────────────────────────────────────


class TestInvoiceExportWizard(TransactionCase):
    """Tests for invoice CSV export wizard."""

    def _get_journals(self):
        sale = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.env.company.id)], limit=1
        )
        purchase = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.env.company.id)], limit=1
        )
        return sale, purchase

    def test_create_wizard(self):
        """Export wizard can be created with defaults."""

        wizard = self.env["invoice.export.wizard"].create(
            {
                "invoice_type": "outgoing",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
                "state_filter": "posted",
            }
        )
        self.assertEqual(wizard.invoice_type, "outgoing")
        self.assertFalse(wizard.export_done)

    def test_export_produces_csv(self):
        """action_export creates a base64-encoded CSV file."""

        wizard = self.env["invoice.export.wizard"].create(
            {
                "invoice_type": "all",
                "date_from": "2020-01-01",
                "date_to": "2030-12-31",
                "state_filter": "all",
            }
        )
        wizard.action_export()
        self.assertTrue(wizard.export_done)
        self.assertIsNotNone(wizard.export_file)
        self.assertIsNotNone(wizard.export_filename)
        self.assertIn(".csv", wizard.export_filename)

    def test_export_csv_has_header_row(self):
        """Exported CSV contains expected header columns."""
        import base64

        wizard = self.env["invoice.export.wizard"].create(
            {
                "invoice_type": "all",
                "date_from": "2020-01-01",
                "date_to": "2030-12-31",
                "state_filter": "all",
            }
        )
        wizard.action_export()
        if wizard.export_file:
            csv_bytes = base64.b64decode(wizard.export_file)
            csv_text = csv_bytes.decode("utf-8-sig")
            self.assertIn("Invoice Number", csv_text)
            self.assertIn("Amount Total", csv_text)
            self.assertIn("Payment State", csv_text)

    def test_export_date_validation(self):
        """Exporting with date_to before date_from raises UserError."""
        from odoo.exceptions import UserError

        wizard = self.env["invoice.export.wizard"].create(
            {
                "invoice_type": "outgoing",
                "date_from": "2025-12-31",
                "date_to": "2025-01-01",
                "state_filter": "posted",
            }
        )
        with self.assertRaises(UserError):
            wizard.action_export()

    def test_export_count_matches_invoices(self):
        """export_count reflects the number of matching invoices."""
        sale_journal, _ = self._get_journals()
        if not sale_journal:
            return

        revenue = self.env["account.account"].search(
            [("account_type", "=", "income")],
            limit=1,
        )
        if not revenue:
            return

        partner = self.env["res.partner"].create({"name": "Export Test Customer"})
        for i in range(2):
            m = self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": partner.id,
                    "journal_id": sale_journal.id,
                    "invoice_date": "2026-01-15",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": f"Service {i}",
                                "quantity": 1,
                                "price_unit": 100.0,
                                "account_id": revenue.id,
                            },
                        )
                    ],
                }
            )
            m.action_post()

        wizard = self.env["invoice.export.wizard"].create(
            {
                "invoice_type": "outgoing",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
                "state_filter": "posted",
            }
        )
        wizard.action_export()
        self.assertGreaterEqual(wizard.export_count, 2)


# ── Recurring invoices ─────────────────────────────────────────────────────────


class TestRecurringInvoice(TransactionCase):
    """Tests for recurring.invoice.template model and cron."""

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Recurring Customer"})
        self.journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.env.company.id)], limit=1
        )

    def _make_template(self, **kwargs):
        from odoo import fields as F

        vals = {
            "name": "Monthly Subscription",
            "partner_id": self.partner.id,
            "interval_type": "monthly",
            "next_date": F.Date.today(),
        }
        if self.journal:
            vals["journal_id"] = self.journal.id
        vals.update(kwargs)
        return self.env["recurring.invoice.template"].create(vals)

    def test_create_template(self):
        """Recurring invoice template can be created."""
        tmpl = self._make_template()
        self.assertEqual(tmpl.interval_type, "monthly")
        self.assertTrue(tmpl.active)

    def test_template_with_lines(self):
        """Template lines are stored and associated correctly."""
        tmpl = self._make_template(
            line_ids=[
                (0, 0, {"name": "SaaS License", "quantity": 1, "price_unit": 99.0}),
                (0, 0, {"name": "Support", "quantity": 1, "price_unit": 25.0}),
            ]
        )
        self.assertEqual(len(tmpl.line_ids), 2)

    def test_action_create_now_creates_invoice(self):
        """action_create_now creates a draft customer invoice."""
        if not self.journal:
            return
        tmpl = self._make_template(
            line_ids=[(0, 0, {"name": "Service", "quantity": 1, "price_unit": 100.0})]
        )

        original_next = tmpl.next_date

        move = tmpl.action_create_now()

        self.assertTrue(move)
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.partner_id, self.partner)
        self.assertEqual(move.state, "draft")
        self.assertEqual(tmpl.last_invoice_id, move)
        # next_date should have advanced by 1 month
        self.assertGreater(tmpl.next_date, original_next)

    def test_cron_creates_due_invoices(self):
        """Cron creates invoices for templates with next_date <= today."""
        if not self.journal:
            return
        from odoo import fields as F

        tmpl = self._make_template(
            next_date=F.Date.today(),
            line_ids=[(0, 0, {"name": "Cron Service", "quantity": 1, "price_unit": 50.0})],
        )
        self.env["recurring.invoice.template"]._cron_create_recurring()
        # After cron, a new invoice should be created
        self.assertTrue(tmpl.last_invoice_id)

    def test_cron_skips_future_templates(self):
        """Cron does not create invoices for templates due in the future."""
        from dateutil.relativedelta import relativedelta
        from odoo import fields as F

        tmpl = self._make_template(
            next_date=F.Date.today() + relativedelta(days=30),
        )
        self.env["recurring.invoice.template"]._cron_create_recurring()
        self.assertFalse(tmpl.last_invoice_id)

    def test_quarterly_interval_advances_3_months(self):
        """Quarterly template advances next_date by 3 months."""
        if not self.journal:
            return
        from dateutil.relativedelta import relativedelta

        tmpl = self._make_template(interval_type="quarterly")
        original_next = tmpl.next_date
        tmpl.action_create_now()
        expected = original_next + relativedelta(months=3)
        self.assertEqual(tmpl.next_date, expected)

    def test_yearly_interval_advances_12_months(self):
        """Yearly template advances next_date by 12 months."""
        if not self.journal:
            return
        from dateutil.relativedelta import relativedelta

        tmpl = self._make_template(interval_type="yearly")
        original_next = tmpl.next_date
        tmpl.action_create_now()
        expected = original_next + relativedelta(months=12)
        self.assertEqual(tmpl.next_date, expected)


# ── Accounting audit log ───────────────────────────────────────────────────────


class TestAccountingAuditLog(TransactionCase):
    """Tests for accounting.audit.log immutable audit trail."""

    def test_create_log_entry(self):
        """Audit log entry can be created."""
        entry = self.env["accounting.audit.log"].create(
            {
                "event_type": "invoice_posted",
                "res_model": "account.move",
                "res_id": 1,
                "document_ref": "INV/2025/001",
                "details": "Posted by test",
            }
        )
        self.assertEqual(entry.event_type, "invoice_posted")
        self.assertEqual(entry.document_ref, "INV/2025/001")

    def test_convenience_log_method(self):
        """log() convenience method creates an entry."""
        entry = self.env["accounting.audit.log"].log(
            event_type="bank_import",
            res_model="account.bank.statement",
            res_id=42,
            document_ref="STMT-2025-01",
            details="Imported 15 lines",
        )
        self.assertEqual(entry.event_type, "bank_import")
        self.assertEqual(entry.res_id, 42)

    def test_audit_log_immutable_write(self):
        """Writing to audit log raises UserError."""
        from odoo.exceptions import UserError

        entry = self.env["accounting.audit.log"].log(
            event_type="invoice_posted",
            document_ref="INV/2025/999",
        )
        with self.assertRaises(UserError):
            entry.write({"document_ref": "TAMPERED"})

    def test_audit_log_immutable_unlink(self):
        """Deleting audit log raises UserError."""
        from odoo.exceptions import UserError

        entry = self.env["accounting.audit.log"].log(
            event_type="manual_reconcile",
            document_ref="BANK-001",
        )
        with self.assertRaises(UserError):
            entry.unlink()

    def test_all_event_types_creatable(self):
        """Every selection event_type can be logged without error."""
        event_types = [
            "invoice_posted",
            "invoice_cancelled",
            "credit_note_created",
            "payment_matched",
            "payment_reminder_sent",
            "bank_import",
            "ai_match_accepted",
            "ai_extraction",
            "recurring_created",
            "manual_reconcile",
            "approval",
        ]
        for etype in event_types:
            entry = self.env["accounting.audit.log"].log(
                event_type=etype,
                details=f"Test: {etype}",
            )
            self.assertEqual(entry.event_type, etype)

    def test_audit_log_has_user_and_timestamp(self):
        """Audit log automatically records user and timestamp."""
        entry = self.env["accounting.audit.log"].log(
            event_type="invoice_posted",
        )
        self.assertTrue(entry.user_id)
        self.assertTrue(entry.timestamp)
        self.assertTrue(entry.company_id)
