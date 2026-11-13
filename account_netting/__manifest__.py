# Manifest of the Account Netting module.
{
    "name": "Account Netting",
    "summary": "Settle customer invoices against the same customer's open vendor bills",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Bassel Nubiaa",
    "website": "https://github.com/Bassel-Nubiaa/odoo-gold-retail",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}