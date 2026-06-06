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
    print_hour = fields.Selection(
        [(str(h), '{:02d}:00'.format(h)) for h in range(24)],
        string='Hora de impresion',
        default='2',
        help='Hora del dia en que se imprimira automaticamente el resumen de pedidos.',
    )
    print_email_to = fields.Char(string='Email de destino',
        help='Direccion de email donde se enviara el reporte PDF.')
    print_email_active = fields.Boolean(string='Enviar por email', default=False)

    module1_title = fields.Char(string='Titulo Modulo 1', default='Totales por Familia Principal')
    module1_active = fields.Boolean(string='Imprimir modulo', default=True)
    module1_description = fields.Text(string='Descripcion',
        default='Totales por categoria principal con numero de copias por categoria. '
                'Muestra las cantidades totales de cada producto agrupado por familia.')

    module2_title = fields.Char(string='Titulo Modulo 2', default='Encargos de Tiendas')
    module2_active = fields.Boolean(string='Imprimir modulo', default=True)
    module2_description = fields.Text(string='Descripcion',
        default='Todos los encargos de las tiendas, excluyendo las categorias seleccionadas. '
                'Agrupados por tienda con notas y productos.')
    module2_exclude_category_ids = fields.Many2many(
        'pos.category', string='Excluir categorias',
        help='Categorias a EXCLUIR de los encargos del Modulo 2.',
    )

    module3_title = fields.Char(string='Titulo Modulo 3', default='Pedidos de Clientes')
    module3_active = fields.Boolean(string='Imprimir modulo', default=True)
    module3_description = fields.Text(string='Descripcion',
        default='Pedidos de clientes externos (VIP y tarjeta). '
                'Incluye datos de contacto y metodo de entrega.')

    module4_title = fields.Char(string='Titulo Modulo 4', default='Encargos Especificos')
    module4_active = fields.Boolean(string='Imprimir modulo', default=True)
    module4_description = fields.Text(string='Descripcion',
        default='Encargos filtrados por categorias seleccionadas.')

    module5_title = fields.Char(string='Titulo Modulo 5', default='Pedidos Personalizados')
    module5_active = fields.Boolean(string='Imprimir modulo', default=True)
    module5_description = fields.Text(string='Descripcion',
        default='Seleccione el origen y las categorias para este modulo.')
    module5_origin_web = fields.Boolean(string='Web', default=False)
    module5_origin_encargo = fields.Boolean(string='Encargo', default=False)
    module5_origin_pedido = fields.Boolean(string='Pedido Tienda', default=False)

    report_line_ids = fields.One2many(
        'tpv.pedido.report.line', 'config_id',
        string='Configuracion de modulos',
    )
