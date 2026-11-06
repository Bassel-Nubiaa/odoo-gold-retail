"""Purchase order extension: allocate purchased quantities to customers."""

from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    """Allocate a purchase to customers and generate their sales orders."""

    _inherit = "purchase.order"

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    allocation_ids = fields.One2many(
        "purchase.order.allocation", "order_id",
        string="Customer Allocations", copy=False,
    )
    # Products on the order; used to limit the products offered in allocations.
    allocation_product_ids = fields.Many2many(
        "product.product", compute="_compute_allocation_product_ids"
    )
    sale_order_ids = fields.One2many(
        "sale.order", "source_purchase_id", string="Customer Orders"
    )
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends("order_line.product_id")
    def _compute_allocation_product_ids(self):
        """List the products purchased on the order."""
        for order in self:
            order.allocation_product_ids = order.order_line.product_id

    @api.depends("sale_order_ids")
    def _compute_sale_order_count(self):
        """Count the customer orders generated from this purchase."""
        for order in self:
            order.sale_order_count = len(order.sale_order_ids)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_generate_customer_orders(self):
        """Create and confirm one sales order per customer with new allocations."""
        for order in self:
            if order.state not in ("purchase", "done"):
                raise UserError(_("Confirm the purchase order before generating customer orders."))
            pending = order.allocation_ids.filtered(lambda a: not a.sale_line_id)
            if not pending:
                raise UserError(_("%s has no new allocations to generate.", order.name))
            for customer, allocations in pending.grouped("partner_id").items():
                order._create_customer_sale_order(customer, allocations).action_confirm()
        return True

    def action_view_customer_orders(self):
        """Open the sales orders generated from this purchase."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_orders")
        action["domain"] = [("source_purchase_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _create_customer_sale_order(self, customer, allocations):
        """Create one customer's sales order and link each allocation to its line.

        Sale prices are entered in the purchase order's currency and converted
        to the sales order's currency when they differ.
        """
        self.ensure_one()
        sale_order = self.env["sale.order"].create({
            "partner_id": customer.id,
            "company_id": self.company_id.id,
            "origin": self.name,
            "source_purchase_id": self.id,
        })
        sale_order.order_line = [
            Command.create({
                "product_id": allocation.product_id.id,
                "product_uom_qty": allocation.product_qty,
                "product_uom": allocation.product_uom_id.id,
                "price_unit": self.currency_id._convert(
                    allocation.price_unit, sale_order.currency_id,
                    self.company_id, fields.Date.context_today(self),
                ),
            })
            for allocation in allocations
        ]
        # Lines are created in the same order as the allocations.
        for allocation, line in zip(allocations, sale_order.order_line):
            allocation.sale_line_id = line
        return sale_order

    def _get_purchased_quantities(self):
        """Return {product: purchased quantity}, in each product's own unit."""
        self.ensure_one()
        quantities = defaultdict(float)
        for line in self.order_line.filtered(lambda l: l.product_id and not l.display_type):
            quantities[line.product_id] += line.product_uom._compute_quantity(
                line.product_qty, line.product_id.uom_id
            )
        return quantities

    def _get_allocated_quantities(self):
        """Return {product: allocated quantity}, in each product's own unit."""
        self.ensure_one()
        quantities = defaultdict(float)
        for allocation in self.allocation_ids:
            quantities[allocation.product_id] += allocation.product_qty
        return quantities