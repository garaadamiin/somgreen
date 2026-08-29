# -*- coding: utf-8 -*-
"""Structure of a SomGreen financial report.

One record per printed row. The tree is shipped as data in
``data/balance_sheet_lines.xml`` with ``noupdate="1"`` so the accountant can
rename, resequence or add lines without a module upgrade undoing the work.

The design mirrors what Odoo Enterprise's ``account.report.line`` does, minus the
formula engine: each line declares WHERE its number comes from (``line_type``),
WHICH accounts feed it (``account_type_codes``) and HOW it is displayed (``sign``,
``style_override``). Nothing about the SomGreen chart of accounts is hardcoded -
lines group by ``account_type``, so accounts added later land in the right
section on their own.
"""

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# A formula is line codes joined by + and -, e.g. "BS_LIABILITIES + BS_EQUITY".
# Referring to operands by CODE rather than by database id is deliberate: a
# subtotal whose operands are its own children cannot name them with ref() at the
# point the XML creates it, and a second <record> for the same xmlid is silently
# skipped in a noupdate="1" file. Codes sidestep the ordering problem entirely,
# and they stay readable in the UI. It is also how Odoo Enterprise writes
# account.report.expression formulas.
FORMULA_RE = re.compile(r'^[+-]?\s*\w+(\s*[+-]\s*\w+)*$')
FORMULA_TERM_RE = re.compile(r'([+-]?)\s*(\w+)')

# Account types that make up the profit and loss statement. Used by the
# 'net_profit' and 'unallocated_prior' line types to work out retained and
# current-year earnings, which is the only part of a balance sheet that cannot
# be derived from a plain account_type grouping.
PROFIT_AND_LOSS_TYPES = (
    'income',
    'income_other',
    'expense',
    'expense_direct_cost',
    'expense_depreciation',
)

# Odoo posts no year-end closing entry in Community, so the balance of
# 'equity_unaffected' accounts (SomGreen: 999999 Undistributed Profits/Losses)
# is only part of the prior-year result. The rest is the P&L of closed years.
UNAFFECTED_EARNINGS_TYPE = 'equity_unaffected'


class SomgreenAccountReportLine(models.Model):
    _name = 'somgreen.account.report.line'
    _description = 'SomGreen Financial Report Line'
    _order = 'sequence, id'

    name = fields.Char(
        string='Name', required=True, translate=True,
        help="Label printed in the Name column.",
    )
    code = fields.Char(
        string='Code', required=True,
        help="Stable handle for this line, e.g. BS_ASSETS. Referenced by other "
             "lines and by the report engine; changing it can break an "
             "aggregate line that points at it.",
    )
    report_key = fields.Selection(
        selection=[
            ('balance_sheet', 'Balance Sheet'),
            ('profit_and_loss', 'Profit and Loss'),
        ],
        string='Report', required=True, default='balance_sheet',
        help="Which statement this line belongs to. One model carries both "
             "trees; the engine reads whichever one the report asks for.",
    )
    parent_id = fields.Many2one(
        'somgreen.account.report.line', string='Parent', ondelete='cascade', index=True,
    )
    child_ids = fields.One2many(
        'somgreen.account.report.line', 'parent_id', string='Children',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    level = fields.Integer(
        string='Level', compute='_compute_level', store=True, recursive=True,
        help="Depth in the tree. Drives indentation and, unless overridden, the "
             "row styling.",
    )

    line_type = fields.Selection(
        selection=[
            ('header', 'Header (no value)'),
            ('sum', 'Sum of children'),
            ('account_type', 'Accounts of a type'),
            ('net_profit', 'Current year profit or loss'),
            ('unallocated_prior', 'Previous years unallocated earnings'),
            ('aggregate', 'Formula over other lines'),
        ],
        string='Type', required=True, default='sum',
        help="Header: prints an em dash instead of a number.\n"
             "Sum of children: total of the lines nested under this one.\n"
             "Accounts of a type: total of every account whose type is listed "
             "in Account Types.\n"
             "Current year profit or loss: net of the P&L accounts over the "
             "fiscal year containing the As of Date.\n"
             "Previous years unallocated earnings: net of the P&L accounts "
             "before that fiscal year, plus the Current Year Earnings accounts.\n"
             "Formula over other lines: line codes combined with + and -, taken "
             "at their displayed value.",
    )
    account_type_codes = fields.Char(
        string='Account Types',
        help="Comma-separated Odoo account types, e.g. "
             "'liability_current,liability_credit_card'. Only used when Type is "
             "'Accounts of a type'.",
    )
    formula = fields.Char(
        string='Formula',
        help="How a 'Formula over other lines' line is computed, written as "
             "line codes joined by + and -, e.g. 'BS_LIABILITIES + BS_EQUITY' "
             "or 'PL_OPERATING_INCOME - PL_COST_OF_REVENUE'. Operands are taken "
             "at their displayed value.\n\n"
             "This is what lets the Profit and Loss print expenses as positive "
             "numbers and still deduct them: the subtraction lives in the "
             "structure rather than in the sign of the amount.",
    )

    sign = fields.Selection(
        selection=[('1', 'Preserve balance sign'), ('-1', 'Reverse balance sign')],
        string='Sign',
        help="Leave empty to inherit from the parent line. Set 'Reverse' on "
             "LIABILITIES and EQUITY so credit balances print as positive "
             "numbers and ASSETS equals LIABILITIES + EQUITY.",
    )
    effective_sign = fields.Integer(
        string='Effective Sign', compute='_compute_effective_sign', recursive=True,
        help="This line's own sign, or the nearest ancestor's if it has none.",
    )

    show_accounts = fields.Boolean(
        string='Show Accounts',
        help="Print one row per account beneath this line, labelled 'code name'.",
    )
    hide_if_zero = fields.Boolean(
        string='Hide at Zero', default=True,
        help="Drop this row when its value is zero and every row nested under it "
             "is dropped too. Clear it on the section headings that must always "
             "print.",
    )
    style_override = fields.Selection(
        selection=[
            ('section', 'Section (bold, shaded)'),
            ('subsection', 'Sub-section (bold)'),
            ('regular', 'Regular'),
        ],
        string='Style',
        help="Leave empty to derive from the level: 0-1 section, 2 sub-section, "
             "3 and deeper regular.",
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'A report line with this code already exists.'),
    ]

    # ------------------------------------------------------------------
    # Computes and constraints
    # ------------------------------------------------------------------

    @api.depends('parent_id', 'parent_id.level')
    def _compute_level(self):
        for line in self:
            line.level = line.parent_id.level + 1 if line.parent_id else 0

    @api.depends('sign', 'parent_id', 'parent_id.effective_sign')
    def _compute_effective_sign(self):
        for line in self:
            if line.sign:
                line.effective_sign = int(line.sign)
            elif line.parent_id:
                line.effective_sign = line.parent_id.effective_sign
            else:
                line.effective_sign = 1

    @api.constrains('parent_id')
    def _check_parent_recursion(self):
        # Odoo 18 renamed _check_recursion to _has_cycle (odoo/models.py).
        if self._has_cycle('parent_id'):
            raise ValidationError(_("A report line cannot be its own ancestor."))

    @api.constrains('account_type_codes')
    def _check_account_type_codes(self):
        """Fail loudly on a typo.

        An unknown account type would otherwise contribute a silent 0.00 and the
        balance sheet would quietly stop balancing.
        """
        valid = set(self.env['account.account']._fields['account_type'].get_values(self.env))
        for line in self:
            unknown = sorted(set(line._get_account_types()) - valid)
            if unknown:
                raise ValidationError(_(
                    "Unknown account type(s) on report line '%(line)s': %(unknown)s.\n"
                    "Valid types are: %(valid)s",
                    line=line.name,
                    unknown=', '.join(unknown),
                    valid=', '.join(sorted(valid)),
                ))

    @api.constrains('line_type', 'account_type_codes', 'formula')
    def _check_line_type_operands(self):
        for line in self:
            if line.line_type == 'account_type' and not line._get_account_types():
                raise ValidationError(_(
                    "Report line '%s' groups accounts by type but names no "
                    "account type.", line.name,
                ))
            if line.line_type == 'aggregate':
                if not (line.formula or '').strip():
                    raise ValidationError(_(
                        "Report line '%s' is a formula line but has no formula.",
                        line.name,
                    ))
                if not FORMULA_RE.match(line.formula.strip()):
                    raise ValidationError(_(
                        "Report line '%(line)s' has a malformed formula: %(formula)s\n"
                        "Write line codes joined by + and -, for example "
                        "'BS_LIABILITIES + BS_EQUITY'.",
                        line=line.name, formula=line.formula,
                    ))
        # Whether each code actually resolves is checked when the report runs,
        # not here: a subtotal may legitimately name lines that are created after
        # it in the same data file, so existence cannot be asserted at write time.

    # ------------------------------------------------------------------
    # Helpers used by the report engine
    # ------------------------------------------------------------------

    def _get_account_types(self):
        """Return this line's account types as a clean list."""
        self.ensure_one()
        return [code.strip() for code in (self.account_type_codes or '').split(',') if code.strip()]

    def _parse_formula(self):
        """Return the formula as [(factor, code), ...], factor being 1.0 or -1.0."""
        self.ensure_one()
        return [
            (-1.0 if sign == '-' else 1.0, code)
            for sign, code in FORMULA_TERM_RE.findall((self.formula or '').strip())
        ]

    def _get_style(self):
        """Row styling: explicit override, else derived from the level."""
        self.ensure_one()
        if self.style_override:
            return self.style_override
        if self.level <= 1:
            return 'section'
        if self.level == 2:
            return 'subsection'
        return 'regular'

    def _get_lines_in_order(self):
        """Depth-first walk of the tree, siblings ordered by sequence.

        Same shape as accounting_pdf_reports' _get_children_by_order, but driven
        from the roots so the caller gets the whole report in print order.
        """
        ordered = self.env['somgreen.account.report.line']
        for line in self.sorted(lambda l: (l.sequence, l.id)):
            ordered |= line
            ordered |= line.child_ids._get_lines_in_order()
        return ordered

    @api.model
    def _get_report_root_lines(self, report_key):
        """Top-level lines of a report, in sequence order."""
        return self.search([
            ('report_key', '=', report_key),
            ('parent_id', '=', False),
        ], order='sequence, id')
