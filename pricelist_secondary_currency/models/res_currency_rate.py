from odoo import api, models


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    def _update_secondary_pricelist_prices(self, currencies):
        """Recompute pricelist rules priced in a secondary currency affected by
        a change of the exchange rate of ``currencies``."""
        if not currencies:
            return
        items = self.env['product.pricelist.item'].sudo().search([
            ('compute_price', '=', 'fixed'),
            ('secondary_currency_id', '!=', False),
            ('secondary_price', '!=', 0),
            '|',
            ('secondary_currency_id', 'in', currencies.ids),
            ('pricelist_id.currency_id', 'in', currencies.ids),
        ])
        items._recompute_fixed_price()
        items._sync_list_price()

    def _refresh_after_rate_change(self, currencies):
        self.env['res.currency.rate'].flush_model()
        self.env['res.currency.rate']._invalidate_rates()
        self._update_secondary_pricelist_prices(currencies)

    def write(self, vals):
        currencies = self.currency_id
        res = super().write(vals)
        self._refresh_after_rate_change(currencies | self.currency_id)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_after_rate_change(records.currency_id)
        return records

    def unlink(self):
        currencies = self.currency_id
        res = super().unlink()
        self.env['res.currency.rate']._refresh_after_rate_change(currencies)
        return res
