# -*- coding: utf-8 -*-

from odoo import api, models


class ReportPedidoObrador(models.AbstractModel):
    _name = 'report.tpv_pedidos.report_pedido_obrador'
    _description = 'Reporte de Pedidos al Obrador'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['tpv.pedido'].browse(docids)
        resumen = docs.get_resumen_por_producto(
            date_from=min(docs.mapped('date_pedido')),
            date_to=max(docs.mapped('date_pedido')),
        )
        detalle = docs.get_detalle_por_tienda(
            date_from=min(docs.mapped('date_pedido')),
            date_to=max(docs.mapped('date_pedido')),
        )
        # Ordenar resumen por cantidad descendente
        resumen_sorted = sorted(
            resumen.values(), key=lambda x: x['qty_total'], reverse=True
        )
        return {
            'doc_ids': docids,
            'doc_model': 'tpv.pedido',
            'docs': docs,
            'resumen': resumen_sorted,
            'detalle': detalle,
        }