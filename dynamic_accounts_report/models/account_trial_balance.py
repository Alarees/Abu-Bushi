# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#############################################################################
import calendar
import io
import json
import xlsxwriter
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.tools.date_utils import get_month, get_fiscal_year, \
    get_quarter_number, subtract
from .report_mixin import report_access, clean_ids, to_date


class AccountTrialBalance(models.TransientModel):
    """For creating Trial Balance report"""
    _name = 'account.trial.balance'
    _inherit = 'dynamic.report.mixin'
    _description = 'Trial Balance Report'

    @api.model
    def _sums_by_account(self, domain):
        """{account_id: (debit, credit)} using one grouped SQL query
        (previously: two ``search`` per account and per period)."""
        result = {}
        for account, debit, credit in self.env[
                'account.move.line']._read_group(
                domain, ['account_id'], ['debit:sum', 'credit:sum']):
            result[account.id] = (debit or 0.0, credit or 0.0)
        return result

    @api.model
    def _shift_end(self, end_date, months):
        """Shift a period end back ``months`` months, keeping "last day of
        the month" semantics (30 Apr - 1 month = 31 Mar, not 30 Mar)."""
        shifted = end_date - relativedelta(months=months)
        if (end_date + relativedelta(days=1)).day == 1:
            shifted += relativedelta(day=31)
        return shifted

    @api.model
    @report_access
    def view_report(self):
        """Current month trial balance. Returns (accounts, {journal_ids})."""
        today = fields.Date.context_today(self)
        month_start, month_end = get_month(today)
        data = self.get_filter_values(
            month_start.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d'),
            None, None, [], [], None, None)
        journals = self._report_journals()
        for row in data:
            row.pop('journal_ids', None)
        return data, {'journal_ids': journals}

    @api.model
    def _report_journals(self):
        return self.env['account.journal'].search_read(
            [('company_id', 'in', self.env.companies.ids)], ['name'])

    @api.model
    @report_access
    def get_filter_values(self, start_date, end_date, comparison_number,
                          comparison_type, journal_list, analytic, options,
                          method, partner_ids=None):
        """Trial balance for [start_date, end_date] with optional comparison
        periods, journal / analytic / partner filters.

        Values are returned as raw floats (the front-end formats them with
        the user's number format).
        """
        start = to_date(start_date)
        end = to_date(end_date)
        if comparison_type == 'year':
            start = get_fiscal_year(start)[0]
            end = get_fiscal_year(end)[1]
        count = int(comparison_number or 0)
        count = max(0, min(count, 24))
        base = [('parent_state', 'in', self._report_states(options))]
        base += self._report_company_domain()
        journal_list = clean_ids(journal_list)
        if journal_list:
            base.append(('journal_id', 'in', journal_list))
        analytic = clean_ids(analytic)
        if analytic:
            base.append(('analytic_line_ids.account_id', 'in', analytic))
        if method and 'cash' in method:
            base.append(('journal_id', 'in',
                         self._report_cash_basis_journal_ids()))
        base += self._report_partner_domain(partner_ids)

        def shift(delta):
            if comparison_type == 'year':
                return subtract(start, years=delta), subtract(end, years=delta)
            months = delta * (3 if comparison_type == 'quarter' else 1)
            return (subtract(start, months=months),
                    self._shift_end(end, months))

        initial_start = shift(count)[0] if count else start
        initial = self._sums_by_account(base + [('date', '<', initial_start)])
        periods = {}
        labels = {}
        if count and comparison_type in ('month', 'quarter'):
            labels['dynamic_date_num0'] = self._period_label(
                start, comparison_type)
            for i in range(1, count + 1):
                p_start, p_end = shift(i)
                periods[i] = self._sums_by_account(
                    base + [('date', '>=', p_start), ('date', '<=', p_end)])
                if comparison_type in ('month', 'quarter'):
                    labels['dynamic_date_num%d' % i] = self._period_label(
                        p_start, comparison_type)
        current = self._sums_by_account(
            base + [('date', '>=', start), ('date', '<=', end)])
        # every account that has at least one line (same as before)
        account_ids = {
            account.id for account, in self.env[
                'account.move.line']._read_group(
                self._report_company_domain(), ['account_id'])}
        accounts = self.env['account.account'].browse(account_ids).sorted(
            lambda a: (a.code or '', a.id))
        journals = self._report_journals()
        rows = []
        for account in accounts:
            init_d, init_c = initial.get(account.id, (0.0, 0.0))
            cur_d, cur_c = current.get(account.id, (0.0, 0.0))
            sum_d, sum_c = init_d + cur_d, init_c + cur_c
            for i in range(1, count + 1):
                p_d, p_c = periods[i].get(account.id, (0.0, 0.0))
                sum_d += p_d
                sum_c += p_c
            diff = round(sum_d - sum_c, 2)
            row = {
                'account': account.display_name,
                'account_id': account.id,
                'journal_ids': journals,
                'initial_total_debit': round(init_d, 2),
                'initial_total_credit': round(init_c, 2),
                'total_debit': round(cur_d, 2),
                'total_credit': round(cur_c, 2),
                'end_total_debit': diff if diff > 0 else 0.0,
                'end_total_credit': abs(diff) if diff <= 0 else 0.0,
            }
            if count:
                if labels:
                    row['dynamic_date_num'] = labels
                # column 1 = oldest period (same ordering as before)
                for i in range(1, count + 1):
                    p_d, p_c = periods[count + 1 - i].get(
                        account.id, (0.0, 0.0))
                    row['dynamic_total_debit_%d' % i] = round(p_d, 2)
                    row['dynamic_total_credit_%d' % i] = round(p_c, 2)
            rows.append(row)
        return rows

    @api.model
    def _period_label(self, date, comparison_type):
        if comparison_type == 'quarter':
            return 'Q %s %s' % (get_quarter_number(date), date.year)
        if comparison_type == 'year':
            return str(date.year)
        return '%s %s' % (calendar.month_abbr[date.month], date.year)

    @api.model
    def get_month_name(self, date):
        """Abbreviated month name (kept for backward compatibility)."""
        return calendar.month_abbr[date.month]

    @api.model
    @report_access
    def get_xlsx_report(self, data, response, report_name, report_action):
        """
        Generate an XLSX report based on provided data and response stream.
        Generates an Excel workbook with specified report format, including
        subheadings,column headers, and row data for the given financial report
        data.
        :param str data: JSON-encoded data for the report.
        :param response: Response object to stream the generated report.
        :param str report_name: Name of the financial report.
        """
        data = json.loads(data)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            # SECURITY: never turn cell text into formulas / links
            # (partner or label starting with '=' would execute in Excel)
            'strings_to_formulas': False,
            'strings_to_urls': False,
            'strings_to_numbers': False,
        })
        start_date = data['filters']['start_date'] if \
            data['filters']['start_date'] else ''
        end_date = data['filters']['end_date'] if \
            data['filters']['end_date'] else ''
        head = workbook.add_format(
            {'font_size': 15, 'align': 'center', 'bold': True})
        sheet = workbook.add_worksheet()
        sub_heading = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px',
             'border': 1, 'bg_color': '#D3D3D3',
             'border_color': 'black'})
        filter_head = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px',
             'border': 1, 'bg_color': '#D3D3D3',
             'border_color': 'black'})
        filter_body = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px'})
        side_heading_sub = workbook.add_format(
            {'align': 'left', 'bold': True, 'font_size': '10px',
             'border': 1,
             'border_color': 'black'})
        side_heading_sub.set_indent(1)
        txt_name = workbook.add_format({'font_size': '10px', 'border': 1})
        txt_name.set_indent(2)
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 15)
        sheet.set_column(3, 3, 15)
        col = 0
        sheet.write('A1:b1', report_name, head)
        sheet.write('B3:b4', 'Date Range', filter_head)
        sheet.write('B4:b4', 'Comparison', filter_head)
        sheet.write('B5:b4', 'Journal', filter_head)
        sheet.write('B6:b4', 'Account', filter_head)
        sheet.write('B7:b4', 'Option', filter_head)
        if start_date or end_date:
            sheet.merge_range('C3:G3', f"{start_date} to {end_date}",
                              filter_body)
        if data['filters']['comparison_number_range']:
            sheet.merge_range('C4:G4',
                              f"{data['filters']['comparison_type']} : {data['filters']['comparison_number_range']}",
                              filter_body)
        if data['filters']['journal']:
            display_names = [journal for
                             journal in data['filters']['journal']]
            display_names_str = ', '.join(display_names)
            sheet.merge_range('C5:G5', display_names_str, filter_body)
        if data['filters']['account']:
            account_keys = [account.get('display_name', 'undefined') for
                            account in data['filters']['account']]
            account_keys_str = ', '.join(account_keys)
            sheet.merge_range('C6:G6', account_keys_str, filter_body)
        if data['filters']['options']:
            option_keys = list(data['filters']['options'].keys())
            option_keys_str = ', '.join(option_keys)
            sheet.merge_range('C7:G7', option_keys_str, filter_body)
        sheet.write(9, col, '', sub_heading)
        # sheet.merge_range(9, col + 1, 9, col + 2, 'Initial Balance',
        #                   sub_heading)
        i = 1  # starting offset

        # Initial Balance header
        sheet.merge_range(9, col + i, 9, col + i + 1, 'Initial Balance', sub_heading)
        sheet.write(10, col + i, 'Debit', sub_heading)
        sheet.write(10, col + i + 1, 'Credit', sub_heading)
        i += 2

        # Dynamic date headers (safely)
        dynamic_dates = {}
        if data.get('data') and len(data['data']) > 0 and len(data['data'][0]) > 0:
            dynamic_dates = data['data'][0][0].get('dynamic_date_num', {})

        if data.get('apply_comparison') and dynamic_dates:
            for key, display in dynamic_dates.items():
                sheet.merge_range(9, col + i, 9, col + i + 1, display, sub_heading)
                sheet.write(10, col + i, 'Debit', sub_heading)
                sheet.write(10, col + i + 1, 'Credit', sub_heading)
                i += 2
        else:
            for date_view in data.get('date_viewed', []):
                sheet.merge_range(9, col + i, 9, col + i + 1, date_view, sub_heading)
                sheet.write(10, col + i, 'Debit', sub_heading)
                sheet.write(10, col + i + 1, 'Credit', sub_heading)
                i += 2

        # End Balance header
        sheet.merge_range(9, col + i, 9, col + i + 1, 'End Balance', sub_heading)
        sheet.write(10, col + i, 'Debit', sub_heading)
        sheet.write(10, col + i + 1, 'Credit', sub_heading)

        if data:
            if report_action == 'dynamic_accounts_report.action_trial_balance':
                row = 11
                for move_line in data['data'][0]:
                    sheet.write(row, col, move_line['account'],
                                side_heading_sub)
                    sheet.write(row, col + 1, move_line['initial_total_debit'],
                                txt_name)
                    sheet.write(row, col + 2,
                                move_line['initial_total_credit'], txt_name)
                    j = 3
                    if data['apply_comparison']:
                        number_of_periods = data['comparison_number_range']
                        for num in number_of_periods:
                            sheet.write(row, col + j, move_line[
                                'dynamic_total_debit_' + str(num)], txt_name)
                            sheet.write(row, col + j + 1, move_line[
                                'dynamic_total_credit_' + str(num)], txt_name)
                            j += 2
                    sheet.write(row, col + j, move_line['total_debit'],
                                txt_name)
                    sheet.write(row, col + j + 1, move_line['total_credit'],
                                txt_name)
                    sheet.write(row, col + j + 2, move_line['end_total_debit'],
                                txt_name)
                    sheet.write(row, col + j + 3,
                                move_line['end_total_credit'], txt_name)
                    row += 1
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
