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

    def action_net_and_post(self):
        """Post the invoice and settle it against the selected bills, oldest first."""
        self.ensure_one()
        journal = self.invoice_id.company_id.netting_journal_id
        selected = self.line_ids.filtered("selected")
        self._check_netting(journal, selected)

        bills = selected.bill_id
        bills.filtered(lambda bill: bill.state == "draft").action_post()
        self.invoice_id.with_context(netting_check=False).action_post()

        allocations = self._allocate(bills)
        if allocations:
            entry = self._create_netting_entry(journal, allocations)
            self._reconcile(entry, allocations)
            self.invoice_id.netting_move_id = entry
        return {"type": "ir.actions.act_window_close"}

    # ------------------------------------------------------------
    # Netting
    # ------------------------------------------------------------

    def _check_netting(self, journal, selected):
        """Stop before posting anything when netting is not possible."""
        if not journal:
            raise UserError(_(
                "Set a Netting Journal in Invoicing / Accounting settings before netting."
            ))
        if not selected:
            raise UserError(_("Select at least one bill, or post without netting."))
        if self.line_ids.filtered(lambda line: line.mandatory and not line.selected):
            raise UserError(_("Bills that must be netted with this invoice cannot be unselected."))

    def _allocate(self, bills):
        """Spread the invoice's open amount over the bills, oldest first.

        Returns a list of (bill, amount) in company currency; the last bill may be partial.
        """
        currency = self.company_currency_id
        remaining = abs(self.invoice_id.amount_residual_signed)
        allocations = []
        for line in self.line_ids.filtered("selected"):
            if currency.is_zero(remaining):
                break
            amount = min(remaining, abs(line.bill_id.amount_residual_signed))
            if not currency.is_zero(amount):
                allocations.append((line.bill_id, amount))
                remaining -= amount
        return allocations

    def _create_netting_entry(self, journal, allocations):
        """Create and post the entry: credit receivable, debit payable per bill."""
        invoice = self.invoice_id
        receivable = invoice._get_netting_payable_lines()[:1]
        total = sum(amount for _bill, amount in allocations)
        lines = [Command.create({
            "name": _("Netting: %s", invoice.name),
            "account_id": receivable.account_id.id,
            "partner_id": invoice.commercial_partner_id.id,
            "balance": -total,
        })]
        for bill, amount in allocations:
            lines.append(Command.create({
                "name": _("Netting: %s", bill.name),
                "account_id": bill._get_netting_payable_lines()[:1].account_id.id,
                "partner_id": bill.commercial_partner_id.id,
                "balance": amount,
            }))
        entry = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": invoice.invoice_date,
            "ref": _("Netting of %s", invoice.name),
            "currency_id": invoice.company_currency_id.id,
            "line_ids": lines,
        })
        entry.action_post()
        return entry

    def _reconcile(self, entry, allocations):
        """Reconcile the entry with the invoice and with each bill."""
        invoice = self.invoice_id
        entry_lines = entry._get_netting_payable_lines()
        receivable = entry_lines.filtered(lambda line: line.balance < 0)
        (receivable | invoice._get_netting_payable_lines()).reconcile()
        for bill, _amount in allocations:
            payable = entry_lines.filtered(lambda line: line.name == _("Netting: %s", bill.name))
            (payable | bill._get_netting_payable_lines()).reconcile()


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