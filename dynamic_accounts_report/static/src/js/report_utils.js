/** @odoo-module */
import { Component, proxy } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";

/* ------------------------------------------------------------------ *
 *  Number formatting (thousands separators, locale aware)
 * ------------------------------------------------------------------ */
const LRM = "\u200E";

function groupDigits(intStr, grouping, sep) {
    if (!sep) {
        return intStr;
    }
    const groups = Array.isArray(grouping) && grouping.length ? [...grouping] : [3, 0];
    let size = groups.shift();
    let rest = intStr;
    let out = "";
    while (size > 0 && rest.length > size) {
        out = sep + rest.slice(-size) + out;
        rest = rest.slice(0, -size);
        if (groups.length) {
            const next = groups.shift();
            if (next === -1) {
                size = 0;
            } else if (next > 0) {
                size = next;
            }
        }
    }
    return rest + out;
}

/** Accepts numbers or the legacy "1,234.50" strings coming from the server. */
function toNumber(value) {
    if (typeof value === "number") {
        return value;
    }
    if (typeof value === "string") {
        const cleaned = value.replace(/[\s\u200E,]/g, "");
        if (/^[-+]?\d*\.?\d+$/.test(cleaned)) {
            return parseFloat(cleaned);
        }
    }
    return NaN;
}

/**
 * Format a monetary / quantity value with the *user's* language settings
 * (decimal point, thousands separator, grouping). Falls back to en-US.
 * Non numeric input is returned untouched, null/undefined gives "".
 */
export function formatAmount(value, digits = 2) {
    if (value === null || value === undefined || value === false || value === "") {
        return "";
    }
    const number = toNumber(value);
    if (Number.isNaN(number)) {
        return value;
    }
    const factor = Math.pow(10, digits);
    let rounded = Math.round((Math.abs(number) + Number.EPSILON) * factor) / factor;
    const negative = number < 0 && rounded !== 0;
    const [intPart, decPart = ""] = rounded.toFixed(digits).split(".");
    const decimalPoint = localization?.decimalPoint || ".";
    const thousandsSep = localization?.thousandsSep ?? ",";
    const text =
        (negative ? "-" : "") +
        groupDigits(intPart, localization?.grouping, thousandsSep) +
        (digits > 0 ? decimalPoint + decPart.padEnd(digits, "0") : "");
    // keep "-1,234.00" in the right visual order inside RTL (Arabic) pages
    return document.documentElement.dir === "rtl" ? LRM + text + LRM : text;
}

export function sumAmounts(rows, key) {
    return (rows || []).reduce((acc, row) => {
        const n = toNumber(row?.[key]);
        return acc + (Number.isNaN(n) ? 0 : n);
    }, 0);
}

/* ------------------------------------------------------------------ *
 *  Shared filters: Companies / Partners / Accounts
 * ------------------------------------------------------------------ */
const SEARCH_CONFIG = {
    partner: {
        model: "res.partner",
        domain: (term) => ["|", ["name", "ilike", term], ["ref", "ilike", term]],
        fields: ["id", "display_name"],
    },
    account: {
        model: "account.account",
        domain: (term) => ["|", ["code", "ilike", term], ["name", "ilike", term]],
        fields: ["id", "display_name"],
    },
};

/* Kept only so existing `static components = { ReportFilters }` lines stay
 * valid. The filter UI is rendered with t-call (Owl 3 gives a component its
 * props only through useProps, so a child component is not needed). */
export class ReportFilters extends Component {
    static template = "dynamic_accounts_report.ReportFilters";
}

/* ------------------------------------------------------------------ *
 *  Mixin used by every report component
 * ------------------------------------------------------------------ */
/**
 * Call at the end of ``setup()`` (after ``this.orm`` / ``this.state``).
 *
 *  - adds ``this.fmt`` (locale aware number formatting) for the templates;
 *  - adds the company / partner / account filter state and
 *    ``this.onFilterChange``;
 *  - wraps ``this.orm.call`` so the *selected companies* are sent as
 *    ``allowed_company_ids`` (the server validates them against the
 *    user's allowed companies, so this cannot widen access);
 *
 * The component must implement ``reloadReport()``.
 */
export function setupReportExtras(component, { model } = {}) {
    const state = component.state;
    const baseOrm = component.orm;
    state.companies = { options: [], selectedIds: [], mixedCurrency: false };
    state.selected_company_ids = [];
    if (!Array.isArray(state.selected_partner_rec)) {
        state.selected_partner_rec = [];
    }
    if (!Array.isArray(state.selected_partner)) {
        state.selected_partner = [];
    }
    if (!Array.isArray(state.selected_account_rec)) {
        state.selected_account_rec = [];
    }
    component.baseOrm = baseOrm;
    component.fmt = (value, digits = 2) => formatAmount(value, digits);
    component.orm = new Proxy(baseOrm, {
        get(target, prop) {
            if (prop === "call") {
                return (modelName, method, args = [], kwargs = {}) => {
                    const ids = state.selected_company_ids;
                    if (ids && ids.length) {
                        kwargs = {
                            ...kwargs,
                            context: { ...(kwargs.context || {}), allowed_company_ids: [...ids] },
                        };
                    }
                    return target.call(modelName, method, args, kwargs);
                };
            }
            const member = target[prop];
            return typeof member === "function" ? member.bind(target) : member;
        },
    });
    state.filterUi = { kind: null, query: "", results: [], loading: false };
    let searchTimer = null;
    component.isCompanySelected = (id) => state.companies.selectedIds.includes(id);
    component.toggleCompany = (id) => {
        const current = [...state.companies.selectedIds];
        const index = current.indexOf(id);
        if (index >= 0) {
            if (current.length === 1) {
                return; // keep at least one company selected
            }
            current.splice(index, 1);
        } else {
            current.push(id);
        }
        component.onFilterChange("company", current);
    };
    component.selectedOf = (kind) =>
        kind === "partner" ? state.selected_partner_rec : state.selected_account_rec;
    component.onSearch = (kind, ev) => {
        const term = ev.target.value.trim();
        state.filterUi.kind = kind;
        state.filterUi.query = ev.target.value;
        clearTimeout(searchTimer);
        if (!term) {
            state.filterUi.results = [];
            return;
        }
        searchTimer = setTimeout(async () => {
            const config = SEARCH_CONFIG[kind];
            state.filterUi.loading = true;
            try {
                const rows = await baseOrm.searchRead(config.model, config.domain(term), config.fields, { limit: 12 });
                const taken = new Set(component.selectedOf(kind).map((r) => r.id));
                state.filterUi.results = rows
                    .filter((r) => !taken.has(r.id))
                    .map((r) => ({ id: r.id, name: r.display_name, display_name: r.display_name }));
            } catch (error) {
                console.error(error);
                state.filterUi.results = [];
            } finally {
                state.filterUi.loading = false;
            }
        }, 250);
    };
    component.addRecord = (kind, record) => {
        state.filterUi.results = state.filterUi.results.filter((r) => r.id !== record.id);
        component.onFilterChange(kind, [...component.selectedOf(kind), record]);
    };
    component.removeRecord = (kind, record) =>
        component.onFilterChange(kind, component.selectedOf(kind).filter((r) => r.id !== record.id));
    component.clearFilter = (kind) => component.onFilterChange(kind, []);
    component.onFilterChange = async (kind, list) => {
        if (kind === "company") {
            state.selected_company_ids = list;
            state.companies.selectedIds = list;
        } else if (kind === "partner") {
            state.selected_partner_rec = list;
            state.selected_partner = list.map((r) => r.id);
        } else if (kind === "account") {
            state.selected_account_rec = list;
            state.selected_account_list = list.map((r) => r.id);
        }
        await component.reloadReport();
    };
    component.loadCompanyOptions = async () => {
        if (!model) {
            return;
        }
        try {
            const info = await baseOrm.call(model, "get_company_options", []);
            state.companies = {
                options: info.companies,
                selectedIds: info.selected_ids,
                mixedCurrency: info.mixed_currency,
            };
            state.selected_company_ids = info.selected_ids;
        } catch (error) {
            console.error(error);
        }
    };
    component.loadCompanyOptions();
}
