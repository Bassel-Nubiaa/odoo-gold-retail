# Account Netting

Settles a customer invoice against the same partner's open vendor bills when the invoice is
confirmed. One netting entry replaces a payment received and a payment made for the same
partner.

Built for a gold trading company whose customers are often also its suppliers.

## Features

| Feature | Description |
|---------|-------------|
| Netting popup | Confirming a customer invoice opens a popup when the partner has open vendor bills |
| Open bills | Posted bills of the invoice partner, not paid or partially paid, oldest first, in any currency |
| Selection | Each bill can be unticked; the amount to net is updated immediately |
| Net and Post | Posts the invoice, creates one netting entry and reconciles it with the invoice and the bills |
| Post Without Netting | Posts the invoice normally |
| Netting journal | A Miscellaneous journal per company, set in the Invoicing / Accounting settings |
| Traceability | The invoice shows its netting entry in the Other Info tab |

## Workflow

1. Set the **Netting Journal** in **Invoicing / Accounting → Configuration → Settings**.
2. Create a customer invoice and click **Confirm**.
3. If the partner has open bills, the popup lists them. Untick the bills to keep open.
4. Click **Net and Post**, or **Post Without Netting**.

## Rules

| Rule | Reason |
|------|--------|
| Only bills of the invoice partner are offered | Netting settles one partner's balance |
| Fully paid bills are excluded | Nothing is left to settle |
| Bills **In Payment** are excluded | A payment is already registered; netting could pay the bill twice |
| Bills of any currency are offered | Amounts are compared and netted in company currency |
| The amount netted is the smaller of the invoice and the selected bills | The netting never exceeds either side |
| Bills are settled oldest first | The last bill used can remain partially open |
| No netting journal, no selected bill: nothing is posted | All checks run before posting |
| Invoices posted from code never open the popup | Only the invoice **Confirm** button checks for netting |

## Netting entry

Posted in the netting journal, dated on the invoice date, in company currency:

| Account | Partner | Debit | Credit |
|---------|---------|-------|--------|
| Receivable | Customer | | Total netted |
| Payable, one line per bill | Vendor | Amount netted for the bill | |

The receivable line is reconciled with the invoice, each payable line with its bill. Exchange
differences follow the standard Odoo reconciliation.

## Extension

`account.move._get_mandatory_netting_bills()` returns the bills that must be netted with an
invoice. Mandatory bills are listed first, cannot be unticked, are posted when still in draft,
and hide **Post Without Netting**. Empty in this module; used by `sale_broken_gold`.

## Technical design

| Element | Implementation |
|---------|----------------|
| Netting journal | `res.company.netting_journal_id`, shown through `res.config.settings` |
| Popup trigger | `action_post` with the `netting_check` context key, set on the invoice Confirm button |
| Popup | Transient models `account.netting.wizard` and `account.netting.wizard.line` |
| Link | `account.move.netting_move_id` on the invoice |
| Core changes | None |

## Dependencies

`account`. Works on Community (Invoicing) and Enterprise (Accounting).

## Tests

23 tests cover the netting journal, the bills offered, selection and amounts, posting with and
without netting, the netting entry, oldest-first allocation, partial and multi-currency bills,
and the checks before posting.

```
odoo -d <database> -u account_netting --test-tags /account_netting --stop-after-init
```

## Compatibility

| Odoo version | Status |
|--------------|--------|
| 18.0 | Available |
| 17.0, 19.0 | Planned |

## License

LGPL-3. Author: Bassel Nubiaa.