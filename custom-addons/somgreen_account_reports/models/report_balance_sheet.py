# -*- coding: utf-8 -*-
"""Balance Sheet - a statement of position.

All the work is in somgreen.account.report.engine. Carrying no date_from is what
makes every account line cumulative from the beginning of the books, which is the
whole difference between this report and the Profit and Loss.
"""

from odoo import models


class ReportBalanceSheet(models.AbstractModel):
    _name = 'report.somgreen_account_reports.report_balance_sheet'
    _inherit = 'somgreen.account.report.engine'
    _description = 'SomGreen Balance Sheet'

    REPORT_KEY = 'balance_sheet'
    REPORT_TITLE = 'Balance Sheet'
    WIZARD_MODEL = 'somgreen.balance.sheet.wizard'
