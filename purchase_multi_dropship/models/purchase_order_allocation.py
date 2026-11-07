"""Customer allocation: the share of a purchase order delivered to one customer."""

from odoo import _, api, fields, models
from odoo.tools import float_compare
from odoo.exceptions import UserError, ValidationError


# Fields a generated allocation must keep, because its sales order line was built from them.
LOCKED_FIELDS = {"order_id", "partner_id", "product_id", "product_qty", "price_unit", "currency_id"}

class PurchaseOrderAllocation(models.Model):
    """One customer's share of a product purchased on a confirmed purchase order.

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
    currency_id = fields.Many2one("res.currency", string="Sale Currency", required=True, default=lambda self: self._default_currency_id(), )

    # Currency the unit sale price was entered in; the price is converted from it on currency change.
    price_currency_id = fields.Many2one("res.currency", string="Price Currency")

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    product_id = fields.Many2one("product.product", string="Product", required=True)
    # Quantities are expressed in the product's own unit of measure.
    product_uom_id = fields.Many2one(related="product_id.uom_id", string="Unit")
    product_qty = fields.Float(
        string="Quantity", required=True, digits="Product Unit of Measure"
    )
    price_unit = fields.Monetary(string="Unit Sale Price", currency_field="currency_id")
    price_subtotal = fields.Monetary( string="Subtotal", currency_field="currency_id", compute="_compute_price_subtotal",store=True,)    

    # Set when the customer's sales order is generated.
    sale_line_id = fields.Many2one(
        "sale.order.line", string="Sales Order Line", readonly=True, copy=False
    )
    sale_order_id = fields.Many2one(
        related="sale_line_id.order_id", string="Sales Order"
    )
    # Set when the customer's dropship is created.
    move_id = fields.Many2one("stock.move", string="Dropship Move", readonly=True, copy=False)
    picking_id = fields.Many2one(related="move_id.picking_id", string="Dropship")

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("order_id")
    def _check_order_confirmed(self):
        """Allocations exist only on confirmed purchase orders."""
        for allocation in self:
            if allocation.order_id.state not in ("purchase", "done"):
                raise ValidationError(
                    _("Confirm %s before allocating it to customers.", allocation.order_id.name)
                )

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

    # ------------------------------------------------------------
    # Currency
    # ------------------------------------------------------------

    @api.model
    def _default_currency_id(self):
        """Return AED when it is active, otherwise the company currency."""
        aed = self.env.ref("base.AED", raise_if_not_found=False)
        return aed if aed and aed.active else self.env.company.currency_id

    @api.onchange("price_unit")
    def _onchange_price_unit(self):
        """Remember the currency the price was entered in."""
        for allocation in self:
            allocation.price_currency_id = allocation.currency_id

    @api.onchange("currency_id")
    def _onchange_currency_id(self):
        """Convert an entered unit sale price to the new currency at today's rate."""
        for allocation in self:
            source, target = allocation.price_currency_id, allocation.currency_id
            if allocation.price_unit and source and target and source != target:
                allocation.price_unit = source._convert(
                    allocation.price_unit,
                    target,
                    allocation.order_id.company_id or self.env.company,
                    fields.Date.context_today(allocation),
                )
            allocation.price_currency_id = target


    # ------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------

    @api.depends("product_qty", "price_unit")
    def _compute_price_subtotal(self):
        """Multiply the allocated quantity by the unit sale price."""
        for allocation in self:
            allocation.price_subtotal = allocation.product_qty * allocation.price_unit

    # ------------------------------------------------------------
    # Lock generated allocations
    # ------------------------------------------------------------

    def write(self, vals):
        """Block changes to allocations that already have a customer sales order."""
        if LOCKED_FIELDS & vals.keys() and self.filtered("sale_line_id"):
            raise UserError(_("Allocations that already have a customer order cannot be changed."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_generated(self):
        """Block deleting allocations that already have a customer sales order."""
        if self.filtered("sale_line_id"):
            raise UserError(_("Allocations that already have a customer order cannot be deleted."))
                    