# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TpvPedidoConfig(models.Model):
    _name = 'tpv.pedido.config'
    _description = 'Configuracion de impresion del obrador'
    _rec_name = 'name'

    name = fields.Char(string='Nombre', default='Configuracion Obrador', required=True)
    printer_ip = fields.Char(string='IP Impresora Obrador')
    printer_port = fields.Integer(string='Puerto', default=9100)
    printer_type = fields.Selection([
        ('esc_pos', 'ESC/POS (Termica Ticket)'),
        ('network', 'Impresora de Red (CUPS/IP)'),
    ], string='Tipo de Impresora', default='esc_pos')
    print_hour = fields.Float(string='Hora de impresion', default=2.0,
        help='Hora del dia en que se imprimira el resumen (0-23, ej: 2.0 = 02:00)')
