# -*- coding: utf-8 -*-
"""Print options for the Balance Sheet.

A statement of position has one date, not a range: balances accumulate from the
beginning of the books to the As of Date. _get_date_from is left returning None,
which is what tells the engine to stay cumulative.
"""

from odoo import fields, models


class SomgreenBalanceSheetWizard(models.TransientModel):
    _name = 'somgreen.balance.sheet.wizard'
    _inherit = 'somgreen.account.report.wizard.mixin'
    _description = 'SomGreen Balance Sheet Options'

    PDF_ACTION = 'somgreen_account_reports.action_report_balance_sheet_pdf'
    HTML_ACTION = 'somgreen_account_reports.action_report_balance_sheet_html'

    date_to = fields.Date(
        string='As of Date', required=True,
        default=lambda self: fields.Date.context_today(self),
        help="Balances are accumulated from the beginning of the books up to "
             "this date.",
    )
