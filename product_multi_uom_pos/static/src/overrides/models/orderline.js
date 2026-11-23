import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    /**
     * Lines of the same product but with a different packaging must not be
     * merged together, otherwise the packaging label would be wrong.
     */
    canBeMergedWith(orderline) {
        if ((this.custom_uom_name || "") !== (orderline.custom_uom_name || "")) {
            return false;
        }
        return super.canBeMergedWith(...arguments);
    },
});
