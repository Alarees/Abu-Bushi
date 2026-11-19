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


class AgePayableReport(models.TransientModel):
    """For creating Aged Payable report"""
    _name = 'age.payable.report'
    _inherit = 'dynamic.report.mixin'
    _description = 'Aged Payable Report'

    @api.model
    @report_access
    def view_report(self):
        """Open liability_payable items aged as of today, grouped by partner."""
        return self._aged_payload('liability_payable', 'credit', formatted=False)

    @api.model
    @report_access
    def get_filter_values(self, date, partner):
        """Same report as of ``date`` ('YYYY-MM-DD') for the given partners."""
        return self._aged_payload(
            'liability_payable', 'credit', date, partner, formatted=False)

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
        if end_date:
            sheet.merge_range('C3:G3', f"{end_date}", filter_body)
        if data['filters']['partner']:
            display_names = [partner.get('display_name', 'undefined') for
                             partner in data['filters']['partner']]
            display_names_str = ', '.join(display_names)
            sheet.merge_range('C4:G4', display_names_str, filter_body)
        if data:
            if report_action == 'dynamic_accounts_report.action_aged_payable':
                sheet.write(6, col, ' ', sub_heading)
                sheet.write(6, col + 1, 'Invoice Date', sub_heading)
                sheet.write(6, col + 2, 'Amount Currency', sub_heading)
                sheet.write(6, col + 3, 'Currency', sub_heading)
                sheet.merge_range(6, col + 4, 6, col + 5, 'Account',
                                  sub_heading)
                sheet.merge_range(6, col + 6, 6, col + 7, 'Expected Date',
                                  sub_heading)
                sheet.write(6, col + 8, 'At Date', sub_heading)
                sheet.write(6, col + 9, '1-30', sub_heading)
                sheet.write(6, col + 10, '31-60', sub_heading)
                sheet.write(6, col + 11, '61-90', sub_heading)
                sheet.write(6, col + 12, '91-120', sub_heading)
                sheet.write(6, col + 13, 'Older', sub_heading)
                sheet.write(6, col + 14, 'Total', sub_heading)
                row = 6
                for move_line in data['move_lines']:
                    row += 1
                    sheet.write(row, col, move_line, txt_name)
                    sheet.write(row, col + 1, ' ', txt_name)
                    sheet.write(row, col + 2, ' ', txt_name)
                    sheet.write(row, col + 3, ' ', txt_name)
                    sheet.merge_range(row, col + 4, row, col + 5, ' ',
                                      txt_name)
                    sheet.merge_range(row, col + 6, row, col + 7, ' ',
                                      txt_name)
                    sheet.write(row, col + 8,
                                data['total'][move_line]['diff0_sum'],
                                txt_name)
                    sheet.write(row, col + 9,
                                data['total'][move_line]['diff1_sum'],
                                txt_name)
                    sheet.write(row, col + 10,
                                data['total'][move_line]['diff2_sum'],
                                txt_name)
                    sheet.write(row, col + 11,
                                data['total'][move_line]['diff3_sum'],
                                txt_name)
                    sheet.write(row, col + 12,
                                data['total'][move_line]['diff4_sum'],
                                txt_name)
                    sheet.write(row, col + 13,
                                data['total'][move_line]['diff5_sum'],
                                txt_name)
                    sheet.write(row, col + 14,
                                data['total'][move_line]['credit_sum'],
                                txt_name)
                    for rec in data['data'][move_line]:
                        row += 1
                        sheet.write(row, col, rec['move_name'] + (rec['name'] or ""), txt_name)
                        sheet.write(row, col + 1, rec['date'],
                                    txt_name)
                        sheet.write(row, col + 2, rec['amount_currency'],
                                    txt_name)
                        sheet.write(row, col + 3, rec['currency_id'][1],
                                    txt_name)
                        sheet.merge_range(row, col + 4, row, col + 5,
                                          rec['account_id'][1],
                                          txt_name)
                        sheet.merge_range(row, col + 6, row, col + 7,
                                          rec['date_maturity'],
                                          txt_name)
                        sheet.write(row, col + 8, rec['diff0'], txt_name)
                        sheet.write(row, col + 9, rec['diff1'], txt_name)
                        sheet.write(row, col + 10, rec['diff2'], txt_name)
                        sheet.write(row, col + 11, rec['diff3'], txt_name)
                        sheet.write(row, col + 12, rec['diff4'], txt_name)
                        sheet.write(row, col + 13, rec['diff5'], txt_name)
                        sheet.write(row, col + 14, ' ', txt_name)
                sheet.merge_range(row + 1, col, row + 1, col + 7, 'Total',
                                  filter_head)
                sheet.write(row + 1, col + 8,
                            data['grand_total']['diff0_sum'],
                            filter_head)
                sheet.write(row + 1, col + 9,
                            data['grand_total']['diff1_sum'],
                            filter_head)
                sheet.write(row + 1, col + 10,
                            data['grand_total']['diff2_sum'],
                            filter_head)
                sheet.write(row + 1, col + 11,
                            data['grand_total']['diff3_sum'],
                            filter_head)
                sheet.write(row + 1, col + 12,
                            data['grand_total']['diff4_sum'],
                            filter_head)
                sheet.write(row + 1, col + 13,
                            data['grand_total']['diff5_sum'],
                            filter_head)
                sheet.write(row + 1, col + 14,
                            data['grand_total']['total_credit'],
                            filter_head)
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
