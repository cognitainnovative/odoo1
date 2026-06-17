"""Tests for bank statement parsers (CSV, MT940, CAMT.053)."""

from odoo.tests.common import TransactionCase


class TestBankParsers(TransactionCase):
    """Unit tests for the bank parser library (no DB needed, but uses TransactionCase for imports)."""

    def setUp(self):
        super().setUp()
        from odoo.addons.custom_accounting_basic.lib.bank_parsers import (
            parse_camt053,
            parse_csv,
            parse_mt940,
        )

        self.parse_csv = parse_csv
        self.parse_mt940 = parse_mt940
        self.parse_camt053 = parse_camt053

    # ── CSV ──────────────────────────────────────────────────────────────────

    def test_csv_basic(self):
        """Parse a minimal 3-column CSV."""
        csv_data = b"date,description,amount\n2025-01-15,Invoice payment,1250.00\n2025-01-16,Office supplies,-89.50"
        txns = self.parse_csv(csv_data)
        self.assertEqual(len(txns), 2)
        self.assertAlmostEqual(txns[0]["amount"], 1250.0)
        self.assertAlmostEqual(txns[1]["amount"], -89.50)

    def test_csv_semicolon(self):
        """Parse semicolon-delimited CSV."""
        csv_data = b"Datum;Omschrijving;Bedrag\n15-01-2025;Betaling factuur;1250,00\n16-01-2025;Kantoorspullen;-89,50"
        txns = self.parse_csv(csv_data, delimiter=";")
        self.assertEqual(len(txns), 2)

    def test_csv_skips_zero_amount(self):
        """Rows with zero amount are skipped."""
        csv_data = b"date,description,amount\n2025-01-15,zero row,0\n2025-01-16,Real payment,100.00"
        txns = self.parse_csv(csv_data)
        self.assertEqual(len(txns), 1)
        self.assertAlmostEqual(txns[0]["amount"], 100.0)

    def test_csv_dedup_id_stable(self):
        """Unique import ID is deterministic for same data."""
        csv_data = b"date,description,amount\n2025-01-15,Test,100.00"
        txns1 = self.parse_csv(csv_data)
        txns2 = self.parse_csv(csv_data)
        self.assertEqual(txns1[0]["unique_import_id"], txns2[0]["unique_import_id"])

    def test_csv_european_amount(self):
        """European number format (1.234,56) is parsed correctly."""
        csv_data = b'date,description,amount\n2025-01-15,Test,"1.234,56"'
        txns = self.parse_csv(csv_data)
        self.assertAlmostEqual(txns[0]["amount"], 1234.56)

    # ── MT940 ────────────────────────────────────────────────────────────────

    def test_mt940_basic(self):
        """Parse a minimal MT940 transaction."""
        mt940_data = (
            ":20:STARTUMS\n"
            ":25:NL91ABNA0417164300\n"
            ":28C:00001/001\n"
            ":60F:C250101EUR10000,00\n"
            ":61:2501150115C1250,00NTRFREF123//REF123\n"
            ":86:/NAME/Test Supplier/IBAN/NL02ABNA0123456789\n"
            ":62F:C250115EUR11250,00\n"
        )
        txns = self.parse_mt940(mt940_data.encode())
        self.assertEqual(len(txns), 1)
        self.assertAlmostEqual(txns[0]["amount"], 1250.0, places=0)
        self.assertIn("Test Supplier", txns[0]["partner_name"])

    def test_mt940_debit_is_negative(self):
        """Debit transactions have negative amounts."""
        mt940_data = (
            ":20:TEST\n"
            ":25:NL91ABNA0417164300\n"
            ":61:2501150115D500,00NTRFTEST/\n"
            ":86:Test debit\n"
        )
        txns = self.parse_mt940(mt940_data.encode())
        self.assertEqual(len(txns), 1)
        self.assertLess(txns[0]["amount"], 0)

    def test_mt940_empty_returns_empty(self):
        """Empty MT940 returns empty list."""
        txns = self.parse_mt940(b"no transactions here")
        self.assertEqual(txns, [])

    # ── CAMT.053 ─────────────────────────────────────────────────────────────

    def test_camt053_basic(self):
        """Parse a minimal CAMT.053 XML."""
        camt_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Ntry>
        <Amt Ccy="EUR">1500.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2025-01-15</Dt></BookgDt>
        <NtryDtls>
          <TxDtls>
            <Refs><EndToEndId>REF20250115001</EndToEndId></Refs>
          </TxDtls>
        </NtryDtls>
        <AddtlNtryInf>Invoice INV/2025/001 payment</AddtlNtryInf>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""
        txns = self.parse_camt053(camt_xml)
        self.assertEqual(len(txns), 1)
        self.assertAlmostEqual(txns[0]["amount"], 1500.0)
        # payment_ref should be either the AddtlNtryInf or the EndToEndId
        self.assertTrue(txns[0]["payment_ref"], "payment_ref should be non-empty")

    def test_camt053_debit(self):
        """DBIT entries have negative amounts."""
        camt_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt><Stmt>
    <Ntry>
      <Amt Ccy="EUR">200.00</Amt>
      <CdtDbtInd>DBIT</CdtDbtInd>
      <BookgDt><Dt>2025-01-16</Dt></BookgDt>
    </Ntry>
  </Stmt></BkToCstmrStmt>
</Document>"""
        txns = self.parse_camt053(camt_xml)
        self.assertEqual(len(txns), 1)
        self.assertLess(txns[0]["amount"], 0)

    def test_camt053_invalid_xml_returns_empty(self):
        """Invalid XML returns empty list (graceful degradation)."""
        txns = self.parse_camt053(b"not xml at all")
        self.assertEqual(txns, [])
