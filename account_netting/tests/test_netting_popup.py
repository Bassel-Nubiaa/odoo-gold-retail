"""Tests for the netting popup opened when a customer invoice is confirmed."""
from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNettingPopup(TransactionCase):
    """The popup lists the partner's open bills; invoices without them post directly."""

    @classmethod
    def setUpClass(cls):
        """Create a partner who is both customer and vendor, and another partner."""
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Gold Customer"})
        cls.other_partner = cls.env["res.partner"].create({"name": "Other Partner"})

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _move(self, move_type, amount, partner=None, date="2026-11-01", currency=None):
        """Create a draft invoice or bill with one untaxed line."""
        return self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": (partner or self.partner).id,
            "invoice_date": date,
            "currency_id": (currency or self.company.currency_id).id,
            "invoice_line_ids": [Command.create({
                "name": "Gold",
                "quantity": 1.0,
                "price_unit": amount,
                "tax_ids": [Command.clear()],
            })],
        })

    def _bill(self, amount, **kwargs):
        """Create and post a vendor bill."""
        bill = self._move("in_invoice", amount, **kwargs)
        bill.action_post()
        return bill

    def _pay(self, bill, amount):
        """Settle part or all of a bill with a reconciled vendor credit note."""
        refund = self._move("in_refund", amount)
        refund.action_post()
        (bill.line_ids | refund.line_ids).filtered(
            lambda line: line.account_id.account_type == "liability_payable"
        ).reconcile()

    def _confirm(self, invoice):
        """Click the invoice Confirm button."""
        return invoice.with_context(netting_check=True).action_post()

    # ------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------

    def test_no_open_bills_posts_directly(self):
        """Without open bills, Confirm posts the invoice."""
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))
        self.assertEqual(invoice.state, "posted")

    def test_open_bill_opens_popup(self):
        """With an open bill, Confirm opens the popup and the invoice stays draft."""
        bill = self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        action = self._confirm(invoice)
        self.assertEqual(action["res_model"], "account.netting.wizard")
        self.assertEqual(invoice.state, "draft")
        wizard = self.env["account.netting.wizard"].browse(action["res_id"])
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
        wizard = self.env["account.netting.wizard"].browse(self._confirm(invoice)["res_id"])
        self.assertEqual(wizard.line_ids.amount_residual, 400.0)

    def test_netting_limited_to_invoice_amount(self):
        """The amount to net never exceeds the invoice amount."""
        self._bill(700.0, date="2026-10-01")
        self._bill(500.0, date="2026-10-15")
        invoice = self._move("out_invoice", 1000.0)
        wizard = self.env["account.netting.wizard"].browse(self._confirm(invoice)["res_id"])
        self.assertEqual(wizard.selected_amount, 1200.0)
        self.assertEqual(wizard.netting_amount, 1000.0)

    def test_bills_oldest_first(self):
        """Bills are listed from the oldest bill date."""
        newer = self._bill(100.0, date="2026-10-20")
        older = self._bill(100.0, date="2026-09-05")
        invoice = self._move("out_invoice", 1000.0)
        wizard = self.env["account.netting.wizard"].browse(self._confirm(invoice)["res_id"])
        self.assertEqual(wizard.line_ids.bill_id.ids, [older.id, newer.id])

    def test_untick_reduces_amount(self):
        """Unticking a bill removes it from the amount to net."""
        self._bill(300.0, date="2026-10-01")
        self._bill(200.0, date="2026-10-02")
        invoice = self._move("out_invoice", 1000.0)
        wizard = self.env["account.netting.wizard"].browse(self._confirm(invoice)["res_id"])
        wizard.line_ids[0].selected = False
        self.assertEqual(wizard.netting_amount, 200.0)

    def test_bill_in_other_currency_offered(self):
        """Bills in another currency are offered, valued in company currency."""
        other = self.env.ref("base.EUR")
        if other == self.company.currency_id:
            other = self.env.ref("base.USD")
        other.active = True
        self.env["res.currency.rate"].create({
            "currency_id": other.id,
            "company_id": self.company.id,
            "name": "2026-11-01",
            "rate": 0.5,
        })
        bill = self._bill(100.0, currency=other)
        invoice = self._move("out_invoice", 1000.0)
        wizard = self.env["account.netting.wizard"].browse(self._confirm(invoice)["res_id"])
        self.assertEqual(wizard.line_ids.bill_id, bill)
        self.assertEqual(wizard.line_ids.amount_residual, 100.0)
        self.assertEqual(wizard.line_ids.amount_residual_company, abs(bill.amount_residual_signed))
        self.assertNotEqual(wizard.line_ids.amount_residual_company, 100.0)

    def test_post_without_netting(self):
        """Post Without Netting posts the invoice and leaves the bill open."""
        bill = self._bill(600.0)
        invoice = self._move("out_invoice", 1000.0)
        wizard = self.env["account.netting.wizard"].browse(self._confirm(invoice)["res_id"])
        wizard.action_post_without_netting()
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(bill.amount_residual, 600.0)

    def test_draft_bill_not_offered(self):
        """Draft bills are not offered unless another module makes them mandatory."""
        self._move("in_invoice", 600.0)
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))
        
    def test_bill_with_payment_in_process_excluded(self):
        """A bill whose payment is registered but not yet posted is not offered."""
        bill = self._bill(600.0)
        bill.payment_state = "in_payment"
        invoice = self._move("out_invoice", 1000.0)
        self.assertFalse(self._confirm(invoice))        