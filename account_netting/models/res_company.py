"""Company settings for netting."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    """Store the journal that receives netting entries, per company."""

    _inherit = "res.company"

    netting_journal_id = fields.Many2one(
        "account.journal",
        string="Netting Journal",
        check_company=True,
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        help="Miscellaneous journal that receives the entries settling invoices against bills.",
    )

    @api.constrains("netting_journal_id")
    def _check_netting_journal_type(self):
        """Only a Miscellaneous journal can hold netting entries."""
        for company in self:
            if company.netting_journal_id and company.netting_journal_id.type != "general":
                raise ValidationError(_("The netting journal must be a Miscellaneous journal."))
