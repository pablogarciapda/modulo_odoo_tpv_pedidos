/* tpv_pedidos - NotaLineaPopup
 * Popup para añadir nota (categoría + texto libre) a una línea de pedido
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class NotaLineaPopup extends Component {
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
        const categoriaName = "";
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