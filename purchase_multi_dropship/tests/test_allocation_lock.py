"""Tests for locked generated allocations, subtotals and the standard Sales button."""
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAllocationLock(TransactionCase):
    """Generated allocations are locked and their orders use the standard Sales button."""

    @classmethod
    def setUpClass(cls):
        """Confirm a purchase of 10 units and allocate 4 units to each of two customers."""
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Gold Supplier"})
        cls.customer_a = cls.env["res.partner"].create({"name": "Customer A"})
        cls.customer_b = cls.env["res.partner"].create({"name": "Customer B"})
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
        cls.allocation_a, cls.allocation_b = cls.env["purchase.order.allocation"].create([
            {"order_id": cls.order.id, "partner_id": customer.id, "product_id": cls.product.id,
             "product_qty": 4.0, "price_unit": 50.0}
            for customer in (cls.customer_a, cls.customer_b)
        ])

    def test_subtotal(self):
        """The subtotal is the quantity times the unit sale price."""
        self.assertEqual(self.allocation_a.price_subtotal, 200.0)

    def test_pending_allocation_editable(self):
        """Allocations without a customer order can be changed and deleted."""
        self.allocation_a.product_qty = 3.0
        self.assertEqual(self.allocation_a.price_subtotal, 150.0)
        self.allocation_b.unlink()
        self.assertFalse(self.allocation_b.exists())

    def test_generated_allocation_locked(self):
        """Generated allocations keep their customer, product, quantity and price."""
        self.order.action_generate_customer_orders()
        with self.assertRaises(UserError):
            self.allocation_a.product_qty = 3.0
        with self.assertRaises(UserError):
            self.allocation_a.partner_id = self.customer_b

    def test_generated_allocation_not_deleted(self):
        """Generated allocations cannot be deleted."""
        self.order.action_generate_customer_orders()
        with self.assertRaises(UserError):
            self.allocation_a.unlink()

    def test_generated_order_not_cancelled(self):
        """Generated customer orders cannot be cancelled."""
        self.order.action_generate_customer_orders()
        with self.assertRaises(UserError):
            self.order.sale_order_ids[:1].action_cancel()

    def test_standard_sales_button(self):
        """The standard Sales button counts and opens the generated customer orders."""
        self.order.action_generate_customer_orders()
        self.assertEqual(self.order.sale_order_count, 2)
        self.assertEqual(self.order._get_sale_orders(), self.order.sale_order_ids)