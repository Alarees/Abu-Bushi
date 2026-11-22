from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    secondary_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string="Secondary Currency",
        help="If set, fixed-price rules of this pricelist are entered in this currency "
             "and converted to the pricelist currency using the current exchange rate.",
    )
    secondary_rate = fields.Float(
        string="Current Rate",
        compute='_compute_secondary_rate',
        digits=0,
        help="Amount of pricelist currency for 1 unit of the secondary currency.",
    )
    secondary_rounding = fields.Float(
        string="Rounding",
        default=1.0,
        help="Converted prices are rounded to a multiple of this value "
             "(1 = nearest whole number).",
    )

    @api.constrains('secondary_currency_id', 'currency_id')
    def _check_secondary_currency(self):
        for pricelist in self:
            if pricelist.secondary_currency_id and pricelist.secondary_currency_id == pricelist.currency_id:
                raise ValidationError(self.env._(
                    "The secondary currency must be different from the pricelist currency."
                ))

    @api.constrains('secondary_rounding')
    def _check_secondary_rounding(self):
        for pricelist in self:
            if pricelist.secondary_rounding <= 0:
                raise ValidationError(self.env._("Rounding must be strictly positive."))

    def _get_secondary_rate(self):
        """Pricelist-currency units per 1 unit of the secondary currency (today)."""
        self.ensure_one()
        if not self.secondary_currency_id:
            return 0.0
        company = self.company_id or self.env.company
        currency = self.currency_id or company.currency_id
        return self.env['res.currency']._get_conversion_rate(
            self.secondary_currency_id, currency, company,
        )

    @api.depends('secondary_currency_id', 'currency_id', 'company_id')
    def _compute_secondary_rate(self):
        for pricelist in self:
            pricelist.secondary_rate = pricelist._get_secondary_rate()

    def action_update_secondary_prices(self):
        """Force recalculation of all fixed prices from the secondary prices."""
        self.mapped('item_ids')._recompute_fixed_price()
        return True

    def action_init_secondary_prices(self):
        """Fill the secondary price of existing fixed rules from their current
        fixed price (fixed price / current rate). Only rules without a secondary price."""
        for pricelist in self.filtered('secondary_currency_id'):
            rate = pricelist._get_secondary_rate()
            if not rate:
                continue
            items = pricelist.item_ids.filtered(
                lambda i: i.compute_price == 'fixed' and not i.secondary_price and i.fixed_price
            )
            for item in items:
                item.secondary_price = float_round(
                    item.fixed_price / rate,
                    precision_rounding=pricelist.secondary_currency_id.rounding,
                )
        return True
