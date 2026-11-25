import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { patch } from "@web/core/utils/patch";

patch(ProductCard.prototype, {
    /** Available quantity for the badge, or null when there is nothing to show. */
    get stockGuardQty() {
        const pos = this.env.services.pos;
        if (!pos?.config?.stock_guard_show || this.props.isComboPopup || !this.props.product) {
            return null;
        }
        return pos.stockGuardCardQty(this.props.product);
    },

    get stockGuardQtyText() {
        return this.env.services.pos.formatProductQty(this.stockGuardQty ?? 0, false);
    },

    /**
     * Sale price of the product (quantity 1) according to the pricelist of the current
     * order, formatted for display, or null when there is nothing to show.
     * Uses the same computation as the product info popup, so the price shown on the card
     * is the one the line gets when the product is added. It follows the point of sale
     * setting for taxes (price with or without taxes).
     */
    get pricelistPriceText() {
        const pos = this.env.services.pos;
        const product = this.props.product;
        if (!pos?.config?.pricelist_price_show || this.props.isComboPopup || !product) {
            return null;
        }
        try {
            const order = pos.getOrder();
            const overridedValues = {
                pricelist: order ? order.pricelist_id : pos.config.pricelist_id,
                fiscalPosition: order?.fiscal_position_id,
            };
            const template = product.product_tmpl_id || product;
            const taxDetails =
                template.type === "combo"
                    ? product.getComboTaxDetails({ overridedValues })
                    : product.getTaxDetails({ overridedValues });
            if (!taxDetails) {
                return null;
            }
            const price =
                pos.config.iface_tax_included === "total"
                    ? taxDetails.total_included
                    : taxDetails.total_excluded;
            return pos.formatCurrency(price);
        } catch {
            // A price that cannot be computed must never break the product grid.
            return null;
        }
    },
});
