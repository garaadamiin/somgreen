# -*- coding: utf-8 -*-
import calendar
from datetime import date, timedelta

from odoo import api, models
from odoo.tools import formatLang

# Fallback account codes for the current chart of accounts, used only when a
# company has no account tagged with the expected account_type (e.g. a fresh
# database before the accountant finishes classifying the chart).
FALLBACK_CODES = {
    'asset_receivable': '103100',
    'liability_payable': '201100',
    'expense_direct_cost': '501100',
}


class SomgreenDashboard(models.AbstractModel):
    """Read-only aggregation layer for the executive dashboard client action.

    Every query here runs under sudo() and is scoped explicitly by
    company_id: the dashboard is meant for a manager who may not hold the
    Sales/Purchase/Inventory group memberships needed to read those models
    directly, and it only ever returns aggregated sums or a short top-5 list,
    never raw records.
    """
    _name = 'somgreen.dashboard'
    _description = 'SomGreen Executive Dashboard'

    def _get_companies(self):
        companies = self.env.companies
        return companies, companies.ids

    def _default_dates(self, date_from, date_to):
        today = date.today()
        if not date_to:
            date_to = today
        else:
            date_to = date.fromisoformat(date_to)
        if not date_from:
            date_from = date_to - timedelta(days=90)
        else:
            date_from = date.fromisoformat(date_from)
        return date_from, date_to

    def _account_domain(self, account_type, company_ids):
        """Return a domain on account.account for account_type, falling back
        to the reference chart-of-accounts code if nothing is classified
        with that type yet."""
        Account = self.env['account.account'].sudo()
        accounts = Account.search([
            ('account_type', '=', account_type),
            ('company_ids', 'in', company_ids),
        ])
        if accounts:
            return [('account_id', 'in', accounts.ids)]
        code = FALLBACK_CODES.get(account_type)
        if code:
            accounts = Account.search([('code', '=', code)])
            if accounts:
                return [('account_id', 'in', accounts.ids)]
        return [('account_id', '=', -1)]

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        companies, company_ids = self._get_companies()
        company = self.env.company
        currency = company.currency_id
        date_from, date_to = self._default_dates(date_from, date_to)

        AccountMove = self.env['account.move'].sudo()
        AML = self.env['account.move.line'].sudo()
        SVL = self.env['stock.valuation.layer'].sudo()

        # 1. Total Sales: posted customer invoices/credit notes (account.move),
        # net of tax, in company currency. Credit notes subtract naturally
        # because amount_untaxed_signed is already negative for out_refund.
        sales_moves = AccountMove.search([
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            ('company_id', 'in', company_ids),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ])
        total_sales = sum(sales_moves.mapped('amount_untaxed_signed'))

        # 2. Total Purchases: posted vendor bills/refunds, same convention,
        # sign-flipped since amount_untaxed_signed is negative for in_invoice.
        purchase_moves = AccountMove.search([
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '=', 'posted'),
            ('company_id', 'in', company_ids),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ])
        total_purchases = -sum(purchase_moves.mapped('amount_untaxed_signed'))

        # 3. Inventory Value: current on-hand valuation, independent of the
        # date filter (it is a balance, not a period flow).
        svl_groups = SVL.read_group(
            [('company_id', 'in', company_ids)],
            ['value:sum'], [],
        )
        inventory_value = svl_groups[0]['value'] if svl_groups else 0.0

        # 4/5. Receivables / Payables: balance of receivable/payable accounts
        # as of date_to (a balance-sheet snapshot, not a period flow).
        ar_domain = [('parent_state', '=', 'posted'), ('company_id', 'in', company_ids),
                     ('date', '<=', date_to)] + self._account_domain('asset_receivable', company_ids)
        ar_groups = AML.read_group(ar_domain, ['balance:sum'], [])
        receivables = ar_groups[0]['balance'] if ar_groups else 0.0

        ap_domain = [('parent_state', '=', 'posted'), ('company_id', 'in', company_ids),
                     ('date', '<=', date_to)] + self._account_domain('liability_payable', company_ids)
        ap_groups = AML.read_group(ap_domain, ['balance:sum'], [])
        payables = -(ap_groups[0]['balance'] if ap_groups else 0.0)

        # 6. Gross Profit = Total Sales - COGS (expense_direct_cost accounts,
        # same period as sales).
        cogs_domain = [('parent_state', '=', 'posted'), ('company_id', 'in', company_ids),
                        ('date', '>=', date_from), ('date', '<=', date_to)
                        ] + self._account_domain('expense_direct_cost', company_ids)
        cogs_groups = AML.read_group(cogs_domain, ['balance:sum'], [])
        cogs = cogs_groups[0]['balance'] if cogs_groups else 0.0
        gross_profit = total_sales - cogs

        def fmt(value):
            return formatLang(self.env, value, currency_obj=currency)

        kpis = [
            {'key': 'total_sales', 'label': 'Total Sales', 'value': total_sales, 'formatted': fmt(total_sales)},
            {'key': 'total_purchases', 'label': 'Total Purchases', 'value': total_purchases, 'formatted': fmt(total_purchases)},
            {'key': 'inventory_value', 'label': 'Inventory Value', 'value': inventory_value, 'formatted': fmt(inventory_value)},
            {'key': 'receivables', 'label': 'Accounts Receivable', 'value': receivables, 'formatted': fmt(receivables)},
            {'key': 'payables', 'label': 'Accounts Payable', 'value': payables, 'formatted': fmt(payables)},
            {'key': 'gross_profit', 'label': 'Gross Profit', 'value': gross_profit, 'formatted': fmt(gross_profit)},
        ]

        return {
            'company_name': company.name,
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'kpis': kpis,
            'monthly_sales': self._get_monthly_sales(company_ids),
            'top_products': self._get_top_products(company_ids, date_from, date_to),
        }

    def _get_monthly_sales(self, company_ids):
        """Monthly sales for the current calendar year, Jan through the
        current month, independent of the dashboard's date-range filter."""
        today = date.today()
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)

        AccountMove = self.env['account.move'].sudo()
        groups = AccountMove.read_group(
            [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('state', '=', 'posted'),
                ('company_id', 'in', company_ids),
                ('invoice_date', '>=', year_start),
                ('invoice_date', '<=', year_end),
            ],
            ['amount_untaxed_signed:sum'],
            ['invoice_date:month_number'],
        )
        by_month = {}
        for group in groups:
            month_index = group['invoice_date:month_number']
            if not month_index:
                continue
            by_month[int(month_index)] = group['amount_untaxed_signed']

        labels, values = [], []
        for month_index in range(1, today.month + 1):
            labels.append(calendar.month_abbr[month_index])
            values.append(round(by_month.get(month_index, 0.0), 2))
        return {'labels': labels, 'values': values}

    def _get_top_products(self, company_ids, date_from, date_to):
        AML = self.env['account.move.line'].sudo()
        domain = [
            ('move_id.move_type', 'in', ['out_invoice', 'out_refund']),
            ('parent_state', '=', 'posted'),
            ('display_type', '=', 'product'),
            ('product_id', '!=', False),
            ('company_id', 'in', company_ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        groups = AML.read_group(domain, ['balance:sum'], ['product_id'], orderby='balance asc', limit=5)
        currency = self.env.company.currency_id
        products = []
        for group in groups:
            amount = -(group['balance'] or 0.0)
            products.append({
                'name': group['product_id'][1] if group['product_id'] else 'Unknown',
                'amount': amount,
                'formatted': formatLang(self.env, amount, currency_obj=currency),
            })
        return products
