# -*- coding: utf-8 -*-
{
    'name': 'SomGreen Executive Dashboard',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Light-themed executive dashboard: sales, purchases, inventory, receivables/payables, profit',
    'description': """
SomGreen Executive Dashboard
=============================

A single-page overview of the business for management: total sales, total
purchases, inventory value, accounts receivable, accounts payable and gross
profit, plus a monthly sales trend chart and a top-5-products-by-sales table.

Read-only. Adds one new menu, one client action and one server-side
AbstractModel that aggregates figures already present in Accounting, Sales,
Purchase and Inventory. Nothing in those apps is modified.
""",
    'author': 'SomGreen',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'account',
        'sale',
        'purchase',
        'stock',
        'mrp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'somgreen_dashboard/static/src/scss/dashboard.scss',
            'somgreen_dashboard/static/src/js/dashboard.js',
            'somgreen_dashboard/static/src/xml/dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
