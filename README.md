# Odoo Gold Retail

Odoo modules for a gold trading company: bulk purchases resold to several customers before
delivery, invoices netted against the same customer's bills, sales paid partly in old gold,
gold stock and gold position reporting.

The modules rebuild, as clean and tested code, processes first implemented with Odoo Studio
and custom developments for a gold trading company in the UAE.

## Modules

| Module | Description | Status |
|--------|-------------|--------|
| [`purchase_multi_dropship`](purchase_multi_dropship/README.md) | Split a confirmed purchase order between several customers: one sales order and one dropship per customer, the rest received into the warehouse | Available |
| [`account_netting`](account_netting/README.md) | Settle customer invoices against the same customer's open vendor bills when the invoice is confirmed | Available |
| `sale_broken_gold` | Sales orders paid partly in old gold: the gold received becomes a vendor bill netted with the invoice | Planned |
| `purchase_gold_stock` | Gold stock information in Purchase | Planned |
| `account_gold_position` | Gold position report in Accounting | Planned |

Install only modules marked **Available**: modules **In development** are incomplete.

## Versions

| Branch | Status |
|--------|--------|
| 18.0 | Active |
| 17.0, 19.0 | Planned |

## License

LGPL-3. See [LICENSE](LICENSE).

## Author

Bassel Nubiaa, [github.com/Bassel-Nubiaa](https://github.com/Bassel-Nubiaa)