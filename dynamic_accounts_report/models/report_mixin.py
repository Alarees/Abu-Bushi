# -*- coding: utf-8 -*-
#############################################################################
#    Shared helpers for the Dynamic Accounting Reports module.
#    Provides: access control, multi-company support, a single (correct)
#    implementation of the date-range / state / partner domains and
#    safe XLSX helpers.
#############################################################################
import functools
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import date_utils

REPORT_GROUP = 'account.group_account_readonly'
DATE_KEYWORDS = ('month', 'quarter', 'year', 'last-month', 'last-quarter',
                 'last-year')


def report_access(func):
    """Decorator: every public report entry point (called through RPC) must
    be reachable only by users that have at least read access to
    accounting. TransientModels are not protected by ir.model.access, so
    without this any internal user could call the methods."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        self._check_report_access()
        return func(self, *args, **kwargs)

    return wrapper


def to_date(value):
    """Parse 'YYYY-MM-DD' safely, raising a user friendly error."""
    if not value:
        return False
    if hasattr(value, 'year'):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        raise UserError(_("Invalid date: %s", value))


def clean_ids(values):
    """Return a list of ints from client input (drops anything else)."""
    result = []
    for value in values or []:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


class DynamicReportMixin(models.AbstractModel):
    _name = 'dynamic.report.mixin'
    _description = 'Dynamic Accounting Reports - shared helpers'

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    @api.model
    def _check_report_access(self):
        if self.env.su:
            return True
        if not self.env.user.has_group(REPORT_GROUP):
            raise AccessError(
                _("You are not allowed to access the accounting reports."))
        return True

    # ------------------------------------------------------------------
    # Multi-company
    # ------------------------------------------------------------------
    @api.model
    @report_access
    def get_company_options(self):
        """Companies the user may select + the ones currently selected.
        ``self.env.companies`` is derived from ``allowed_company_ids`` in the
        context, which Odoo validates against the user's allowed companies,
        so a forged context can never widen access."""
        selected = self.env.companies
        return {
            'companies': [{
                'id': company.id,
                'name': company.name,
                'currency': company.currency_id.name,
                'symbol': company.currency_id.symbol,
            } for company in self.env.user.company_ids],
            'selected_ids': selected.ids,
            'mixed_currency': len(selected.currency_id) > 1,
        }

    @api.model
    def _report_company_domain(self):
        """Explicit company restriction (in addition to record rules)."""
        return [('company_id', 'in', self.env.companies.ids)]

    @api.model
    def _report_currency_symbol(self):
        return self.env.company.currency_id.symbol or ''

    @api.model
    def _report_cash_basis_journal_ids(self):
        return self.env.companies.mapped('tax_cash_basis_journal_id').ids

    # ------------------------------------------------------------------
    # Domains
    # ------------------------------------------------------------------
    @api.model
    def _report_states(self, options):
        """``options`` is a dict like {'draft': True}, a list or None."""
        if options and 'draft' in options:
            return ['posted', 'draft']
        return ['posted']

    @api.model
    def _report_date_range(self, date_range):
        """Return (start, end) dates for a keyword or a {start_date,
        end_date} dict. Either bound can be False."""
        if not date_range:
            return False, False
        today = fields.Date.context_today(self)
        if isinstance(date_range, str):
            if date_range not in DATE_KEYWORDS:
                raise UserError(_("Unknown date range."))
            if date_range == 'month':
                return date_utils.get_month(today)
            if date_range == 'quarter':
                return date_utils.get_quarter(today)
            if date_range == 'year':
                return (today.replace(month=1, day=1),
                        today.replace(month=12, day=31))
            if date_range == 'last-month':
                start = today.replace(day=1) - relativedelta(months=1)
                return start, today.replace(day=1) - relativedelta(days=1)
            if date_range == 'last-quarter':
                quarter_start = date_utils.get_quarter(today)[0]
                return (quarter_start - relativedelta(months=3),
                        quarter_start - relativedelta(days=1))
            year_start = today.replace(month=1, day=1) - relativedelta(years=1)
            return year_start, year_start.replace(month=12, day=31)
        if isinstance(date_range, dict):
            return (to_date(date_range.get('start_date')),
                    to_date(date_range.get('end_date')))
        raise UserError(_("Unknown date range."))

    @api.model
    def _report_date_domain(self, date_range, field='date'):
        start, end = self._report_date_range(date_range)
        domain = []
        if start:
            domain.append((field, '>=', start))
        if end:
            domain.append((field, '<=', end))
        return domain

    @api.model
    def _report_partner_domain(self, partner_ids):
        partner_ids = clean_ids(partner_ids)
        return [('partner_id', 'in', partner_ids)] if partner_ids else []

    @api.model
    def _report_group_lines(self, lines, fields_list, key_field='account_id'):
        """Single ``read`` for all lines, grouped by the key m2o.
        Returns {key_id: [[vals], ...]} using the legacy one-item-list shape
        the front-end templates expect."""
        grouped = {}
        for vals in lines.read(fields_list):
            key = vals[key_field][0] if vals[key_field] else False
            grouped.setdefault(key, []).append([vals])
        return grouped

    @api.model
    def _journal_book_payload(self, journal_type, partner_ids=None,
                              data_range=None, account_list=None,
                              options=None):
        """Shared implementation for the Cash Book and Bank Book.

        Same payload shape as before:
        {<account display_name>: [[line], ...],
         'move_lines_total': {...}, 'accounts': [...]}
        """
        journals = self.env['account.journal'].search(
            [('type', '=', journal_type),
             ('company_id', 'in', self.env.companies.ids)])
        domain = [('parent_state', 'in', self._report_states(options)),
                  ('journal_id', 'in', journals.ids)]
        domain += self._report_company_domain()
        domain += self._report_partner_domain(partner_ids)
        account_ids = clean_ids(account_list)
        if account_ids:
            domain.append(('account_id', 'in', account_ids))
        domain += self._report_date_domain(data_range)
        lines = self.env['account.move.line'].search(domain, order='date, id')
        grouped = self._report_group_lines(
            lines, ['date', 'journal_id', 'partner_id', 'move_name', 'debit',
                    'move_id', 'credit', 'name', 'ref', 'account_id'])
        data, totals = {}, {}
        symbol = self._report_currency_symbol()
        accounts = lines.mapped('account_id')
        for account in accounts:
            rows = grouped.get(account.id, [])
            data[account.display_name] = rows
            totals[account.display_name] = {
                'total_debit': round(sum(r[0]['debit'] for r in rows), 2),
                'total_credit': round(sum(r[0]['credit'] for r in rows), 2),
                'currency_id': symbol,
            }
        data['move_lines_total'] = totals
        data['accounts'] = accounts.read(['display_name', 'name'])
        return data

    @api.model
    def _aged_payload(self, account_type, side, date=None, partner_ids=None,
                      formatted=False):
        """Shared aged partner balance (receivable / payable).

        * uses the *residual* of every open line (partial payments are no
          longer ignored, unapplied payments reduce the balance);
        * ages relative to the report date (not always "today");
        * lines without a due date fall back to their own date
          (the old payable report crashed on them).
        ``side`` is 'debit' (receivable) or 'credit' (payable); ``formatted``
        keeps the legacy "1,234.50" strings used by the receivable screen.
        """
        as_of = to_date(date) or fields.Date.context_today(self)
        domain = [('parent_state', '=', 'posted'),
                  ('account_type', '=', account_type),
                  ('reconciled', '=', False),
                  ('partner_id', '!=', False),
                  ('date', '<=', as_of)]
        domain += self._report_company_domain()
        partner_ids = clean_ids(partner_ids)
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        lines = self.env['account.move.line'].search(
            domain, order='date_maturity, date, id')
        sign = 1.0 if side == 'debit' else -1.0
        read_fields = ['name', 'move_name', 'date', 'amount_currency',
                       'account_id', 'date_maturity', 'currency_id',
                       'amount_residual', 'move_id', 'partner_id']

        def fmt(value):
            return "{:,.2f}".format(value)

        by_partner = {}
        for vals in lines.read(read_fields):
            amount = round(sign * vals.pop('amount_residual'), 2)
            due = vals['date_maturity'] or vals['date']
            days = (as_of - due).days
            buckets = [0.0] * 6
            if days <= 0:
                buckets[0] = amount
            elif days <= 30:
                buckets[1] = amount
            elif days <= 60:
                buckets[2] = amount
            elif days <= 90:
                buckets[3] = amount
            elif days <= 120:
                buckets[4] = amount
            else:
                buckets[5] = amount
            raw_currency_amount = vals['amount_currency']
            vals[side] = amount
            for index, bucket in enumerate(buckets):
                vals['diff%d' % index] = bucket
            if formatted:
                vals['raw_amount_currency'] = raw_currency_amount
                vals['raw_' + side] = amount
                for index, bucket in enumerate(buckets):
                    vals['raw_diff%d' % index] = bucket
                vals['amount_currency'] = fmt(raw_currency_amount)
                vals[side] = fmt(amount)
                for index, bucket in enumerate(buckets):
                    vals['diff%d' % index] = fmt(bucket)
            by_partner.setdefault(vals['partner_id'][0], []).append(vals)

        symbol = self._report_currency_symbol()
        partners = (self.env['res.partner'].browse(partner_ids).exists()
                    if partner_ids else
                    self.env['res.partner'].browse(list(by_partner)).sorted(
                        'name'))
        result, totals = {}, {}
        prefix = 'raw_' if formatted else ''
        for partner in partners:
            key = partner.name or str(partner.id)
            if key in result or key == 'partner_totals':
                key = '%s #%s' % (key, partner.id)
            rows = by_partner.get(partner.id, [])
            result[key] = rows
            total = {
                side + '_sum': round(sum(r[prefix + side] for r in rows), 2),
                'currency_id': symbol,
                'partner_id': partner.id,
            }
            for index in range(6):
                name = 'diff%d' % index
                value = round(sum(r[prefix + name] for r in rows), 2)
                total[name + '_sum'] = value
                if formatted:
                    total[name + '_sum_display'] = fmt(value)
            if formatted:
                total[side + '_sum_display'] = fmt(total[side + '_sum'])
            totals[key] = total
        result['partner_totals'] = totals
        return result
