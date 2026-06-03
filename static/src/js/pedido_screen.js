/* tpv_pedidos - PedidoScreen
 * Pantalla tipo TPV para seleccionar productos y crear pedidos al obrador.
 * Reutiliza categorías y productos del POS sin necesidad de abrir sesión.
 */
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { PedidoOrder } from "@tpv_pedidos/static/src/js/pedido_order";
import { PedidoActionButtons } from "@tpv_pedidos/static/src/js/pedido_action_buttons";
import { CategorySelector } from "@point_of_sale/app/components/category_selector/category_selector";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";

export class PedidoScreen extends Component {
    static template = "tpv_pedidos.PedidoScreen";
    static components = {
        PedidoOrder,
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
        this.router = useService("pos_router");

        this.pedidoOrder = new PedidoOrder(this, {});
        this.state = useState({
            selectedCategoryId: null,
            notaCategorias: [],
            searchText: "",
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

    get rootCategory() {
        return null;
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

    onProductClick(product) {
        this.pedidoOrder.addLine(product);
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