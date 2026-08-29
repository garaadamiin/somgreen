# -*- coding: utf-8 -*-
"""Print options shared by the SomGreen financial statements.

Deliberately NOT built on `account.common.report` (accounting_pdf_reports):
that base requires a `date_from` and a non-empty `journal_ids`. A Balance Sheet
with a start date is not a balance sheet - it silently becomes a statement of
period movement - so the start date belongs on the Profit and Loss wizard alone,
not in a base both statements share.
"""

from odoo import _, fields, models
from odoo.exceptions import UserError


class SomgreenAccountReportWizardMixin(models.AbstractModel):
    _name = 'somgreen.account.report.wizard.mixin'
    _description = 'SomGreen Financial Report Options'

    # Set by each concrete wizard.
    PDF_ACTION = None
    HTML_ACTION = None

    company_id = fields.Many2one(
        'res.company', string='Company', required=True, readonly=True,
        default=lambda self: self.env.company,
    )
    date_to = fields.Date(
        string='End Date', required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    target_move = fields.Selection(
        selection=[('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves', required=True, default='posted',
    )
    journal_ids = fields.Many2many(
        'account.journal', string='Journals',
        domain="[('company_id', '=', company_id)]",
        help="Leave empty to include every journal. Filtering a financial "
             "statement by journal produces a partial view of the books - use "
             "it for investigation, not for reporting.",
    )
    hide_zero_lines = fields.Boolean(
        string='Hide Lines at 0', default=True,
        help="Drop sections and accounts with a nil balance, which is what "
             "keeps the statement short and readable.",
    )
    show_accounts = fields.Boolean(
        string='Show Individual Accounts', default=True,
        help="Print each account beneath its section. Untick for section "
             "totals only.",
    )

    def _get_date_from(self):
        """None for a cumulative statement, a date for a period one.

        The engine keys off this: no date_from means every account line runs
        from the beginning of the books.
        """
        self.ensure_one()
        return None

    def _prepare_report_data(self):
        self.ensure_one()
        if not self.company_id.currency_id:
            raise UserError(_("Company %s has no currency set.", self.company_id.display_name))
        date_from = self._get_date_from()
        return {
            'form': {
                'company_id': self.company_id.id,
                'date_from': fields.Date.to_string(date_from) if date_from else None,
                'date_to': fields.Date.to_string(self.date_to),
                'target_move': self.target_move,
                'journal_ids': self.journal_ids.ids,
                'hide_zero_lines': self.hide_zero_lines,
                'show_accounts': self.show_accounts,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(self.PDF_ACTION).report_action(
            self, data=self._prepare_report_data(), config=False)

    def action_view_html(self):
        self.ensure_one()
        return self.env.ref(self.HTML_ACTION).report_action(
            self, data=self._prepare_report_data(), config=False)
