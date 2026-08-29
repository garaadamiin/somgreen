# Master data

Versioned import files for the chart of accounts, partners and products. They
are in the repository so that an import is repeatable and any rebuild starts
from the same data.

Folders match the rollout phases. **Import `phase1-trading` only.** Leave
`phase2-manufacturing` alone until the factory actually starts — those files
reference categories that do not exist until `somgreen_mrp` is installed, and
importing them early fails with an unhelpful "no matching record" error.

```
data/
├── phase1-trading/          <- trading go-live
│   ├── accounts.csv
│   ├── partners.csv
│   ├── customers.csv
│   └── products_traded.csv
└── phase2-manufacturing/    <- only when the factory starts
    ├── accounts.csv
    ├── products_raw.csv
    ├── products_packaging.csv
    ├── products_finished.csv
    └── products_waste.csv
```

Always click **Test** in the import dialog before **Import**. It validates every
row without writing anything, and it is what turns a code collision or a bad
reference into a message instead of a half-finished import.

After go-live these records are maintained in the Odoo UI, not here. The files
stay in the repository as the record of what was loaded.

---

## Phase 1 — import order

Order matters: later files reference records created by earlier ones.

| # | File | Import into |
|---|---|---|
| 1 | `accounts.csv` | Accounting → Configuration → Chart of Accounts (list → ⚙ → Import records) |
| 2 | `partners.csv` | Contacts |
| 3 | `customers.csv` | Contacts |
| 4 | `products_traded.csv` | Inventory → Products → Products |

`somgreen_config` must already be installed before step 3 — every product row
references a product category that module creates.

### Before importing `accounts.csv`: check for code collisions

Odoo installs a chart template when the database is created, and account codes
must be unique per company. If that chart already uses one of our codes, the
import fails on that row.

List what already exists first:

```bash
docker exec somgreen_db psql -U odoo -d somgreen -tAc "SELECT code, name FROM account_account ORDER BY code;"
```

If a code from `accounts.csv` is already taken, there are two clean options:
rename the existing account to ours and drop our row, or renumber our row to a
free code. Do **not** create a near-duplicate at a neighbouring code — two
accounts that mean the same thing is how a trial balance stops being readable.

Clicking **Test** surfaces the same collisions harmlessly, so if you skip the
query, do not skip Test.

### The chart

`accounts.csv` is a complete working chart for a small Somali importer trading
in USD — cash, mobile money, receivables, inventory, payables, equity, income,
cost of sales and operating expenses. It is not a supplement to something else;
it is the whole chart.

A few entries earn a word:

| Account | Why it is there |
|---|---|
| `101300` Mobile Money | EVC Plus / eDahab settle a real share of collections. Folding them into the cash account makes both untraceable. |
| `103300` Import Deposits and LCs | Money paid to the bank against a shipment that has not arrived. An asset, not an expense, and reconcilable so it clears when the goods land. |
| `104100` Goods in Transit | Goods paid for and shipped but not yet received. Without it, stock that exists and money that is gone are both invisible for the length of a sea voyage. |
| `106100/106200` Stock Interim | Automated valuation posts through these between the receipt and the vendor bill. Reconcilable, so a receipt with no bill behind it stands out. |
| `502100` Customs Duty and Clearing | Expense account for the `SRV-LC-*` landed cost services. Without it, validating a landed cost fails at the last step. |
| `504200` Purchase Price Difference | Absorbs the gap when a vendor bill differs from the PO cost. Leave it unwired until you meet the problem; easier to add than to unpick. |
| `409200/609100` FX Gain / Loss | Buying in one currency and selling in another produces these whether or not you have an account for them. |

Phase 2 adds twelve accounts, in three groups.

**Inventory** — `105200` Raw Material, `105300` Finished Goods, `105400` Waste,
plus `105600` Cost of Production and `105700` Work in Progress. The last two are
Odoo's own `110400`/`110500` renumbered rather than created, which is why Phase 2
runs `scripts/setup_chart_of_accounts.py` instead of a UI import — an import
cannot rename an existing account. Both are **assets**: material passes through
`105600` on the way from Raw Materials to Finished Goods, so while an order is
open it holds work in progress.

**Revenue and cost of sales** — `401200` Sales and `501200` COGS for manufactured
goods, mirroring `401100`/`501100` on the trading side.

**Factory conversion cost** — `503100`–`503400` for what the factory actually
costs (labour, power, consumables, depreciation), and `503900` Conversion Cost
Absorbed for what the work-center rate capitalised into the cartons. The net of
the five is the under/over-absorption variance.

That third group is what makes the margin split honest. Without it, absorbed
conversion cost is credited into `501200` and the actual factory wages sit in
`601100` beside the office payroll — manufacturing margin then reads better than
it is, which is precisely the failure the phased chart exists to prevent.

**Splitting sales and COGS between merchandise and manufactured goods is the
point of the phased chart.** Blend them and the P&L shows a single margin, and
whichever side of the business is weaker hides behind the stronger.

---

## Column notes

### `id` — external ID

Every row has one. This is what makes the import **idempotent**: re-importing
the same file updates the existing records instead of creating duplicates. Never
remove this column, and never renumber an existing row — a changed external ID
creates a second record rather than editing the first.

The `somgreen.` prefix is the import namespace, deliberately distinct from the
`somgreen_config.` / `somgreen_mrp.` module namespaces these files reference. A
module upgrade can therefore never overwrite imported business data, and an
import can never overwrite module configuration.

### `type` and `is_storable`

Odoo 18 removed the "Storable Product" type. A stocked item is `type=consu` with
`is_storable=1`. Anyone importing a file written for Odoo 16 or 17
(`type=product`) will silently create untracked products that never hold stock.

### `weight` **and** `volume` — both required for landed costs

**Neither column is cosmetic, and neither is optional.**

Landed costs are split across the goods in a shipment by one of these fields. A
product with `volume` 0 receives none of a `by_volume` allocation; a product with
`weight` 0 receives none of a `by_weight` one. Everything else in the container
absorbs the missing share. The totals still balance, which is exactly what makes
it hard to catch — it surfaces months later as one product that always looks
unusually profitable.

Both are filled on every row so either method works, and so a shipment that needs
the non-default method can use it without a data cleanup first.

Values are per unit of the product's own UoM: a carton's weight in kg, its volume
in m³. Measure a real carton rather than copying the supplier's spec sheet — the
spec describes the product, the carton is what ships.

Why both matter here, concretely:

| Product | kg per m³ |
|---|---:|
| Baby diapers | 75 – 99 |
| Wet wipes | 255 |

Wet wipes are roughly three times as dense as diapers. Split a container's
freight by weight and the wipes absorb about three times the freight they should,
while every diaper line looks cheaper than it is. Both *cube out* — the container
fills before it reaches its weight limit — so freight is charged on volume, and
`by_volume` is the default. See
`custom-addons/somgreen_config/data/landed_cost_products.xml`.

### `tracking`

`none` everywhere by default. Turn a line to `lot` only where you actually want
per-shipment traceability — imported diapers are a reasonable candidate, so a
customer complaint traces back to a supplier batch and a container.

Landed costs settle onto an AVCO product with or without lots, so tracking is
about traceability, not costing. Turning it on for a product that already holds
stock is awkward, so decide per product before the first receipt.

### `uom_id` vs `uom_po_id`

Stock unit vs purchase unit. They must be in the same UoM category. Everything in
`phase1-trading` is stocked and bought by the carton, so the two match. The one
exception across both phases is BOPP tape, bought by the Roll (100 m) and
consumed by the metre.

### Prices

`standard_price` and `list_price` are 0.00 deliberately.

Cost is set by the first receipt plus its landed costs. Typing a guess would be
overwritten anyway, and would corrupt the AVCO average in the meantime. Selling
prices belong on a pricelist, not on the product — see the Wholesale / Retail /
Export pricelists in `somgreen_config`.

### Product names and brands

The traded product names are descriptive and carry no brand. **If you stock more
than one brand in the same size, put the brand in the name.**

This is not cosmetic either. Odoo matches on name during import, so two brands of
Medium diaper sharing one name merge into a single product — and because costing
is AVCO, their landed costs blend into one average. You are then left with one
cost figure covering two products bought at different prices, and no way to
separate them after the fact.

---

## Hygiene products are stocked by the PACK, not the carton

`MD-DIA-007` and `MD-DIA-008` break the pattern used by the rest of this file,
and the reason is commercial: SomGreen sells whole cartons to wholesalers **and
single packs to small shops**. A product whose stock unit is the carton cannot
sell one pack without a fractional quantity, so for these the stock unit is the
pack and the carton is a `product.packaging`:

| Code | Name | 1 Unit | Packaging |
|---|---|---|---|
| `MD-DIA-007` | Baby Diaper Size 3 - Pack | one pack | Carton (12 packs) |
| `MD-DIA-008` | Baby Diaper Size 4 - Pack | one pack | Carton (12 packs) |

Buying and receiving still happen by the carton: pick the packaging on the PO
line and enter cartons, and Odoo fills the pack quantity (547 cartons -> 6,564
packs). Entering packs works too - it back-fills the carton count and suggests
the packaging automatically.

`uom_id` is still `Units` on both. Nothing about the UoM record changed; what
changed is what one Unit *means*. The names end in `- Pack` so that nobody types
547 meaning cartons and receives 547 packs.

**This inverts the `weight` / `volume` rule above for these products.** Those
fields are per unit of the product's own UoM, so for these two that is a PACK's
weight and volume, not a carton's. Measure a carton and divide by 12. Getting
this backwards overstates their freight share by 12x and starves everything else
in the container.

It is also why `Volume` precision is 4 rather than 3 - see
`custom-addons/somgreen_config/data/decimal_precision.xml`.

### Both are still unmeasured

Both carry `weight = 0` and `volume = 0`, and are **deliberately not in
`products_traded.csv` yet**. Adding them now would mean rows with zeros in those
two columns, and because the `id` column makes an import idempotent, a later
re-import would **overwrite whatever was measured in the UI with those zeros** -
silently re-arming the by_volume trap described above, on the two products most
likely to be in a container.

Measure a real carton of each, divide by 12, set weight and volume on the
product, then add the rows here. Not before.

---

## What is not here

**Bills of materials.** Phase 2 only, built in the UI once with the production
supervisor present — the quantities are the pack, box, tape and label counts that
go into one carton, and they come from measuring the machine. See the project
README.

**Pricelist rules, payment terms and reordering rules.** Commercial decisions
that change far more often than this repository does, and Odoo ships usable
payment terms already. Set them in the UI.
