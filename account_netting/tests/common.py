"""Shared setup and helpers for the netting tests."""
from odoo import Command
from odoo.tests import TransactionCase


class NettingCommon(TransactionCase):
    """A partner who is both customer and vendor, and a netting journal."""

    @classmethod
    def setUpClass(cls):
        """Create the partners and set the company's netting journal."""
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Gold Customer"})
        cls.other_partner = cls.env["res.partner"].create({"name": "Other Partner"})
        cls.netting_journal = cls.env["account.journal"].create({
            "name": "Test Netting",
            "code": "TNTG",
            "type": "general",
        })
        cls.company.netting_journal_id = cls.netting_journal

    def _move(self, move_type, amount, partner=None, date="2026-11-01", currency=None):
        """Create a draft invoice, bill or credit note with one untaxed line."""
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

    def _wizard(self, invoice):
        """Click Confirm and return the netting popup that opens."""
        action = self._confirm(invoice)
        return self.env["account.netting.wizard"].browse(action["res_id"])

    def _other_currency(self, rate):
        """Activate a currency other than the company's, with a rate on the test date."""
        currency = self.env.ref("base.EUR")
        if currency == self.company.currency_id:
            currency = self.env.ref("base.USD")
        currency.active = True
        self.env["res.currency.rate"].create({
            "currency_id": currency.id,
            "company_id": self.company.id,
            "name": "2026-11-01",
            "rate": rate,
        })
        return currency