# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models
from odoo.exceptions import UserError


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
        relation='tpv_pedido_config_module2_exclude_category_rel',
        column1='tpv_pedido_config_id', column2='pos_category_id',
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
    module5_category_ids = fields.Many2many(
        'pos.category', string='Categorias',
        relation='tpv_pedido_config_module5_category_rel',
        column1='tpv_pedido_config_id', column2='pos_category_id',
        help='Categorias a incluir en este modulo.',
    )

    module1_line_ids = fields.One2many(
        'tpv.pedido.report.line', 'config_id',
        string='Categorias Modulo 1',
        domain=[('module', '=', '1')],
        context={'default_module': '1'},
    )
    module4_line_ids = fields.One2many(
        'tpv.pedido.report.line', 'config_id',
        string='Categorias Modulo 4',
        domain=[('module', '=', '4')],
        context={'default_module': '4'},
    )

    @api.model
    def get_config(self):
        """Returns the singleton config record, creating it if needed."""
        config = self.search([], limit=1)
        if not config:
            config = self.create({'name': 'Configuracion Obrador'})
        return config

    @api.model
    def action_open_config(self):
        """Opens the singleton configuration form."""
        config = self.get_config()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tpv.pedido.config',
            'view_mode': 'form',
            'res_id': config.id,
            'target': 'current',
        }

    def action_print_report(self):
        """Genera el reporte PDF de los 5 modulos inmediatamente."""
        pedido_model = self.env['tpv.pedido']
        from datetime import datetime, timedelta

        today = fields.Date.today()

        # Get ALL confirmed pedidos with pending delivery
        all_pedidos = pedido_model.search([
            ('state', '=', 'confirmed'),
            ('fecha_entrega', '>=', today),
        ])
        web_orders = self.env['sale.order'].search([
            ('state', '=', 'sale'),
            ('tpv_pedido_id', '=', False),
        ])

        if not all_pedidos and not web_orders:
            raise UserError('No hay pedidos pendientes para generar el reporte.')

        # Module 1: Generate with WeasyPrint (landscape, clean design)
        import io
        try:
            from PyPDF2 import PdfMerger
        except ImportError:
            from pypdf import PdfMerger as PdfMerger
        
        merger = PdfMerger()
        
        pdf1 = pedido_model._generate_modulo1_pdf(all_pedidos, web_orders, today)
        if pdf1:
            merger.append(io.BytesIO(pdf1))
        
        # Modules 2-5: WeasyPrint (A4 portrait, modulo_generico template)
        if self.module2_active:
            pdf2 = pedido_model._generate_modulo2_pdf(all_pedidos, today, self.module2_title)
            if pdf2:
                merger.append(io.BytesIO(pdf2))

        if self.module3_active:
            pdf3 = pedido_model._generate_modulo3_pdf(web_orders, today, self.module3_title)
            if pdf3:
                merger.append(io.BytesIO(pdf3))

        if self.module4_active:
            pdf4 = pedido_model._generate_modulo4_pdf(all_pedidos, today, self.module4_title)
            if pdf4:
                merger.append(io.BytesIO(pdf4))

        if self.module5_active:
            pdf5 = pedido_model._generate_modulo5_pdf(all_pedidos, web_orders, today, self.module5_title)
            if pdf5:
                merger.append(io.BytesIO(pdf5))
        
        # Get merged PDF
        output = io.BytesIO()
        merger.write(output)
        merger.close()
        pdf_content = output.getvalue()

        # Create attachment and return download action
        attachment = self.env['ir.attachment'].create({
            'name': 'reporte_obrador_%s.pdf' % today,
            'datas': base64.b64encode(pdf_content).decode(),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    @api.model_create_multi
    def create(self, vals_list):
        """Enforce singleton: if a record already exists, update it instead."""
        existing = self.search([], limit=1)
        if existing:
            for vals in vals_list:
                existing.write(vals)
            return existing
        return super().create(vals_list)
