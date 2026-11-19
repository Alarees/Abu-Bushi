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
import json
import logging
import re

from odoo import http, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.http.stream import content_disposition

_logger = logging.getLogger(__name__)

# Only these models may be exported (the model name comes from the browser).
EXPORTABLE_MODELS = {
    'account.general.ledger', 'account.trial.balance',
    'account.partner.ledger', 'cash.book.report', 'bank.book.report',
    'dynamic.balance.sheet.report', 'age.payable.report',
    'age.receivable.report', 'tax.report',
}
XLSX_MIME = ('application/vnd.openxmlformats-officedocument.'
             'spreadsheetml.sheet')


def _safe_filename(name):
    """Strip path separators / control characters / quotes."""
    name = re.sub(r'[^\w\- .()]+', '_', str(name or 'report'), flags=re.UNICODE)
    return (name.strip(' .') or 'report')[:80]


class XLSXReportController(http.Controller):
    # CSRF protection is ON (default): the web client's ``download`` helper
    # already sends the csrf_token with the POST. It used to be disabled
    # (csrf=False), which let any website trigger the export for a logged
    # in user.
    @http.route('/dynamic_account/xlsx_report', type='http', auth='user',
                methods=['POST'])
    def get_report_xlsx(self, model, data, output_format, report_name,
                        report_action, options=None, **kwargs):
        """Generate an XLSX report and return it as a download."""
        if model not in EXPORTABLE_MODELS or output_format != 'xlsx':
            return request.make_response(
                _("Unsupported report."), status=400,
                headers=[('Content-Type', 'text/plain; charset=utf-8')])
        try:
            payload = json.loads(data)
            if not isinstance(payload, dict):
                raise ValueError('payload must be an object')
        except ValueError:
            return request.make_response(
                _("Invalid report data."), status=400,
                headers=[('Content-Type', 'text/plain; charset=utf-8')])
        try:
            report_obj = request.env[model]
            response = request.make_response(None, headers=[
                ('Content-Type', XLSX_MIME),
                ('Content-Disposition', content_disposition(
                    _safe_filename(report_name) + '.xlsx')),
                ('X-Content-Type-Options', 'nosniff'),
            ])
            report_obj.get_xlsx_report(data, response, report_name,
                                       report_action)
            response.set_cookie('fileToken', 'dummy-because-api-expects-one')
            return response
        except (AccessError, UserError) as exc:
            return request.make_response(
                str(exc), status=403 if isinstance(exc, AccessError) else 400,
                headers=[('Content-Type', 'text/plain; charset=utf-8')])
        except Exception:  # never leak tracebacks to the browser
            _logger.exception("XLSX export failed for %s", model)
            return request.make_response(
                _("The report could not be generated. Please contact your administrator."),
                status=500,
                headers=[('Content-Type', 'text/plain; charset=utf-8')])
