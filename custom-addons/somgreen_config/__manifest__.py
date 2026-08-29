# -*- coding: utf-8 -*-
{
    'name': 'SomGreen Configuration',
    'version': '18.0.2.1.0',
    'category': 'Inventory',
    'summary': 'Core and trading configuration for SomGreen (Phase 1)',
    'description': """
SomGreen Configuration - core and trading
=========================================

Phase 1 of a two-phase rollout. This module carries everything the TRADING
business needs and nothing that only manufacturing needs:

* Account groups: the code-prefix hierarchy behind the Chart of Accounts
* Unit of measure rounding corrections
* Weight and volume decimal precision, for accurate landed-cost splits
* Merchandise product categories with AVCO costing and automated valuation
* Quarantine and damaged-goods locations for imported stock
* Landed-cost service products for sea-freighted merchandise
* The Cost Centre analytic plan
* Wholesale / Retail / Export pricelist shells

DELIBERATELY DOES NOT DEPEND ON `mrp`. A company that only buys and resells
should not carry Manufacturing. When the tissue factory starts, install
`somgreen_mrp`, which depends on this module and adds the production
categories, locations, work center and analytic account on top. Nothing here
has to change for that to happen.

Deliberately NOT included: anything referencing chart-of-accounts records. Odoo
18 generates per-company account XML IDs dynamically, so hardcoding them here
would make this module brittle and company-specific. `data/account_group.xml` is
not an exception to that rule - account groups reference no account, only code
prefixes, so they carry none of the fragility. Accounts are imported from
`data/phase1-trading/accounts.csv` and wired to categories in the UI with the
accountant - see the project README.
""",
    'author': 'SomGreen',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'stock_landed_costs',
        'purchase',
        'sale_management',
        'account',
    ],
    'data': [
        'data/account_group.xml',
        'data/uom_data.xml',
        'data/decimal_precision.xml',
        'data/product_category.xml',
        'data/stock_location.xml',
        'data/landed_cost_products.xml',
        'data/analytic_plan.xml',
        'data/product_pricelist.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
