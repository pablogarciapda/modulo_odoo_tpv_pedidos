# -*- coding: utf-8 -*-
from odoo import fields, models


class TpvPedidoReportLine(models.Model):
    _name = 'tpv.pedido.report.line'
    _description = 'Linea de configuracion de modulo del reporte'
    _order = 'sequence, id'

    config_id = fields.Many2one('tpv.pedido.config', string='Configuracion',
        ondelete='cascade', required=True)
    module = fields.Selection([
        ('1', 'Modulo 1 - Totales'),
        ('4', 'Modulo 4 - Encargos'),
        ('5', 'Modulo 5 - Pedidos'),
    ], string='Modulo', required=True)
    category_id = fields.Many2one('pos.category', string='Categoria',
        required=True)
    copies = fields.Integer(string='Copias', default=1,
        help='Numero de copias a imprimir de esta categoria (solo Modulo 1).')
    sequence = fields.Integer(string='Secuencia', default=10)
