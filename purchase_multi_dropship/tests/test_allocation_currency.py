"""Tests for allocation currencies and their conversion."""
from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAllocationCurrency(TransactionCase):
    """Allocations have their own currency, default to AED and convert their price on change."""

    @classmethod
    def setUpClass(cls):
        """Confirm a purchase of 10 units; prepare a second currency with a rate for today."""
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id
        cls.other_currency = cls.env.ref("base.EUR")
        if cls.other_currency == cls.company_currency:
            cls.other_currency = cls.env.ref("base.USD")
        cls.other_currency.active = True
        cls.env["res.currency.rate"].create({
            "currency_id": cls.other_currency.id,
            "company_id": cls.company.id,
            "name": fields.Date.context_today(cls.env.user),
            "rate": 2.5,
        })
        cls.vendor = cls.env["res.partner"].create({"name": "Gold Supplier"})
        cls.customer = cls.env["res.partner"].create({"name": "Customer A"})
        cls.product = cls.env["product.product"].create({
            "name": "Gold Bar 100 g",
            "type": "consu",
            "is_storable": True,
        })
        cls.order = cls.env["purchase.order"].create({
            "partner_id": cls.vendor.id,
            "order_line": [Command.create({
                "product_id": cls.product.id,
                "product_qty": 10.0,
                "price_unit": 30.0,
            })],
        })
        cls.order.button_confirm()

    def _allocation(self, currency, quantity=4.0, price=50.0):
        """Create an allocation for the customer in the given currency."""
        return self.env["purchase.order.allocation"].create({
            "order_id": self.order.id,
            "partner_id": self.customer.id,
            "product_id": self.product.id,
            "product_qty": quantity,
            "price_unit": price,
            "currency_id": currency.id,
        })

    def test_default_currency_aed(self):
        """New allocations use AED when it is active."""
        aed = self.env.ref("base.AED")
        aed.active = True
        allocation = self.env["purchase.order.allocation"].create({
            "order_id": self.order.id,
            "partner_id": self.customer.id,
            "product_id": self.product.id,
            "product_qty": 1.0,
            "price_unit": 10.0,
        })
        self.assertEqual(allocation.currency_id, aed)

    def test_price_converted_on_currency_change(self):
        """Changing the currency converts an entered price at today's rate."""
        allocation = self.env["purchase.order.allocation"].new({
            "order_id": self.order.id,
            "currency_id": self.company_currency.id,
            "price_unit": 100.0,
        })
        allocation._onchange_price_unit()
        allocation.currency_id = self.other_currency
        allocation._onchange_currency_id()
        expected = self.company_currency._convert(
            100.0, self.other_currency, self.company, fields.Date.context_today(allocation))
        self.assertNotEqual(expected, 100.0)
        self.assertAlmostEqual(allocation.price_unit, expected)

    def test_no_conversion_without_price(self):
        """Changing the currency of an allocation without a price only changes the currency."""
        allocation = self.env["purchase.order.allocation"].new({
            "order_id": self.order.id,
            "currency_id": self.company_currency.id,
        })
        allocation.currency_id = self.other_currency
        allocation._onchange_currency_id()
        self.assertFalse(allocation.price_unit)
        self.assertEqual(allocation.price_currency_id, self.other_currency)

    def test_order_in_allocation_currency(self):
        """The customer order uses the allocation currency and price, without conversion."""
        allocation = self._allocation(self.other_currency)
        self.order.action_generate_customer_orders()
        sale_order = allocation.sale_order_id
        self.assertEqual(sale_order.currency_id, self.other_currency)
        self.assertEqual(allocation.sale_line_id.price_unit, 50.0)
        self.assertEqual(sale_order.amount_untaxed, 200.0)

    def test_one_order_per_customer_and_currency(self):
        """One customer with two currencies receives two orders."""
        self._allocation(self.company_currency, quantity=3.0)
        self._allocation(self.other_currency, quantity=3.0)
        self.order.action_generate_customer_orders()
        self.assertEqual(len(self.order.sale_order_ids), 2)
        self.assertEqual(self.order.sale_order_ids.currency_id,
                         self.company_currency | self.other_currency)