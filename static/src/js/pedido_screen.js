/* tpv_pedidos - NotaLineaPopup + PedidoConfirmPopup + PedidoScreen
 * Fusionado en un solo archivo para evitar imports @tpv_pedidos que el bundler no resuelve.
 */
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";

// ============================================================
// NotaLineaPopup
// ============================================================
class NotaLineaPopup extends Component {
    static template = "tpv_pedidos.NotaLineaPopup";
    static components = { Dialog };
    static props = {
        line: Object,
        notaCategorias: { type: Array, optional: true },
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.state = useState({
            nota_linea: this.props.line.nota_linea || "",
            nota_categoria_id: this.props.line.nota_categoria_id || null,
        });
    }

    get categorias() {
        return this.props.notaCategorias || [];
    }

    selectCategoria(cat) {
        this.state.nota_categoria_id = cat.id;
    }

    confirm() {
        if (this.state.nota_categoria_id) {
            const cat = this.categorias.find((c) => c.id === this.state.nota_categoria_id);
            if (cat) {
                this.props.onConfirm({
                    nota_linea: this.state.nota_linea,
                    nota_categoria_id: this.state.nota_categoria_id,
                    nota_categoria_name: cat.name || "",
                });
            }
        } else {
            this.props.onConfirm({
                nota_linea: this.state.nota_linea,
                nota_categoria_id: null,
                nota_categoria_name: "",
            });
        }
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

// ============================================================
// PedidoConfirmPopup
// ============================================================
class PedidoConfirmPopup extends Component {
    static template = "tpv_pedidos.PedidoConfirmPopup";
    static components = { Dialog };
    static props = {
        tipoPedido: { type: String },
        lines: { type: Array },
        linesToJSON: { type: Function },
        posConfigId: { type: Number },
        posConfigName: { type: String },
        onConfirm: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.state = useState({
            nota_general: "",
        });
    }

    get isEncargo() {
        return this.props.tipoPedido === "encargo";
    }

    get titulo() {
        return this.isEncargo
            ? _t("Confirmar Encargo")
            : _t("Confirmar Pedido Tienda");
    }

    get lineas() {
        return this.props.lines;
    }

    get totalLineas() {
        return this.lineas.length;
    }

    confirm() {
        this.props.onConfirm(this.state.nota_general);
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

// ============================================================
// PedidoScreen
// ============================================================
class PedidoScreen extends Component {
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
            catMap: {},
            notaCategorias: [],
            searchText: "",
            lines: [],
        });

        onMounted(() => {
            this._loadData();
        });
    }

    _loadData() {
        this._loadNotaCategorias();
        this._loadPosCategories();
    }

    _loadNotaCategorias() {
        this.orm.call(
            "tpv.nota.categoria",
            "search_read",
            [[["activa", "=", true]], ["id", "name", "sequence"]],
            { order: "sequence, name" }
        ).then((cats) => {
            this.state.notaCategorias = cats || [];
        }).catch((err) => {
            console.error("Error loading nota categorias:", err);
        });
    }

    _loadPosCategories() {
        let catMap = {};

        // Method 1: Try POS models
        if (this.pos.models && this.pos.models["pos.category"]) {
            const cats = this.pos.models["pos.category"].getAll();
            if (cats && cats.length) {
                for (const c of cats) {
                    catMap[c.id] = {
                        id: c.id,
                        name: c.name,
                        parent_id: c.parent_id ? (typeof c.parent_id === 'object' ? c.parent_id.id : c.parent_id) : null,
                    };
                }
            }
        }

        // Method 2: Extract from products
        if (Object.keys(catMap).length === 0 && this.pos.models && this.pos.models["product.product"]) {
            const products = this.pos.models["product.product"].getAll();
            if (products && products.length) {
                for (const p of products) {
                    if (p.pos_categ_ids) {
                        for (const cat of p.pos_categ_ids) {
                            const catId = cat && typeof cat === "object" ? cat.id : cat;
                            const catName = cat && typeof cat === "object" ? (cat.name || "") : "";
                            const parentId = cat && typeof cat === "object" && cat.parent_id
                                ? (typeof cat.parent_id === 'object' ? cat.parent_id.id : cat.parent_id)
                                : null;
                            if (catId && !catMap[catId]) {
                                catMap[catId] = { id: catId, name: catName, parent_id: parentId };
                            }
                        }
                    }
                }
            }
        }

        // Method 3: ORM fallback
        if (Object.keys(catMap).length === 0) {
            this.orm.call(
                "pos.category", "search_read", [[], ["id", "name", "parent_id"]]
            ).then((result) => {
                if (result && result.length) {
                    for (const c of result) {
                        catMap[c.id] = {
                            id: c.id,
                            name: c.name,
                            parent_id: c.parent_id ? c.parent_id[0] : null,
                        };
                    }
                    this._buildCategoryIndex(catMap);
                }
            }).catch((err) => {
                console.warn("Could not load categories from backend:", err);
            });
            return;
        }
        this._buildCategoryIndex(catMap);
    }

    _buildCategoryIndex(catMap) {
        const catArray = Object.values(catMap);
        for (const cat of catArray) {
            cat.children = [];
        }
        for (const cat of catArray) {
            if (cat.parent_id && catMap[cat.parent_id]) {
                catMap[cat.parent_id].children.push(cat);
            }
        }
        this.state.posCategories = catArray;
        this.state.catMap = catMap;
    }

    // --- Category navigation ---

    get rootCategories() {
        return this.state.posCategories.filter(c => !c.parent_id);
    }

    getCategoryChildren(catId) {
        const cat = this.state.catMap?.[catId];
        return cat ? cat.children || [] : [];
    }

    getAncestorChain(catId) {
        const chain = [];
        let current = this.state.catMap?.[catId];
        while (current && current.parent_id) {
            const parent = this.state.catMap?.[current.parent_id];
            if (parent) {
                chain.unshift(parent);
                current = parent;
            } else break;
        }
        return chain;
    }

    get visibleCategories() {
        if (!this.state.selectedCategoryId) {
            return this.rootCategories;
        }
        const selected = this.state.catMap?.[this.state.selectedCategoryId];
        if (!selected) return this.rootCategories;

        const ancestors = this.getAncestorChain(this.state.selectedCategoryId);
        const siblings = selected.parent_id
            ? this.getCategoryChildren(selected.parent_id)
            : [];
        const children = this.getCategoryChildren(this.state.selectedCategoryId);

        const visible = new Set();
        for (const c of ancestors) visible.add(c.id);
        for (const c of siblings) visible.add(c.id);
        if (selected) visible.add(selected.id);
        for (const c of children) visible.add(c.id);

        return this.state.posCategories.filter(c => visible.has(c.id));
    }

    getChildCategoryIds(catId) {
        const ids = [catId];
        const cat = this.state.catMap?.[catId];
        if (cat && cat.children) {
            for (const child of cat.children) {
                ids.push(...this.getChildCategoryIds(child.id));
            }
        }
        return ids;
    }

    selectCategory(categoryId) {
        if (categoryId === this.state.selectedCategoryId) {
            const cat = this.state.catMap?.[categoryId];
            if (cat && cat.parent_id) {
                this.state.selectedCategoryId = cat.parent_id;
            } else {
                this.state.selectedCategoryId = null;
            }
        } else {
            this.state.selectedCategoryId = categoryId;
        }
    }

    isCategorySelected(catId) {
        return this.state.selectedCategoryId === catId;
    }

    isCategoryAncestor(catId) {
        if (!this.state.selectedCategoryId) return false;
        return this.getAncestorChain(this.state.selectedCategoryId).some(c => c.id === catId);
    }

    // --- Product image URL ---

    getProductImageUrl(product) {
        if (!product) return false;
        const base = "/web/image?model=product.product&field=image_128&id=";
        const unique = product.write_date ? "&unique=" + product.write_date : "";
        return base + product.id + unique;
    }

    // --- Product filtering ---

    get products() {
        if (!this.pos.models || !this.pos.models["product.product"]) {
            return [];
        }
        let products = this.pos.models["product.product"].getAll();
        if (!products || !products.length) return [];

        products = products.filter((p) => {
            try {
                return p.canBeDisplayed !== false;
            } catch (e) {
                return true;
            }
        });

        if (this.state.searchText) {
            const searchLower = this.state.searchText.toLowerCase();
            products = products.filter((p) =>
                (p.display_name || "").toLowerCase().includes(searchLower)
            );
        }

        if (this.state.selectedCategoryId) {
            const allCatIds = new Set(this.getChildCategoryIds(this.state.selectedCategoryId));
            products = products.filter((p) =>
                p.pos_categ_ids &&
                p.pos_categ_ids.some((cat) => {
                    const catId = cat && typeof cat === "object" ? cat.id : cat;
                    return allCatIds.has(catId);
                })
            );
        }

        return products;
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
            onConfirm: (notaGeneral) => {
                this._createPedido(tipoPedido, notaGeneral);
            },
        });
    }

    _createPedido(tipoPedido, notaGeneral) {
        const lines = this.state.lines.map((l) => ({
            product_id: l.product_id,
            qty: l.qty,
            nota_linea: l.nota_linea,
            nota_categoria_id: l.nota_categoria_id,
        }));
        this.orm.call(
            "tpv.pedido",
            "create_pedido_from_pos",
            [],
            {
                pos_config_id: this.pos.config.id,
                tipo_pedido: tipoPedido,
                lines: lines,
                nota_general: notaGeneral,
            }
        ).then((result) => {
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
        }).catch((error) => {
            this.notification.add(
                _t("Error: %s", error.message || error.data?.message || JSON.stringify(error)),
                { type: "danger" }
            );
        });
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
    route: "/pos/ui/" + odoo.pos_config_id + "/pedido",
    params: {},
});