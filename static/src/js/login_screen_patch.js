/* tpv_pedidos - LoginScreen Patch
 * Añade botón "Pedido a Obrador" en la LoginScreen del POS
 */
import { patch } from "@web/core/utils/patch";
import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";
import { _t } from "@web/core/l10n/translation";

patch(LoginScreen.prototype, {
    openPedidoObrador() {
        this.pos.navigate("PedidoScreen");
    },
});