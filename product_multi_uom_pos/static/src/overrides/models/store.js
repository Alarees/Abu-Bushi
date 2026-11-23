import { PosStore } from "@point_of_sale/app/services/pos_store";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    /**
     * Packagings of a product template (the "Packagings" field of the
     * product form), excluding the base unit itself.
     */
    getProductPackagings(productTemplate) {
        const baseUom = productTemplate?.uom_id;
        const packagings = productTemplate?.uom_ids || [];
        return packagings.filter((uom) => uom && uom.id !== baseUom?.id && uom.factor > 0);
    },

    /**
     * Ask the cashier which packaging to use, only for products having
     * packagings. The line quantity stays in the base unit (same behaviour
     * as scanning a packaging barcode), so the price and the stock moves
     * are computed automatically from the conversion factor.
     */
    async handleOrderLineConfiguration(order, values, code, vals, options, configure) {
        const result = await super.handleOrderLineConfiguration(...arguments);
        if (!result || !configure || code || "price_unit" in vals || "custom_uom_name" in vals) {
            return result;
        }
        if (values.combo_parent_id || values.refunded_orderline_id) {
            return result;
        }
        const template = values.product_tmpl_id;
        const packagings = this.getProductPackagings(template);
        if (!packagings.length) {
            return result;
        }

        const baseUom = template.uom_id;
        const sign = values.qty < 0 ? -1 : 1;
        const unitPrice = values.product_id.getPrice(
            order.pricelist_id,
            1,
            values.price_extra || 0,
            false,
            values.product_id
        );
        const list = [
            {
                id: 0,
                label: baseUom.name,
                description: this.formatCurrency(unitPrice),
                item: { name: "", ratio: 1 },
            },
        ];
        for (const uom of packagings) {
            const ratio = uom.factor / baseUom.factor;
            list.push({
                id: uom.id,
                label: uom.name,
                description: `${ratio} ${baseUom.name} - ${this.formatCurrency(unitPrice * ratio)}`,
                item: { name: uom.name, ratio },
            });
        }

        const choice = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Select packaging"),
            list,
            size: "md",
            bodyClass: "pb-4",
        });
        if (!choice) {
            return false;
        }
        values.qty = sign * choice.ratio;
        if (choice.name) {
            values.custom_uom_name = choice.name;
        }
        return result;
    },
});
