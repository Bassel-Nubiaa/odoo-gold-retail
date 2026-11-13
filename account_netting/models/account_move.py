"""Open the netting popup when a customer invoice is confirmed."""
from odoo import fields, models


class AccountMove(models.Model):
    """Offer the partner's open bills for netting before posting an invoice."""

    _inherit = "account.move"

    netting_move_id = fields.Many2one(
        "account.move",
        string="Netting Entry",
        readonly=True,
        copy=False,
        help="Entry that settled this invoice against the partner's vendor bills.",
    )

    def action_post(self):
        """Open the netting popup instead of posting when the partner has open bills.

        Only the invoice Confirm button sets the 'netting_check' context key, so invoices
        posted from code are posted as before.
        """
        if self._should_check_netting():
            mandatory = self._get_mandatory_netting_bills()
            bills = mandatory | self._get_netting_candidate_bills()
            if bills:
                return self.env["account.netting.wizard"]._open_for_invoice(self, bills, mandatory)
        return super().action_post()

    def _should_check_netting(self):
        """Return True for one draft customer invoice confirmed from its button."""
        return (
            self.env.context.get("netting_check")
            and len(self) == 1
            and self.move_type == "out_invoice"
            and self.state == "draft"
        )

    def _get_netting_candidate_bills(self):
        """Return the posted, not fully paid bills of the invoice partner, oldest first.

        Bills 'In Payment' are excluded: a payment is already on its way, so netting
        their open amount could pay them twice.
        """
        self.ensure_one()
        return self.env["account.move"].search([
            ("move_type", "=", "in_invoice"),
            ("state", "=", "posted"),
            ("partner_id", "=", self.partner_id.id),
            ("company_id", "=", self.company_id.id),
            ("payment_state", "in", ("not_paid", "partial")),
        ], order="invoice_date, id")

    def _get_mandatory_netting_bills(self):
        """Return the bills that must be netted with this invoice.

        Empty here; modules such as sale_broken_gold add the bill of the same sales order.
        """
        return self.env["account.move"]

    def _get_netting_payable_lines(self):
        """Return the open receivable or payable lines of an invoice or bill."""
        return self.line_ids.filtered(
            lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable")
            and not line.reconciled
        )
