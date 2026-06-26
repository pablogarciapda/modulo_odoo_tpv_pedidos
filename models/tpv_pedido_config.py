# -*- coding: utf-8 -*-
import base64
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError


class TpvPedidoConfig(models.Model):
    _name = 'tpv.pedido.config'
    _description = 'Configuracion de impresion del obrador'
    _rec_name = 'name'

    name = fields.Char(string='Nombre', default='Configuracion Obrador', required=True)
    printer_ip = fields.Char(string='IP Impresora Obrador')
    printer_port = fields.Char(string='Puerto', default='9100',
        help='Puerto de la impresora de red (ej: 9100).')
    printer_type = fields.Selection([
        ('esc_pos', 'ESC/POS (Termica Ticket)'),
        ('network', 'Impresora de Red (CUPS/IP)'),
    ], string='Tipo de Impresora', default='esc_pos')
    print_hour = fields.Selection(
        [(f'{h:02d}', f'{h:02d}') for h in range(24)],
        string='Hora de impresion',
        default='02',
        help='Hora a la que se imprimira automaticamente el resumen de pedidos.',
    )
    print_minute = fields.Selection(
        [(f'{m:02d}', f'{m:02d}') for m in range(60)],
        string='Minuto de impresion',
        default='00',
        help='Minuto de la hora de impresion.',
    )
    print_email_to = fields.Char(string='Email de destino',
        help='Direccion de email donde se enviara el reporte PDF.')
    print_email_active = fields.Boolean(string='Enviar por email', default=False)
    font_size = fields.Integer(string='Fuente base', default=11,
        help='Tamano base de la fuente en puntos (8-14).')
    font_size_title = fields.Integer(string='Fuente titulos', default=14,
        help='Tamano de los titulos.')
    font_size_section = fields.Integer(string='Fuente secciones', default=12,
        help='Tamano de los nombres de seccion.')
    font_size_notes = fields.Integer(string='Fuente notas', default=9,
        help='Tamano de las notas por producto.')
    font_size_date = fields.Integer(string='Fuente fecha', default=11,
        help='Tamano de la fecha en los informes.')
    font_size_sub = fields.Integer(string='Fuente sub', default=10,
        help='Tamano de textos secundarios (item-sub).')
    font_size_table_header = fields.Integer(string='Fuente tabla cabecera', default=9,
        help='Tamano de las cabeceras de tabla.')
    font_size_table_cell = fields.Integer(string='Fuente tabla celdas', default=9,
        help='Tamano de las celdas de tabla.')
    font_size_footer = fields.Integer(string='Fuente pie pagina', default=9,
        help='Tamano del pie de pagina, contador y etiquetas de copia.')

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
        """Genera el reporte PDF, guarda backup y descarga. No imprime ni envía email."""
        pedido_model = self.env['tpv.pedido']
        from datetime import datetime, timedelta

        today = fields.Date.today()

        all_pedidos = pedido_model.search([
            ('state', '=', 'confirmed'),
            ('fecha_entrega', '=', today),
        ])
        web_orders = self.env['sale.order'].search([
            ('fecha_entrega', '=', today),
            ('state', '=', 'sale'),
            ('tpv_pedido_id', '=', False),
        ])

        if not all_pedidos and not web_orders:
            raise UserError('No hay pedidos pendientes para generar el reporte.')

        import io
        try:
            from PyPDF2 import PdfMerger
        except ImportError:
            from pypdf import PdfMerger as PdfMerger
        
        merger = PdfMerger()

        try:
            import weasyprint
            from weasyprint import HTML
            test_pdf = HTML(string='<html><body><p>t</p></body></html>').write_pdf()
            if not test_pdf or len(test_pdf) < 50:
                raise Exception('PDF vacio')
        except (ImportError, OSError, Exception) as e:
            msg = (
                '<h3>Falta WeasyPrint para generar informes PDF</h3>'
                '<p>Ejecutar segun tu entorno:</p>'
                '<br/><b>En DOCKER:</b><br/>'
                '<code>docker exec -u root NOMBRE_CONTENEDOR pip3 install weasyprint --break-system-packages</code><br/>'
                '<code>docker exec -u root NOMBRE_CONTENEDOR apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info</code>'
                '<br/><br/><b>En VPS:</b><br/>'
                '<code>pip3 install weasyprint --break-system-packages</code><br/>'
                '<code>sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info</code>'
                '<br/><br/><b>Verificar:</b><br/>'
                '<code>python3 -c "import weasyprint; print(weasyprint.__version__)"</code>'
            )
            raise UserError(msg)

        pdf1 = pedido_model._generate_modulo1_pdf(all_pedidos, web_orders, today)
        if pdf1:
            merger.append(io.BytesIO(pdf1))
        
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

        output = io.BytesIO()
        merger.write(output)
        merger.close()
        pdf_content = output.getvalue()

        # Save backup
        BackupFile = self.env['tpv.backup.file']
        fecha_str = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)
        filename = 'resumen_obrador_%s.pdf' % fecha_str
        file_path = BackupFile._save_pdf(pdf_content, filename)
        BackupFile.create({
            'name': 'Resumen obrador %s' % today,
            'date': fields.Datetime.now(),
            'date_pedido': today,
            'filename': filename,
            'file_path': file_path,
        })
        BackupFile._cleanup_old_files(days=30)

        # Return download
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

    def action_print_font_sample(self):
        """Genera un PDF de muestra con todas las fuentes configuradas."""
        import weasyprint

        fs = self.font_size or 11
        fs_title = self.font_size_title or 14
        fs_section = self.font_size_section or 12
        fs_notes = self.font_size_notes or 9
        fs_date = self.font_size_date or 11
        fs_sub = self.font_size_sub or 10
        fs_th = self.font_size_table_header or 9
        fs_td = self.font_size_table_cell or 9
        fs_footer = self.font_size_footer or 9

        html = '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
@page { size: A4 portrait; margin: 1.5cm;
    @bottom-center {
        content: "Pagina " counter(page) " de " counter(pages);
        font-size: ''' + str(fs_footer) + '''px;
        color: #999;
        font-family: 'DejaVu Sans', Arial, sans-serif;
    }
}
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: ''' + str(fs) + '''px; color: #222; }
.title { font-size: ''' + str(fs_title) + '''px; font-weight: bold; margin-bottom: 4px; }
.date { font-size: ''' + str(fs_date) + '''px; color: #666; margin-bottom: 12px; }
.section-title { font-size: ''' + str(fs_section) + '''px; font-weight: bold; margin: 10px 0 4px 0; color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 3px; }
.item-box { border: 1px solid #ddd; border-radius: 4px; padding: 6px 8px; margin-bottom: 6px; }
.item-name { font-weight: bold; font-size: ''' + str(fs) + '''px; }
.item-sub { color: #666; font-size: ''' + str(fs_sub) + '''px; }
.item-line { padding: 2px 0; font-size: ''' + str(fs) + '''px; border-bottom: 1px dotted #ccc; }
.item-line .qty { float: right; font-weight: bold; }
.item-line-alt { padding: 3px 0; font-size: ''' + str(fs) + '''px; border-bottom: 1px dashed #999; }
.item-line-alt .qty { float: right; font-weight: bold; }
.item-note { font-size: ''' + str(fs_notes) + '''px; color: #888; font-style: italic; padding-left: 12px; padding-bottom: 2px; }
table { width: 100%%; border-collapse: collapse; }
th { background: #2c2c2c; color: #fff; padding: 4px; font-size: ''' + str(fs_th) + '''px; text-align: left; }
td { padding: 3px 4px; border-bottom: 1px solid #eee; font-size: ''' + str(fs_td) + '''px; }
td.r { text-align: right; }
.tag { display: inline-block; background: #f0f0f0; color: #888; font-size: 8px; padding: 1px 5px; border-radius: 3px; font-family: monospace; margin-left: 4px; }
</style>
</head>
<body>
<div class="title">MUESTRA DE FUENTES <span class="tag">font_size_title = ''' + str(fs_title) + '''px</span></div>
<div class="date">23/06/2026 <span class="tag">font_size_date = ''' + str(fs_date) + '''px</span></div>

<div class="section-title">SECCION DE EJEMPLO <span class="tag">font_size_section = ''' + str(fs_section) + '''px</span></div>

<div class="item-box">
<div class="item-name">Producto de ejemplo <span class="tag">font_size = ''' + str(fs) + '''px</span></div>
<div class="item-sub">Tel: 666 123 456 <span class="tag">font_size_sub = ''' + str(fs_sub) + '''px</span></div>
<div class="item-sub">Entrega: Recoger en Tienda <span class="tag">font_size_sub = ''' + str(fs_sub) + '''px</span></div>

<div class="item-line">Pan de molde integral <span class="qty">12 uds</span></div>
<div class="item-line-alt">Croissant de mantequilla <span class="qty">24 uds</span></div>
<div class="item-note">Sin gluten, por favor <span class="tag">font_size_notes = ''' + str(fs_notes) + '''px</span></div>
<div class="item-line">Barra de payes <span class="qty">6 uds</span></div>
<div class="item-note">Muy hecho <span class="tag">font_size_notes = ''' + str(fs_notes) + '''px</span></div>

<table>
<thead>
<tr><th>Producto <span class="tag" style="color:#ccc;">font_size_table_header = ''' + str(fs_th) + '''px</span></th><th class="r">Cant.</th><th class="r">Total</th></tr>
</thead>
<tbody>
<tr><td>Pan integral</td><td class="r">12</td><td class="r">24.00</td></tr>
<tr><td>Croissant</td><td class="r">24</td><td class="r">36.00</td></tr>
<tr><td>Barra payes</td><td class="r">6</td><td class="r">12.00</td></tr>
<tr><td colspan="3" style="font-size: ''' + str(fs_td) + '''px; color: #999; text-align:center;">font_size_table_cell = ''' + str(fs_td) + '''px <span style="font-size:8px;color:#ccc;">(celdas de tabla)</span></td></tr>
</tbody>
</table>
</div>

<div class="section-title" style="margin-top:18px;">RESUMEN DE CAMPOS</div>
<table>
<thead>
<tr><th>Campo</th><th>Valor</th><th>Uso</th></tr>
</thead>
<tbody>
<tr><td>font_size</td><td>''' + str(fs) + '''px</td><td>body, item-name, item-line</td></tr>
<tr><td>font_size_title</td><td>''' + str(fs_title) + '''px</td><td>.title (titulo del informe)</td></tr>
<tr><td>font_size_section</td><td>''' + str(fs_section) + '''px</td><td>.section-title, category-name</td></tr>
<tr><td>font_size_notes</td><td>''' + str(fs_notes) + '''px</td><td>.item-note (notas de producto)</td></tr>
<tr><td>font_size_date</td><td>''' + str(fs_date) + '''px</td><td>.date (fecha del informe)</td></tr>
<tr><td>font_size_sub</td><td>''' + str(fs_sub) + '''px</td><td>.item-sub (telefono, entrega)</td></tr>
<tr><td>font_size_table_header</td><td>''' + str(fs_th) + '''px</td><td>th (cabeceras de tabla)</td></tr>
<tr><td>font_size_table_cell</td><td>''' + str(fs_td) + '''px</td><td>td (celdas de tabla)</td></tr>
<tr><td>font_size_footer</td><td>''' + str(fs_footer) + '''px</td><td>@bottom-center, .footer, .copy-label</td></tr>
</tbody>
</table>

<div style="margin-top:12px; font-size:8px; color:#999; text-align:center;">
font_size_footer = ''' + str(fs_footer) + '''px — (pie de pagina, numeracion, etiqueta de copia)
</div>
</body>
</html>'''

        pdf_content = weasyprint.HTML(string=html).write_pdf()

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'muestra_fuentes_obrador.pdf',
            'datas': base64.b64encode(pdf_content).decode(),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def write(self, vals):
        """Override write to recalculate cron nextcall when print_hour or print_minute changes."""
        res = super().write(vals)
        if 'print_hour' in vals or 'print_minute' in vals:
            self._update_cron_nextcall()
        return res

    def _update_cron_nextcall(self):
        """Recalcula el nextcall del cron para que coincida con print_hour/print_minute."""
        from datetime import datetime, timedelta
        import pytz

        cron = self.env['ir.cron'].sudo().search([
            ('name', '=', 'TPV Pedidos: Imprimir resumen diario del obrador'),
        ], limit=1)
        if not cron:
            return

        spain_tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(spain_tz)
        config = self.sudo().browse(self.id) if self.id else self

        target_hour = int(config.print_hour or '02')
        target_minute = int(config.print_minute or '00')

        # Calculate today's target time in Spain timezone
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

        # If already passed, set for tomorrow
        if target <= now:
            target += timedelta(days=1)

        # Convert to UTC for Odoo's cron system
        target_utc = target.astimezone(pytz.UTC).replace(tzinfo=None)

        cron.write({
            'nextcall': target_utc.strftime('%Y-%m-%d %H:%M:%S'),
            'interval_number': 1,
            'interval_type': 'days',
        })

    @api.model_create_multi
    def create(self, vals_list):
        """Enforce singleton: if a record already exists, update it instead."""
        existing = self.search([], limit=1)
        if existing:
            for vals in vals_list:
                existing.write(vals)
            return existing
        records = super().create(vals_list)
        records._update_cron_nextcall()
        return records
