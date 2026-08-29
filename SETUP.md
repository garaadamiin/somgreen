# SomGreen ERP — Phase 1 Implementation Guide

**Trading operations · Odoo 18 Community**

---

## Purpose

This guide covers the configuration required to bring the trading business live
on Odoo. It is written to be followed in the Odoo interface, in the order given.

`README.md` describes how the system is put together. This document is the
one-time implementation.

Technical rebuild procedures — platform provisioning, database creation and the
chart of accounts build — are held separately in `scripts/REBUILD.md` and are not
required for the work below.

---

## Current status

| Stage | Status |
|---|---|
| Platform and database | Complete |
| Application modules | Complete |
| Chart of accounts — 80 accounts | Complete |
| Financial statements — Balance Sheet and P&L | Complete |
| System configuration | **Outstanding — begins at Section 1** |
| Business data | Outstanding |
| Go-live verification | Outstanding |

**Next action:** Section 3.1. The Inventory Valuation setting is not yet visible
on any product category, and Section 3 cannot be started until it is.

---

## How to read this guide

Each section is marked according to whether it can be completed immediately or
depends on information from someone else.

| Marked | Meaning |
|---|---|
| **[System]** | Can be completed now, in the Odoo interface, without consulting anyone. |
| **[Business input]** | Requires a decision, a figure or a document from the owner, the accountant or the warehouse. Identify what is needed early — these are the sections that stall an implementation. |

All configuration is carried out by the SomGreen system administrator in the
Odoo interface. Nothing in this guide requires command line access.

---

## Order of work

Sections 1 to 6 must be completed in sequence.

**Section 3 governs inventory valuation and blocks all physical stock
movement.** Until it is complete, no goods receipt can be validated. Nothing in
Sections 7 onward will function before it is finished.

---

# Part 1 — System configuration

## 1. Enable required features — [System]

**Settings → General Settings**

| Area | Features to enable |
|---|---|
| Inventory | Storage Locations, Multi-Step Routes, Units of Measure, Landed Costs, Lots & Serial Numbers |
| Sales | Pricelists, Discounts |
| Accounting | Multi-Currency, Analytic Accounting |

**Enable Pricelists before saving any other setting.**

Three pricelists — Wholesale, Retail and Export — were created during
installation. While the Pricelists feature is switched off, saving the Settings
page archives all three, whether or not the pricelist option itself was touched.
Saving the page once to record company details is enough to lose them.

Odoo gives a warning when this is about to happen:

> *You are deactivating the pricelist feature. Every active pricelist will be
> archived.*

If this appears, select **Discard** rather than Save, then enable Pricelists and
save again.

**A note on Lots & Serial Numbers.** This is enabled but left unused; no product
is currently tracked. Enabling it now costs nothing, whereas introducing tracking
for a product that already holds stock is disruptive. The decision is taken per
product before its first receipt.

## 2. Company profile — [Business input]

**Settings → Users & Companies → Companies**

Record the registered legal name, address, telephone, tax identification number
and logo.

Country and currency are already set to **Somalia** and **US Dollar**.

The company name appears on every invoice and delivery note. Use the registered
legal name rather than the trading name.

## 3. Product categories and inventory valuation — [System]

> **This section blocks all physical stock movement.** Inventory valuation posts
> to the general ledger on every stock move, and Odoo refuses a movement it
> cannot post. Until this is complete, validating a goods receipt fails.

### 3.1 Prerequisite — access to the valuation setting

The Inventory Valuation setting is hidden until the relevant permission is
granted. If the category form shows only *Costing Method* under Inventory
Valuation, this step has not been done.

**Settings → Users & Companies → Groups**

Locate **Stock Accounting Automatic**, open it, and add the administrator on the
**Users** tab. Save, then refresh the browser.

Developer mode must be active for this menu to appear. It is enabled at the
bottom of **Settings → General Settings**.

### 3.2 Configure each category

**Inventory → Configuration → Product Categories**

Apply the following to **all three** merchandise categories:

- Merchandise / Traded Goods *(parent)*
- Diapers & Hygiene
- General Merchandise

| Field | Value |
|---|---|
| Costing Method | Average Cost (AVCO) — already set |
| Inventory Valuation | **Automated** |
| Stock Valuation Account | 105100 Merchandise Inventory |
| Stock Journal | Inventory Valuation |
| Stock Input Account | 106100 Stock Interim - Received |
| Stock Output Account | 106200 Stock Interim - Delivered |
| Income Account | 401100 Sales - Merchandise |
| Expense Account | 501100 COGS - Merchandise |

Most of these values appear automatically, because company defaults were set
during the chart of accounts build. Confirm each one rather than assuming it.

Leave **Price Difference Account** blank. It applies only where a vendor invoice
differs from the purchase order value, and account 504200 is available if that
becomes necessary.

### 3.3 Two rules that matter

**Set the valuation method and the three stock accounts in a single save.**
Odoo rejects a category saved as Automated with any stock account left empty,
returning *"The stock accounts should be set in order to use the automatic
valuation."* Selecting Automated reveals the account fields without saving;
complete them all, then save once.

**Accounts are not inherited from a parent category.** A product takes its
accounts from its own category only. Configuring the parent alone leaves every
product beneath it unpostable, and configuring only the children leaves any
product filed directly on the parent unpostable. All three are configured
identically for this reason.

### 3.4 Confirm before continuing

Open each of the three categories and verify that Inventory Valuation reads
**Automated** and that all five accounts are populated. A category left on
Manual, or missing an account, will fail at the first goods receipt.

## 4. Landed cost services — [System]

**Inventory → Products → Products**

Seven landed cost service products were created during installation, each
prefixed `SRV-LC-`. They sit in the Services category, which deliberately carries
no accounts, so an expense account is set on each product individually.

| Products | Expense account |
|---|---|
| Sea Freight, Clearing & Forwarding, Port Handling, Inland Transport | 502200 Freight and Handling - Inward |
| Customs Duty, Marine Insurance, LC & Bank Charges | 502100 Customs Duty and Clearing |

If this is omitted, a landed cost fails at the point of validation with a missing
account error — typically once the clearing agent's invoice is already in hand.

## 5. Tax and export handling — [Business input]

The domestic rate is not yet settled, so the structure is built now and the rate
recorded as a placeholder.

**Accounting → Configuration → Taxes**

- A domestic sales tax posting to **204100 Taxes Payable**, at a placeholder
  rate, set as the sales default.
- A fiscal position, **Export — Zero Rated**, mapping that tax to zero.

Assign the fiscal position to export customers so that tax treatment follows the
customer record rather than depending on the salesperson.

> **The rate must be confirmed with the company accountant before the first
> invoice is issued.** The structure is correct; the rate is an assumption. An
> invoice raised at the wrong rate requires a credit note and reissue, and once
> paid becomes a discussion with the customer.

## 6. Warehouse — [System]

**Inventory → Configuration → Warehouses**

Rename the warehouse to **SomGreen**, short code **SG**.

Set **Receipts to two steps** (Input → Stock) and direct the intermediate step to
the **QC** location. Deliveries remain a single step.

This is the control that pays for itself. A container is counted against the
packing list in QC before any goods reach saleable stock, so a short or damaged
shipment is identified while the claim window with the supplier, the shipping
line and the insurer is still open. It substitutes for the Quality module, which
is not available in Odoo Community.

Damaged goods are moved to the **DAMAGED** location. This is deliberately an
internal location rather than a scrap location, so the goods remain valued on the
balance sheet while a claim is open. Scrap only once the claim is settled or
abandoned.

---

# Part 2 — Business data

Every section in this part depends on information the system cannot supply.
Collect all of it before starting, rather than section by section — the product
measurements in Section 8 in particular require physical access to cartons and
are the item most likely to delay go-live.

## 7. Trading partners — [Business input]

Supplier and customer records are supplied in `data/phase1-trading/partners.csv`.
All twelve rows are marked `EXAMPLE` and must be replaced with real trading
partners before import.

Import partners before products.

Always use **Test** in the import dialog before **Import**. It validates every row
without writing anything, turning a bad reference into a message rather than a
partially completed import.

## 8. Product catalogue — [Business input]

Ten diaper and hygiene lines are supplied in
`data/phase1-trading/products_traded.csv`. Two fields require particular care.

**Include the brand in the product name** where more than one brand is stocked in
the same size. Odoo matches on name during import, so two brands of medium diaper
sharing a name are merged into one product. Because costing is average cost,
their landed costs then blend into a single figure that cannot be separated
afterwards.

**Measure weight and volume from an actual carton**, not from a supplier
specification sheet. The specification describes the product; the carton is what
ships. Freight is apportioned by volume, so an incorrect cubic measurement
misprices the line — and because the container total still balances, nothing
appears wrong.

## 9. Commercial terms — [Business input]

**Pricelists.** Wholesale, Retail and Export already exist as empty structures.
Add pricing rules and assign one to every customer, so that price follows the
customer rather than the salesperson.

**Payment terms.** Assign a real term to every customer. Leaving a wholesaler who
genuinely receives 30 days recorded as Immediate makes the aged receivables
report meaningless.

**Credit limits.** Set one per customer. A distributor's largest single loss is
usually a receivable, not a theft.

**Reordering rules.** Set minimum and maximum quantities per product, with a lead
time reflecting the real voyage — approximately 30 days from Turkey and 45 from
China, plus clearing. A rule left at the default zero lead time advises reordering
on the day stock runs out.

---

# Part 3 — Governance and go-live

## 10. User roles — [Business input]

**Settings → Users & Companies → Users**

| Role | Access |
|---|---|
| General Manager / Owner | Settings administration, Manager on all applications |
| Accountant | Accounting: Adviser. Sales and Purchase: read only |
| Sales Officer | Sales: User, own documents only. Inventory: read only |
| Purchasing Officer | Purchase: User. Inventory: User |
| Store Keeper | Inventory: User |

Three separation-of-duties rules matter more than the permission grid itself:

- Only the accountant posts journal entries.
- Only the store keeper validates transfers.
- Whoever raises a vendor bill does not pay it.

## 11. Backups and security — [System]

**Scheduled backup.** The daily backup task is **not yet registered** on the
server. Every backup taken so far has been run manually. Registration is covered
in `scripts/REBUILD.md`.

**Restore rehearsal.** Complete the restore procedure in `scripts/RESTORE.md`
once, before real data exists. An untested backup is not a backup, and the least
costly moment to discover that is now.

**Master password.** The database master password was exposed during
implementation. It permits creation, deletion, backup and restoration of any
database on this server and must be treated as a root credential. Rotate it.

**Administrator password.** A short password was set during implementation.
Before the system is reachable from outside this machine, replace it with a
strong passphrase or enable two-factor authentication for the administrator
account.

## 12. Acceptance test — [System + Business input]

Complete one full trading cycle using a test supplier and test customer before
any real transaction, then reverse it. This is the only step that demonstrates
the configuration works rather than assuming it does.

**1. Purchase.** Raise a purchase order for two diaper lines, confirm it, receive
into QC, then move from QC to Stock.
*Expected:* stock on hand, and a journal entry against 105100 and 106100.

**2. Landed cost.** Record a landed cost against that receipt for sea freight and
customs duty. Compute, then validate.
*Expected:* freight apportioned across the two lines in proportion to their cubic
volume — not evenly, and not by weight — with unit cost rising accordingly.

This single check exercises average costing, volume-based apportionment and the
landed cost expense accounts together. It is the test most likely to reveal a
configuration error.

**3. Sale.** Raise a quotation, confirm, deliver, invoice and post.
*Expected:* revenue against 401100, cost against 501100 at the landed unit cost
rather than the purchase price, and a tax line consistent with Section 5.

**4. Reports.** Accounting → Reporting → Financial Reports → **Balance Sheet**
and **Profit and Loss**; then Audit Reports → Trial Balance; then Inventory →
Reporting → Valuation.

*Expected, and each one is worth checking separately:*

- Inventory value on the balance sheet agrees **exactly** with the stock
  valuation report. Any difference indicates an incompletely configured
  category — return to Section 3.
- `LIABILITIES + EQUITY` equals `ASSETS`. If it does not, the ledger is
  unbalanced and nothing else on the page can be trusted.
- `NET PROFIT` on the Profit and Loss equals *Profit (Loss) to report* on the
  Balance Sheet, for the same fiscal year. The P&L defaults to that year, so the
  two are directly comparable without changing any dates.
- Revenue appears under **Operating Income** and cost under **Cost of Revenue**,
  each showing 401100 and 501100 as their own rows. Once Phase 2 starts, 401200
  and 501200 appear beside them — which is the whole reason the chart keeps the
  four codes apart.
- Also once Phase 2 starts, the factory conversion accounts 503100–503400 print
  under **Cost of Revenue** with 503900 Conversion Cost Absorbed as a *negative*
  row beside them. That is correct: 503900 carries a credit, and the net of the
  five is the under/over-absorption variance flowing into Gross Profit. No change
  to the report structure is needed for any of this — lines group by
  `account_type`, so `expense_direct_cost` accounts land there on their own.

**5. Reverse** the entire cycle and confirm the accounts return to nil.

No opening balances are required. This is a clean start, so the first real
transaction is genuinely the first.

---

## Troubleshooting

| Symptom | Cause and resolution |
|---|---|
| Inventory Valuation setting is not visible on a product category | The Stock Accounting Automatic permission has not been granted. See Section 3.1. |
| *"The stock accounts should be set in order to use the automatic valuation"* | Valuation was set to Automated without completing the three stock accounts in the same save. See Section 3.3. |
| *"You are deactivating the pricelist feature"* | The Pricelists feature is off, and saving would archive all three pricelists. Discard, then enable Pricelists. See Section 1. |
| A goods receipt fails reporting a missing account | A product category is incompletely configured. Re-check all three against Section 3.2. |
| A landed cost validates but unit cost does not change | The category is not on average costing, or the product volume is zero. Both fail silently. |
| One product consistently appears unusually profitable | Its weight or volume is zero, so it absorbed no share of freight while other lines covered it. |
| A landed cost fails on validation with a missing account | The landed cost service products have no expense account. See Section 4. |
| Import rejected with *"Account codes must be unique"* | The account code already exists in the chart. Do not renumber by hand; refer to `scripts/REBUILD.md`. |
| `LIABILITIES + EQUITY` does not equal `ASSETS` | The ledger itself is unbalanced — the statement is reporting it faithfully. Run the Trial Balance for the same date; total debits must equal total credits. |
| An account appears on no section of the Balance Sheet | Its account type is one the statement does not place, `off_balance` being the only one excluded on purpose. Check the account type, then Accounting → Configuration → Financial Reports → Financial Report Structure. |
| A section shows `$ 0.00` that should have a figure | *Hide Lines at 0* is unticked, or the accounts carry a type that feeds a different section. Untick *Show Individual Accounts* to see section totals alone. |
| *"...has formula ... which refers to ... No line with that code exists"* | A formula on a report line names a line code that is not on that statement. Fix it in Financial Report Structure; the code must belong to the same statement. |

For anything not listed, the application log is the authoritative record. Its
location and the escalation procedure are given in `scripts/REBUILD.md`.
