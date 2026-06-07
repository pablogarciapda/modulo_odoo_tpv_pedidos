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
        config = self.env['tpv.pedido.config'].search([], limit=1)
        report_data = {
            'fecha': fecha,
            'bloque1': docs._get_bloque1_data(docs, []),
            'bloque2': docs._get_bloque2_data([]),
            'bloque3': docs._get_bloque3_data(docs),
            'bloque4': docs._get_bloque4_data(docs),
            'bloque5': docs._get_bloque5_data(docs, []),
            'module1_title': config.module1_title if config else 'Totales por Familia Principal',
            'module2_title': config.module2_title if config else 'Encargos de Tiendas',
            'module3_title': config.module3_title if config else 'Pedidos de Clientes',
            'module4_title': config.module4_title if config else 'Encargos Especificos',
            'module5_title': config.module5_title if config else 'Pedidos Personalizados',
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
