/* tpv_pedidos - PedidoOrder
 * Gestión local del carrito del pedido (sin crear orden POS real)
 */
import { Component, useState } from "@odoo/owl";

export class PedidoOrder extends Component {
    static template = "tpv_pedidos.PedidoOrder";

    setup() {
        this.state = useState({
            lines: [],
        });
    }

    addLine(product, qty = 1) {
        const existingLine = this.state.lines.find(
            (l) => l.product_id === product.id && !l.nota_linea && !l.nota_categoria_id
        );
        if (existingLine) {
            existingLine.qty += qty;
        } else {
            this.state.lines.push({
                id: Date.now(),
                product_id: product.id,
                product_name: product.display_name,
                qty: qty,
                precio_unitario: product.lst_price,
                nota_linea: "",
                nota_categoria_id: null,
                nota_categoria_name: "",
            });
        }
    }

    removeLine(lineId) {
        const index = this.state.lines.findIndex((l) => l.id === lineId);
        if (index !== -1) {
            this.state.lines.splice(index, 1);
        }
    }

    updateQty(lineId, newQty) {
        const line = this.state.lines.find((l) => l.id === lineId);
        if (line) {
            line.qty = newQty;
            if (newQty <= 0) {
                this.removeLine(lineId);
            }
        }
    }

    setNotaLinea(lineId, nota) {
        const line = this.state.lines.find((l) => l.id === lineId);
        if (line) {
            line.nota_linea = nota;
        }
    }

    setNotaCategoria(lineId, categoriaId, categoriaName) {
        const line = this.state.lines.find((l) => l.id === lineId);
        if (line) {
            line.nota_categoria_id = categoriaId;
            line.nota_categoria_name = categoriaName;
        }
    }

    get totalLines() {
        return this.state.lines.length;
    }

    get toJSON() {
        return this.state.lines.map((l) => ({
            product_id: l.product_id,
            qty: l.qty,
            nota_linea: l.nota_linea,
            nota_categoria_id: l.nota_categoria_id,
        }));
    }

    clear() {
        this.state.lines = [];
    }
}