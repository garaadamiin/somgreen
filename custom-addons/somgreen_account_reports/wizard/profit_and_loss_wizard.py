# -*- coding: utf-8 -*-
"""Print options for the Profit and Loss.

A statement of performance covers a period, so this wizard adds a start date and
defaults to the fiscal year containing today - which is what an accountant wants
nine times out of ten, and what makes NET PROFIT here agree with the
"Profit (Loss) to report" line on the Balance Sheet.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _default_fiscalyear(self, key):
    company = self.env.company
    return company.compute_fiscalyear_dates(fields.Date.context_today(self))[key]


class SomgreenProfitLossWizard(models.TransientModel):
    _name = 'somgreen.profit.loss.wizard'
    _inherit = 'somgreen.account.report.wizard.mixin'
    _description = 'SomGreen Profit and Loss Options'

    PDF_ACTION = 'somgreen_account_reports.action_report_profit_and_loss_pdf'
    HTML_ACTION = 'somgreen_account_reports.action_report_profit_and_loss_html'

    date_from = fields.Date(
        string='Start Date', required=True,
        default=lambda self: _default_fiscalyear(self, 'date_from'),
        help="Defaults to the start of the fiscal year containing today.",
    )
    date_to = fields.Date(
        string='End Date', required=True,
        default=lambda self: _default_fiscalyear(self, 'date_to'),
        help="Defaults to the end of the fiscal year containing today.",
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("The start date must not be after the end date."))

    def _get_date_from(self):
        self.ensure_one()
        return self.date_from
