"""Tests for customer dropships and the reduced purchase receipt."""

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCustomerDropship(TransactionCase):
    """Allocated quantities are dropshipped; the receipt keeps the rest."""

    @classmethod
    def setUpClass(cls):
        """A confirmed purchase of 10 units of one product."""
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
                "product_id": cls.product.id, "product_qty": 10, "price_unit": 50,
            })],
        })
        cls.order.button_confirm()

    def _allocate(self, customer, quantity):
        """Allocate a quantity to a customer."""
        return self.env["purchase.order.allocation"].create({
            "order_id": self.order.id,
            "partner_id": customer.id,
            "product_id": self.product.id,
            "product_qty": quantity,
            "price_unit": 60,
        })

    def _open_receipt_quantity(self):
        """Quantity still expected on the purchase order's receipt."""
        return sum(self.order._get_open_receipt_moves().mapped("product_uom_qty"))

    @staticmethod
    def _validate(picking):
        """Validate a transfer with its full quantities."""
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.move_ids.picked = True
        picking.button_validate()

    def test_one_dropship_per_customer(self):
        """Each customer gets a dropship from the vendor, linked to both orders."""
        allocation_a = self._allocate(self.customer_a, 6)
        self._allocate(self.customer_b, 3)
        self.order.action_generate_customer_orders()

        dropship = allocation_a.picking_id
        self.assertEqual(dropship.picking_type_id.code, "dropship")
        self.assertEqual(dropship.partner_id, self.customer_a)
        self.assertEqual(dropship.location_id.usage, "supplier")
        self.assertEqual(dropship.location_dest_id.usage, "customer")
        self.assertEqual(allocation_a.move_id.product_uom_qty, 6)
        self.assertEqual(allocation_a.move_id.sale_line_id, allocation_a.sale_line_id)
        self.assertEqual(allocation_a.move_id.purchase_line_id, self.order.order_line)
        self.assertIn(dropship, allocation_a.sale_order_id.picking_ids)

    def test_receipt_reduced_to_remainder(self):
        """The receipt keeps only the unallocated quantity."""
        self._allocate(self.customer_a, 6)
        self._allocate(self.customer_b, 3)
        self.order.action_generate_customer_orders()
        self.assertEqual(self._open_receipt_quantity(), 1)

    def test_full_allocation_cancels_receipt(self):
        """Allocating everything leaves nothing to receive."""
        self._allocate(self.customer_a, 10)
        self.order.action_generate_customer_orders()
        self.assertEqual(self._open_receipt_quantity(), 0)

    def test_validated_dropship_updates_quantities(self):
        """A done dropship counts as delivered to the customer and received from the vendor."""
        allocation = self._allocate(self.customer_a, 6)
        self.order.action_generate_customer_orders()
        self._validate(allocation.picking_id)
        self.assertEqual(allocation.sale_line_id.qty_delivered, 6)
        self.assertEqual(self.order.order_line.qty_received, 6)

    def test_cannot_allocate_received_quantity(self):
        """Gold already received into stock cannot be dropshipped."""
        receipt = self.order.picking_ids.filtered(lambda p: p.picking_type_id.code == "incoming")
        self._validate(receipt)
        self._allocate(self.customer_a, 6)
        with self.assertRaises(UserError):
            self.order.action_generate_customer_orders()


    def test_generate_button_only_for_pending_allocations(self):
        """The button is offered only while some allocations are not generated."""
        self._allocate(self.customer_a, 6)
        self.assertTrue(self.order.has_pending_allocations)
        self.order.action_generate_customer_orders()
        self.assertFalse(self.order.has_pending_allocations)
        self._allocate(self.customer_b, 2)
        self.assertTrue(self.order.has_pending_allocations)

    def test_nothing_left_to_allocate_after_full_receipt(self):
        """Once everything is received into stock, nothing can be allocated."""
        self.assertTrue(self.order.can_allocate)
        receipt = self.order.picking_ids.filtered(lambda p: p.picking_type_id.code == "incoming")
        self._validate(receipt)
        self.assertFalse(self.order.can_allocate)

    def test_nothing_left_to_allocate_when_fully_allocated(self):
        """Generating the whole purchase empties the receipt: ordered = dropshipped + received."""
        self._allocate(self.customer_a, 10)
        self.assertTrue(self.order.can_allocate)
        self.order.action_generate_customer_orders()
        self.assertFalse(self.order.can_allocate)
        self.assertEqual(self._open_receipt_quantity(), 0)