# -*- coding: utf-8 -*-
{
    'name': 'SomGreen Financial Reports',
    'version': '18.0.1.1.0',
    'category': 'Accounting/Accounting',
    'summary': 'Balance Sheet and Profit and Loss in the Odoo Enterprise layout, for Odoo 18 Community',
    'description': """
SomGreen Financial Reports
==========================

Two statements that read the way an accountant expects them to read::

    BALANCE SHEET                 PROFIT AND LOSS
      ASSETS                        INCOME
        Current Assets                Gross Profit
          Bank and Cash Accounts        Operating Income
          Receivables                   Cost of Revenue
          ...                         Other Income
      LIABILITIES                   EXPENSES
      EQUITY                          Operating Expenses
      LIABILITIES + EQUITY            Depreciation
                                    NET PROFIT

That is the Odoo *Enterprise* layout. Odoo 18 Community cannot produce it, and
this module supplies it without Enterprise.

WHY THIS EXISTS
---------------
Odoo 18 Community ships the `account.report` MODEL (account/models/account_report.py)
but not the ENGINE that drives it: there is no `_get_lines`, no
`account.report.custom.handler`, and no `account_report` client action. The only
`account.report` records Community defines are the three generic TAX reports in
`account/data/account_reports_data.xml`. The reporting engine is Enterprise-only.

The stack's stand-in is `accounting_pdf_reports` (Odoo Mates), whose statements
are the pre-v14 `account.financial.report` tree - two levels deep, equity folded
into liabilities, no LIABILITIES + EQUITY check line, and a P&L with no Gross
Profit. Neither can be reshaped into the layout above by data alone.

WHY IT DOES NOT REUSE `account.financial.report`
------------------------------------------------
This module depends on `accounting_pdf_reports` for one thing only: the
"Financial Reports" menu it creates, and archiving the two menu items it puts
there that these statements replace. None of its reporting code is used,
deliberately:

* Its engine calls `account.move.line._query_get()`, a v13 API back-ported in
  `accounting_pdf_reports/models/account_move_line.py`. That back-port filters on
  `account_id.include_initial_balance`, a field Odoo 18 no longer has on
  `account.account`. The branch is currently unreachable only because
  `account.common.report._build_contexts()` always sets `strict_range=True`.
* It needs a re-created `account.account.type` lookup table, because Odoo 18 made
  `account_type` a plain Selection on `account.account`. This module reads that
  Selection directly - no shim model.
* Its shared `account.common.report` base offers `date_from` on a Balance Sheet,
  which silently turns a statement of position into a statement of period
  movement. Here the start date lives on the Profit and Loss wizard alone.

Everything else the vendor bundle provides - Trial Balance, General Ledger,
Partner Ledger, Aged Payable/Receivable, Cash Book, Day Book, Bank Book, Tax
Report, Journal Audit - is untouched and still in use.

SIGN CONVENTION
---------------
Every line on both statements prints as a POSITIVE number, so that::

    ASSETS      ==  LIABILITIES + EQUITY
    NET PROFIT  ==  INCOME - EXPENSES

hold on the face of the reports, exactly as Odoo Enterprise prints them. The
reversal is declared once on LIABILITIES, once on EQUITY, once on INCOME, and
once back to normal on Cost of Revenue (an expense sitting under INCOME). Every
descendant, down to individual account rows, inherits it - see the
`effective_sign` computed field on `somgreen.account.report.line`. Deduction is
expressed in the structure instead, through the Subtract operand on an aggregate
line, so expenses never have to be printed as negative numbers to make the
arithmetic work.

CUMULATIVE VERSUS PERIOD
------------------------
One flag decides it: whether the print options carry a start date.

* Balance Sheet - As of Date only. Every account line runs from the beginning of
  the books, which is what a statement of position requires.
* Profit and Loss - a date range, defaulting to the fiscal year containing today.

The Balance Sheet line "Profit (Loss) to report" is always measured over the
fiscal year, so it agrees with NET PROFIT on the Profit and Loss for the same
year.

STRUCTURE IS DATA, NOT CODE
---------------------------
Both trees live in `data/balance_sheet_lines.xml` and
`data/profit_and_loss_lines.xml` as `somgreen.account.report.line` records,
marked `noupdate="1"` so a module upgrade never undoes an accountant's edits.
Accounting > Configuration > Financial Reports > Financial Report Structure
exposes them for tuning. Adding an account to the chart needs no change here -
lines group by `account_type`, so the separate trading and manufacturing sales
and COGS accounts print as their own rows, and Phase 2 accounts appear on their
own.
""",
    'author': 'SomGreen',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'accounting_pdf_reports',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/paperformat.xml',
        'report/financial_report_templates.xml',
        'data/report_action.xml',
        'data/balance_sheet_lines.xml',
        'data/profit_and_loss_lines.xml',
        'wizard/balance_sheet_wizard_views.xml',
        'wizard/profit_and_loss_wizard_views.xml',
        'views/account_report_line_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
