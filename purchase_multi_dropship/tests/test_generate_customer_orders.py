"""Tests for generating customer sales orders from purchase allocations."""

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGenerateCustomerOrders(TransactionCase):
    """One confirmed sales order per customer, without warehouse deliveries."""

    @classmethod
    def setUpClass(cls):
        """A confirmed purchase of two products, allocated to two customers."""
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Gold Supplier"})
        cls.customer_a = cls.env["res.partner"].create({"name": "Customer A"})
        cls.customer_b = cls.env["res.partner"].create({"name": "Customer B"})
        cls.gold_21k = cls.env["product.product"].create(
            {"name": "Gold 21K", "type": "consu", "is_storable": True}
        )
        cls.gold_18k = cls.env["product.product"].create(
            {"name": "Gold 18K", "type": "consu", "is_storable": True}
        )
        cls.order = cls.env["purchase.order"].create({
            "partner_id": cls.vendor.id,
            "order_line": [
                Command.create({"product_id": cls.gold_21k.id, "product_qty": 10, "price_unit": 50}),
                Command.create({"product_id": cls.gold_18k.id, "product_qty": 5, "price_unit": 40}),
            ],
        })
        cls.order.button_confirm()

    def _allocate(self, customer, product, quantity, price):
        """Allocate a quantity of a product to a customer at a sale price."""
        return self.env["purchase.order.allocation"].create({
            "order_id": self.order.id,
            "partner_id": customer.id,
            "product_id": product.id,
            "product_qty": quantity,
            "price_unit": price,
        })

    def test_one_confirmed_order_per_customer(self):
        """Allocations are grouped into one confirmed sales order per customer."""
        self._allocate(self.customer_a, self.gold_21k, 6, 60)
        self._allocate(self.customer_a, self.gold_18k, 2, 45)
        self._allocate(self.customer_b, self.gold_21k, 3, 62)
        self.order.action_generate_customer_orders()

        self.assertEqual(len(self.order.sale_order_ids), 2)
        order_a = self.order.sale_order_ids.filtered(lambda o: o.partner_id == self.customer_a)
        self.assertEqual(order_a.state, "sale")
        self.assertEqual(len(order_a.order_line), 2)
        line_21k = order_a.order_line.filtered(lambda l: l.product_id == self.gold_21k)
        self.assertEqual(line_21k.product_uom_qty, 6)
        self.assertEqual(line_21k.price_unit, 60)
        self.assertEqual(order_a.source_purchase_id, self.order)

    def test_no_warehouse_delivery(self):
        """Confirming the generated orders creates no delivery from stock."""
        self._allocate(self.customer_a, self.gold_21k, 6, 60)
        self.order.action_generate_customer_orders()
        self.assertFalse(self.order.sale_order_ids.picking_ids)

    def test_no_duplicates(self):
        """Generating again only creates orders for new allocations."""
        self._allocate(self.customer_a, self.gold_21k, 6, 60)
        self.order.action_generate_customer_orders()
        with self.assertRaises(UserError):
            self.order.action_generate_customer_orders()

        self._allocate(self.customer_b, self.gold_21k, 2, 62)
        self.order.action_generate_customer_orders()
        self.assertEqual(len(self.order.sale_order_ids), 2)

    def test_purchase_must_be_confirmed(self):
        """A draft purchase order cannot generate customer orders."""
        draft = self.order.copy()
        self.env["purchase.order.allocation"].create({
            "order_id": draft.id,
            "partner_id": self.customer_a.id,
            "product_id": self.gold_21k.id,
            "product_qty": 1,
            "price_unit": 60,
        })
        with self.assertRaises(UserError):
            draft.action_generate_customer_orders()