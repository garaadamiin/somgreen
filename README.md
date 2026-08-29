# SomGreen ERP

Odoo 18.0 Community on Docker, for one company running two businesses.

```
Phase 1  TRADING       Buy imported goods  ->  Stock  ->  Sell
Phase 2  MANUFACTURING Tissue packs  ->  Packing line  ->  Cartons  ->  Sell
```

Phase 1 is live first and stands entirely on its own — the trading business
never needs Manufacturing installed. Phase 2 layers the factory on top when it
starts, and nothing configured in Phase 1 has to change for that to happen.

The two are kept apart where it counts: traded goods and manufactured goods
carry **separate Sales and COGS accounts**, so the P&L shows trading margin and
manufacturing margin as two readable lines instead of one blended number that
lets the weaker side hide behind the stronger.

---

## Quick start

```powershell
docker compose up -d
```

```powershell
docker compose ps
```

Both services should read "healthy". Odoo is at **http://localhost:8071**.

> **Not 8069.** That port is held by the unrelated `pms_erp` project on this
> machine. Changing it back will make this stack fail to start.

| Port | Purpose |
|---|---|
| 8071 → 8069 | Odoo web |
| 8072 | Websockets. `workers = 2` puts Odoo in multi-process mode, where live chatter and activity notifications are served by a separate gevent process. Unpublished, those features fail silently rather than erroring. |

Logs are written to `./logs/odoo.log`, bind-mounted so they survive container
recreation. `docker compose logs app` shows only container-level output — the
detail is in the file.

---

## Database

One database, `somgreen`, created **without demo data**. `dbfilter = ^somgreen$`
in `config/odoo.conf` means it is selected automatically and no database picker
ever appears.

### Country and chart of accounts

The company is Somali and trades in **USD**. Odoo has no `l10n_so`
localization, so the database uses Odoo's **generic chart**, and the working
chart of accounts is imported from `data/phase1-trading/accounts.csv`.

> An earlier build of this stack used `l10n_us`. That was a mistake — it brings
> a US chart and US tax defaults to a Somali business, and **Odoo cannot cleanly
> switch localization once transactions exist.** If you are looking at a
> database with 110100-style US account codes, rebuild it now, while it is still
> cheap. See below.

### Creating the database from scratch

**See `SETUP.md`.** It is the ordered runbook for building Phase 1 on an empty
stack — database creation, module installs, chart import, category wiring,
warehouse, users, and an end-to-end verification cycle.

The stack data (`postgres-data/`, `odoo-web-data/`) was deleted on 2026-08-19 for
a clean rebuild. Backups under `D:\somgreen-backups\` were deliberately kept.

Two notes that apply whenever a database is recreated:

- **Move the filestore with the database.** Odoo names the filestore directory
  after the database, so a new `somgreen` will silently adopt
  `odoo-web-data/filestore/somgreen` if an old one is still sitting there —
  inheriting orphaned attachments. Both halves move together, always.
- **A fresh `postgres-data/` re-reads `POSTGRES_PASSWORD` from `.env`.** That is
  the one time it does. `db_password` in `config/odoo.conf` must match it or Odoo
  cannot connect on first boot.

### Spinning up a throwaway copy

There is no standing sandbox, so rehearse on a temporary clone and drop it after:

```powershell
docker exec somgreen_db psql -U odoo -d postgres -c "CREATE DATABASE somgreen_test WITH TEMPLATE somgreen OWNER odoo;"
```

Stop the app first, widen `dbfilter` to `^somgreen(_test)?$`, then start it
again. On the copy, before opening it, disable scheduled jobs and outbound mail
so it cannot act on real data — `scripts/RESTORE.md` covers the same precautions
for a restored database. Drop it and restore the narrow `dbfilter` when finished.

---

## Credentials

`config/odoo.conf` and `.env` are gitignored and hold real secrets. `.example`
copies of both are committed as templates.

### Rotating the database password

Three things must change, in this order. Doing fewer leaves the stack broken in
a way that looks like a connection bug:

```powershell
docker exec somgreen_db psql -U odoo -d postgres -c "ALTER USER odoo WITH PASSWORD '<new>';"
```

Changing `POSTGRES_PASSWORD` in `.env` does **not** do this — the data directory
is already initialised, so the role password is never re-read from the
environment. Then update `.env`, then `config/odoo.conf` — that one **overrides**
the env var, because the config file is bind-mounted into the container. Finally
`docker compose down` and `up -d`.

### Master password

`admin_passwd` in `config/odoo.conf` can create, drop, back up and **restore**
any database on this instance. Treat it as a root credential.

---

## Backups

```powershell
powershell -File scripts\backup.ps1
```

Writes a timestamped set to `D:\somgreen-backups\` containing the database dump,
the filestore and a copy of the stack configuration. 30-day retention.

**Register it to run daily. This is not currently registered** — backups so far
have all been run by hand:

```powershell
schtasks /Create /TN "SomGreen Backup" /RL HIGHEST /SC DAILY /ST 02:00 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File d:\somgreen\scripts\backup.ps1"
```

Confirm it took:

```powershell
schtasks /Query /TN "SomGreen Backup"
```

**An untested backup is not a backup.** `scripts\RESTORE.md` has a ten-minute
restore drill that restores into a throwaway database without touching
production. Run it once before go-live and quarterly after.

Both halves matter — database *and* filestore. Restoring one without the other
gives a system that looks complete until someone opens an invoice PDF.

---

## Configuration as code

Structural configuration is deployed rather than clicked in, so it survives a
rebuild. Two modules matching the two phases, plus one that carries the financial
statements.

### `custom-addons/somgreen_config` — Phase 1, core and trading

Depends on Inventory, Purchase, Sales and Accounting. **Deliberately does not
depend on `mrp`.**

| File | Creates |
|---|---|
| `account_group.xml` | 43 account groups — the code-prefix hierarchy behind the Chart of Accounts |
| `uom_data.xml` | kg and m rounding fixed to 0.001 |
| `product_category.xml` | Merchandise / Traded Goods, with Diapers & Hygiene and General Merchandise beneath it; Spares; Services. All stocked ones AVCO + automated |
| `stock_location.xml` | QC (import quarantine) and DAMAGED (segregated, still valued) under the warehouse Stock location |
| `landed_cost_products.xml` | 7 landed-cost services with split methods |
| `analytic_plan.xml` | Cost Centre plan — Trading, Logistics & Import, Sales & Distribution, Administration |
| `product_pricelist.xml` | Wholesale / Retail / Export pricelist shells |

### `custom-addons/somgreen_mrp` — Phase 2, the factory

Depends on `somgreen_config` and `mrp`. **Install only when the factory starts.**

| File | Creates |
|---|---|
| `uom_data.xml` | Roll (100 m) purchase unit for carton tape |
| `product_category.xml` | Raw Materials, Finished Goods, Waste |
| `stock_location.xml` | RAW / PACK / WIP / FG |
| `mrp_workcenter.xml` | Packing Line work center |
| `analytic_account.xml` | Production, added to the existing Cost Centre plan |

Keeping these apart is the point: a company that only buys and resells has no
business carrying Manufacturing menus, and uninstalling `mrp` later is far more
disruptive than never having installed it.

### `custom-addons/somgreen_account_reports` — the financial statements

The **Balance Sheet** and **Profit and Loss**, in the Odoo Enterprise layout,
built for Community. Accounting → Reporting → Financial Reports.

```
BALANCE SHEET                 PROFIT AND LOSS
  ASSETS                        INCOME
    Current Assets                Gross Profit
      Bank and Cash Accounts        Operating Income
      Receivables                   Cost of Revenue
      Current Assets              Other Income
      Prepayments                 EXPENSES
    Plus Fixed Assets               Operating Expenses
    Plus Non-current Assets         Depreciation
  LIABILITIES                     NET PROFIT
  EQUITY
  LIABILITIES + EQUITY
```

Odoo 18 Community ships the `account.report` **model** but not the engine that
drives it — no `_get_lines`, no report handlers, no client action; the only
`account.report` records it defines are the three generic tax reports. So this
module computes its own, straight off `account.move.line`.

| File | Carries |
|---|---|
| `data/balance_sheet_lines.xml` | The Balance Sheet tree |
| `data/profit_and_loss_lines.xml` | The Profit and Loss tree |
| `models/account_report_engine.py` | The engine both statements share |
| `report/financial_report_templates.xml` | One QWeb layout, both statements |

Four things worth knowing:

- **Every line prints positive**, so `ASSETS = LIABILITIES + EQUITY` and
  `NET PROFIT = INCOME − EXPENSES` hold on the face of the page. Sign reversal is
  declared once on LIABILITIES, EQUITY and INCOME, and inherited all the way down
  to individual account rows. Deduction lives in the structure — a `formula`
  field like `PL_INCOME - PL_EXPENSES` — never in the sign of an amount.
- **The Balance Sheet has one date, the P&L a range.** Whether the print options
  carry a start date is exactly what makes account lines cumulative or periodic.
  A balance sheet with a start date is not a balance sheet, so it does not offer
  one. The P&L defaults to the fiscal year, so its NET PROFIT agrees with the
  balance sheet line *Profit (Loss) to report*.
- **The structure is data.** Accounting → Configuration → Financial Reports →
  Financial Report Structure. Both trees are `noupdate="1"`, so renames and
  resequencing survive an upgrade. Lines group by `account_type`, never by
  account code — which is why 401100/401200 and 501100/501200 print as their own
  rows, keeping trading and manufacturing margin readable, and why Phase 2
  accounts need no change here.
- **It hides the two `accounting_pdf_reports` statements it replaces**, so the
  accountant is not offered two menu items with the same name and two different
  answers. Reversible: the vendor actions and their report trees are untouched,
  and either menu can be un-archived from Settings → Technical → User Interface →
  Menu Items.

### Upgrading a module

```powershell
docker compose run --rm app odoo -d somgreen -u somgreen_config --workers=0 --max-cron-threads=0 --stop-after-init
```

Back up first. `--workers=0` matters — the config sets `workers = 2`, which
misbehaves under `--stop-after-init`.

Records marked `noupdate="1"` — work centers, landed-cost products, analytic
accounts, pricelists — are created once and never overwritten by an upgrade,
because the accountant tunes them.

The image is **pinned by digest** in `docker-compose.yml`. That is deliberate: a
floating `odoo:18.0` tag lets a routine `docker compose pull` land a new build
and trigger unplanned module upgrades. Change the digest when you intend to
upgrade, never as a side effect.

### `custom-addons/accounting/`

Eight third-party accounting modules (Odoo Mates). Odoo 18 **Community has no
`account_reports`**, so everything below the two headline statements comes from
here: Trial Balance, General Ledger, Partner Ledger, Aged Payable/Receivable,
Cash Book, Day Book, Bank Book, Tax Report and Journal Audit — plus assets,
budgets, follow-ups, fiscal years and recurring payments.

The **Balance Sheet and P&L are no longer among them.** Those now come from
`somgreen_account_reports` above, and the vendor versions are archived out of the
menu. Everything else in the bundle is untouched and still in use.

Worth knowing what that means: much of your reporting still depends on a third
party. Pin the versions, back up before touching them, and check them first
whenever an Odoo point release misbehaves.

---

# Phase 1 — Trading go-live

Ordered by dependency. Step 4 blocks everything physical; do not skip ahead.

### 1. Install the apps

Apps → install **Inventory**, **Purchase**, **Sales**, **Accounting**. Then the
eight `om_*` / `accounting_pdf_reports` modules from `custom-addons/accounting`,
then **SomGreen Configuration** (`somgreen_config`), then **SomGreen Financial
Reports** (`somgreen_account_reports`).

Order matters for the last one: it depends on `accounting_pdf_reports` for the
Financial Reports menu it hangs the statements on.

Do **not** install Manufacturing.

### 2. Company details

Settings → Companies. Legal name, address, tax ID, logo. Currency **USD**.
Country **Somalia** — this drives date and address formats as well as tax
defaults.

### Account groups

`somgreen_config/data/account_group.xml` gives the chart a two-level hierarchy —
account class at the top, functional block beneath:

```
1  ASSETS                                5  COST OF SALES
   101-102  Cash, Bank and Mobile Money     501      Cost of Goods Sold
   103-104  Receivables and Advances        502      Import and Landed Costs
   105-106  Inventory and Stock Interim     503      Factory Conversion Cost
   107      Prepayments                     504-599  Inventory Adjustments
   108      Property, Plant and Equipment
   109-149  Other Current Assets         6  OPERATING EXPENSES
   150-199  Non-current Assets              601 Payroll · 602 Premises · …
```

**Odoo derives the whole thing from code prefixes.** `account.account.group_id`
is a *computed* field resolved by longest prefix match at read time, so creating
the groups files every existing account automatically — nothing is migrated, and
an account added later lands in the right group on its own. `parent_id` is
readonly and maintained by `_adapt_parent_account_group()`, so the file declares
prefixes only and Odoo builds the tree.

Two rules govern the values: start and end prefix must be the **same length** (a
SQL check enforces it), and groups **of the same length** may not overlap.
Different lengths never conflict, which is what makes the two levels nest.

Several groups are ranges rather than single prefixes, because Odoo's generic
chart left accounts at codes outside the SomGreen numbering — `121100 Products to
receive`, `151000 Fixed Asset`, `211100 Bills to receive`. Sweeping a span means
every account has a home and none appear loose at the root. `960-998 Unused
Generic Accounts` deliberately names the two that have no role here (`961000`,
`962000`), so the decision to delete them can be taken later rather than by
accident.

Groups affect the Chart of Accounts view, the Trial Balance and General Ledger
grouping. They do **not** affect the Balance Sheet or Profit and Loss from
`somgreen_account_reports`, which group by `account_type` — see that module.

Load them into an existing database with:

```bash
docker compose run --rm app odoo -d somgreen -u somgreen_config --workers=0 --max-cron-threads=0 --stop-after-init
```

### 3. Chart of accounts

Import `data/phase1-trading/accounts.csv` into Accounting → Configuration →
Chart of Accounts. Check for code collisions with the generic chart first — see
`data/README.md`, which covers the query and how to resolve a clash.

Then set the company defaults that the generic chart pointed at its own
accounts: Accounting → Configuration → Settings → Default Accounts, plus the
receivable and payable accounts on Contacts.

### 4. Wire the product categories — **blocks all stock movement**

Every stocked category is set to **Automated** valuation, which means Odoo posts
inventory to the GL on every move — and refuses the move if it has nowhere to
post it. Until this is done, validating a single receipt fails.

Set these on **all three** merchandise categories — *Merchandise / Traded Goods*,
*Diapers & Hygiene* and *General Merchandise*:

| Field | Account |
|---|---|
| Stock Valuation | 105100 Merchandise Inventory |
| Stock Input | 106100 Stock Interim - Received |
| Stock Output | 106200 Stock Interim - Delivered |
| Stock Journal | the Inventory Valuation journal |
| Income | 401100 Sales - Merchandise |
| Expense | 501100 COGS - Merchandise |

Price Difference can stay blank for now; it only matters when a vendor bill
differs from the PO cost, and `504200` is there when you want it.

> **Accounts do NOT inherit from a parent category.** A product reads accounts
> from its *own* category only — `account/models/product.py` and
> `stock_account/models/product.py` read `self.categ_id.property_*`, never
> `parent_id`. Filling the parent alone leaves every diaper unpostable. Fill all
> three, parent included, so a product filed on the parent by mistake still
> works.

**The seven landed-cost services** (`SRV-LC-*`) each need an expense account too.
They sit in the Services category, which carries no accounts by design, so set
one per product — *502100 Customs Duty and Clearing* suits most of them, and
*502200 Freight and Handling - Inward* the rest. Without it, validating a landed
cost fails at the last step with a missing-account error, usually with the
clearing agent's bill already on the desk.

> Half-configured categories are the single most common cause of an Odoo
> inventory value that will not tie to the balance sheet.

### 5. Settings to enable

| Area | Enable |
|---|---|
| Inventory | Storage Locations, Multi-Step Routes, Units of Measure, Landed Costs, Lots & Serial Numbers |
| Sales | Pricelists, Discounts |
| Accounting | Multi-Currency, Analytic Accounting |

Lots & Serial Numbers is switched on but unused: every CSV row ships
`tracking=none`. Having the setting available costs nothing, and turning tracking
on for a product that already holds stock is awkward — so enable it now and
decide per product later.

### 6. Warehouse

Rename the default warehouse to *SomGreen* with code `SG`. Set **Receipts to
2-step** (Input → Stock) so an imported container is counted and checked against
the packing list before entering saleable stock — this is the substitute for the
Quality app, which is Enterprise-only. Leave Delivery at 1-step.

Point the intermediate step at the **QC** location. This is the step that pays
for itself: a short or damaged container is discovered while the claim window
with the supplier, the shipping line and the insurer is still open.

### 7. Master data

Import `partners.csv` then `products_traded.csv` per `data/README.md`, after
replacing the placeholder rows. Every partner row is marked `EXAMPLE -` and must
be replaced before go-live.

### 8. Commercial setup

- **Pricelists.** Wholesale / Retail / Export shells already exist. Add rules
  and assign one to every customer, so price follows the customer rather than
  depending on a salesperson remembering.
- **Payment terms.** Odoo ships usable ones. Assign a real term to every
  customer — the default of Immediate on a wholesaler you actually give 30 days
  is what makes an aged receivable report meaningless.
- **Credit limits.** Set one per customer. A distributor's largest loss is
  usually a receivable, not a theft.
- **Export fiscal position.** Create *Export — Zero Rated* mapping domestic tax
  to 0%, and assign it on export customers. The pricelist sets the price, the
  fiscal position sets the tax; neither does the other's job.

### 9. Reordering rules

For a trader, replenishment *is* the operation. Set a min/max rule per product
with a **lead time that reflects the real sea voyage** — 30 days from Turkey,
45 from China, plus clearing. A rule with the default zero lead time will tell
you to reorder on the day you run out.

### 10. Users

| Role | Access |
|---|---|
| GM / Owner | Settings admin, Manager on all apps |
| Accountant | Accounting: Adviser; Sales & Purchase: read only |
| Sales Officer | Sales: User (own documents only); Inventory: read only |
| Purchasing Officer | Purchase: User; Inventory: User |
| Store Keeper | Inventory: User |

Three rules matter more than the group grid: only the accountant posts journal
entries; only the store keeper validates transfers; whoever creates a vendor bill
never pays it.

### 11. Opening balances and go-live

Freeze a cutoff date. Count opening stock **by carton** — that count, plus its
landed cost, becomes the cost base for everything after. Post opening balances as
a Miscellaneous entry. Load open AR/AP as individual invoices, not one lump per
partner, or ageing and follow-up will not work. Register the backup task
(above). Run parallel for two weeks.

---

# Phase 2 — The factory

Start here only when tissue packing actually begins. Phase 1 keeps running
throughout; nothing below changes how trading works.

### 1. Back up, then install

```powershell
powershell -File scripts\backup.ps1
```

Apps → install **SomGreen Manufacturing** (`somgreen_mrp`). This pulls in `mrp`.
Enable **Work Orders** in Manufacturing settings. By-Products can stay off —
packing has no routine by-product.

### 2. Accounts and categories

Phase 2 accounts are loaded by the **same script that built the Phase 1 chart**,
run a second time with the Phase 2 CSV mounted:

```bash
docker compose run --rm -T -v ./data/phase2-manufacturing:/mnt/data app odoo shell -d somgreen --workers=0 --max-cron-threads=0 --log-level=warn < scripts/setup_chart_of_accounts.py
```

**Not a UI import.** Twelve accounts, and two of them — `105600` and `105700` —
are Odoo's own `110400 Cost of Production` and `110500 Work in Progress`
renumbered into our inventory block. A UI import cannot rename an existing
account; the script retargets them, which keeps the record ids and therefore the
two `res_company.account_production_wip_*` fields that already point at them.

Five more are the factory conversion-cost block, `503100`–`503900`, which has no
Phase 1 equivalent — see *Reading the factory* below for what it is for.

Then wire the three new categories:

| Field | Raw Materials | Finished Goods | Waste |
|---|---|---|---|
| Stock Valuation | 105200 Raw Material Inventory | 105300 Finished Goods Inventory | 105400 Waste and Rejects Inventory |
| Stock Input | 106100 Stock Interim - Received | same | same |
| Stock Output | 106200 Stock Interim - Delivered | same | same |
| Production Account | 105600 Cost of Production | same | same |
| Stock Journal | Inventory Valuation | same | same |
| Income | 401200 Sales - Manufactured Goods | same | same |
| Expense | 501200 COGS - Manufactured Goods | same | same |

**Production Account** is the only manufacturing-specific field — material passes
through it on the way from Raw Materials to Finished Goods, and it nets to zero
per completed order. It is an **asset**, not an expense: while an order is open it
holds material issued to the floor but not yet finished, which is work in
progress. It is also *not* covered by the valuation constraint, so leaving it
blank blocks nothing and quietly falls back to the stock input account.

The three categories are flat, so wire each one directly — and set **Costing
Method** to Average Cost and **Inventory Valuation** to Automated in the *same
save* as the accounts. The module deliberately ships them on Manual: the three
mandatory accounts resolve through company fallbacks pointing at the *trading*
accounts, so a category left half-wired posts manufacturing stock to `105100
Merchandise Inventory` without raising anything. See the comment in
`somgreen_mrp/data/product_category.xml`.

### 3. Master data and the work center

Import the four `phase2-manufacturing` product files. Then three fields on the
Packing Line work center, all three of which matter:

**Hourly cost.** Replace the placeholder. It should carry labour + electricity +
a share of machine depreciation, so a manufacturing order's cost reflects real
packing cost rather than materials wearing a disguise. A carton costed at
materials only will look profitable at a price that loses money.

**Expense Account → `503900` Conversion Cost Absorbed.** The highest-value field
in the whole Phase 2 setup. When an order is marked done, `_post_labour` credits
`workcenter.expense_account_id` — or, if it is blank, falls back to the finished
product's expense account, which is `501200 COGS - Manufactured Goods`. Absorbed
conversion cost would then be credited straight into manufacturing COGS while the
actual wages sit in `601100` beside the office payroll, and manufacturing margin
would read better than it is.

**Analytic Distribution → Production.** Creating the analytic account routes
nothing to it; work-center time posts there only when the work center itself
carries a distribution. Without this the Production cost centre stays empty
permanently.

### 4. Bills of materials

Build in the UI with the production supervisor present — the quantities come from
measuring the machine. **Replace every number below with your real pack counts.**

`FG-TIS-001` — Carton, Toilet Tissue 2-ply 200s, 8 packs × 10 rolls. A carton is
eight tissue packs boxed, taped and labelled:

| Component | Qty | UoM |
|---|---:|---|
| `RM-TIS-001` Toilet Tissue Pack 2-ply 200s (10 rolls) | 8 | Units |
| `PM-BOX-001` Carton Box 8-pack | 1 | Units |
| `PM-TAP-001` BOPP Tape 48mm | 1.5 | m |
| `PM-LBL-001` Product Label | 8 | Units |

Operation: **Packing Line**, a couple of minutes per carton — set the real time
so the work-center cost lands on the carton.

**No by-product.** The occasional torn pack or crushed carton is written off with
a scrap or inventory adjustment against the **Waste** category; it is not a BoM
line.

**Damage rate.** Packs received against cartons shipped. A batch that loses more
packs than your target points to a supplier packaging or handling problem you can
now prove rather than suspect.

### 5. Reading the factory, month by month

Two things to do every month once production is running.

**Read the absorption variance.** On the Profit and Loss, accounts `503100`–`503400`
carry what the factory actually cost — labour, power, consumables, depreciation.
Account `503900` carries what was absorbed into the cartons at the work-center
rate, as a credit. All five print as their own rows under **Cost of Revenue**, and
the net of them is your under/over-absorption:

```
503100  Factory Labour                        30.00
503200  Factory Power and Fuel                 8.00
503900  Conversion Cost Absorbed             (24.00)
        under-absorption                      14.00
```

That number is the control on `costs_hour`. Persistent under-absorption means the
rate is too low or the line is running below the utilisation the rate assumes;
persistent over-absorption means the opposite. Neither question is answerable if
factory cost is left mixed into `601100` and `602200`.

**Post the WIP entry if orders are open at period end.** Manufacturing → WIP
accounting snapshots open orders onto the balance sheet and auto-reverses the next
day. The company fields it reads (`105700` for WIP, `105600` for overhead) are
already set.

> **Check one line before confirming it.** The wizard's *WIP – Component Value*
> credit is taken from the company-wide fallback valuation account, which is
> `105100 Merchandise Inventory` — the *trading* account. Repoint it to `105200
> Raw Material Inventory`. The wizard's lines are editable, so this is a review
> step, not a blocker.

---

## Imports and landed costs

Applies to both phases — it is how imported goods get their real cost.

Receive the PO → **Inventory → Operations → Landed Costs** → select the receipt →
add cost lines → Compute → Validate. Value settles onto the received stock.

Without this, the cost of a carton is the supplier's invoice price alone, and
every sale is credited with a margin it did not earn — typically 15–30%
overstated on sea-freighted consumer goods.

### Split methods

Set as defaults on the seven `SRV-LC-*` products, and **editable on every landed
cost line** when a shipment is genuinely different.

| Split by | Services | Why |
|---|---|---|
| Volume | Sea Freight, Clearing & Forwarding, Port Handling, Inland Transport | Diapers, wipes and tissue are low-density cargo: a container *cubes out* long before it reaches its weight limit, so freight is charged on volume |
| Value | Customs Duty, Marine Insurance, LC & Bank Charges | Assessed on declared value |

Override the default when the shipment warrants it — dense cargo that hits the
weight limit should split freight `by_weight`, and a specific (per-kg or per-unit)
customs duty should split `by_weight` or `by_quantity` rather than by value.

> **Three things silently break landed costs.**
>
> **Costing method.** Odoo only adjusts value when costing is AVCO or FIFO
> (`stock_landed_costs/models/stock_landed_cost.py` guards on
> `cost_method in ('fifo','average')`). Under standard costing the adjustment is
> skipped outright. Every category here is AVCO for exactly this reason.
>
> **A zero on the field being split by.** A product with volume 0 receives none
> of a `by_volume` allocation, and everything else in the container absorbs its
> share. Same for weight under `by_weight`. Both columns are mandatory on every
> product CSV for this reason.
>
> **Timing — a process rule, not a setting.** Post landed costs *before* the
> goods are sold or consumed. Once stock has left, the adjustment cannot follow
> it: you get a valuation correction floating in the P&L and every carton from
> that batch is mispriced permanently. Clearing paperwork must reach the
> accountant faster than the goods reach the customer.

### Currency rates

Odoo 18 Community has **no automatic exchange-rate provider**. Rates must be
entered by hand — put a recurring monthly task on the accountant. Without it Odoo
keeps using the last rate entered, with no error and no warning.

---

## Known warnings

Both are harmless and appear on every startup:

- `om_account_followup ... no translation language detected` with a stack trace.
  The module calls `_()` at class-definition time, which Odoo 18 logs loudly.
  Cosmetic.
- `Two fields (hard_lock_date, tax_lock_date) ... have the same label`. Odoo 18
  added **native lock dates** to `account`, which now duplicate the ones
  `om_fiscal_year` provides. Prefer the native ones (Accounting → Settings) —
  they are maintained by Odoo.

## Deliberately not done

- **TLS / reverse proxy.** Plain HTTP on a LAN port. Before anyone logs in from
  outside this machine, put nginx or Caddy in front and set `proxy_mode = True`.
- **Blocking `/web/database/manager` outright.** `list_db = False` stops database
  enumeration — `/web/database/list` returns `AccessDenied` and no database names
  appear anywhere. But the manager page itself still renders, because that route
  has no `list_db` check in Odoo 18. Every action on it requires the master
  password, so it is gated rather than hidden. Deny `/web/database/*` at the
  reverse proxy when you add one; that is the real fix.
- **Point of Sale.** Nothing here supports counter sales. If the business starts
  selling over a counter rather than on invoice, that is a separate setup.
