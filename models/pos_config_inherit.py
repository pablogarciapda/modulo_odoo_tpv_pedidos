# -*- coding: utf-8 -*-

from odoo import fields, models


class PosConfigInherit(models.Model):
    _inherit = 'pos.config'

    tpv_pedido_printer_ip = fields.Char(
        string='IP Impresora Obrador',
        help='Dirección IP de la impresora de red del obrador para '
             'la impresión automática de pedidos a las 02:00.',
    )
    tpv_pedido_printer_port = fields.Integer(
        string='Puerto Impresora Obrador',
        default=9100,
        help='Puerto de la impresora de red. Por defecto 9100 (ESC/POS).',
    )
    tpv_pedido_printer_type = fields.Selection(
        [
            ('esc_pos', 'ESC/POS (Térmica Ticket)'),
            ('network', 'Impresora de Red (CUPS/IP)'),
        ],
        string='Tipo de Impresora',
        default='esc_pos',
        help='Tipo de impresora conectada en red.',
    )
    tpv_pedido_print_hour = fields.Float(
        string='Hora de impresión',
        default=2.0,
        help='Hora del día en que se imprimirá automáticamente el resumen de pedidos en el obrador (0-23).',
    )