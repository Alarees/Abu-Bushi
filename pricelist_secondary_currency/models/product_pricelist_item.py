from odoo import api, fields, models
from odoo.tools import float_round


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    secondary_currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='pricelist_id.secondary_currency_id',
        string="Secondary Currency",
        store=True,
        index='btree_not_null',
    )
    secondary_price = fields.Monetary(
        string="Secondary Price",
        currency_field='secondary_currency_id',
        help="Price expressed in the pricelist's secondary currency.",
    )
    # The fixed price becomes a stored computed (but still editable) field.
    fixed_price = fields.Float(
        compute='_compute_fixed_price',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends(
        'compute_price',
        'secondary_price',
        'secondary_currency_id',
        'pricelist_id.currency_id',
        'pricelist_id.company_id',
        'pricelist_id.secondary_rounding',
    )
    def _compute_fixed_price(self):
        rate_cache = {}
        for item in self:
            if (
                item.compute_price == 'fixed'
                and item.secondary_currency_id
                and item.secondary_price
            ):
                item.fixed_price = item._convert_secondary_price(rate_cache)
            else:
                # Keep the manually entered / existing value untouched.
                item.fixed_price = item.fixed_price

    def _convert_secondary_price(self, rate_cache):
        self.ensure_one()
        pricelist = self.pricelist_id
        company = pricelist.company_id or self.env.company
        currency = pricelist.currency_id or company.currency_id
        key = (self.secondary_currency_id.id, currency.id, company.id)
        if key not in rate_cache:
            rate_cache[key] = self.env['res.currency']._get_conversion_rate(
                self.secondary_currency_id, currency, company,
            )
        return float_round(
            self.secondary_price * rate_cache[key],
            precision_rounding=pricelist.secondary_rounding or 1.0,
        )

    def _recompute_fixed_price(self):
        """Schedule the recomputation of fixed_price (exchange rate changed)."""
        items = self.filtered(
            lambda i: i.compute_price == 'fixed' and i.secondary_currency_id and i.secondary_price
        )
        if items:
            self.env.add_to_compute(self._fields['fixed_price'], items)

    @api.model
    def _cron_update_secondary_prices(self):
        items = self.sudo().search([
            ('compute_price', '=', 'fixed'),
            ('secondary_currency_id', '!=', False),
            ('secondary_price', '!=', 0),
        ])
        items._recompute_fixed_price()
