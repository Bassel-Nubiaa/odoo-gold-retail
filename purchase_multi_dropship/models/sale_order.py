"""Sales order extension: link generated orders to their source purchase."""

from odoo import fields, models


class SaleOrder(models.Model):
    """Record which purchase order a customer order was generated from."""

    _inherit = "sale.order"

    source_purchase_id = fields.Many2one(
        "purchase.order", string="Source Purchase Order",
        readonly=True, copy=False, index=True,
    )