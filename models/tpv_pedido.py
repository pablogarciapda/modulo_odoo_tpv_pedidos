# -*- coding: utf-8 -*-

import base64
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta

_logger = logging.getLogger(__name__)


class TpvPedido(models.Model):
    _name = 'tpv.pedido'
    _description = 'Pedido al Obrador desde TPV'
    _order = 'date_pedido desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    pos_config_id = fields.Many2one(
        'pos.config',
        string='Tienda (TPV)',
        required=True,
        tracking=True,
    )
    tipo_pedido = fields.Selection(
        [
            ('encargo', 'Encargo'),
            ('pedido_tienda', 'Pedido Tienda'),
        ],
        string='Tipo de Pedido',
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('confirmed', 'Confirmado'),
            ('done', 'Hecho'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        tracking=True,
    )
    nota_general = fields.Text(
        string='Nota General',
    )
    date_pedido = fields.Date(
        string='Fecha del Pedido',
        default=fields.Date.context_today,
        required=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Pedido de Venta',
        readonly=True,
        copy=False,
    )
    line_ids = fields.One2many(
        'tpv.pedido.linea',
        'pedido_id',
        string='Líneas del Pedido',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    es_encargo = fields.Boolean(
        string='Es Encargo',
        compute='_compute_es_encargo',
        store=True,
    )
    fecha_entrega = fields.Date(
        string='Fecha de entrega',
        help='Fecha en que el cliente/tienda necesita recibir el pedido. '
             'Para pedidos tienda se calcula automaticamente como date_pedido + 1.',
        compute='_compute_fecha_entrega',
        store=True,
        readonly=False,
    )

    @api.depends('tipo_pedido')
    def _compute_es_encargo(self):
        for rec in self:
            rec.es_encargo = rec.tipo_pedido == 'encargo'

    @api.depends('date_pedido', 'tipo_pedido')
    def _compute_fecha_entrega(self):
        for rec in self:
            if rec.tipo_pedido == 'encargo' and rec.fecha_entrega:
                # Manual, keep as is
                continue
            elif rec.tipo_pedido == 'pedido_tienda':
                rec.fecha_entrega = rec.date_pedido + timedelta(days=1)
            else:
                rec.fecha_entrega = rec.date_pedido

    @api.model
    def _get_store_partner(self, pos_config_id):
        """
        Devuelve o crea un partner con el nombre de la tienda (pos.config).
        Este partner se usa como cliente del pedido en lugar del OBRADOR genérico.
        """
        pos_config = self.env['pos.config'].browse(pos_config_id)
        if not pos_config or not pos_config.name:
            return False
        store_name = pos_config.name
        partner = self.env['res.partner'].sudo().search([
            ('name', '=', store_name),
        ], limit=1)
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name': store_name,
                'is_company': True,
            })
        return partner

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tpv.pedido'
                ) or _('New')
            # Asignar la tienda como cliente por defecto
            if not vals.get('partner_id') and vals.get('pos_config_id'):
                store_partner = self._get_store_partner(vals['pos_config_id'])
                if store_partner:
                    vals['partner_id'] = store_partner.id
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(
                    _('No se puede confirmar un pedido sin líneas.')
                )
            rec._create_sale_order()
            rec.write({'state': 'confirmed'})

    def action_cancel(self):
        for rec in self:
            if rec.sale_order_id:
                so = rec.sale_order_id
                # Cancel the sale.order if it's in sale state
                if so.state == 'sale':
                    so.sudo().action_cancel()
                elif so.state == 'draft' or so.state == 'sent':
                    so.sudo().action_cancel()
                elif so.state == 'done':
                    raise ValidationError(
                        _('No se puede cancelar un pedido cuyo pedido de venta ya está hecho.')
                    )
            rec.write({'state': 'cancelled'})

    def action_draft(self):
        for rec in self:
            rec.write({'state': 'draft'})

    def action_view_sale_order(self):
        """Abre el sale.order asociado al pedido."""
        self.ensure_one()
        if not self.sale_order_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
            'target': 'current',
        }

    @api.model
    def create_pedido_from_pos(self, pos_config_id, tipo_pedido, lines,
                               nota_general='', partner_id=False, fecha_entrega=None):
        """
        Crea un pedido desde el frontend del TPV.
        Usado por el controller JSON-RPC y directamente por orm.call.

        :param pos_config_id: ID del pos.config (tienda)
        :param tipo_pedido: 'encargo' o 'pedido_tienda'
        :param lines: lista de dicts [{product_id, qty, nota_linea, nota_categoria_id}]
        :param nota_general: texto libre
        :param partner_id: ID del cliente (opcional)
        :return: dict con {pedido_id, name, sale_order_id}
        """
        if not lines:
            raise ValidationError(
                _('El pedido debe tener al menos una línea.')
            )

        # Cliente por defecto: el nombre de la tienda
        if not partner_id:
            store_partner = self._get_store_partner(pos_config_id)
            if store_partner:
                partner_id = store_partner.id

        # Validate fecha_entrega
        if fecha_entrega:
            fecha_entrega_date = fields.Date.to_date(fecha_entrega)
            min_date = fields.Date.today() + timedelta(days=1)
            if fecha_entrega_date < min_date:
                raise ValidationError(
                    _('La fecha de entrega debe ser igual o posterior a mañana.')
                )
        else:
            fecha_entrega = fields.Date.today() + timedelta(days=1)

        line_vals = []
        for line in lines:
            line_vals.append((0, 0, {
                'product_id': line.get('product_id'),
                'qty': line.get('qty', 1.0),
                'nota_linea': line.get('nota_linea', ''),
                'nota_categoria_id': line.get('nota_categoria_id') or False,
            }))

        pedido_vals = {
            'pos_config_id': pos_config_id,
            'tipo_pedido': tipo_pedido,
            'partner_id': partner_id,
            'nota_general': nota_general,
            'fecha_entrega': fecha_entrega,
            'line_ids': line_vals,
        }

        pedido = self.create(pedido_vals)
        pedido.action_confirm()
        return {
            'pedido_id': pedido.id,
            'name': pedido.name,
            'sale_order_id': pedido.sale_order_id.id,
        }

    @api.model
    def update_pedido_from_pos(self, pedido_id, lines, nota_general='', fecha_entrega=None):
        """
        Actualiza un pedido existente desde el frontend POS.
        Reemplaza líneas y opcionalmente la nota general.
        """
        pedido = self.sudo().browse(pedido_id)
        if not pedido.exists():
            raise ValidationError(_('El pedido no existe.'))
        if pedido.state not in ('draft', 'confirmed'):
            raise ValidationError(
                _('Solo se pueden modificar pedidos en borrador o confirmados.')
            )

        # Reemplazar líneas
        line_vals = []
        for line in lines:
            line_vals.append((0, 0, {
                'product_id': line.get('product_id'),
                'qty': line.get('qty', 1.0),
                'nota_linea': line.get('nota_linea', ''),
                'nota_categoria_id': line.get('nota_categoria_id') or False,
            }))

        pedido.line_ids.unlink()
        vals = {
            'line_ids': line_vals,
            'nota_general': nota_general,
        }
        if fecha_entrega:
            vals['fecha_entrega'] = fecha_entrega
        pedido.write(vals)

        # Si estaba confirmado, mantener confirmado;
        # si estaba en borrador, confirmar automáticamente
        if pedido.state == 'draft':
            pedido.action_confirm()

        return {
            'pedido_id': pedido.id,
            'name': pedido.name,
            'sale_order_id': pedido.sale_order_id.id if pedido.sale_order_id else False,
        }

    @api.model
    def cancel_pedido_from_pos(self, pedido_id):
        """Cancela un pedido desde el frontend POS."""
        pedido = self.sudo().browse(pedido_id)
        if not pedido.exists():
            raise ValidationError(_('El pedido no existe.'))
        pedido.action_cancel()
        return {
            'pedido_id': pedido.id,
            'state': pedido.state,
        }

    @api.model
    def get_pedidos_today_for_pos(self, pos_config_id):
        """
        Devuelve los pedidos para una tienda específica desde el POS.
        Incluye:
          - Pedidos de hoy (date_pedido = today) para poder modificarlos.
          - Encargos con fecha de entrega >= mañana (fecha_entrega >= tomorrow)
            para poder cancelarlos o modificarlos.
        Solo pedidos del TPV indicado (no incluye pedidos web).
        Usa sudo() para evitar problemas de permisos del cajero.
        """
        from datetime import date, timedelta
        today = date.today()
        tomorrow = today + timedelta(days=1)

        domain = [
            ('pos_config_id', '=', pos_config_id),
            ('state', 'in', ['draft', 'confirmed']),
            '|',
            ('date_pedido', '=', today),
            '&',
            ('tipo_pedido', '=', 'encargo'),
            ('fecha_entrega', '>=', tomorrow),
        ]
        pedidos = self.sudo().search(domain, order='id desc')
        result = []

        for p in pedidos:
            lines_data = []
            for l in p.line_ids.sudo():
                lines_data.append({
                    'id': l.id,
                    'product_id': l.product_id.id,
                    'product_name': l.product_id.display_name,
                    'qty': l.qty,
                    'nota_linea': l.nota_linea or '',
                    'nota_categoria_id': l.nota_categoria_id.id if l.nota_categoria_id else False,
                    'nota_categoria_name': l.nota_categoria_id.name if l.nota_categoria_id else '',
                })
            result.append({
                'id': p.id,
                'name': p.name,
                'tipo_pedido': p.tipo_pedido,
                'state': p.state,
                'nota_general': p.nota_general or '',
                'fecha_entrega': p.fecha_entrega,
                'line_ids': lines_data,
                'origen': 'tpv',
            })

        return result

    def action_done(self):
        for rec in self:
            rec.write({'state': 'done'})

    def _create_sale_order(self):
        """Crea un sale.order confirmado a partir del pedido."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            raise ValidationError(
                _('El pedido %s no tiene un cliente asignado. '
                  'Los pedidos deben tener la tienda como cliente.') % self.name
            )

        # Pricelist: usar el del partner o buscar uno disponible
        pricelist = partner.property_product_pricelist
        if not pricelist:
            pricelist = self.env['product.pricelist'].sudo().search(
                [('company_id', '=', self.env.company.id)], limit=1
            )
        if not pricelist:
            pricelist = self.env['product.pricelist'].sudo().search([], limit=1)

        order_lines = []
        for line in self.line_ids:
            order_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'name': line._get_sale_line_name(),
                'price_unit': line.precio_unitario,
                'product_uom_id': line.product_uom_id.id,
                'tax_ids': [(6, 0, line.product_id.taxes_id.ids)],
            }))
        sale_order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'origin': self.name,
            'tpv_pedido_id': self.id,
            'tipo_pedido_tag': self.tipo_pedido,
            'date_order': fields.Datetime.now(),
            'order_line': order_lines,
            'pricelist_id': pricelist.id if pricelist else False,
            'company_id': self.company_id.id or self.env.company.id,
        }
        # warehouse_id es necesario si sale_stock está instalado
        if 'stock.warehouse' in self.env.registry:
            warehouse = self.env['stock.warehouse'].search(
                [('company_id', '=', self.env.company.id)], limit=1
            )
            if warehouse:
                sale_order_vals['warehouse_id'] = warehouse.id
        if self.nota_general:
            sale_order_vals['note'] = self.nota_general
        try:
            _logger.info('Creando sale.order para pedido %s con vals: %s',
                         self.name, sale_order_vals)
            sale_order = self.env['sale.order'].sudo().create(sale_order_vals)
            sale_order.sudo().action_confirm()
            self.write({'sale_order_id': sale_order.id})
            return sale_order
        except Exception as e:
            _logger.error(
                'Error creando sale.order para pedido %s: %s',
                self.name, str(e), exc_info=True
            )
            raise ValidationError(
                _('Error al crear el pedido de venta (consulta los logs del servidor): %s') % str(e)
            )

    def get_resumen_por_producto(self, date_from=None, date_to=None, pedidos=None):
        """
        Devuelve un diccionario con el resumen agregado por producto.
        Formato: {product_id: {name, qty_total, lineas_con_nota: [{nota, qty, tienda}]}}
        Usado por el reporte de impresión del obrador.
        Si se pasa 'pedidos', se usa ese recordset en lugar de buscar por fecha.
        """
        if pedidos is None:
            domain = [('state', '=', 'confirmed')]
            if date_from:
                domain.append(('date_pedido', '>=', date_from))
            if date_to:
                domain.append(('date_pedido', '<=', date_to))
            pedidos = self.search(domain)
        resumen = {}
        for pedido in pedidos:
            tienda = pedido.pos_config_id.name or 'Sin TPV'
            tipo = dict(pedido._fields['tipo_pedido'].selection).get(
                pedido.tipo_pedido, pedido.tipo_pedido
            )
            for line in pedido.line_ids:
                pid = line.product_id.id
                if pid not in resumen:
                    resumen[pid] = {
                        'product_id': pid,
                        'product_name': line.product_id.display_name,
                        'qty_total': 0.0,
                        'lineas_con_nota': [],
                    }
                resumen[pid]['qty_total'] += line.qty
                if line.nota_linea or line.nota_categoria_id:
                    nota_text = ''
                    if line.nota_categoria_id:
                        nota_text = '[%s] ' % line.nota_categoria_id.name
                    nota_text += line.nota_linea or ''
                    resumen[pid]['lineas_con_nota'].append({
                        'nota': nota_text.strip(),
                        'qty': line.qty,
                        'tienda': tienda,
                        'tipo': tipo,
                    })
        return resumen

    @api.model
    def _cron_imprimir_resumen_obrador(self):
        """Cron que corre cada 1 minuto. Solo ejecuta si la hora España coincide con la configurada."""
        import pytz
        from datetime import datetime

        spain_tz = pytz.timezone('Europe/Madrid')
        now = datetime.now(spain_tz)

        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config:
            return

        if not config.printer_ip and not (config.print_email_active and config.print_email_to):
            return

        if now.hour != int(config.print_hour) or now.minute != int(config.print_minute):
            return

        _logger.info(
            'CRON: hora España %02d:%02d — ejecutando impresion',
            now.hour, now.minute,
        )

        today = fields.Date.today()

        all_pedidos = self.search([
            ('state', '=', 'confirmed'),
            ('fecha_entrega', '=', today),
        ])

        web_orders = self.env['sale.order'].search([
            ('fecha_entrega', '=', today),
            ('state', '=', 'sale'),
        ])

        if not all_pedidos and not web_orders:
            _logger.info('CRON: sin pedidos para hoy %s', today)
            return

        # Generar PDF con 4 bloques
        pdf = self._generar_reporte_4_bloques(all_pedidos, web_orders, today)

        # Imprimir
        if config.printer_type == 'esc_pos':
            self._enviar_esc_pos(config, all_pedidos, today)
        else:
            self._enviar_impresora_red(config, pdf, today)

        # Enviar email
        if config.print_email_active and config.print_email_to:
            self._enviar_reporte_email(config, pdf, today)

        # Guardar backup del informe en disco
        if pdf:
            fecha_str = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)
            filename = 'resumen_obrador_%s.pdf' % fecha_str
            BackupFile = self.env['tpv.backup.file']
            file_path = BackupFile._save_pdf(pdf, filename)
            BackupFile.create({
                'name': 'Resumen obrador %s' % today,
                'date': fields.Datetime.now(),
                'date_pedido': today,
                'filename': filename,
                'file_path': file_path,
            })
            BackupFile._cleanup_old_files(days=30)

    def _do_print(self, config, pedidos, fecha):
        """Send the printout using the configured printer."""
        if config.printer_type == 'esc_pos':
            self._enviar_esc_pos(config, pedidos, fecha)
        else:
            pdf_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
                'tpv_pedidos.action_report_pedido_obrador',
                pedidos.ids,
            )
            self._enviar_impresora_red(config, pdf_content, fecha)

    @api.model
    def _generar_reporte_4_bloques(self, pedidos, web_orders, fecha):
        """
        Genera el PDF con los 5 modulos del reporte.
        Todos los modulos usan WeasyPrint (HTML+CSS).
        Modulo 1: A4 landscape. Modulos 2-5: A4 portrait.
        Returns PDF bytes.
        """
        import io
        try:
            from PyPDF2 import PdfMerger
        except ImportError:
            from pypdf import PdfMerger as PdfMerger
        
        config = self.env['tpv.pedido.config'].search([], limit=1)
        merger = PdfMerger()
        
        # Module 1: WeasyPrint
        if config and config.module1_active:
            pdf1 = self._generate_modulo1_pdf(pedidos, web_orders, fecha)
            if pdf1:
                merger.append(io.BytesIO(pdf1))
        
        # Modules 2-5: WeasyPrint (A4 portrait, modular_generico template)
        if config and config.module2_active:
            pdf2 = self._generate_modulo2_pdf(pedidos, fecha, config.module2_title)
            if pdf2:
                merger.append(io.BytesIO(pdf2))

        if config and config.module3_active:
            pdf3 = self._generate_modulo3_pdf(web_orders, fecha, config.module3_title)
            if pdf3:
                merger.append(io.BytesIO(pdf3))

        if config and config.module4_active:
            pdf4 = self._generate_modulo4_pdf(pedidos, fecha, config.module4_title)
            if pdf4:
                merger.append(io.BytesIO(pdf4))

        if config and config.module5_active:
            pdf5 = self._generate_modulo5_pdf(pedidos, web_orders, fecha, config.module5_title)
            if pdf5:
                merger.append(io.BytesIO(pdf5))
        
        output = io.BytesIO()
        merger.write(output)
        merger.close()
        return output.getvalue()

    @api.model
    def _render_weasy_template(self, template_name, title, fecha, content_html):
        """Render a module PDF using WeasyPrint with the given template."""
        import weasyprint
        import os

        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'report', 'templates', template_name
        )
        with open(template_path, 'r') as f:
            template = f.read()

        config = self.env['tpv.pedido.config'].sudo().search([], limit=1)
        font_size = config.font_size if config and config.font_size else 11
        font_size_title = config.font_size_title if config and config.font_size_title else 14
        font_size_section = config.font_size_section if config and config.font_size_section else 12
        font_size_notes = config.font_size_notes if config and config.font_size_notes else 9
        font_size_date = config.font_size_date if config and config.font_size_date else 11
        font_size_sub = config.font_size_sub if config and config.font_size_sub else 10
        font_size_table_header = config.font_size_table_header if config and config.font_size_table_header else 9
        font_size_table_cell = config.font_size_table_cell if config and config.font_size_table_cell else 9
        font_size_footer = config.font_size_footer if config and config.font_size_footer else 9

        html = template.replace('{TITLE}', title)
        html = html.replace('{FECHA}', str(fecha))
        html = html.replace('{MODULE_CONTENT}', content_html)
        html = html.replace('{FONT_SIZE}', str(font_size))
        html = html.replace('{FONT_SIZE_TITLE}', str(font_size_title))
        html = html.replace('{FONT_SIZE_SECTION}', str(font_size_section))
        html = html.replace('{FONT_SIZE_NOTES}', str(font_size_notes))
        html = html.replace('{FONT_SIZE_DATE}', str(font_size_date))
        html = html.replace('{FONT_SIZE_SUB}', str(font_size_sub))
        html = html.replace('{FONT_SIZE_TABLE_HEADER}', str(font_size_table_header))
        html = html.replace('{FONT_SIZE_TABLE_CELL}', str(font_size_table_cell))
        html = html.replace('{FONT_SIZE_FOOTER}', str(font_size_footer))

        return weasyprint.HTML(string=html).write_pdf()

    @api.model
    def _generate_modulo1_pdf(self, pedidos, web_orders, fecha):
        """
        Genera el PDF del Modulo 1 (totales por categoria) usando WeasyPrint.
        A4 landscape, una pagina por categoria con copias.
        """
        import weasyprint
        import os

        # Get module 1 config
        config = self.env['tpv.pedido.config'].sudo().search([], limit=1)
        if not config or not config.module1_active:
            return b''
        
        # Get category data
        bloque1 = self._get_bloque1_data(pedidos, web_orders)
        if not bloque1:
            return b''
        
        # Get all store names from products
        all_stores = set()
        for cat_id, cat_data in bloque1.items():
            for prod in cat_data.get('products', []):
                for store in prod.get('tiendas', {}):
                    all_stores.add(store)
        sorted_stores = sorted(all_stores)
        
        # Build HTML for each category page
        category_pages_html = ""
        first = True
        for cat_id, cat_data in bloque1.items():
            copies = cat_data.get('copies', 1)
            for copy_num in range(copies):
                if not first:
                    category_pages_html += '<div class="page-break"></div>\n'
                first = False
                
                # Category header
                copy_label = ' (Copia %d de %d)' % (copy_num + 1, copies) if copies > 1 else ''
                category_pages_html += '<div class="category-name">%s<span class="copy-label">%s</span></div>\n' % (
                    self._escape_html(cat_data['name']), copy_label)
                
                # Table headers
                n_stores = max(len(sorted_stores), 1)
                store_w = max(3, min(8, (100 - 22 - 6 - 6) // n_stores))
                category_pages_html += '<table>\n<thead>\n<tr>\n'
                category_pages_html += '<th style="width:22%">Producto</th>\n'
                category_pages_html += '<th class="r" style="width:6%">Total</th>\n'
                category_pages_html += '<th class="r" style="width:6%">Ext</th>\n'
                for store in sorted_stores:
                    category_pages_html += '<th class="r" style="width:%d%%">%s</th>\n' % (
                        store_w, self._escape_html(store))
                category_pages_html += '</tr>\n</thead>\n<tbody>\n'
                
                # Product rows
                for prod in cat_data.get('products', []):
                    category_pages_html += '<tr>\n'
                    category_pages_html += '<td>%s</td>\n' % self._escape_html(prod['name'])
                    category_pages_html += '<td class="r">%d</td>\n' % int(prod['total'])
                    category_pages_html += '<td class="r">%d</td>\n' % int(prod['exterior'])
                    for store in sorted_stores:
                        qty = prod.get('tiendas', {}).get(store, 0)
                        category_pages_html += '<td class="r">%d</td>\n' % int(qty)
                    category_pages_html += '</tr>\n'
                
                category_pages_html += '</tbody>\n</table>\n'
        
        # Read template
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'report', 'templates', 'modulo1.html'
        )
        with open(template_path, 'r') as f:
            template = f.read()
        
        # Replace placeholders
        html = template.replace('{FECHA}', str(fecha))
        html = html.replace('<!--CATEGORY_PAGES-->', category_pages_html)

        font_size = config.font_size if config and config.font_size else 11
        font_size_title = config.font_size_title if config and config.font_size_title else 14
        font_size_section = config.font_size_section if config and config.font_size_section else 12
        font_size_notes = config.font_size_notes if config and config.font_size_notes else 9
        font_size_date = config.font_size_date if config and config.font_size_date else 11
        font_size_sub = config.font_size_sub if config and config.font_size_sub else 10
        font_size_table_header = config.font_size_table_header if config and config.font_size_table_header else 9
        font_size_table_cell = config.font_size_table_cell if config and config.font_size_table_cell else 9
        font_size_footer = config.font_size_footer if config and config.font_size_footer else 9
        html = html.replace('{FONT_SIZE}', str(font_size))
        html = html.replace('{FONT_SIZE_TITLE}', str(font_size_title))
        html = html.replace('{FONT_SIZE_SECTION}', str(font_size_section))
        html = html.replace('{FONT_SIZE_NOTES}', str(font_size_notes))
        html = html.replace('{FONT_SIZE_DATE}', str(font_size_date))
        html = html.replace('{FONT_SIZE_SUB}', str(font_size_sub))
        html = html.replace('{FONT_SIZE_TABLE_HEADER}', str(font_size_table_header))
        html = html.replace('{FONT_SIZE_TABLE_CELL}', str(font_size_table_cell))
        html = html.replace('{FONT_SIZE_FOOTER}', str(font_size_footer))

        # Generate PDF
        pdf = weasyprint.HTML(string=html).write_pdf()
        return pdf

    @api.model
    def _generate_modulo2_pdf(self, pedidos, fecha, title):
        """Module 2: Store encargos (bloque3 data)."""
        config = self.env['tpv.pedido.config'].sudo().search([], limit=1)
        if not config or not config.module2_active:
            return b''

        bloque3 = self._get_bloque3_data(pedidos)
        if not bloque3:
            return b''

        content = ""
        for tienda_name in sorted(bloque3.keys()):
            encargos = bloque3[tienda_name]
            if not encargos:
                continue
            content += '<div class="section-title">%s</div>\n' % self._escape_html(tienda_name)

            for enc in encargos:
                content += '<div class="item-box">\n'
                content += '<div class="item-name">%s</div>\n' % self._escape_html(enc['name'])
                nota = self._strip_html(enc.get('nota', ''))
                if nota:
                    content += '<div class="item-sub">%s</div>\n' % self._escape_html(nota)
                for i, l in enumerate(enc.get('lines', [])):
                    row_class = 'item-line-alt' if i % 2 == 0 else 'item-line-alt even'
                    content += '<div class="%s">%s <span class="qty">%d uds</span></div>\n' % (
                        row_class, self._escape_html(l['name']), int(l['qty']))
                    nota_linea = self._strip_html(l.get('nota', ''))
                    if nota_linea:
                        content += '<div class="item-note">%s</div>\n' % self._escape_html(nota_linea)
                content += '</div>\n'

        if not content:
            return b''
        return self._render_weasy_template('modulo_generico.html', title, fecha, content)

    @api.model
    def _generate_modulo3_pdf(self, web_orders, fecha, title=None):
        """Module 3: External clients VIP y WEB (bloque2 data)."""
        config = self.env['tpv.pedido.config'].sudo().search([], limit=1)
        if not config or not config.module3_active:
            return b''

        bloque2 = self._get_bloque2_data(web_orders)
        if not bloque2:
            return b''

        title = title or 'Pedidos Clientes VIP y pedidos WEB'

        content = ""
        vips = [c for c in bloque2 if c.get('tipo_cliente') == 'VIP']
        webs = [c for c in bloque2 if c.get('tipo_cliente') == 'WEB']

        if vips:
            content += '<div class="section-title">CLIENTES VIP</div>\n'
        for cliente in vips:
            content += self._render_cliente_box(cliente)

        if webs:
            content += '<div class="section-title">PEDIDOS WEB (TARJETA)</div>\n'
        for cliente in webs:
            content += self._render_cliente_box(cliente)

        if not content:
            return b''
        return self._render_weasy_template('modulo_generico.html', title, fecha, content)

    @api.model
    def _render_cliente_box(self, cliente):
        """Render a client order box for Module 3."""
        html = '<div class="item-box">\n'
        html += '<table style="width:100%; border:none;"><tr>\n'

        # Left column
        html += '<td style="width:60%; vertical-align:top; border:none; padding:0;">\n'
        badge = cliente.get('tipo_cliente', '')
        if badge:
            html += '<div class="item-name">%s <strong>"(%s)"</strong></div>\n' % (
                self._escape_html(cliente['name']), badge)
        else:
            html += '<div class="item-name">%s</div>\n' % self._escape_html(cliente['name'])
        if cliente.get('phone'):
            html += '<div class="item-sub">Tel: %s</div>\n' % self._escape_html(cliente['phone'])
        html += '</td>\n'

        # Right column
        html += '<td style="width:40%; vertical-align:top; border:none; padding:0; text-align:right;">\n'
        html += '<div class="item-sub">Entrega: %s</div>\n' % self._escape_html(cliente.get('delivery', ''))
        if cliente.get('pickup_address'):
            html += '<div class="item-sub">%s</div>\n' % self._escape_html(cliente['pickup_address'])
        html += '<div class="item-sub">Total: %.2f €</div>\n' % cliente.get('total_amount', 0)
        html += '</td>\n'
        html += '</tr></table>\n'

        # Nota general
        nota_general = self._clean_note(cliente.get('nota_general', ''))
        if nota_general:
            html += '<div class="item-note">%s</div>\n' % self._escape_html(nota_general)

        # Products
        for i, prod in enumerate(cliente.get('products', [])):
            html += '<div class="item-line-alt">%s <span class="qty">%d uds</span></div>\n' % (
                self._escape_html(prod['name']), int(prod['qty']))
            nota_producto = self._strip_html(prod.get('nota', ''))
            if nota_producto:
                html += '<div class="item-note">%s</div>\n' % self._escape_html(nota_producto)

        html += '</div>\n'
        return html

    @api.model
    def _generate_modulo4_pdf(self, pedidos, fecha, title):
        """Module 4: Pastry encargos (bloque4 data)."""
        config = self.env['tpv.pedido.config'].sudo().search([], limit=1)
        if not config or not config.module4_active:
            return b''

        bloque4 = self._get_bloque4_data(pedidos)
        if not bloque4:
            return b''

        content = ""
        for tienda_name in sorted(bloque4.keys()):
            encargos = bloque4[tienda_name]
            if not encargos:
                continue
            content += '<div class="section-title">%s</div>\n' % self._escape_html(tienda_name)

            for enc in encargos:
                content += '<div class="item-box">\n'
                content += '<div class="item-name">%s</div>\n' % self._escape_html(enc['name'])
                nota = self._strip_html(enc.get('nota', ''))
                if nota:
                    content += '<div class="item-sub">%s</div>\n' % self._escape_html(nota)
                for i, l in enumerate(enc.get('lines', [])):
                    row_class = 'item-line-alt' if i % 2 == 0 else 'item-line-alt even'
                    content += '<div class="%s">%s <span class="qty">%d uds</span></div>\n' % (
                        row_class, self._escape_html(l['name']), int(l['qty']))
                    nota_linea = self._strip_html(l.get('nota', ''))
                    if nota_linea:
                        content += '<div class="item-note">%s</div>\n' % self._escape_html(nota_linea)
                content += '</div>\n'

        if not content:
            return b''
        return self._render_weasy_template('modulo_generico.html', title, fecha, content)

    @api.model
    def _generate_modulo5_pdf(self, pedidos, web_orders, fecha, title):
        """Module 5: Custom orders with origin filter (bloque5 data)."""
        config = self.env['tpv.pedido.config'].sudo().search([], limit=1)
        if not config or not config.module5_active:
            return b''

        bloque5 = self._get_bloque5_data(pedidos, web_orders)
        if not bloque5:
            return b''

        content = ""
        for item in bloque5:
            content += '<div class="item-box">\n'
            content += '<div class="item-name">%s</div>\n' % self._escape_html(item['name'])
            content += '<div class="item-sub">Origen: %s</div>\n' % self._escape_html(item.get('origen', ''))
            if item.get('tienda'):
                content += '<div class="item-sub">Tienda: %s</div>\n' % self._escape_html(item['tienda'])
            if item.get('cliente'):
                content += '<div class="item-sub">Cliente: %s</div>\n' % self._escape_html(item['cliente'])
            if item.get('pickup_name'):
                content += '<div class="item-sub">Recogida: %s</div>\n' % self._escape_html(item['pickup_name'])
            if item.get('pickup_address'):
                content += '<div class="item-sub">%s</div>\n' % self._escape_html(item['pickup_address'])
            nota_item = item.get('nota', '')
            if nota_item:
                content += '<div class="item-sub">%s</div>\n' % self._escape_html(nota_item)
            for l in item.get('lines', []):
                content += '<div class="item-line">%s <span class="qty">%d uds</span></div>\n' % (
                    self._escape_html(l['name']), int(l['qty']))
                nota_linea = self._strip_html(l.get('nota', ''))
                if nota_linea:
                    content += '<div class="item-note">%s</div>\n' % self._escape_html(nota_linea)
            content += '</div>\n'

        if not content:
            return b''
        return self._render_weasy_template('modulo_generico.html', title, fecha, content)

    @api.model
    def _strip_html(self, text):
        """Remove HTML tags from text."""
        if not text:
            return ''
        import re
        text = str(text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @api.model
    def _clean_note(self, note):
        """Strip HTML from note and remove terms boilerplate.
        Returns empty string if the note looks like auto-generated T&C.
        """
        if not note:
            return ''
        plain = self._strip_html(note)
        lines = [l.strip() for l in plain.split('\n') if l.strip()]
        if len(lines) > 5 or len(plain) > 300:
            return ''
        term_keywords = ['términos', 'condiciones', 'terminos', 'conditions', 'terms',
                         'http://', 'https://']
        cleaned = [l for l in lines if not any(
            kw in l.lower() for kw in term_keywords
        )]
        if not cleaned:
            return ''
        return '\n'.join(cleaned)

    @api.model
    def _escape_html(self, text):
        """Escape HTML special characters."""
        if not text:
            return ''
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        return text

    @api.model
    def _get_bloque1_data(self, pedidos, web_orders):
        """
        Bloque 1: Totales por familia principal.
        Uses config.report_line_ids filtered by module='1'.
        Returns: {category_id: {name, copies, products: [{name, total, exterior, tiendas: {name: qty}}]}}
        """
        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config:
            return {}

        module1_lines = config.module1_line_ids
        result = {}

        for line in module1_lines:
            cat = line.category_id
            copies = line.copies or 1
            cat_data = {
                'name': cat.name,
                'copies': copies,
                'products': [],
            }

            # Get all subcategories
            all_cat_ids = self._get_all_subcategory_ids(cat)

            # Aggregate products
            product_totals = {}
            for p in pedidos:
                for l in p.line_ids:
                    if l.product_id.pos_categ_ids:
                        prod_cat_ids = [c.id for c in l.product_id.pos_categ_ids]
                        if any(cid in all_cat_ids for cid in prod_cat_ids):
                            if l.product_id.id not in product_totals:
                                product_totals[l.product_id.id] = {
                                    'name': l.product_id.display_name,
                                    'total': 0.0,
                                    'exterior': 0.0,
                                    'tiendas': {},
                                }
                            product_totals[l.product_id.id]['total'] += l.qty

                            tienda = p.pos_config_id.name if p.pos_config_id else 'Desconocida'
                            if tienda not in product_totals[l.product_id.id]['tiendas']:
                                product_totals[l.product_id.id]['tiendas'][tienda] = 0.0
                            product_totals[l.product_id.id]['tiendas'][tienda] += l.qty

            # Add web orders too
            for so in web_orders:
                for l in so.order_line:
                    if l.product_id.pos_categ_ids:
                        prod_cat_ids = [c.id for c in l.product_id.pos_categ_ids]
                        if any(cid in all_cat_ids for cid in prod_cat_ids):
                            if l.product_id.id not in product_totals:
                                product_totals[l.product_id.id] = {
                                    'name': l.product_id.display_name,
                                    'total': 0.0,
                                    'exterior': 0.0,
                                    'tiendas': {},
                                }
                            product_totals[l.product_id.id]['total'] += l.product_uom_qty
                            product_totals[l.product_id.id]['exterior'] += l.product_uom_qty

            # Sort by total desc
            sorted_products = sorted(
                product_totals.values(),
                key=lambda x: x['total'],
                reverse=True,
            )
            cat_data['products'] = sorted_products
            result[cat.id] = cat_data

        return result

    @api.model
    def _get_all_subcategory_ids(self, category):
        """Recursively get all subcategory IDs."""
        ids = [category.id]
        for child in category.child_ids:
            ids.extend(self._get_all_subcategory_ids(child))
        return ids

    @api.model
    def _get_bloque2_data(self, web_orders):
        """
        Bloque 2: Clientes externos.
        Returns: [{name, phone, pickup_name, pickup_address, delivery, total_amount, products: [{name, qty}]}]
        """
        obrador_config = self.env['tpv.cliente.config'].sudo().get_config() if hasattr(
            self.env['tpv.cliente.config'], 'get_config') else None
        obrador_dir = obrador_config.obrador_direccion if obrador_config else ''

        result = []
        for so in web_orders:
            products = []
            for line in so.order_line:
                products.append({
                    'name': line.product_id.display_name,
                    'qty': line.product_uom_qty,
                    'nota': '',
                })

            # Determine pickup location (TPV/store or obrador)
            pickup_name = ''
            pickup_address = ''
            if so.pos_config_id:
                pickup_name = so.pos_config_id.name
                pickup_address = so.pos_config_id.direccion or ''
            elif so.warehouse_id:
                pickup_name = 'Obrador'
                pickup_address = obrador_dir

            total = so.amount_total
            delivery = 'Recoger en tienda'
            if pickup_name:
                delivery = 'Recoger en %s' % pickup_name
            if so.warehouse_id and not so.pos_config_id:
                delivery = 'Recoger en obrador'

            is_vip = so.partner_id.tpv_vip if hasattr(so.partner_id, 'tpv_vip') else False

            result.append({
                'name': so.partner_id.name,
                'tipo_cliente': 'VIP' if is_vip else 'WEB',
                'phone': so.partner_id.phone or getattr(so.partner_id, 'mobile', '') or '',
                'pickup_name': pickup_name,
                'pickup_address': pickup_address,
                'delivery': delivery,
                'total_amount': total,
                'nota_general': so.note or '',
                'products': products,
            })
        return result

    @api.model
    def _get_bloque3_data(self, pedidos):
        """
        Bloque 3 -> Modulo 2: Encargos de tiendas excluyendo categorias seleccionadas.
        Products whose categories overlap with module2_exclude_category_ids are excluded.
        Returns: {tienda_name: [{pedido_name, nota, lines: [{name, qty, nota}]}]}
        """
        config = self.env['tpv.pedido.config'].search([], limit=1)
        # Get categories to exclude from Module 2 config
        exclude_cat_ids = []
        if config and config.module2_exclude_category_ids:
            exclude_cat_ids = config.module2_exclude_category_ids.ids

        result = {}
        for p in pedidos.filtered(lambda x: x.tipo_pedido == 'encargo'):
            tienda = p.pos_config_id.name or 'Desconocida'
            if tienda not in result:
                result[tienda] = []

            lines = []
            for line in p.line_ids:
                # Skip if product belongs to excluded categories
                is_excluded = False
                if exclude_cat_ids and line.product_id.pos_categ_ids:
                    prod_cat_ids = [c.id if not isinstance(c, int) else c for c in line.product_id.pos_categ_ids]
                    if any(cid in exclude_cat_ids for cid in prod_cat_ids):
                        is_excluded = True

                if not is_excluded:
                    nota = line.nota_linea or ''
                    if line.nota_categoria_id:
                        nota = '[%s] %s' % (line.nota_categoria_id.name, nota)
                    lines.append({
                        'name': line.product_id.display_name,
                        'qty': line.qty,
                        'nota': nota.strip(),
                    })

            if lines:
                result[tienda].append({
                    'name': p.name,
                    'nota': p.nota_general or '',
                    'lines': lines,
                })

        return result

    @api.model
    def _get_bloque4_data(self, pedidos):
        """
        Bloque 4 -> Modulo 4: Encargos de pasteleria.
        Uses config.report_line_ids filtered by module='4'.
        Returns: {tienda_name: [{pedido_name, nota, lines: [{name, qty, nota}]}]}
        """
        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config:
            return {}

        module4_lines = config.module4_line_ids

        module4_cat_ids = set()
        for l in module4_lines:
            module4_cat_ids.update(self._get_all_subcategory_ids(l.category_id))

        result = {}
        for p in pedidos.filtered(lambda x: x.tipo_pedido == 'encargo'):
            tienda = p.pos_config_id.name or 'Desconocida'
            if tienda not in result:
                result[tienda] = []

            lines = []
            for line in p.line_ids:
                if not line.product_id.pos_categ_ids:
                    continue

                prod_cat_ids = [c.id for c in line.product_id.pos_categ_ids]
                in_module4 = any(cid in module4_cat_ids for cid in prod_cat_ids)

                if in_module4:
                    nota = line.nota_linea or ''
                    if line.nota_categoria_id:
                        nota = '[%s] %s' % (line.nota_categoria_id.name, nota)
                    lines.append({
                        'name': line.product_id.display_name,
                        'qty': line.qty,
                        'nota': nota.strip(),
                    })

            if lines:
                result[tienda].append({
                    'name': p.name,
                    'nota': p.nota_general or '',
                    'lines': lines,
                })

        return result

    @api.model
    def _get_bloque5_data(self, pedidos, web_orders):
        """Modulo 5: Pedidos personalizados con filtros de origen y categoria."""
        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config or not config.module5_active:
            return {}

        # Get selected origins
        origins = []
        if config.module5_origin_web:
            origins.append('web')
        if config.module5_origin_encargo:
            origins.append('encargo')
        if config.module5_origin_pedido:
            origins.append('pedido_tienda')

        # Get Module 5 categories
        module5_cat_ids = config.module5_category_ids.ids if config and config.module5_category_ids else []

        result = []

        # Process pedidos (TPV)
        for p in pedidos:
            if p.tipo_pedido not in origins:
                continue
            lines = []
            for line in p.line_ids:
                if module5_cat_ids and line.product_id.pos_categ_ids:
                    prod_cat_ids = [c.id if not isinstance(c, int) else c for c in line.product_id.pos_categ_ids]
                    if not any(cid in module5_cat_ids for cid in prod_cat_ids):
                        continue
                nota = line.nota_linea or ''
                if line.nota_categoria_id:
                    nota = '[%s] %s' % (line.nota_categoria_id.name, nota)
                lines.append({
                    'name': line.product_id.display_name,
                    'qty': line.qty,
                    'nota': nota.strip(),
                })
            if lines:
                result.append({
                    'name': p.name,
                    'origen': dict(p._fields['tipo_pedido'].selection).get(p.tipo_pedido, p.tipo_pedido),
                    'tienda': p.pos_config_id.name or '',
                    'nota': self._clean_note(p.nota_general or ''),
                    'lines': lines,
                })

        # Process web orders
        if config.module5_origin_web and web_orders:
            obrador_config = self.env['tpv.cliente.config'].sudo().get_config() if hasattr(
                self.env['tpv.cliente.config'], 'get_config') else None
            obrador_dir = obrador_config.obrador_direccion if obrador_config else ''

            for so in web_orders:
                lines = []
                for line in so.order_line:
                    if module5_cat_ids and line.product_id.pos_categ_ids:
                        prod_cat_ids = [c.id if not isinstance(c, int) else c for c in line.product_id.pos_categ_ids]
                        if not any(cid in module5_cat_ids for cid in prod_cat_ids):
                            continue
                    lines.append({
                        'name': line.product_id.display_name,
                        'qty': line.product_uom_qty,
                        'nota': '',
                    })
                if lines:
                    pickup_name = ''
                    pickup_address = ''
                    if so.pos_config_id:
                        pickup_name = so.pos_config_id.name
                        pickup_address = so.pos_config_id.direccion or ''
                    elif so.warehouse_id:
                        pickup_name = 'Obrador'
                        pickup_address = obrador_dir

                    is_vip = so.partner_id.tpv_vip if hasattr(so.partner_id, 'tpv_vip') else False
                    result.append({
                        'name': so.name,
                        'origen': 'VIP' if is_vip else 'Web',
                        'cliente': so.partner_id.name,
                        'pickup_name': pickup_name,
                        'pickup_address': pickup_address,
                        'nota': self._clean_note(so.note or ''),
                        'lines': lines,
                    })

        return result

    @api.model
    def _enviar_reporte_email(self, config, pdf_content, fecha):
        """Envía el reporte PDF por email."""
        if not config.print_email_active or not config.print_email_to:
            return

        mail_mail = self.env['mail.mail']
        mail_values = {
            'subject': 'Resumen de pedidos del obrador - %s' % fecha,
            'body_html': '''
                <p>Adjunto encontrará el resumen de pedidos del obrador
                para la fecha <strong>%s</strong>.</p>
                <p>Saludos.</p>
            ''' % fecha,
            'email_to': config.print_email_to,
            'email_from': self.env['ir.mail_server'].sudo().search([('active', '=', True)], limit=1).smtp_user or self.env.company.email,
            'attachment_ids': [(0, 0, {
                'name': 'resumen_obrador_%s.pdf' % fecha,
                'datas': base64.b64encode(pdf_content).decode(),
                'mimetype': 'application/pdf',
            })],
        }
        try:
            mail = mail_mail.create(mail_values)
            mail.send()
        except Exception as e:
            _logger.error('Error enviando email del reporte: %s', str(e))

    def _enviar_impresora_red(self, config, pdf_content, fecha):
        """Envía el PDF a una impresora de red vía CUPS o direct IP."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((
                config.printer_ip,
                int(config.printer_port) if config.printer_port else 9100,
            ))
            # Enviar el PDF directamente (impresoras de red modernas
            # aceptan PDF en el stream)
            sock.sendall(pdf_content)
            sock.close()
        except (socket.timeout, socket.error, OSError):
            # Log del error pero no detener el cron
            _logger.error(
                'Error conectando a impresora de red %s:%s',
                config.printer_ip,
                config.printer_port or '9100',
            )

    def _enviar_esc_pos(self, config, pedidos, fecha):
        """Genera comandos ESC/POS para impresora térmica y los envía por socket."""
        import socket
        resumen = self.get_resumen_por_producto(pedidos=pedidos)
        detalle = self.get_detalle_por_tienda(pedidos=pedidos)

        # Comandos ESC/POS básicos
        ESC = b'\x1b'
        INIT = ESC + b'@'                    # Reset
        BOLD_ON = ESC + b'E\x01'             # Bold on
        BOLD_OFF = ESC + b'E\x00'            # Bold off
        CENTER = ESC + b'a\x01'              # Center align
        LEFT = ESC + b'a\x00'                # Left align
        LINE_FEED = b'\n'
        SEP_LINE = b'-' * 42 + LINE_FEED

        cmds = INIT + CENTER + BOLD_ON
        cmds += b'RESUMEN OBRADOR\n'
        cmds += str(fecha).encode() + LINE_FEED
        cmds += BOLD_OFF + LEFT + SEP_LINE

        # Sección 1: Resumen por productos
        cmds += BOLD_ON + b'RESUMEN POR PRODUCTOS\n' + BOLD_OFF + SEP_LINE
        for pid, data in sorted(
            resumen.items(), key=lambda x: x[1]['qty_total'], reverse=True
        ):
            line = '%-30s %8.0f uds' % (
                data['product_name'][:30], data['qty_total']
            )
            cmds += line.encode() + LINE_FEED
            for nota_data in data['lineas_con_nota']:
                nota_line = '  %-28s %5.0f uds [%s] %s' % (
                    nota_data['nota'][:28],
                    nota_data['qty'],
                    nota_data['tipo'],
                    nota_data['tienda'],
                )
                cmds += nota_line.encode() + LINE_FEED
            cmds += LINE_FEED

        # Sección 2: Detalle por tienda
        cmds += SEP_LINE + BOLD_ON + b'DETALLE POR TIENDA\n' + BOLD_OFF + SEP_LINE
        for tienda, data in detalle.items():
            cmds += ('--- %s ---\n' % tienda).encode()
            if data['encargos']:
                cmds += b'  ENCARGOS:\n'
                for enc in data['encargos']:
                    cmds += ('  %s\n' % enc['name']).encode()
                    for l in enc['lineas']:
                        nota_str = ' (%s)' % l['nota'] if l['nota'] else ''
                        cmds += ('    - %-25s %5.0f uds%s\n' % (
                            l['product_name'][:25], l['qty'], nota_str
                        )).encode()
                    if enc['nota_general']:
                        cmds += ('    Nota: %s\n' % enc['nota_general'][:38]).encode()
            if data['pedidos_tienda']:
                cmds += b'  PEDIDOS TIENDA:\n'
                for pt in data['pedidos_tienda']:
                    cmds += ('  %s\n' % pt['name']).encode()
                    for l in pt['lineas']:
                        nota_str = ' (%s)' % l['nota'] if l['nota'] else ''
                        cmds += ('    - %-25s %5.0f uds%s\n' % (
                            l['product_name'][:25], l['qty'], nota_str
                        )).encode()
                    if pt['nota_general']:
                        cmds += ('    Nota: %s\n' % pt['nota_general'][:38]).encode()

        cmds += SEP_LINE + LINE_FEED + LINE_FEED
        # Cortar papel
        cmds += ESC + b'm'     # Partial cut

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((
                config.printer_ip,
                int(config.printer_port) if config.printer_port else 9100,
            ))
            sock.sendall(cmds)
            sock.close()
        except (socket.timeout, socket.error, OSError):
            _logger.error(
                'Error conectando a impresora ESC/POS %s:%s',
                config.printer_ip,
                config.printer_port or '9100',
            )

    def get_detalle_por_tienda(self, date_from=None, date_to=None, pedidos=None):
        """
        Devuelve un diccionario con el detalle por tienda, separando encargos
        y pedidos de tienda.
        Formato: {tienda: {encargos: [pedido_vals], pedidos_tienda: [pedido_vals]}}
        Si se pasa 'pedidos', se usa ese recordset en lugar de buscar por fecha.
        """
        if pedidos is None:
            domain = [('state', '=', 'confirmed')]
            if date_from:
                domain.append(('date_pedido', '>=', date_from))
            if date_to:
                domain.append(('date_pedido', '<=', date_to))
            pedidos = self.search(domain)
        detalle = {}
        for pedido in pedidos:
            tienda = pedido.pos_config_id.name or 'Sin TPV'
            if tienda not in detalle:
                detalle[tienda] = {
                    'encargos': [],
                    'pedidos_tienda': [],
                }
            pedido_vals = {
                'name': pedido.name,
                'date': pedido.date_pedido,
                'nota_general': pedido.nota_general or '',
                'lineas': [{
                    'product_name': l.product_id.display_name,
                    'qty': l.qty,
                    'nota': (
                        ('[%s] ' % l.nota_categoria_id.name if l.nota_categoria_id else '')
                        + (l.nota_linea or '')
                    ).strip(),
                } for l in pedido.line_ids],
            }
            if pedido.tipo_pedido == 'encargo':
                detalle[tienda]['encargos'].append(pedido_vals)
            else:
                detalle[tienda]['pedidos_tienda'].append(pedido_vals)
        return detalle