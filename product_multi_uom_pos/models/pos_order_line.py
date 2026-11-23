from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    custom_uom_name = fields.Char(
        string='Packaging',
        help="Packaging selected by the cashier in the POS. The quantity of "
             "the line is always expressed in the product's base unit.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        if 'custom_uom_name' not in params:
            params.append('custom_uom_name')
        return params
