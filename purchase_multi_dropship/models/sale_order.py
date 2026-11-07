"""Sales orders generated from purchase order allocations."""
from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Link each generated sales order to its source purchase order."""

    _inherit = "sale.order"

    source_purchase_id = fields.Many2one(
        "purchase.order",
        string="Source Purchase",
        readonly=True,
        copy=False,
        index=True,
    )

    def action_cancel(self):
        """Block cancelling orders generated from purchase allocations.

        The purchase receipt was already reduced by their quantities, so cancelling
        them would leave goods that are neither received nor delivered.
        """
        if self.filtered("source_purchase_id"):
            raise UserError(_(
                "This order was generated from a purchase allocation and cannot be cancelled. "
                "Use a return on its dropship instead."
            ))
        return super().action_cancel()