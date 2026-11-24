import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(Navbar.prototype, {
    /**
     * Pricelists shown as quick buttons: the ones enabled in the POS settings
     * (Available Pricelists, plus the default one). When the POS has no default
     * pricelist, a "Default Price" entry is added, like the standard popup does.
     */
    get quickPricelists() {
        const config = this.pos.config;
        if (!config.use_pricelist) {
            return [];
        }
        const list = config.availablePricelists.map((pricelist) => ({
            id: pricelist.id,
            name: pricelist.display_name || pricelist.name,
            record: pricelist,
        }));
        if (!config.pricelist_id) {
            list.push({ id: false, name: _t("Default Price"), record: null });
        }
        return list;
    },

    get showPricelistSwitcher() {
        const order = this.pos.getOrder();
        return Boolean(
            order &&
                !order.finalized &&
                this.pos.router.currentScreen() === "ProductScreen" &&
                this.pos.accessRight.canAccessPricelist &&
                this.quickPricelists.length > 1
        );
    },

    isQuickPricelistActive(item) {
        const current = this.pos.getOrder()?.pricelist_id;
        return (current ? current.id : false) === item.id;
    },

    async onClickQuickPricelist(item) {
        if (this.isQuickPricelistActive(item)) {
            return;
        }
        await this.pos.selectPricelist(item.record);
    },

    async onChangeQuickPricelist(ev) {
        const item = this.quickPricelists.find((pl) => String(pl.id || "") === ev.target.value);
        if (item) {
            await this.onClickQuickPricelist(item);
        }
    },
});
