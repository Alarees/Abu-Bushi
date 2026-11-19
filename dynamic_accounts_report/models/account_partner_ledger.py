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


class AccountPartnerLedger(models.TransientModel):
    """For creating Partner Ledger report"""
    _name = 'account.partner.ledger'
    _inherit = 'dynamic.report.mixin'
    _description = 'Partner Ledger Report'

    _LINE_FIELDS = ['date', 'move_name', 'account_type', 'debit', 'credit',
                    'date_maturity', 'account_id', 'journal_id', 'move_id',
                    'matching_number', 'amount_currency', 'partner_id']

    @api.model
    def _build_payload(self, domain, opening_domain=None, partner_ids=None):
        """One search + one read + one grouped query for opening balances
        (the previous version issued several queries per partner and per
        line)."""
        aml = self.env['account.move.line']
        company_domain = self._report_company_domain()
        lines = aml.search(domain + company_domain, order='date, id')
        accounts = {a.id: a.code for a in lines.account_id}
        journals = {j.id: j.code for j in lines.journal_id}
        rows = {}
        for vals in lines.read(self._LINE_FIELDS):
            account_code = accounts.get(vals['account_id'][0])
            if account_code:
                vals['jrnl'] = journals.get(vals['journal_id'][0])
                vals['code'] = account_code
            pid = vals['partner_id'][0] if vals['partner_id'] else False
            rows.setdefault(pid, []).append([vals])
        opening = {}
        if opening_domain is not None:
            for partner, debit, credit in aml._read_group(
                    opening_domain + company_domain, ['partner_id'],
                    ['debit:sum', 'credit:sum']):
                opening[partner.id] = (debit or 0.0, credit or 0.0)
        partner_ids = clean_ids(partner_ids)
        if partner_ids:
            partners = self.env['res.partner'].browse(partner_ids).exists()
        else:
            partners = self.env['res.partner'].browse(
                [pid for pid in rows if pid]).sorted('name')
        symbol = self._report_currency_symbol()
        partner_dict, partner_totals = {}, {}
        for partner in partners:
            key = partner.name or str(partner.id)
            if key in partner_dict or key == 'partner_totals':
                key = '%s #%s' % (key, partner.id)
            partner_rows = rows.get(partner.id, [])
            init_debit, init_credit = opening.get(partner.id, (0.0, 0.0))
            partner_dict[key] = partner_rows
            partner_totals[key] = {
                'total_debit': round(sum(r[0]['debit'] for r in partner_rows), 2),
                'total_credit': round(sum(r[0]['credit'] for r in partner_rows), 2),
                'currency_id': symbol,
                'partner_id': partner.id,
                'initial_balance': round(init_debit - init_credit, 2),
                'move_name': 'Initial Balance',
                'initial_debit': round(init_debit, 2),
                'initial_credit': round(init_credit, 2),
            }
        partner_dict['partner_totals'] = partner_totals
        return partner_dict

    @api.model
    @report_access
    def view_report(self, option=None, tag=None):
        """Initial load: all posted receivable / payable lines."""
        domain = [('account_type', 'in', ['liability_payable',
                                          'asset_receivable']),
                  ('parent_state', '=', 'posted'),
                  ('partner_id', '!=', False)]
        return self._build_payload(domain)

    @api.model
    @report_access
    def get_filter_values(self, partner_id, data_range, account, options):
        """Filtered Partner Ledger.

        The opening balance is now computed from *every* line dated before
        the start of the period (the previous version used invoice_date,
        which silently dropped payments and journal entries).
        """
        account_types = []
        if not account or ('Receivable' in account and 'Payable' in account):
            account_types = ['liability_payable', 'asset_receivable']
        elif 'Receivable' in account:
            account_types = ['asset_receivable']
        elif 'Payable' in account:
            account_types = ['liability_payable']
        else:
            account_types = ['liability_payable', 'asset_receivable']
        states = self._report_states(options)
        base = [('account_type', 'in', account_types),
                ('parent_state', 'in', states)]
        partner_ids = clean_ids(partner_id)
        if partner_ids:
            base.append(('partner_id', 'in', partner_ids))
        else:
            base.append(('partner_id', '!=', False))
        start, end = self._report_date_range(data_range)
        domain = list(base)
        if start:
            domain.append(('date', '>=', start))
        if end:
            domain.append(('date', '<=', end))
        opening_domain = (base + [('date', '<', start)]) if start else None
        return self._build_payload(domain, opening_domain, partner_ids)

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
        start_date = data['filters']['start_date'] if data['filters']['start_date'] else ''
        end_date = data['filters']['end_date'] if data['filters']['end_date'] else ''
        sheet = workbook.add_worksheet()

        # Define formats
        head = workbook.add_format({'font_size': 15, 'align': 'center', 'bold': True})
        head_highlight = workbook.add_format({'font_size': 10, 'align': 'center', 'bold': True})
        sub_heading = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px', 'border': 1, 'bg_color': '#D3D3D3',
             'border_color': 'black'})
        filter_head = workbook.add_format(
            {'align': 'center', 'bold': True, 'font_size': '10px', 'border': 1, 'bg_color': '#D3D3D3',
             'border_color': 'black'})
        filter_body = workbook.add_format({'align': 'center', 'bold': True, 'font_size': '10px'})
        side_heading_sub = workbook.add_format(
            {'align': 'left', 'bold': True, 'font_size': '10px', 'border': 1, 'border_color': 'black'})
        side_heading_sub.set_indent(1)
        txt_name = workbook.add_format({'font_size': '10px', 'border': 1})
        txt_name.set_indent(2)

        # Set column widths
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 15)
        sheet.set_column(3, 3, 15)

        # Write headers and filters
        col = 0
        sheet.write('A1:B1', report_name, head)
        sheet.write('B3:B4', 'Date Range', filter_head)
        sheet.write('B4:B4', 'Partners', filter_head)
        sheet.write('B5:B4', 'Accounts', filter_head)
        sheet.write('B6:B4', 'Options', filter_head)

        if start_date or end_date:
            sheet.merge_range('C3:G3', f"{start_date} to {end_date}", filter_body)

        if data['filters']['partner']:
            display_names = [partner.get('display_name', 'undefined') for partner in data['filters']['partner']]
            display_names_str = ', '.join(display_names)
            sheet.merge_range('C4:G4', display_names_str, filter_body)

        if data['filters']['account']:
            account_keys = list(data['filters']['account'].keys())
            account_keys_str = ', '.join(account_keys)
            sheet.merge_range('C5:G5', account_keys_str, filter_body)

        if data['filters']['options']:
            option_keys = list(data['filters']['options'].keys())
            option_keys_str = ', '.join(option_keys)
            sheet.merge_range('C6:G6', option_keys_str, filter_body)

        # Define a helper function to format numbers with thousand separators
        def format_number(value):
            if value is None:
                return "0.00"
            return "{:,.2f}".format(float(value))

        # Process partner data
        if data and report_action == 'dynamic_accounts_report.action_partner_ledger':
            sheet.write(8, col, ' ', sub_heading)
            sheet.write(8, col + 1, 'JNRL', sub_heading)
            sheet.write(8, col + 2, 'Account', sub_heading)
            sheet.merge_range('D9:E9', 'Ref', sub_heading)
            sheet.merge_range('F9:G9', 'Due Date', sub_heading)
            sheet.merge_range('H9:I9', 'Debit', sub_heading)
            sheet.merge_range('J9:K9', 'Credit', sub_heading)
            sheet.merge_range('L9:M9', 'Balance', sub_heading)

            row = 8
            # Ensure data['partners'] is iterable; default to empty list if None
            partners = data.get('partners', []) or []
            for partner in partners:
                row += 1
                # Format partner totals
                total_debit = data['total'][partner]['total_debit'] if data['total'] and partner in data['total'] else 0
                total_credit = data['total'][partner]['total_credit'] if data['total'] and partner in data[
                    'total'] else 0
                balance = total_debit - total_credit

                sheet.write(row, col, partner, txt_name)
                sheet.write(row, col + 1, ' ', txt_name)
                sheet.write(row, col + 2, ' ', txt_name)
                sheet.merge_range(row, col + 3, row, col + 4, ' ', txt_name)
                sheet.merge_range(row, col + 5, row, col + 6, ' ', txt_name)
                sheet.merge_range(row, col + 7, row, col + 8, format_number(total_debit), txt_name)
                sheet.merge_range(row, col + 9, row, col + 10, format_number(total_credit), txt_name)
                sheet.merge_range(row, col + 11, row, col + 12, format_number(balance), txt_name)

                # Handle initial balance
                initial_balance = data['total'][partner]['initial_balance'] if data['total'] and partner in data[
                    'total'] else 0
                if initial_balance != 0:
                    row += 1
                    initial_debit = data['total'][partner]['initial_debit'] if data['total'] and partner in data[
                        'total'] else 0
                    initial_credit = data['total'][partner]['initial_credit'] if data['total'] and partner in data[
                        'total'] else 0

                    sheet.write(row, col, '', txt_name)
                    sheet.write(row, col + 1, ' ', txt_name)
                    sheet.write(row, col + 2, ' ', txt_name)
                    sheet.merge_range(row, col + 3, row, col + 4, 'Initial Balance', head_highlight)
                    sheet.merge_range(row, col + 5, row, col + 6, ' ', txt_name)
                    sheet.merge_range(row, col + 7, row, col + 8, format_number(initial_debit), txt_name)
                    sheet.merge_range(row, col + 9, row, col + 10, format_number(initial_credit), txt_name)
                    sheet.merge_range(row, col + 11, row, col + 12, format_number(initial_balance), txt_name)

                # Process move lines for the partner
                for rec in data['data'][partner]:
                    row += 1
                    sheet.write(row, col, rec[0]['date'], txt_name)
                    sheet.write(row, col + 1, rec[0]['jrnl'], txt_name)
                    sheet.write(row, col + 2, rec[0]['code'], txt_name)
                    sheet.merge_range(row, col + 3, row, col + 4, rec[0]['move_name'], txt_name)
                    sheet.merge_range(row, col + 5, row, col + 6, rec[0]['date_maturity'] or '', txt_name)
                    sheet.merge_range(row, col + 7, row, col + 8, format_number(rec[0]['debit']), txt_name)
                    sheet.merge_range(row, col + 9, row, col + 10, format_number(rec[0]['credit']), txt_name)
                    sheet.merge_range(row, col + 11, row, col + 12, ' ', txt_name)

            # Grand totals
            row += 1
            # Ensure grand_total values are numbers
            grand_total_debit = data['grand_total']['total_debit'] if data['grand_total'] and data['grand_total'][
                'total_debit'] is not None else 0
            grand_total_credit = data['grand_total']['total_credit'] if data['grand_total'] and data['grand_total'][
                'total_credit'] is not None else 0
            grand_balance = grand_total_debit - grand_total_credit

            sheet.merge_range(row, col, row, col + 6, 'Total', filter_head)
            sheet.merge_range(row, col + 7, row, col + 8, format_number(grand_total_debit), filter_head)
            sheet.merge_range(row, col + 9, row, col + 10, format_number(grand_total_credit), filter_head)
            sheet.merge_range(row, col + 11, row, col + 12, format_number(grand_balance), filter_head)

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()