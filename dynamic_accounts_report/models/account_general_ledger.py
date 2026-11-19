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
import io
import json
import xlsxwriter
from odoo import api, models
from .report_mixin import report_access, clean_ids


class AccountGeneralLedger(models.TransientModel):
    """For creating General Ledger report"""
    _name = 'account.general.ledger'
    _inherit = 'dynamic.report.mixin'
    _description = 'General Ledger Report'

    _LINE_FIELDS = ['date', 'name', 'move_name', 'debit', 'credit',
                    'partner_id', 'account_id', 'journal_id', 'move_id',
                    'analytic_line_ids']

    @api.model
    def _build_payload(self, domain):
        """Build the legacy payload from a move line domain using one
        search + one read (instead of one read per line)."""
        lines = self.env['account.move.line'].search(
            domain + self._report_company_domain(), order='date, id')
        grouped = self._report_group_lines(lines, self._LINE_FIELDS)
        account_dict = {
            'journal_ids': self.env['account.journal'].search_read(
                [('company_id', 'in', self.env.companies.ids)], ['name']),
            'analytic_ids': self.env['account.analytic.account'].search_read(
                [], ['name']),
        }
        account_totals = {}
        symbol = self._report_currency_symbol()
        for account in lines.mapped('account_id'):
            rows = grouped.get(account.id, [])
            account_dict[account.display_name] = rows
            account_totals[account.display_name] = {
                'total_debit': round(sum(r[0]['debit'] for r in rows), 2),
                'total_credit': round(sum(r[0]['credit'] for r in rows), 2),
                'currency_id': symbol,
                'account_id': account.id,
            }
        account_dict['account_totals'] = account_totals
        return account_dict

    @api.model
    @report_access
    def view_report(self, option=None, tag=None):
        """Initial load: every posted line of the selected companies."""
        return self._build_payload([('parent_state', '=', 'posted')])

    @api.model
    @report_access
    def get_filter_values(self, journal_id, date_range, options, analytic,
                          method=None, partner_ids=None):
        """Filtered General Ledger.

        :param journal_id: journal ids
        :param date_range: keyword or {'start_date', 'end_date'}
        :param options: {'draft': True} to include draft entries
        :param analytic: analytic account ids
        :param method: {'cash': True} -> cash basis journals only
        :param partner_ids: partner ids (new filter)
        """
        domain = [('parent_state', 'in', self._report_states(options))]
        journal_id = clean_ids(journal_id)
        if journal_id:
            domain.append(('journal_id', 'in', journal_id))
        if method and 'cash' in method:
            domain.append(
                ('journal_id', 'in', self._report_cash_basis_journal_ids()))
        analytic = clean_ids(analytic)
        if analytic:
            domain.append(('analytic_line_ids.account_id', 'in', analytic))
        domain += self._report_partner_domain(partner_ids)
        domain += self._report_date_domain(date_range)
        return self._build_payload(domain)

    @api.model
    @report_access
    def get_xlsx_report(self, data, response, report_name, report_action):
        """
        Generate an XLSX report based on the provided data and write it to the
        response stream.

        :param data: The data used to generate the report.
        :type data: str (JSON format)

        :param response: The response object to write the generated report to.
        :type response: werkzeug.wrappers.Response

        :param report_name: The name of the report.
        :type report_name: str
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
        sheet = workbook.add_worksheet()
        head = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '15px'})
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
        sheet.write('B4:b4', 'Journals', filter_head)
        sheet.write('B5:b4', 'Analytic', filter_head)
        sheet.write('B6:b4', 'Options', filter_head)
        if start_date or end_date:
            sheet.merge_range('C3:G3', f"{start_date} to {end_date}",
                              filter_body)
        if data['filters']['journal']:
            display_names = [journal for
                             journal in data['filters']['journal']]
            display_names_str = ', '.join(display_names)
            sheet.merge_range('C4:G4', display_names_str, filter_body)
        if data['filters']['analytic']:
            display_names = [analytic for
                             analytic in data['filters']['analytic']]
            account_keys_str = ', '.join(display_names)
            sheet.merge_range('C5:G5', account_keys_str, filter_body)
        if data['filters']['options']:
            option_keys = list(data['filters']['options'].keys())
            option_keys_str = ', '.join(option_keys)
            sheet.merge_range('C6:G6', option_keys_str, filter_body)
        if data:
            if report_action == 'dynamic_accounts_report.action_general_ledger':
                sheet.write(8, col, ' ', sub_heading)
                sheet.write(8, col + 1, 'Date', sub_heading)
                sheet.merge_range('C9:E9', 'Communication', sub_heading)
                sheet.merge_range('F9:G9', 'Partner', sub_heading)
                sheet.merge_range('H9:I9', 'Debit', sub_heading)
                sheet.merge_range('J9:K9', 'Credit', sub_heading)
                sheet.merge_range('L9:M9', 'Balance', sub_heading)
                row = 8
                if data['account']:
                    for account in data['account']:
                        row += 1
                        sheet.write(row, col, account, txt_name)
                        sheet.write(row, col + 1, ' ', txt_name)
                        sheet.merge_range(row, col + 2, row, col + 4, ' ', txt_name)
                        sheet.merge_range(row, col + 5, row, col + 6, ' ',
                                          txt_name)
                        sheet.merge_range(row, col + 7, row, col + 8,
                                          data['total'][account]['total_debit_display'],
                                          txt_name)
                        sheet.merge_range(row, col + 9, row, col + 10,
                                          data['total'][account]['total_credit_display'],
                                          txt_name)
                        sheet.merge_range(row, col + 11, row, col + 12,
                                          data['total'][account]['balance_display'],
                                          txt_name)
                        for rec in data['account_data'][account]:
                            row += 1
                            partner = rec[0]['partner_id']
                            name = partner[1] if partner else None
                            sheet.write(row, col, rec[0]['move_name'], txt_name)
                            sheet.write(row, col + 1, rec[0]['date'], txt_name)
                            sheet.merge_range(row, col + 2, row, col + 4,
                                              rec[0]['name'], txt_name)
                            sheet.merge_range(row, col + 5, row, col + 6, name,
                                              txt_name)
                            sheet.merge_range(row, col + 7, row, col + 8,
                                              rec[0]['debit'],
                                              txt_name)
                            sheet.merge_range(row, col + 9, row, col + 10,
                                              rec[0]['credit'], txt_name)
                            sheet.merge_range(row, col + 11, row, col + 12, ' ',
                                              txt_name)
                    row += 1
                    sheet.merge_range(row, col, row, col + 6, 'Total',
                                      filter_head)
                    sheet.merge_range(row, col + 7, row, col + 8,
                                      data['grand_total']['total_debit_display'],
                                      filter_head)
                    sheet.merge_range(row, col + 9, row, col + 10,
                                      data['grand_total']['total_credit_display'],
                                      filter_head)
                    sheet.merge_range(row, col + 11, row, col + 12,
                                      float(data['grand_total']['total_debit']) -
                                      float(data['grand_total']['total_credit']),
                                      filter_head)
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
