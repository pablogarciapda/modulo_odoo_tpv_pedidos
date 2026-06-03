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
            notaCategorias: [],
            searchText: "",
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
        if (this.pos.models && this.pos.models["pos.category"]) {
            return this.pos.models["pos.category"].getAll();
        }
        return [];
    }

    get products() {
        if (!this.pos.models || !this.pos.models["product.product"]) {
            return [];
        }
        let products = this.pos.models["product.product"].getAll();
        if (!products || !products.length) {
            return [];
        }
        if (this.state.searchText) {
            const searchLower = this.state.searchText.toLowerCase();
            products = products.filter((p) =>
                (p.display_name || "").toLowerCase().includes(searchLower)
            );
        }
        if (this.state.selectedCategoryId) {
            products = products.filter((p) =>
                p.pos_categ_ids && p.pos_categ_ids.some(
                    (cid) => cid === this.state.selectedCategoryId
                )
            );
        }
        return products;
    }

    selectCategory(categoryId) {
        this.state.selectedCategoryId = categoryId;
        this.state.searchText = "";
    }

    // --- Order management ---

    addLine(product) {
        const existing = this.state.lines.find(
            (l) => l.product_id === product.id && !l.nota_linea
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
                image_128: product.image_128 || null,
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
            if (result.error) {
                this.notification.add(result.error, { type: "danger" });
            } else {
                this.notification.add(
                    _t("Pedido %s creado correctamente", result.name),
                    { type: "success" }
                );
                this.state.lines = [];
            }
        } catch (error) {
            this.notification.add(
                _t("Error al crear el pedido: %s", error.message || error),
                { type: "danger" }
            );
        }
    }

    get totalLines() {
        return this.state.lines.length;
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