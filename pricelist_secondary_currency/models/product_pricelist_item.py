from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_round


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
    custom_adjustment = fields.Boolean(
        string="Custom Adjustment",
        help="Use the adjustment defined on this rule instead of the pricelist default.",
    )
    adjust_percent = fields.Float(string="Adjustment %")
    adjust_amount = fields.Float(string="Adjustment Amount")
    converted_price = fields.Monetary(
        string="Converted Price",
        currency_field='currency_id',
        compute='_compute_converted_price',
        help="Secondary price x current exchange rate, before adjustment and rounding.",
    )
    # The fixed price becomes a stored computed (but still editable) field.
    fixed_price = fields.Float(
        compute='_compute_fixed_price',
        store=True,
        readonly=False,
    )

    @api.constrains('adjust_percent')
    def _check_adjust_percent(self):
        for item in self:
            if item.adjust_percent <= -100:
                raise ValidationError(self.env._("The adjustment percentage must be greater than -100."))

    @api.depends(
        'compute_price',
        'secondary_price',
        'secondary_currency_id',
        'pricelist_id.currency_id',
        'pricelist_id.company_id',
        'pricelist_id.secondary_rounding',
        'custom_adjustment',
        'adjust_percent',
        'adjust_amount',
        'pricelist_id.adjust_percent',
        'pricelist_id.adjust_amount',
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

    def _get_adjustment(self):
        """(percent, amount) applied after the conversion: the rule's own values when
        'Custom Adjustment' is set, otherwise the pricelist defaults."""
        self.ensure_one()
        if self.custom_adjustment:
            return self.adjust_percent, self.adjust_amount
        return self.pricelist_id.adjust_percent, self.pricelist_id.adjust_amount

    def _get_converted_price(self, rate_cache):
        """Secondary price x exchange rate (no adjustment, no rounding)."""
        self.ensure_one()
        pricelist = self.pricelist_id
        company = pricelist.company_id or self.env.company
        currency = pricelist.currency_id or company.currency_id
        key = (self.secondary_currency_id.id, currency.id, company.id)
        if key not in rate_cache:
            rate_cache[key] = self.env['res.currency']._get_conversion_rate(
                self.secondary_currency_id, currency, company,
            )
        return self.secondary_price * rate_cache[key]

    def _convert_secondary_price(self, rate_cache):
        """converted x (1 + %) + amount, then rounded (adjust first, round last)."""
        self.ensure_one()
        percent, amount = self._get_adjustment()
        adjusted = self._get_converted_price(rate_cache) * (1 + percent / 100.0) + amount
        return float_round(
            adjusted,
            precision_rounding=self.pricelist_id.secondary_rounding or 1.0,
        )

    @api.depends(
        'secondary_price', 'secondary_currency_id',
        'pricelist_id.currency_id', 'pricelist_id.company_id',
    )
    def _compute_converted_price(self):
        rate_cache = {}
        for item in self:
            if item.secondary_currency_id and item.secondary_price:
                item.converted_price = item._get_converted_price(rate_cache)
            else:
                item.converted_price = 0.0

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
        # Safety net: re-sync product sale prices from the master pricelist(s).
        self.sudo().search([('pricelist_id.sync_list_price', '=', True)])._sync_list_price()

    # ---- Product sale price synchronisation -------------------------------
    _SYNC_TRIGGER_FIELDS = {
        'secondary_price', 'fixed_price', 'compute_price', 'applied_on', 'product_tmpl_id',
        'min_quantity', 'uom_id', 'date_start', 'date_end', 'pricelist_id',
        'custom_adjustment', 'adjust_percent', 'adjust_amount',
    }

    def _is_list_price_source(self):
        self.ensure_one()
        pricelist = self.pricelist_id
        return bool(
            pricelist.sync_list_price
            and pricelist.active
            and self.compute_price == 'fixed'
            and self.applied_on == '1_product'
            and self.product_tmpl_id
            and not self.date_start
            and not self.date_end
            and not self.uom_id
            and self.min_quantity <= 1
        )

    def _sync_list_price(self):
        """Write the fixed price of eligible rules on the product Sales Price."""
        items = self.filtered(lambda i: i._is_list_price_source())
        if not items:
            return
        source = {}
        for item in items.sorted('id'):  # latest rule wins for a given product
            source[item.product_tmpl_id] = item
        for template, item in source.items():
            price = item.fixed_price  # forces any pending recomputation
            if price <= 0:
                continue
            rounding = item.currency_id.rounding or 0.01
            if float_compare(template.list_price, price, precision_rounding=rounding):
                template.sudo().write({'list_price': price})

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items._sync_list_price()
        return items

    def write(self, vals):
        res = super().write(vals)
        if self._SYNC_TRIGGER_FIELDS & set(vals):
            self._sync_list_price()
        return res
