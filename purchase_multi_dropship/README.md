# Purchase Multi-Customer Dropship

Splits one confirmed purchase order between several customers. Each customer receives a
confirmed sales order and a dropship directly from the vendor. The remaining quantity is
received into the warehouse.

Built for a gold trading company that buys from a supplier in bulk and resells part of each
purchase to its customers before the goods arrive.

## Features

| Feature | Description |
|---------|-------------|
| Customer allocations | A tab on the confirmed purchase order lists the quantity and unit sale price allocated to each customer |
| Sale currency per allocation | Each allocation has its own currency, AED by default, independent of the purchase order currency. Changing the currency converts an entered price at the current rate |
| Customer orders | One confirmed sales order per customer and currency, at the allocated unit sale price |
| Dropship per customer | One dropship per customer order, from the vendor to the customer, linked to the purchase and sales order lines |
| Receipt reduction | The warehouse receipt is reduced by the allocated quantities, or cancelled when everything is allocated |
| Standard Sales button | Generated orders appear on the standard Sales smart button of the purchase order |
| Source purchase | Each generated sales order shows the purchase order it came from |

## Workflow

1. Confirm the purchase order.
2. Open the **Customer Allocations** tab and add one row per customer: customer, product,
   quantity, sale currency and unit sale price.
3. Click **Generate Customer Orders**.
4. Validate each customer's dropship when the vendor delivers. The delivered quantities update
   both the sales order and the purchase order.
5. Receive the remaining quantity into the warehouse as usual.

## Rules

| Rule | Reason |
|------|--------|
| Allocations are only possible on confirmed purchase orders | A quantity that is not yet confirmed by the vendor cannot be promised to a customer |
| Allocated quantities cannot exceed the purchased quantity, per product | Ordered quantity = dropshipped quantity + received quantity |
| Only quantities not yet received can be allocated | Goods already in the warehouse are sold through the standard sales flow |
| One sales order per customer and currency | A sales order has a single currency |
| Generated allocations cannot be changed or deleted | Their sales order lines and dropships were built from them |
| Generated sales orders cannot be cancelled | The receipt was already reduced by their quantities; returns go through the dropship |
| Generated sales orders do not create warehouse deliveries | The goods go from the vendor to the customer |

## Currencies

| Situation | Behaviour |
|-----------|-----------|
| New allocation | Sale currency is AED when AED is active, otherwise the company currency |
| Currency changed after a price was entered | The price is converted with `res.currency._convert()` at today's rate |
| Currency changed without a price | Only the currency changes |
| Sales order currency | Taken from a pricelist in the allocation currency: the customer's pricelist when it matches, otherwise an existing pricelist of the company in that currency |
| No pricelist in the currency | A pricelist without rules, named "<currency> Customer Orders", is created. Line prices always come from the allocation |

## Technical design

| Element | Implementation |
|---------|----------------|
| New model | `purchase.order.allocation` |
| Sales order procurement | `_action_launch_stock_rule` skips lines that come from an allocation |
| Sales button | Extends `_get_sale_orders()` from `sale_purchase` instead of redefining its count |
| Dropship pickings | The `dropship` operation type from `stock_dropshipping` |
| Valuation | Dropship moves use the purchase line price (`_get_stock_move_price_unit`) |
| Core changes | None |

## Dependencies

`purchase_stock`, `sale_management`, `sale_stock`, `stock_dropshipping`

## Tests

27 tests cover the allocation rules, order generation, dropships, receipt reduction, sale
currencies and conversion, the lock on generated allocations and the Sales button.

```
odoo -d <database> -u purchase_multi_dropship --test-tags /purchase_multi_dropship --stop-after-init
```

## Compatibility

| Odoo version | Status |
|--------------|--------|
| 18.0 | Available |
| 17.0, 19.0 | Planned |

## License

LGPL-3. Author: Bassel Nubiaa.