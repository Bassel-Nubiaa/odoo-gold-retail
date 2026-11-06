"""Sales order line extension: no warehouse delivery for allocated lines."""

from odoo import fields, models


class SaleOrderLine(models.Model):
    """Keep allocated lines out of Odoo's standard delivery process.

    Allocated goods travel directly from the vendor to the customer through
    the purchase order's dropship, so confirming the sales order must not
    create a delivery from the warehouse for these lines.
    """

    _inherit = "sale.order.line"

    purchase_allocation_ids = fields.One2many(
        "purchase.order.allocation", "sale_line_id", string="Purchase Allocations"
    )

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """Launch the standard procurement only for lines without an allocation."""
        # sudo: sales users may not have access to purchase allocations.
        allocated_lines = self.sudo().filtered("purchase_allocation_ids")
        standard_lines = self - allocated_lines
        return super(SaleOrderLine, standard_lines)._action_launch_stock_rule(
            previous_product_uom_qty
        )