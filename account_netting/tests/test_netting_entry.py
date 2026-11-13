"""Tests for Net and Post: the netting entry and its reconciliation."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import NettingCommon


@tagged("post_install", "-at_install")
class TestNettingEntry(NettingCommon):
    """Net and Post creates one entry and reconciles the invoice with the bills."""

    def test_bill_smaller_than_invoice(self):
        """A 600 bill against a 1,000 invoice: bill paid, 400 left on the invoice."""
        bill = self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        self._wizard(invoice).action_net_and_post()
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.payment_state, "partial")
        self.assertEqual(invoice.amount_residual, 400.0)
        self.assertEqual(bill.payment_state, "paid")

    def test_entry_in_netting_journal(self):
        """The entry is posted in the netting journal and linked to the invoice."""
        self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        self._wizard(invoice).action_net_and_post()
        entry = invoice.netting_move_id
        self.assertEqual(entry.journal_id, self.netting_journal)
        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.amount_total, 600.0)

    def test_bills_oldest_first_last_partial(self):
        """700 and 500 bills against 1,000: the older is paid, 200 stays on the newer."""
        older = self._bill(700.0, date="2026-10-01")
        newer = self._bill(500.0, date="2026-10-15")
        invoice = self._move("out_invoice", 1000.0)
        self._wizard(invoice).action_net_and_post()
        self.assertEqual(invoice.payment_state, "paid")
        self.assertEqual(older.payment_state, "paid")
        self.assertEqual(newer.amount_residual, 200.0)

    def test_unticked_bill_untouched(self):
        """An unticked bill keeps its full open amount."""
        first = self._bill(300.0, date="2026-10-01")
        second = self._bill(200.0, date="2026-10-02")
        invoice = self._move("out_invoice", 1000.0)
        wizard = self._wizard(invoice)
        wizard.line_ids.filtered(lambda line: line.bill_id == first).selected = False
        wizard.action_net_and_post()
        self.assertEqual(first.amount_residual, 300.0)
        self.assertEqual(second.payment_state, "paid")
        self.assertEqual(invoice.amount_residual, 800.0)

    def test_bill_in_other_currency(self):
        """A bill in another currency is paid in full; the invoice keeps the rest."""
        bill = self._bill(100.0, currency=self._other_currency(0.5))
        bill_company_amount = abs(bill.amount_residual_signed)
        invoice = self._move("out_invoice", 1000.0)
        self._wizard(invoice).action_net_and_post()
        self.assertEqual(bill.payment_state, "paid")
        self.assertAlmostEqual(invoice.amount_residual, 1000.0 - bill_company_amount)

    def test_requires_netting_journal(self):
        """Without a netting journal nothing is posted."""
        self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        wizard = self._wizard(invoice)
        self.company.netting_journal_id = False
        with self.assertRaises(UserError):
            wizard.action_net_and_post()
        self.assertEqual(invoice.state, "draft")

    def test_requires_selected_bill(self):
        """With every bill unticked, Net and Post asks to select one."""
        self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        wizard = self._wizard(invoice)
        wizard.line_ids.selected = False
        with self.assertRaises(UserError):
            wizard.action_net_and_post()
        self.assertEqual(invoice.state, "draft")