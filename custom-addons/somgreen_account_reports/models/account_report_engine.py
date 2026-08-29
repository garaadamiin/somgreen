# -*- coding: utf-8 -*-
"""Shared engine behind the SomGreen financial statements.

Turns a somgreen.account.report.line tree into printable rows. Both the Balance
Sheet and the Profit and Loss inherit this and differ only in REPORT_KEY,
REPORT_TITLE and WIZARD_MODEL.

Everything is expressed in terms of DISPLAYED values: a 'sum' line is the sum of
what its children print, an 'aggregate' line adds and subtracts what the lines it
names print. What you read on the page therefore adds up to what you read on the
page, and the check lines - LIABILITIES + EQUITY, NET PROFIT - tie without a
second convention running underneath.

Cumulative versus period is decided by one thing: whether the options carry a
`date_from`.

* Balance Sheet - no date_from, so every account line runs from the beginning of
  the books to the As of Date. That is what a statement of position needs.
* Profit and Loss - date_from present, so every account line covers that range
  only. That is what a statement of performance needs.
"""

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang

from .account_report_line import PROFIT_AND_LOSS_TYPES, UNAFFECTED_EARNINGS_TYPE

EM_DASH = u'—'


class SomgreenAccountReportEngine(models.AbstractModel):
    _name = 'somgreen.account.report.engine'
    _description = 'SomGreen Financial Report Engine'

    # Overridden by each concrete report.
    REPORT_KEY = None
    REPORT_TITLE = None
    WIZARD_MODEL = None

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    def _get_options(self, data):
        form = (data or {}).get('form') or {}
        if form.get('company_id'):
            company = self.env['res.company'].browse(form['company_id'])
        else:
            company = self.env.company
        return {
            'company': company,
            'date_from': fields.Date.to_date(form.get('date_from')) or None,
            'date_to': fields.Date.to_date(form.get('date_to')) or fields.Date.context_today(self),
            'target_move': form.get('target_move') or 'posted',
            'journal_ids': form.get('journal_ids') or [],
            'hide_zero_lines': form.get('hide_zero_lines', True),
            'show_accounts': form.get('show_accounts', True),
        }

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def _get_move_line_domain(self, options):
        domain = [
            ('company_id', '=', options['company'].id),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if options['target_move'] == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', '!=', 'cancel'))
        if options['journal_ids']:
            domain.append(('journal_id', 'in', options['journal_ids']))
        return domain

    def _sum_by_account(self, domain):
        return {
            account.id: balance
            for account, balance in self.env['account.move.line']._read_group(
                domain, ['account_id'], ['balance:sum'],
            )
        }

    def _get_account_balances(self, options):
        """Three balance maps, all keyed by account id.

        to_date     - inception to the As of Date.
        before_from - inception to the day before date_from. Empty when the
                      report has no date_from, which makes the subtraction below
                      a no-op and leaves every line cumulative.
        before_fy   - inception to the day before the fiscal year containing the
                      As of Date. Used only to split the P&L into current-year
                      and prior-year earnings on the Balance Sheet.

        `balance` is stored in company currency, so no conversion is needed.
        """
        company = options['company']
        domain = self._get_move_line_domain(options)
        fy_start = company.compute_fiscalyear_dates(options['date_to'])['date_from']

        to_date = self._sum_by_account(domain + [('date', '<=', options['date_to'])])
        before_fy = self._sum_by_account(domain + [('date', '<', fy_start)])
        before_from = (
            self._sum_by_account(domain + [('date', '<', options['date_from'])])
            if options['date_from'] else {}
        )
        return to_date, before_fy, before_from

    def _get_accounts_by_type(self, company):
        """Accounts of the company, grouped by account_type, ordered by code.

        Two Odoo 18 details are handled here:
        * `account.account` is shared through a `company_ids` many2many, not a
          `company_id`, so the inherited _check_company_domain does not apply.
        * `code` is a company-dependent COMPUTED field (_compute_code, fed by
          code_mapping_ids), so it cannot appear in a SQL ORDER BY and the
          recordset has to carry the right company. Hence with_company() and a
          Python sort.
        """
        accounts = self.env['account.account'].with_company(company).with_context(
            # An archived account still holding a balance belongs on the report.
            active_test=False,
        ).search([('company_ids', 'in', company.ids)])

        grouped = defaultdict(list)
        for account in accounts.sorted(lambda a: (a.code or '', a.id)):
            grouped[account.account_type].append(account)
        return grouped

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def _compute_display_values(self, lines, options, to_date, before_fy, before_from, accounts_by_type):
        """Displayed value per report line, keyed by line id. None means no value."""
        values = {}
        by_code = {line.code: line for line in lines}

        def accounts_of(account_types):
            found = []
            for account_type in account_types:
                found.extend(accounts_by_type.get(account_type, []))
            return found

        def balance(account):
            """Period balance, or cumulative when the report has no date_from."""
            return to_date.get(account.id, 0.0) - before_from.get(account.id, 0.0)

        def resolve(line, seen):
            if line.id in values:
                return values[line.id]
            if line.id in seen:
                # Guarded rather than trusted: a formula cycle would
                # otherwise recurse forever.
                values[line.id] = 0.0
                return 0.0
            seen = seen | {line.id}

            sign = line.effective_sign
            line_type = line.line_type

            if line_type == 'header':
                value = None
            elif line_type == 'sum':
                value = sum(
                    resolve(child, seen) or 0.0
                    for child in line.child_ids.sorted(lambda l: (l.sequence, l.id))
                )
            elif line_type == 'aggregate':
                value = 0.0
                for factor, code in line._parse_formula():
                    operand = by_code.get(code)
                    if operand is None:
                        # Loud rather than quiet: a formula naming a line that
                        # does not exist would otherwise contribute nothing and
                        # print a total that looks right and is not.
                        raise UserError(_(
                            "Report line '%(line)s' has formula '%(formula)s', "
                            "which refers to '%(code)s'. No line with that code "
                            "exists on this statement.",
                            line=line.name, formula=line.formula, code=code,
                        ))
                    value += factor * (resolve(operand, seen) or 0.0)
            elif line_type == 'account_type':
                value = sign * sum(balance(account) for account in accounts_of(line._get_account_types()))
            elif line_type == 'net_profit':
                # Current-year result, always measured over the fiscal year
                # regardless of the report's own date range.
                value = sign * sum(
                    to_date.get(account.id, 0.0) - before_fy.get(account.id, 0.0)
                    for account in accounts_of(PROFIT_AND_LOSS_TYPES)
                )
            elif line_type == 'unallocated_prior':
                # Odoo Community posts no year-end closing entry, so prior-year
                # profit sits in two places: still on the P&L accounts of closed
                # years, and on whatever was manually moved to the Current Year
                # Earnings account.
                value = sign * (
                    sum(before_fy.get(account.id, 0.0)
                        for account in accounts_of(PROFIT_AND_LOSS_TYPES))
                    + sum(to_date.get(account.id, 0.0)
                          for account in accounts_of([UNAFFECTED_EARNINGS_TYPE]))
                )
            else:
                value = 0.0

            values[line.id] = value
            return value

        for line in lines:
            resolve(line, frozenset())
        return values

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------

    def _format_value(self, amount, currency):
        """Render an amount the way the reference layout does: "$ 765.00", "$ -300.00".

        Odoo's built-in monetary widget renders "-$ 300.00" - sign before the
        symbol - which does not match, so the string is assembled here.
        """
        text = formatLang(self.env, amount, digits=currency.decimal_places)
        if currency.position == 'before':
            return '%s %s' % (currency.symbol, text)
        return '%s %s' % (text, currency.symbol)

    def _build_rows(self, line, options, values, balances, accounts_by_type, currency):
        """Rows for one line and everything nested under it, in print order.

        Returns [] when the whole subtree is hidden. Hiding resolves bottom-up: a
        line survives if it is marked always-visible, or its own value is
        non-zero, or something under it survived.
        """
        to_date, before_from = balances

        child_rows = []
        for child in line.child_ids.sorted(lambda l: (l.sequence, l.id)):
            child_rows.extend(
                self._build_rows(child, options, values, balances, accounts_by_type, currency)
            )

        account_rows = []
        if options['show_accounts'] and line.show_accounts:
            sign = line.effective_sign
            for account_type in line._get_account_types():
                for account in accounts_by_type.get(account_type, []):
                    amount = sign * (to_date.get(account.id, 0.0) - before_from.get(account.id, 0.0))
                    if options['hide_zero_lines'] and currency.is_zero(amount):
                        continue
                    account_rows.append({
                        'name': '%s %s' % (account.code or '', account.name),
                        'value': self._format_value(amount, currency),
                        'level': line.level + 1,
                        'style': 'regular',
                        'is_account': True,
                        'has_value': True,
                    })

        value = values.get(line.id)
        has_value = value is not None
        keep = (
            not options['hide_zero_lines']
            or not line.hide_if_zero
            or (has_value and not currency.is_zero(value))
            or bool(child_rows)
            or bool(account_rows)
        )
        if not keep:
            return []

        row = {
            'name': line.name,
            'value': self._format_value(value, currency) if has_value else EM_DASH,
            'level': line.level,
            'style': line._get_style(),
            'is_account': False,
            'has_value': has_value,
        }
        return [row] + account_rows + child_rows

    def _get_report_lines(self, options):
        company = options['company']
        currency = company.currency_id

        roots = self.env['somgreen.account.report.line']._get_report_root_lines(self.REPORT_KEY)
        all_lines = roots._get_lines_in_order()

        to_date, before_fy, before_from = self._get_account_balances(options)
        accounts_by_type = self._get_accounts_by_type(company)
        values = self._compute_display_values(
            all_lines, options, to_date, before_fy, before_from, accounts_by_type)

        rows = []
        for root in roots:
            rows.extend(self._build_rows(
                root, options, values, (to_date, before_from), accounts_by_type, currency))
        return rows

    # ------------------------------------------------------------------
    # QWeb entry point
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        options = self._get_options(data)
        company = options['company']
        return {
            'doc_ids': docids,
            'doc_model': self.WIZARD_MODEL,
            'docs': self.env[self.WIZARD_MODEL].browse(docids),
            'company': company,
            'currency': company.currency_id,
            'report_title': self.REPORT_TITLE,
            'date_from': options['date_from'],
            'date_to': options['date_to'],
            'target_move': options['target_move'],
            'report_lines': self._get_report_lines(options),
        }
