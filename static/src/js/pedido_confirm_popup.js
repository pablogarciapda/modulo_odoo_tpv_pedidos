/* tpv_pedidos - PedidoConfirmPopup
 * Popup de confirmación con nota general antes de enviar el pedido
 */
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class PedidoConfirmPopup extends Component {
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