from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, config):
        """Load the product packagings (uom_ids) in the POS."""
        fields_list = super()._load_pos_data_fields(config)
        if 'uom_ids' not in fields_list:
            fields_list.append('uom_ids')
        return fields_list
