"""Build the SomGreen chart of accounts on a freshly created database.

Run from the host, from the repository root:

    docker compose run --rm -T -v ./data/phase1-trading:/mnt/data app \
        odoo shell -d somgreen --workers=0 --max-cron-threads=0 --log-level=warn \
        < scripts/setup_chart_of_accounts.py

WHY THIS IS A SCRIPT AND NOT A UI IMPORT
----------------------------------------
`data/phase1-trading/accounts.csv` cannot simply be imported. Odoo's generic
chart is already loaded by then, and the two charts overlap three ways:

  * Two codes collide outright (101300, 201100) and the import aborts with
    "Account codes must be unique".
  * Twelve more accounts mean the same thing under a different code or a
    different spelling. Those import silently and leave the trial balance with
    two accounts per concept, which is far worse than an error.
  * The generic accounts are wired into journals and into `ir.default`, so
    deleting them up front is not possible either.

So the script RETARGETS. Where the generic chart already carries an account for
a concept we also carry, it rewrites that account's code and name to ours and
keeps the record id. Every journal default, partner default and category
default that pointed at it stays valid, with no repointing. Only genuinely new
accounts get created.

The script is idempotent: running it a second time reports no changes.
"""

import csv
import io
import os

CSV_PATH = os.environ.get("SOMGREEN_ACCOUNTS_CSV", "/mnt/data/accounts.csv")

# Generic chart code -> our code. Same concept, so keep the record and rewrite it.
RETARGET = {
    "121000": "103100",   # Account Receivable      -> Accounts Receivable
    "211000": "201100",   # Account Payable         -> Accounts Payable
    "128000": "107100",   # Prepaid Expenses        -> Prepaid Expenses
    "450000": "409100",   # Other Income            -> Other Income
    "441000": "409200",   # Foreign Exchange Gain   -> Foreign Exchange Gain
    "641000": "609100",   # Foreign Exchange Loss   -> Foreign Exchange Loss
    "101501": "101100",   # Cash                    -> Cash on Hand
    "101401": "101200",   # Bank                    -> Bank - Current Account (USD)
    # Phase 2. Odoo's own manufacturing pair, pulled into our 105xxx inventory
    # block. Both are asset_current and must STAY assets: material debits Cost of
    # Production on consumption and credits it on finished-goods receipt, so an
    # open manufacturing order leaves a debit balance - that is work in progress.
    # Renaming them does not disturb res_company.account_production_wip_account_id
    # or _overhead_account_id, which point at them by id and are already set.
    "110400": "105600",   # Cost of Production      -> Cost of Production
    "110500": "105700",   # Work in Progress        -> Work in Progress
}

# These two occupy codes we need and nothing references them. 101300 is the PoS
# receivable, and point_of_sale is not installed; 201100 is an unused Credit Card
# account, and a Somali importer settles in cash, bank transfer and mobile money.
FREE_FIRST = ["101300", "201100"]

# Company-wide defaults that every new product category inherits. The generic
# chart points these at its own accounts. Left alone, the category-wiring step
# would be handed the wrong ones - and they look plausible enough to accept.
CATEGORY_DEFAULTS = [
    ("property_account_income_categ_id",       "401100"),
    ("property_account_expense_categ_id",      "501100"),
    ("property_stock_account_input_categ_id",  "106100"),
    ("property_stock_account_output_categ_id", "106200"),
    ("property_stock_valuation_account_id",    "105100"),
]

JOURNAL_DEFAULTS = [
    ("INV",  "401100"),   # Customer Invoices -> Sales - Merchandise
    ("BILL", "609900"),   # Vendor Bills -> Miscellaneous Expense.
                          # NOT COGS: this account catches bill lines that carry
                          # no product account, and routing strays into COGS
                          # quietly distorts trading margin.
]

# Generic accounts that duplicate one of ours. Removed only after the defaults
# above are repointed, otherwise the delete hits a foreign key.
DUPLICATES = [
    ("110100", "105100"),  # Stock Valuation           -> Merchandise Inventory
    ("110200", "106100"),  # Stock Interim (Received)  -> Stock Interim - Received
    ("110300", "106200"),  # Stock Interim (Delivered) -> Stock Interim - Delivered
    ("141000", "107100"),  # Prepayments               -> Prepaid Expenses
    ("301000", "301100"),  # Capital                   -> Owner Capital
    ("612000", "602100"),  # Rent                      -> Rent - Warehouse and Office
    ("620000", "605100"),  # Bank Fees                 -> Bank Charges
    ("630000", "601100"),  # Salary Expenses           -> Salaries and Wages
    ("400000", "401100"),  # Product Sales             -> Sales - Merchandise
    ("600000", "609900"),  # Expenses                  -> Miscellaneous Expense
    ("500000", "501100"),  # Cost of Goods Sold        -> COGS - Merchandise
    ("230000", "203200"),  # Salary Payable            -> Salaries and Wages Payable
    ("132000", "109100"),  # Tax Receivable            -> Recoverable Taxes
    ("252000", "204100"),  # Tax Payable               -> Taxes Payable
]

# Deliberately KEPT, even though they are not in our CSV: Odoo's own plumbing
# uses them and we have no replacement. Bank Suspense (101402), the outstanding
# payment pair (101403/101404), Liquidity Transfer (101701), Undistributed
# Profits/Losses (999999), and the two tax accounts that tax repartition lines
# point at (131000 Tax Paid, 251000 Tax Received). Removing any of these breaks
# payment registration, bank reconciliation, tax or year-end close.

company = env["res.company"].search([], limit=1)
AA = env["account.account"].with_company(company)
IMD = env["ir.model.data"]


def by_code(code):
    return AA.search([("code", "=", code)], limit=1)


def set_xmlid(record, ext_id):
    """Point the CSV's external id at this account so a re-import updates it."""
    module, _, name = ext_id.partition(".")
    existing = IMD.search([("module", "=", module), ("name", "=", name)])
    if existing:
        existing.write({"model": "account.account", "res_id": record.id})
    else:
        IMD.create({
            "module": module,
            "name": name,
            "model": "account.account",
            "res_id": record.id,
        })


rows = list(csv.DictReader(io.open(CSV_PATH, encoding="utf-8")))
by_our_code = {r["code"]: r for r in rows}
print("read %d rows from %s" % (len(rows), CSV_PATH))

# --- chart template -------------------------------------------------------
if not company.chart_template:
    somalia = env["res.country"].search([("code", "=", "SO")], limit=1)
    usd = env["res.currency"].search([("name", "=", "USD")], limit=1)
    usd.active = True
    company.partner_id.country_id = somalia.id
    company.currency_id = usd.id
    # Somalia has no l10n_so, so _guess_chart_template resolves to generic_coa
    # on its own; naming it explicitly just makes that legible.
    env["account.chart.template"].try_loading("generic_coa", company, install_demo=False)
    print("loaded generic_coa (country Somalia, currency USD)")
else:
    print("chart template already loaded: %s" % company.chart_template)

# --- free the two blocked codes -------------------------------------------
for code in FREE_FIRST:
    account = by_code(code)
    if not account:
        continue
    # Only free a code THIS CSV actually claims. Without it, running the script
    # with the Phase 2 CSV - which names neither 101300 nor 201100 - leaves `row`
    # empty below, falls through the name check and tries to DELETE Mobile Money
    # and Accounts Payable. Payable is referenced and would be blocked; Mobile
    # Money would very likely go.
    if code not in by_our_code:
        continue
    # On a re-run these codes hold OUR accounts (Mobile Money, Accounts Payable),
    # put there by the create/retarget passes below. Deleting them would be the
    # opposite of the intent, so recognise them by name and leave them alone.
    row = by_our_code.get(code)
    if row and account.name == row["name"]:
        print("kept     %s %s (already ours)" % (code, account.name))
        continue
    was = account.name
    try:
        with env.cr.savepoint():
            if code == "101300":
                company.account_default_pos_receivable_account_id = False
            account.unlink()
        print("freed    %s %s" % (code, was))
    except Exception as exc:
        print("WARNING  %s could not be freed: %s" % (code, str(exc).splitlines()[0][:70]))

# --- retarget the overlapping accounts ------------------------------------
for generic_code, our_code in RETARGET.items():
    account = by_code(generic_code)
    if not account:
        continue
    # Same reasoning as FREE_FIRST above: RETARGET spans both phases, so skip any
    # entry whose target this CSV does not define rather than raising KeyError.
    row = by_our_code.get(our_code)
    if not row:
        continue
    was = account.name
    account.write({
        "code": row["code"],
        "name": row["name"],
        "account_type": row["account_type"],
        "reconcile": row["reconcile"] in ("1", "True", "true"),
    })
    set_xmlid(account, row["id"])
    print("retarget %s %-26s -> %s %s" % (generic_code, was[:26], row["code"], row["name"]))

# --- create everything else -----------------------------------------------
created = 0
for row in rows:
    if by_code(row["code"]):
        continue
    account = AA.create({
        "code": row["code"],
        "name": row["name"],
        "account_type": row["account_type"],
        "reconcile": row["reconcile"] in ("1", "True", "true"),
    })
    set_xmlid(account, row["id"])
    created += 1
print("created  %d new accounts" % created)

# --- repoint defaults BEFORE deleting anything ----------------------------
for field, code in CATEGORY_DEFAULTS:
    account = by_code(code)
    if account:
        env["ir.default"].set("product.category", field, account.id, company_id=company.id)

for journal_code, code in JOURNAL_DEFAULTS:
    journal = env["account.journal"].search([("code", "=", journal_code)], limit=1)
    account = by_code(code)
    if journal and account:
        journal.default_account_id = account.id

print("repointed %d category defaults, %d journal defaults"
      % (len(CATEGORY_DEFAULTS), len(JOURNAL_DEFAULTS)))
env.cr.flush()

# --- remove the duplicates ------------------------------------------------
removed = blocked = 0
for generic_code, kept_code in DUPLICATES:
    account = by_code(generic_code)
    if not account:
        continue
    was = account.name
    try:
        # A savepoint per account. Without it, one blocked delete rolls back the
        # defaults repointed above, which makes every later delete fail too.
        with env.cr.savepoint():
            account.unlink()
        removed += 1
        print("removed  %s %-26s (kept %s)" % (generic_code, was[:26], kept_code))
    except Exception as exc:
        blocked += 1
        print("BLOCKED  %s %-26s %s" % (generic_code, was[:26], str(exc).splitlines()[0][:70]))

env.cr.commit()

missing = [r["code"] for r in rows if not by_code(r["code"])]
print("---")
print("removed %d duplicates, %d blocked" % (removed, blocked))
print("total accounts: %d" % AA.search_count([]))
print("missing from our chart: %s" % (", ".join(missing) if missing else "none"))
