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
from .report_mixin import report_access


class BankBookReport(models.TransientModel):
    """For creating Bank Book report"""
    _name = 'bank.book.report'
    _inherit = 'dynamic.report.mixin'
    _description = 'Account Bank Book Report'

    @api.model
    @report_access
    def view_report(self):
        """Initial load: all posted lines of the bank journals."""
        return self._journal_book_payload('bank')

    @api.model
    @report_access
    def get_filter_values(self, partner_id, data_range, account_list,
                          options):
        """Filtered Bank Book.

        :param partner_id: partner ids
        :param data_range: keyword or {'start_date', 'end_date'}
        :param account_list: account ids (not names)
        :param options: {'draft': True} to include draft entries
        """
        return self._journal_book_payload(
            'bank', partner_id, data_range, account_list, options)

    @api.model
    @report_access
    def get_xlsx_report(self, data, response, report_name, report_action):
        """
        Generate an Excel report based on the provided data.
        :param data: The data used to generate the report.
        :type data: str (JSON format)
        :param response: The response object to write the report to.
        :type response: object
        :param report_name: The name of the report.
        :type report_name: str
        :return: None
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
        sheet.write('B4:b4', 'Partners', filter_head)
        sheet.write('B5:b4', 'Accounts', filter_head)
        sheet.write('B6:b4', 'Options', filter_head)
        if start_date or end_date:
            sheet.merge_range('C3:G3', f"{start_date} to {end_date}",
                              filter_body)
        if data['filters']['partner']:
            display_names = [partner.get('display_name', 'undefined') for
                             partner in data['filters']['partner']]
            display_names_str = ', '.join(display_names)
            sheet.merge_range('C4:G4', display_names_str, filter_body)
        if data['filters']['account']:
            account_keys_str = ', '.join(data['filters']['account'])
            sheet.merge_range('C5:G5', account_keys_str, filter_body)
        if data['filters']['options']:
            option_keys = list(data['filters']['options'].keys())
            option_keys_str = ', '.join(option_keys)
            sheet.merge_range('C6:G6', option_keys_str, filter_body)
        if data:
            if report_action == 'dynamic_accounts_report.action_bank_book':
                sheet.write(8, col, ' ', sub_heading)
                sheet.merge_range('B9:C9', 'Journal', sub_heading)
                sheet.merge_range('D9:E9', 'Partner', sub_heading)
                sheet.merge_range('F9:G9', 'Ref', sub_heading)
                sheet.merge_range('H9:I9', 'Move', sub_heading)
                sheet.merge_range('J9:K9', 'Entry Label', sub_heading)
                sheet.merge_range('L9:M9', 'Debit', sub_heading)
                sheet.merge_range('N9:O9', 'Credit', sub_heading)
                sheet.merge_range('P9:Q9', 'Balance', sub_heading)
                row = 8
                for move_line in data['move_lines']:
                    row += 1
                    sheet.write(row, col, move_line, txt_name)
                    sheet.merge_range(row, col + 1, row, col + 2, ' ',
                                      txt_name)
                    sheet.merge_range(row, col + 3, row, col + 4, ' ',
                                      txt_name)
                    sheet.merge_range(row, col + 5, row, col + 6, ' ',
                                      txt_name)
                    sheet.merge_range(row, col + 7, row, col + 8, ' ',
                                      txt_name)
                    sheet.merge_range(row, col + 9, row, col + 10, ' ',
                                      txt_name)
                    sheet.merge_range(row, col + 11, row, col + 12,
                                      data['total'][move_line]['total_debit'],
                                      txt_name)
                    sheet.merge_range(row, col + 13, row, col + 14,
                                      data['total'][move_line]['total_credit'],
                                      txt_name)
                    sheet.merge_range(row, col + 15, row, col + 16,
                                      data['total'][move_line]['total_debit'] -
                                      data['total'][move_line]['total_credit'],
                                      txt_name)
                    for rec in data['data'][move_line]:
                        row += 1
                        if rec['partner_id']:
                            partner = rec['partner_id'][1]
                        else:
                            partner = ' '
                        sheet.write(row, col, rec['date'], txt_name)
                        sheet.merge_range(row, col + 1, row, col + 2,
                                          rec['journal_id'][1],
                                          txt_name)
                        sheet.merge_range(row, col + 3, row, col + 4, partner,
                                          txt_name)
                        sheet.merge_range(row, col + 5, row, col + 6,
                                          rec['ref'], txt_name)
                        sheet.merge_range(row, col + 7, row, col + 8,
                                          rec['move_name'],
                                          txt_name)
                        sheet.merge_range(row, col + 9, row, col + 10,
                                          rec['name'],
                                          txt_name)
                        sheet.merge_range(row, col + 11, row, col + 12,
                                          rec['debit_display'], txt_name)
                        sheet.merge_range(row, col + 13, row, col + 14,
                                          rec['credit_display'], txt_name)
                        sheet.merge_range(row, col + 15, row, col + 16, ' ',
                                          txt_name)
                sheet.merge_range(row + 1, col, row + 1, col + 10, 'Total',
                                  filter_head)
                sheet.merge_range(row + 1, col + 11, row + 1, col + 12,
                                  data['grand_total']['total_debit_display'],
                                  filter_head)
                sheet.merge_range(row + 1, col + 13, row + 1, col + 14,
                                  data['grand_total']['total_credit_display'],
                                  filter_head)
                sheet.merge_range(row + 1, col + 15, row + 1, col + 16,
                                  float(data['grand_total']['total_debit']) -
                                  float(data['grand_total']['total_credit']),
                                  filter_head)
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
