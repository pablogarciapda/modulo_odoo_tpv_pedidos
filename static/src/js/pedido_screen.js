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
        notaGeneral: { type: String, optional: true },
        linesToJSON: { type: Function },
        posConfigId: { type: Number },
        posConfigName: { type: String },
        fechaEntrega: { type: String, optional: true },
        onConfirm: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.state = useState({
            nota_general: this.props.notaGeneral || "",
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
// PedidoListPopup
// ============================================================
class PedidoListPopup extends Component {
    static template = "tpv_pedidos.PedidoListPopup";
    static components = { Dialog };
    static props = {
        pedidos: { type: Array },
        onSelect: { type: Function },
        close: { type: Function },
    };

    selectPedido(pedido) {
        this.props.onSelect(pedido);
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
        PedidoListPopup,
    };
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");

        // Calculate tomorrow's date in YYYY-MM-DD format
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        const tomorrowStr = tomorrow.toISOString().split('T')[0];
        this._defaultFechaEntrega = tomorrowStr;
        this.tomorrowStr = tomorrowStr;

        this.state = useState({
            selectedCategoryId: null,
            posCategories: [],
            catMap: {},
            notaCategorias: [],
            searchText: "",
            lines: [],
            editingPedidoId: null,
            editingPedidoName: "",
            nota_general: "",
            fecha_entrega: tomorrowStr,
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
        let needsColors = false;

        // Method 1: Try POS models
        if (this.pos.models && this.pos.models["pos.category"]) {
            const cats = this.pos.models["pos.category"].getAll();
            if (cats && cats.length) {
                for (const c of cats) {
                    catMap[c.id] = {
                        id: c.id,
                        name: c.name,
                        color: c.color,
                        parent_id: c.parent_id ? (typeof c.parent_id === 'object' ? c.parent_id.id : c.parent_id) : null,
                    };
                    if (c.color === undefined) needsColors = true;
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
                                const col = cat && typeof cat === "object" ? cat.color : undefined;
                                catMap[catId] = {
                                    id: catId,
                                    name: catName,
                                    color: col,
                                    parent_id: parentId,
                                };
                                if (col === undefined) needsColors = true;
                            }
                        }
                    }
                }
            }
        }

        // If we have categories, try to get colors or build index directly
        // Validate categories against backend (fixes deleted categories still showing)
        if (Object.keys(catMap).length > 0) {
            this.orm.call(
                "pos.category", "search_read", [[], ["id", "color"]]
            ).then((result) => {
                if (result && result.length) {
                    const validIds = new Set();
                    for (const c of result) {
                        validIds.add(c.id);
                    }
                    // Remove deleted categories
                    for (const catId of Object.keys(catMap)) {
                        if (!validIds.has(Number(catId))) {
                            delete catMap[catId];
                        }
                    }
                    // Update colors from backend
                    if (needsColors) {
                        for (const c of result) {
                            if (catMap[c.id] && c.color !== undefined) {
                                catMap[c.id].color = c.color;
                            }
                        }
                    }
                }
                this._buildCategoryIndex(catMap);
            }).catch(() => {
                this._buildCategoryIndex(catMap);
            });
            return;
        }

        // Method 3: ORM fallback (full load + colors)
        if (Object.keys(catMap).length === 0) {
            this.orm.call(
                "pos.category", "search_read", [[], ["id", "name", "parent_id", "color"]]
            ).then((result) => {
                if (result && result.length) {
                    for (const c of result) {
                        catMap[c.id] = {
                            id: c.id,
                            name: c.name,
                            color: c.color,
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

    // Get the color of the deepest category for a product
    getProductColor(product) {
        if (!product || !product.pos_categ_ids || !product.pos_categ_ids.length) return "11";
        // Find deepest category (most child, lowest in hierarchy)
        let bestCat = null;
        let bestDepth = -1;
        for (const catRef of product.pos_categ_ids) {
            const catId = catRef && typeof catRef === "object" ? catRef.id : catRef;
            const cat = this.state.catMap?.[catId];
            if (cat) {
                const depth = this.getAncestorChain(catId).length;
                if (depth > bestDepth) {
                    bestDepth = depth;
                    bestCat = cat;
                } else if (bestCat === null) {
                    bestCat = cat;
                }
            }
        }
        const color = bestCat ? bestCat.color : undefined;
        return color !== undefined && color !== null ? String(color) : "11";
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
            notaGeneral: this.state.nota_general,
            fechaEntrega: this.state.fecha_entrega,
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
                fecha_entrega: this.state.fecha_entrega,
            }
        ).then((result) => {
            if (result && result.error) {
                this.notification.add(String(result.error), { type: "danger" });
            } else if (result && result.name) {
                this.notification.add(
                    _t("Pedido %s creado correctamente", result.name),
                    { type: "success" }
                );
                 this.state.nota_general = "";
                this.state.fecha_entrega = this.tomorrowStr;
                this.state.lines = [];
            } else {
                this.notification.add(
                    _t("Respuesta inesperada del servidor"),
                    { type: "warning" }
                );
            }
        }).catch((error) => {
            var msg = error;
            try {
                if (error.data && error.data.message) msg = error.data.message;
                else if (error.message) msg = error.message;
                else msg = JSON.stringify(error);
            } catch(e) {}
            this.notification.add(msg, { type: "danger" });
        });
    }

    get totalLines() {
        return this.state.lines.length;
    }

    get posConfigName() {
        return this.pos.config?.name || '';    }

    goBack() {
        this.pos.navigate("LoginScreen");
    }

    onProductClick(product) {
        this.addLine(product);
    }

    // --- Pedido management (edit/cancel) ---

    openPedidoList() {
        this.orm.call(
            "tpv.pedido", "get_pedidos_today_for_pos",
            [this.pos.config.id]
        ).then((pedidos) => {
            this.dialog.add(PedidoListPopup, {
                pedidos: pedidos,
                onSelect: (pedido) => {
                    this._loadPedidoForEdit(pedido);
                },
            });
        }).catch((err) => {
            this.notification.add("Error al cargar pedidos", { type: "danger" });
        });
    }

    _loadPedidoForEdit(pedido) {
        // Clear current order
        this.state.lines = [];
        // Load pedido lines
        for (const l of pedido.line_ids) {
            this.state.lines.push({
                id: Date.now() + Math.random(),
                product_id: l.product_id,
                product_name: l.product_name,
                qty: l.qty,
                precio_unitario: 0,
                nota_linea: l.nota_linea || "",
                nota_categoria_id: l.nota_categoria_id || null,
                nota_categoria_name: l.nota_categoria_name || "",
            });
        }
        this.state.editingPedidoId = pedido.id;
        this.state.editingPedidoName = pedido.name;
        this.state.nota_general = pedido.nota_general || "";
        this.state.fecha_entrega = pedido.fecha_entrega || this._defaultFechaEntrega;

        // Re-fetch prices from pos.models
        if (this.pos.models && this.pos.models["product.product"]) {
            for (const line of this.state.lines) {
                const prod = this.pos.models["product.product"].get(line.product_id);
                if (prod) {
                    line.precio_unitario = prod.lst_price || 0;
                }
            }
        }
        this.state.lines = [...this.state.lines];
    }

    get isEditing() {
        return this.state.editingPedidoId !== null;
    }

    updatePedido() {
        if (this.state.lines.length === 0) return;
        const lines = this.state.lines.map((l) => ({
            product_id: l.product_id,
            qty: l.qty,
            nota_linea: l.nota_linea,
            nota_categoria_id: l.nota_categoria_id,
        }));
        this.orm.call(
            "tpv.pedido", "update_pedido_from_pos", [],
            {
                pedido_id: this.state.editingPedidoId,
                lines: lines,
                nota_general: this.state.nota_general || "",
                fecha_entrega: this.state.fecha_entrega || "",
            }
        ).then((result) => {
            if (result && result.name) {
                this.notification.add(
                    "Pedido " + result.name + " actualizado",
                    { type: "success" }
                );
                this.state.editingPedidoId = null;
                this.state.editingPedidoName = "";
                this.state.fecha_entrega = this.tomorrowStr;
                this.state.lines = [];
            }
        }).catch((error) => {
            var msg = error;
            try {
                if (error.data && error.data.message) msg = error.data.message;
                else if (error.message) msg = error.message;
                else msg = JSON.stringify(error);
            } catch(e) {}
            this.notification.add(msg, { type: "danger" });
        });
    }

    cancelPedido() {
        if (!this.state.editingPedidoId) return;
        this.orm.call(
            "tpv.pedido", "cancel_pedido_from_pos",
            [this.state.editingPedidoId]
        ).then((result) => {
            if (result && result.state === 'cancelled') {
                this.notification.add(
                    "Pedido cancelado",
                    { type: "success" }
                );
                this.state.editingPedidoId = null;
                this.state.editingPedidoName = "";
                this.state.nota_general = "";
                this.state.lines = [];
            }
        }).catch((error) => {
            var msg = error;
            try {
                if (error.data && error.data.message) msg = error.data.message;
                else if (error.message) msg = error.message;
                else msg = JSON.stringify(error);
            } catch(e) {}
            this.notification.add(msg, { type: "danger" });
        });
    }

    cancelEditing() {
        // Cancel edit without server call - just clear
        this.state.editingPedidoId = null;
        this.state.editingPedidoName = "";
        this.state.nota_general = "";
        this.state.fecha_entrega = this.tomorrowStr;
        this.state.lines = [];
    }
}

registry.category("pos_pages").add("PedidoScreen", {
    name: "PedidoScreen",
    component: PedidoScreen,
    route: "/pos/ui/" + odoo.pos_config_id + "/pedido",
    params: {},
});