"""Accounting settings for netting."""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Show the company's netting journal in Accounting settings."""

    _inherit = "res.config.settings"

    netting_journal_id = fields.Many2one(
        related="company_id.netting_journal_id",
        readonly=False,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
