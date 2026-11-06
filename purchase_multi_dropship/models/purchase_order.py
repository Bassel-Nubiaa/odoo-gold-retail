"""Purchase order extension: allocate the purchased quantities to customers."""

from collections import defaultdict

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    """Add customer allocations to purchase orders."""

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

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends("order_line.product_id")
    def _compute_allocation_product_ids(self):
        """List the products purchased on the order."""
        for order in self:
            order.allocation_product_ids = order.order_line.product_id

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

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