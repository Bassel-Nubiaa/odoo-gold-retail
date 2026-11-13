"""Netting popup: choose the open bills to settle against a customer invoice."""
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountNettingWizard(models.TransientModel):
    """List the partner's open bills and post the invoice with or without netting."""

    _name = "account.netting.wizard"
    _description = "Invoice Netting"

    invoice_id = fields.Many2one("account.move", string="Invoice", required=True, readonly=True)
    partner_id = fields.Many2one(related="invoice_id.partner_id")
    company_currency_id = fields.Many2one(related="invoice_id.company_currency_id")
    line_ids = fields.One2many("account.netting.wizard.line", "wizard_id", string="Open Bills")
    has_mandatory = fields.Boolean(compute="_compute_amounts")
    invoice_amount = fields.Monetary(
        string="Invoice Amount",
        currency_field="company_currency_id",
        compute="_compute_amounts",
    )
    selected_amount = fields.Monetary(
        string="Selected Bills",
        currency_field="company_currency_id",
        compute="_compute_amounts",
    )
    netting_amount = fields.Monetary(
        string="Amount to Net",
        currency_field="company_currency_id",
        compute="_compute_amounts",
        help="The smaller of the invoice amount and the selected bills, in company currency.",
    )

    # ------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------

    @api.depends("invoice_id", "line_ids.selected", "line_ids.amount_residual_company")
    def _compute_amounts(self):
        """Compare the invoice with the selected bills, in company currency."""
        for wizard in self:
            selected = wizard.line_ids.filtered("selected")
            wizard.has_mandatory = any(wizard.line_ids.mapped("mandatory"))
            wizard.invoice_amount = abs(wizard.invoice_id.amount_total_signed)
            wizard.selected_amount = sum(selected.mapped("amount_residual_company"))
            wizard.netting_amount = min(wizard.invoice_amount, wizard.selected_amount)

    # ------------------------------------------------------------
    # Open
    # ------------------------------------------------------------

    @api.model
    def _open_for_invoice(self, invoice, bills, mandatory):
        """Create the popup for an invoice and return the action that opens it."""
        wizard = self.create({
            "invoice_id": invoice.id,
            "line_ids": [
                Command.create({
                    "bill_id": bill.id,
                    "mandatory": bill in mandatory,
                    "selected": True,
                    "amount_residual": bill.amount_residual,
                    "amount_residual_company": abs(bill.amount_residual_signed),
                })
                for bill in bills
            ],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Net Against Open Bills"),
            "res_model": self._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    # ------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------

    def action_post_without_netting(self):
        """Post the invoice without netting; not allowed when a bill must be netted."""
        self.ensure_one()
        if self.has_mandatory:
            raise UserError(_("This invoice has a bill that must be netted with it."))
        self.invoice_id.with_context(netting_check=False).action_post()
        return {"type": "ir.actions.act_window_close"}


class AccountNettingWizardLine(models.TransientModel):
    """One open bill offered in the netting popup."""

    _name = "account.netting.wizard.line"
    _description = "Invoice Netting Bill"
    _order = "mandatory desc, bill_date, id"

    wizard_id = fields.Many2one("account.netting.wizard", required=True, ondelete="cascade")
    bill_id = fields.Many2one("account.move", string="Bill", required=True, readonly=True)
    bill_date = fields.Date(related="bill_id.invoice_date", string="Bill Date")
    bill_currency_id = fields.Many2one(related="bill_id.currency_id", string="Currency")
    company_currency_id = fields.Many2one(related="wizard_id.company_currency_id")
    selected = fields.Boolean(string="Net", default=True)
    mandatory = fields.Boolean(readonly=True, help="This bill is always netted with the invoice.")
    amount_residual = fields.Monetary(
        string="Open Amount",
        currency_field="bill_currency_id",
        readonly=True,
    )
    amount_residual_company = fields.Monetary(
        string="Open Amount (Company Currency)",
        currency_field="company_currency_id",
        readonly=True,
    )