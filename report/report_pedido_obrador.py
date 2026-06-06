# -*- coding: utf-8 -*-
from odoo import api, models


class ReportPedidoObrador(models.AbstractModel):
    _name = 'report.tpv_pedidos.report_pedido_obrador'
    _description = 'Reporte de Pedidos al Obrador (4 bloques)'

    @api.model
    def _get_report_values(self, docids, data=None):
        if data and data.get('bloque1'):
            # Data was passed from _generar_reporte_4_bloques
            return {
                'doc_ids': docids,
                'doc_model': 'tpv.pedido',
                'docs': data.get('docs', []),
                'web_orders': data.get('web_orders', []),
                'data': data,
            }
        # Fallback: load from database (e.g. when printing from UI)
        docs = self.env['tpv.pedido'].browse(docids)
        from datetime import datetime
        fecha = datetime.now()
        report_data = {
            'fecha': fecha,
            'bloque1': docs._get_bloque1_data(docs, []),
            'bloque2': docs._get_bloque2_data([]),
            'bloque3': docs._get_bloque3_data(docs, pasteleria=False),
            'bloque4': docs._get_bloque4_data(docs),
            'docs': docs,
            'web_orders': [],
        }
        return {
            'doc_ids': docids,
            'doc_model': 'tpv.pedido',
            'docs': docs,
            'web_orders': [],
            'data': report_data,
        }
