"""Tests for customer allocations on purchase orders."""

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseAllocation(TransactionCase):
    """Allocation rules: confirmed order, positive, on the order, within the purchase."""

    @classmethod
    def setUpClass(cls):
        """Create a vendor, two customers and a confirmed purchase of 10 units."""
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Gold Supplier"})
        cls.customer_a = cls.env["res.partner"].create({"name": "Customer A"})
        cls.customer_b = cls.env["res.partner"].create({"name": "Customer B"})
        cls.product = cls.env["product.product"].create(
            {"name": "Gold 21K", "type": "consu", "is_storable": True}
        )
        cls.order = cls.env["purchase.order"].create({
            "partner_id": cls.vendor.id,
            "order_line": [Command.create({
                "product_id": cls.product.id,
                "product_qty": 10,
                "price_unit": 50,
            })],
        })
        cls.order.button_confirm()

    def _allocate(self, customer, quantity, product=None, order=None):
        """Allocate a quantity of the product to a customer."""
        return self.env["purchase.order.allocation"].create({
            "order_id": (order or self.order).id,
            "partner_id": customer.id,
            "product_id": (product or self.product).id,
            "product_qty": quantity,
            "price_unit": 60,
        })

    def test_allocations_within_purchased_quantity(self):
        """Allocating exactly the purchased quantity is accepted."""
        self._allocate(self.customer_a, 6)
        self._allocate(self.customer_b, 4)
        self.assertEqual(self.order._get_allocated_quantities()[self.product], 10)

    def test_allocations_exceeding_purchased_quantity(self):
        """Allocating more than purchased is refused."""
        self._allocate(self.customer_a, 6)
        with self.assertRaises(ValidationError):
            self._allocate(self.customer_b, 5)

    def test_product_not_on_purchase_order(self):
        """A product that is not on the order cannot be allocated."""
        other = self.env["product.product"].create({"name": "Gold 18K", "type": "consu"})
        with self.assertRaises(ValidationError):
            self._allocate(self.customer_a, 1, product=other)

    def test_quantity_must_be_positive(self):
        """Zero or negative quantities are refused."""
        with self.assertRaises(ValidationError):
            self._allocate(self.customer_a, 0)

    def test_no_allocation_on_rfq(self):
        """A purchase order still in RFQ cannot be allocated."""
        rfq = self.order.copy()
        with self.assertRaises(ValidationError):
            self._allocate(self.customer_a, 1, order=rfq)