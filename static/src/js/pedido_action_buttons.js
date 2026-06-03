/* tpv_pedidos - PedidoActionButtons
 * Botones de acción: "Encargo" y "Pedido Tienda"
 */
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { PedidoConfirmPopup } from "@tpv_pedidos/js/pedido_confirm_popup";

export class PedidoActionButtons extends Component {
    static template = "tpv_pedidos.PedidoActionButtons";
    static props = {
        lines: { type: Array },
        linesToJSON: { type: Function },
        posConfigId: { type: Number },
        posConfigName: { type: String },
        onClear: { type: Function },
    };

    setup() {
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get hasLines() {
        return this.props.lines.length > 0;
    }

    _openConfirmPopup(tipoPedido) {
        this.dialog.add(PedidoConfirmPopup, {
            tipoPedido: tipoPedido,
            lines: this.props.lines,
            linesToJSON: this.props.linesToJSON,
            posConfigId: this.props.posConfigId,
            posConfigName: this.props.posConfigName,
            onConfirm: async (notaGeneral) => {
                await this._createPedido(tipoPedido, notaGeneral);
            },
        });
    }

    async _createPedido(tipoPedido, notaGeneral) {
        const lines = this.props.linesToJSON();
        try {
            const result = await this.orm.call(
                "tpv.pedido",
                "create_pedido_from_pos",
                [],
                {
                    pos_config_id: this.props.posConfigId,
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
                this.props.onClear();
            }
        } catch (error) {
            this.notification.add(
                _t("Error al crear el pedido: %s", error.message || error),
                { type: "danger" }
            );
        }
    }

    onClickEncargo() {
        if (!this.hasLines) {
            this.notification.add(_t("Añade al menos un producto al pedido."), { type: "warning" });
            return;
        }
        this._openConfirmPopup("encargo");
    }

    onClickPedidoTienda() {
        if (!this.hasLines) {
            this.notification.add(_t("Añade al menos un producto al pedido."), { type: "warning" });
            return;
        }
        this._openConfirmPopup("pedido_tienda");
    }
}