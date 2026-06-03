/* tpv_pedidos - PedidoScreen
 * Pantalla tipo TPV para seleccionar productos y crear pedidos al obrador.
 * Reutiliza categorías y productos del POS sin necesidad de abrir sesión.
 */
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { PedidoActionButtons } from "@tpv_pedidos/js/pedido_action_buttons";
import { NotaLineaPopup } from "@tpv_pedidos/js/nota_linea_popup";
import { CategorySelector } from "@point_of_sale/app/components/category_selector/category_selector";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";

export class PedidoScreen extends Component {
    static template = "tpv_pedidos.PedidoScreen";
    static components = {
        PedidoActionButtons,
        CategorySelector,
        ProductCard,
    };
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            selectedCategoryId: null,
            notaCategorias: [],
            searchText: "",
            // Order lines management
            lines: [],
        });

        onMounted(async () => {
            await this._loadNotaCategorias();
        });
    }

    async _loadNotaCategorias() {
        try {
            const categorias = await this.orm.call(
                "tpv.nota.categoria",
                "search_read",
                [[["activa", "=", true]], ["id", "name", "sequence"]],
                { order: "sequence, name" }
            );
            this.state.notaCategorias = categorias;
        } catch (error) {
            console.error("Error loading nota categorias:", error);
        }
    }

    get categories() {
        return this.pos.models["pos.category"].getAll();
    }

    get products() {
        let products = this.pos.models["product.product"].getAll();
        if (this.state.searchText) {
            const searchLower = this.state.searchText.toLowerCase();
            products = products.filter((p) =>
                p.display_name.toLowerCase().includes(searchLower)
            );
        }
        if (this.state.selectedCategoryId) {
            const selectedCat = this.pos.models["pos.category"].get(
                this.state.selectedCategoryId
            );
            if (selectedCat) {
                const catIds = [selectedCat.id, ...this._getChildCategoryIds(selectedCat)];
                products = products.filter((p) =>
                    p.pos_categ_ids.some((cid) => catIds.includes(cid))
                );
            }
        }
        return products;
    }

    _getChildCategoryIds(category) {
        const ids = [];
        if (category.child_id) {
            for (const child of category.child_id) {
                ids.push(child.id);
                ids.push(...this._getChildCategoryIds(child));
            }
        }
        return ids;
    }

    selectCategory(categoryId) {
        this.state.selectedCategoryId = categoryId;
    }

    // --- Order Line Management ---

    addLine(product) {
        const existingLine = this.state.lines.find(
            (l) => l.product_id === product.id
            && !l.nota_linea
            && !l.nota_categoria_id
        );
        if (existingLine) {
            existingLine.qty += 1;
        } else {
            this.state.lines.push({
                id: Date.now(),
                product_id: product.id,
                product_name: product.display_name,
                qty: 1,
                precio_unitario: product.lst_price,
                nota_linea: "",
                nota_categoria_id: null,
                nota_categoria_name: "",
            });
        }
        // Force reactivity
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

    clearOrder() {
        this.state.lines = [];
    }

    get linesToJSON() {
        return this.state.lines.map((l) => ({
            product_id: l.product_id,
            qty: l.qty,
            nota_linea: l.nota_linea,
            nota_categoria_id: l.nota_categoria_id,
        }));
    }

    get totalLines() {
        return this.state.lines.length;
    }

    // --- Product selection ---

    onProductClick(product) {
        this.addLine(product);
    }

    updateSearch(event) {
        this.state.searchText = event.target.value;
    }

    get posConfigId() {
        return this.pos.config.id;
    }

    get posConfigName() {
        return this.pos.config.name;
    }

    goBack() {
        this.pos.navigate("LoginScreen");
    }
}

registry.category("pos_pages").add("PedidoScreen", {
    name: "PedidoScreen",
    component: PedidoScreen,
    route: `/pos/ui/${odoo.pos_config_id}/pedido`,
    params: {},
});