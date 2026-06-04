/* tpv_pedidos - PedidoScreen
 * Pantalla tipo TPV para seleccionar productos y crear pedidos al obrador.
 */
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { NotaLineaPopup } from "@tpv_pedidos/js/nota_linea_popup";
import { PedidoConfirmPopup } from "@tpv_pedidos/js/pedido_confirm_popup";

export class PedidoScreen extends Component {
    static template = "tpv_pedidos.PedidoScreen";
    static components = {
        NotaLineaPopup,
        PedidoConfirmPopup,
    };
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            selectedCategoryId: null,
            posCategories: [],
            notaCategorias: [],
            searchText: "",
            lines: [],
        });

        onMounted(async () => {
            await this._loadData();
        });
    }

    async _loadData() {
        // Load note categories from backend
        try {
            const cats = await this.orm.call(
                "tpv.nota.categoria",
                "search_read",
                [[["activa", "=", true]], ["id", "name", "sequence"]],
                { order: "sequence, name" }
            );
            this.state.notaCategorias = cats || [];
        } catch (err) {
            console.error("Error loading nota categorias:", err);
        }

        // Load POS categories (from backend for reliability)
        await this._loadPosCategories();
    }

    async _loadPosCategories() {
        // Method 1: Load from POS models (already loaded in POS app)
        if (this.pos.models && this.pos.models["pos.category"]) {
            const cats = this.pos.models["pos.category"].getAll();
            if (cats && cats.length) {
                this.state.posCategories = cats;
                return;
            }
        }
        // Method 2: Extract unique categories from products
        if (this.pos.models && this.pos.models["product.product"]) {
            const products = this.pos.models["product.product"].getAll();
            if (products && products.length) {
                const catMap = {};
                for (const p of products) {
                    if (p.pos_categ_ids) {
                        for (const cat of p.pos_categ_ids) {
                            const catId = cat && typeof cat === "object" ? cat.id : cat;
                            const catName = cat && typeof cat === "object" ? (cat.name || "") : "";
                            if (catId && !catMap[catId]) {
                                catMap[catId] = { id: catId, name: catName };
                            }
                        }
                    }
                }
                const cats = Object.values(catMap);
                if (cats.length) {
                    this.state.posCategories = cats;
                    return;
                }
            }
        }
        // Method 3: Fallback - try ORM (may fail for cashier users)
        try {
            const result = await this.orm.call(
                "pos.category", "search_read", [[], ["id", "name"]]
            );
            if (result && result.length) {
                this.state.posCategories = result;
            }
        } catch (err) {
            console.warn("Could not load categories from backend:", err);
        }
    }

    // --- Product image URL ---

    getProductImageUrl(product) {
        if (!product) return false;
        // Use the same pattern as POS ProductScreen:
        // /web/image?model=product.product&field=image_128&id=X&unique=write_date
        const base = "/web/image?model=product.product&field=image_128&id=";
        const unique = product.write_date ? `&unique=${product.write_date}` : "";
        return `${base}${product.id}${unique}`;
    }

    // --- Product filtering ---

    get products() {
        if (!this.pos.models || !this.pos.models["product.product"]) {
            return [];
        }
        let products = this.pos.models["product.product"].getAll();
        if (!products || !products.length) {
            return [];
        }

        // Filter out products not available in POS
        // canBeDisplayed delegates to product.template's (active && available_in_pos)
        // Use a safe check: only exclude if explicitly false
        products = products.filter((p) => {
            try {
                const display = p.canBeDisplayed;
                return display !== false; // undefined/null/true = show, false = hide
            } catch {
                return true; // if error, show product
            }
        });

        // Filter by search text
        if (this.state.searchText) {
            const searchLower = this.state.searchText.toLowerCase();
            products = products.filter((p) =>
                (p.display_name || "").toLowerCase().includes(searchLower)
            );
        }

        // Filter by category using getBy (indexed lookup) like POS does
        if (this.state.selectedCategoryId) {
            // getBy returns products that have this category ID in pos_categ_ids
            const catProducts = this.pos.models["product.product"].getBy(
                "pos_categ_ids", this.state.selectedCategoryId
            );
            if (catProducts && catProducts.length) {
                const catProductIds = new Set(catProducts.map((p) => p.id));
                products = products.filter((p) => catProductIds.has(p.id));
            } else {
                // Fallback: manual filter (pos_categ_ids are objects with .id)
                products = products.filter((p) =>
                    p.pos_categ_ids &&
                    p.pos_categ_ids.some((cat) => {
                        const catId = cat && typeof cat === "object" ? cat.id : cat;
                        return catId === this.state.selectedCategoryId;
                    })
                );
            }
        }

        return products;
    }

    selectCategory(categoryId) {
        this.state.selectedCategoryId = categoryId;
    }

    // --- Order management ---

    addLine(product) {
        const existing = this.state.lines.find(
            (l) => l.product_id === product.id && !l.nota_linea && !l.nota_categoria_id
        );
        if (existing) {
            existing.qty += 1;
        } else {
            this.state.lines.push({
                id: Date.now() + Math.random(),
                product_id: product.id,
                product_name: product.display_name,
                qty: 1,
                precio_unitario: product.lst_price || 0,
                nota_linea: "",
                nota_categoria_id: null,
                nota_categoria_name: "",
            });
        }
        this.state.lines = [...this.state.lines];
    }

    removeLine(lineId) {
        this.state.lines = this.state.lines.filter((l) => l.id !== lineId);
    }

    updateQty(lineId, delta) {
        const line = this.state.lines.find((l) => l.id === lineId);
        if (line) {
            line.qty = Math.max(0, line.qty + delta);
            if (line.qty <= 0) {
                this.removeLine(lineId);
            } else {
                this.state.lines = [...this.state.lines];
            }
        }
    }

    openNotaPopup(line) {
        this.dialog.add(NotaLineaPopup, {
            line: line,
            notaCategorias: this.state.notaCategorias,
            onConfirm: (result) => {
                line.nota_linea = result.nota_linea;
                line.nota_categoria_id = result.nota_categoria_id;
                line.nota_categoria_name = result.nota_categoria_name;
                this.state.lines = [...this.state.lines];
            },
        });
    }

    openConfirmPopup(tipoPedido) {
        if (this.state.lines.length === 0) return;
        this.dialog.add(PedidoConfirmPopup, {
            tipoPedido: tipoPedido,
            lines: this.state.lines,
            linesToJSON: () => this.state.lines.map((l) => ({
                product_id: l.product_id,
                qty: l.qty,
                nota_linea: l.nota_linea,
                nota_categoria_id: l.nota_categoria_id,
            })),
            posConfigId: this.pos.config.id,
            posConfigName: this.pos.config.name,
            onConfirm: async (notaGeneral) => {
                await this._createPedido(tipoPedido, notaGeneral);
            },
        });
    }

    async _createPedido(tipoPedido, notaGeneral) {
        const lines = this.state.lines.map((l) => ({
            product_id: l.product_id,
            qty: l.qty,
            nota_linea: l.nota_linea,
            nota_categoria_id: l.nota_categoria_id,
        }));
        try {
            const result = await this.orm.call(
                "tpv.pedido",
                "create_pedido_from_pos",
                [],
                {
                    pos_config_id: this.pos.config.id,
                    tipo_pedido: tipoPedido,
                    lines: lines,
                    nota_general: notaGeneral,
                }
            );
            if (result && result.error) {
                this.notification.add(String(result.error), { type: "danger" });
            } else if (result && result.name) {
                this.notification.add(
                    _t("Pedido %s creado correctamente", result.name),
                    { type: "success" }
                );
                this.state.lines = [];
            } else {
                this.notification.add(
                    _t("Respuesta inesperada del servidor"),
                    { type: "warning" }
                );
            }
        } catch (error) {
            this.notification.add(
                _t("Error: %s", error.message || error.data?.message || JSON.stringify(error)),
                { type: "danger" }
            );
        }
    }

    get totalLines() {
        return this.state.lines.length;
    }

    goBack() {
        this.pos.navigate("LoginScreen");
    }

    onProductClick(product) {
        this.addLine(product);
    }
}

registry.category("pos_pages").add("PedidoScreen", {
    name: "PedidoScreen",
    component: PedidoScreen,
    route: `/pos/ui/${odoo.pos_config_id}/pedido`,
    params: {},
});