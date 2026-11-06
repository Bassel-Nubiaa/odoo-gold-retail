"""Customer allocation: the share of a purchase order delivered to one customer."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class PurchaseOrderAllocation(models.Model):
    """One customer's share of a product purchased on a purchase order.

    The allocated quantity is sold to the customer and dropshipped from the
    vendor; whatever is not allocated is received into stock as usual.
    """

    _name = "purchase.order.allocation"
    _description = "Purchase Order Customer Allocation"
    _order = "order_id, sequence, id"

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    order_id = fields.Many2one(
        "purchase.order", string="Purchase Order", required=True,
        ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    currency_id = fields.Many2one(related="order_id.currency_id")

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    product_id = fields.Many2one("product.product", string="Product", required=True)
    # Quantities are expressed in the product's own unit of measure.
    product_uom_id = fields.Many2one(related="product_id.uom_id", string="Unit")
    product_qty = fields.Float(
        string="Quantity", required=True, digits="Product Unit of Measure"
    )
    price_unit = fields.Monetary(string="Sale Price", currency_field="currency_id")

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("product_qty")
    def _check_positive_quantity(self):
        """Allocated quantities must be greater than zero."""
        for allocation in self:
            if allocation.product_qty <= 0:
                raise ValidationError(_("Allocated quantities must be greater than zero."))

    @api.constrains("order_id", "product_id", "product_qty")
    def _check_allocated_quantity(self):
        """The allocations of a product cannot exceed the quantity purchased."""
        for order in self.order_id:
            purchased = order._get_purchased_quantities()
            for product, allocated in order._get_allocated_quantities().items():
                available = purchased.get(product, 0.0)
                if float_compare(
                    allocated, available, precision_rounding=product.uom_id.rounding
                ) > 0:
                    raise ValidationError(
                        _(
                            "%(product)s: %(allocated)s %(uom)s allocated, but only "
                            "%(available)s %(uom)s purchased on %(order)s.",
                            product=product.display_name,
                            allocated=allocated,
                            available=available,
                            uom=product.uom_id.name,
                            order=order.name,
                        )
                    )