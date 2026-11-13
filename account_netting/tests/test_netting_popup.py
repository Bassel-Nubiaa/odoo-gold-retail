"""Tests for the netting popup opened when a customer invoice is confirmed."""
from odoo.tests import tagged

from .common import NettingCommon


@tagged("post_install", "-at_install")
class TestNettingPopup(NettingCommon):
    """The popup lists the partner's open bills; invoices without them post directly."""

    def test_no_open_bills_posts_directly(self):
        """Without open bills, Confirm posts the invoice."""
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))
        self.assertEqual(invoice.state, "posted")

    def test_open_bill_opens_popup(self):
        """With an open bill, Confirm opens the popup and the invoice stays draft."""
        bill = self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        wizard = self._wizard(invoice)
        self.assertEqual(invoice.state, "draft")
        self.assertEqual(wizard.line_ids.bill_id, bill)
        self.assertEqual(wizard.netting_amount, 600.0)

    def test_posting_from_code_unchanged(self):
        """Posting without the Confirm button never opens the popup."""
        self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_only_invoice_partner(self):
        """Bills of other partners are not offered."""
        self._bill(600.0, partner=self.other_partner)
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))

    def test_paid_bill_excluded(self):
        """Fully paid bills are not offered."""
        bill = self._bill(600.0)
        self._pay(bill, 600.0)
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))

    def test_partly_paid_bill_offered_with_open_amount(self):
        """A partly paid bill is offered with its open amount."""
        bill = self._bill(600.0)
        self._pay(bill, 200.0)
        invoice = self._move("out_invoice", 1000.0)
        self.assertEqual(self._wizard(invoice).line_ids.amount_residual, 400.0)

    def test_bill_with_payment_in_process_excluded(self):
        """A bill whose payment is registered but not yet posted is not offered."""
        bill = self._bill(600.0)
        bill.payment_state = "in_payment"
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))

    def test_netting_limited_to_invoice_amount(self):
        """The amount to net never exceeds the invoice amount."""
        self._bill(700.0, date="2026-10-01")
        self._bill(500.0, date="2026-10-15")
        wizard = self._wizard(self._move("out_invoice", 1000.0))
        self.assertEqual(wizard.selected_amount, 1200.0)
        self.assertEqual(wizard.netting_amount, 1000.0)

    def test_bills_oldest_first(self):
        """Bills are listed from the oldest bill date."""
        newer = self._bill(100.0, date="2026-10-20")
        older = self._bill(100.0, date="2026-09-05")
        wizard = self._wizard(self._move("out_invoice", 1000.0))
        self.assertEqual(wizard.line_ids.bill_id.ids, [older.id, newer.id])

    def test_untick_reduces_amount(self):
        """Unticking a bill removes it from the amount to net."""
        self._bill(300.0, date="2026-10-01")
        self._bill(200.0, date="2026-10-02")
        wizard = self._wizard(self._move("out_invoice", 1000.0))
        wizard.line_ids[0].selected = False
        self.assertEqual(wizard.netting_amount, 200.0)

    def test_bill_in_other_currency_offered(self):
        """Bills in another currency are offered, valued in company currency."""
        bill = self._bill(100.0, currency=self._other_currency(0.5))
        wizard = self._wizard(self._move("out_invoice", 1000.0))
        self.assertEqual(wizard.line_ids.bill_id, bill)
        self.assertEqual(wizard.line_ids.amount_residual, 100.0)
        self.assertEqual(wizard.line_ids.amount_residual_company, abs(bill.amount_residual_signed))
        self.assertNotEqual(wizard.line_ids.amount_residual_company, 100.0)

    def test_post_without_netting(self):
        """Post Without Netting posts the invoice and leaves the bill open."""
        bill = self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        self._wizard(invoice).action_post_without_netting()
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(bill.amount_residual, 600.0)

    def test_draft_bill_not_offered(self):
        """Draft bills are not offered unless another module makes them mandatory."""
        self._move("in_invoice", 600.0)
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))