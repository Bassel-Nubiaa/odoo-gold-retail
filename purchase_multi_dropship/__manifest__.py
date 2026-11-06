{
    "name": "Purchase Multi-Customer Dropship",
    "version": "18.0.1.0.0",
    "summary": "Dropship one supplier purchase order to several customers",
    "category": "Inventory/Purchase",
    "author": "Bassel Nubiaa",
    "website": "https://github.com/Bassel-Nubiaa/odoo-gold-retail",
    "license": "LGPL-3",
    "depends": ["purchase_stock", "sale_management", "sale_stock", "stock_dropshipping"],       
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_order_views.xml",
        "views/sale_order_views.xml",
        ],    
    "installable": True,
    "application": False,
}