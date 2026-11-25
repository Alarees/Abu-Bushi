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

    adjust_percent = fields.Float(
        string="Adjustment %",
        help="Percentage added to the converted price (secondary price x rate), "
             "before rounding. Use a negative value for a discount.",
    )
    adjust_amount = fields.Float(
        string="Adjustment Amount",
        help="Amount (in the pricelist currency) added after the percentage, before rounding. "
             "Use a negative value to subtract.",
    )
    sync_list_price = fields.Boolean(
        string="Update Product Sale Price",
        help="When enabled, the product Sales Price is kept equal to the fixed price of the "
             "product's rule in this pricelist (rules applied on a product, without dates, "
             "packaging or minimum quantity). Only one pricelist per company can do this and "
             "its currency must be the company currency.",
    )

    _SYNC_TRIGGER_FIELDS = {
        'secondary_currency_id', 'currency_id', 'secondary_rounding',
        'adjust_percent', 'adjust_amount',
    }

    @api.constrains('sync_list_price', 'company_id', 'currency_id')
    def _check_sync_list_price(self):
        for pricelist in self.filtered('sync_list_price'):
            company = pricelist.company_id or self.env.company
            if pricelist.currency_id != company.currency_id:
                raise ValidationError(self.env._(
                    "The pricelist that updates product sale prices must use the company currency."
                ))
            others = self.with_context(active_test=False).search_count([
                ('sync_list_price', '=', True),
                ('company_id', '=', pricelist.company_id.id),
                ('id', '!=', pricelist.id),
            ])
            if others:
                raise ValidationError(self.env._(
                    "Only one pricelist per company can update product sale prices."
                ))

    def write(self, vals):
        res = super().write(vals)
        if self._SYNC_TRIGGER_FIELDS & set(vals):
            self.filtered('sync_list_price').item_ids._sync_list_price()
        return res

    def action_sync_list_price(self):
        """Push the pricelist fixed prices to the product Sales Price now."""
        for pricelist in self.filtered('sync_list_price'):
            pricelist.item_ids._recompute_fixed_price()
            pricelist.item_ids._sync_list_price()
        return True

    @api.constrains('secondary_currency_id', 'currency_id')
    def _check_secondary_currency(self):
        for pricelist in self:
            if pricelist.secondary_currency_id and pricelist.secondary_currency_id == pricelist.currency_id:
                raise ValidationError(self.env._(
                    "The secondary currency must be different from the pricelist currency."
                ))

    @api.constrains('adjust_percent')
    def _check_adjust_percent(self):
        for pricelist in self:
            if pricelist.adjust_percent <= -100:
                raise ValidationError(self.env._("The adjustment percentage must be greater than -100."))

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
                # Reverse the adjustment: fixed = converted x (1 + %) + amount
                percent, amount = item._get_adjustment()
                converted = (item.fixed_price - amount) / (1 + percent / 100.0)
                item.secondary_price = float_round(
                    converted / rate,
                    precision_rounding=pricelist.secondary_currency_id.rounding,
                )
        return True
