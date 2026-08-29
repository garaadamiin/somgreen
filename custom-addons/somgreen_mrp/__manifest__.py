# -*- coding: utf-8 -*-
{
    'name': 'SomGreen Manufacturing',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Tissue packing configuration for SomGreen (Phase 2)',
    'description': """
SomGreen Manufacturing - tissue packing
=======================================

Phase 2 of a two-phase rollout. Install this ONLY when the factory actually
starts. It layers the production configuration on top of `somgreen_config`:

* Raw Materials, Finished Goods and Waste product categories
* RAW / PACK / WIP / FG locations under the warehouse Stock location
* The Roll (100 m) purchase unit for carton-sealing tape
* The Packing Line work center
* The Production analytic account, added to the existing Cost Centre plan

Installing this module also installs `mrp`, which is why it is separate: a
company that only buys and resells has no business carrying Manufacturing
menus, and uninstalling `mrp` later is far more disruptive than never having
installed it.

Nothing in `somgreen_config` changes when this is installed. The trading
categories, locations and landed-cost products keep working exactly as before,
and traded goods keep their own Income and COGS accounts, so resale margin
stays readable apart from manufacturing margin.

Accounts are imported from `data/phase2-manufacturing/accounts.csv` and wired
to the new categories in the UI - see the project README, Phase 2.
""",
    'author': 'SomGreen',
    'license': 'LGPL-3',
    'depends': [
        'somgreen_config',
        'mrp',
    ],
    'data': [
        'data/uom_data.xml',
        'data/product_category.xml',
        'data/stock_location.xml',
        'data/mrp_workcenter.xml',
        'data/analytic_account.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
