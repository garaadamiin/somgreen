# -*- coding: utf-8 -*-
"""Profit and Loss - a statement of performance.

All the work is in somgreen.account.report.engine. Carrying a date_from is what
makes every account line cover a period rather than run from the beginning of the
books.
"""

from odoo import models


class ReportProfitAndLoss(models.AbstractModel):
    _name = 'report.somgreen_account_reports.report_profit_and_loss'
    _inherit = 'somgreen.account.report.engine'
    _description = 'SomGreen Profit and Loss'

    REPORT_KEY = 'profit_and_loss'
    REPORT_TITLE = 'Profit and Loss'
    WIZARD_MODEL = 'somgreen.profit.loss.wizard'
