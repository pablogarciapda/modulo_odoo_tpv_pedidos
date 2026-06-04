# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

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
        default=lambda self: self.env.ref(
            'tpv_pedidos.partner_obrador', raise_if_not_found=False
        ),
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

    @api.depends('tipo_pedido')
    def _compute_es_encargo(self):
        for rec in self:
            rec.es_encargo = rec.tipo_pedido == 'encargo'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tpv.pedido'
                ) or _('New')
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
                               nota_general='', partner_id=False):
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

        # Cliente por defecto: OBRADOR
        if not partner_id:
            obrador = self.env.ref(
                'tpv_pedidos.partner_obrador', raise_if_not_found=False
            )
            if obrador:
                partner_id = obrador.id

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
    def update_pedido_from_pos(self, pedido_id, lines, nota_general=''):
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
        pedido.write({
            'line_ids': line_vals,
            'nota_general': nota_general,
        })

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
        Devuelve los pedidos del día para una tienda específica.
        """
        from datetime import date
        domain = [
            ('date_pedido', '=', date.today()),
            ('pos_config_id', '=', pos_config_id),
            ('state', 'in', ['draft', 'confirmed']),
        ]
        pedidos = self.search(domain, order='id desc')
        result = []
        for p in pedidos:
            lines_data = []
            for l in p.line_ids:
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
                'line_ids': lines_data,
            })
        return result

    def action_done(self):
        for rec in self:
            rec.write({'state': 'done'})

    def _create_sale_order(self):
        """Crea un sale.order confirmado a partir del pedido."""
        self.ensure_one()
        partner = self.partner_id or self.env.ref(
            'tpv_pedidos.partner_obrador', raise_if_not_found=False
        )
        if not partner:
            partner = self.env['res.partner'].search(
                [('name', '=', 'OBRADOR')], limit=1
            )
        if not partner:
            raise ValidationError(
                _('No se encontró el contacto OBRADOR. '
                  'Verifica que los datos del módulo se hayan cargado.')
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

    def get_resumen_por_producto(self, date_from=None, date_to=None):
        """
        Devuelve un diccionario con el resumen agregado por producto.
        Formato: {product_id: {name, qty_total, lineas_con_nota: [{nota, qty, tienda}]}}
        Usado por el reporte de impresión del obrador.
        """
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
        """
        Cron job diario. Lee la configuracion central de impresora del obrador
        y, si es la hora configurada, imprime el resumen de pedidos del dia anterior.
        """
        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config or not config.printer_ip:
            return

        from datetime import datetime, timedelta
        now = datetime.now()
        current_hour = now.hour + now.minute / 60.0
        print_hour = int(config.print_hour or '2')

        if abs(current_hour - print_hour) >= 0.5:
            return  # Not time yet

        ayer = fields.Date.context_today(self) - timedelta(days=1)
        pedidos = self.search([
            ('state', '=', 'confirmed'),
            ('date_pedido', '=', ayer),
        ])
        if not pedidos:
            return

        self._do_print(config, pedidos, ayer)

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

    def _enviar_impresora_red(self, config, pdf_content, fecha):
        """Envía el PDF a una impresora de red vía CUPS o direct IP."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((
                config.printer_ip,
                config.printer_port or 9100,
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
                config.printer_port,
            )

    def _enviar_esc_pos(self, config, pedidos, fecha):
        """Genera comandos ESC/POS para impresora térmica y los envía por socket."""
        import socket
        resumen = pedidos.get_resumen_por_producto(date_from=fecha, date_to=fecha)
        detalle = pedidos.get_detalle_por_tienda(date_from=fecha, date_to=fecha)

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
                config.printer_port or 9100,
            ))
            sock.sendall(cmds)
            sock.close()
        except (socket.timeout, socket.error, OSError):
            _logger.error(
                'Error conectando a impresora ESC/POS %s:%s',
                config.printer_ip,
                config.printer_port,
            )

    def get_detalle_por_tienda(self, date_from=None, date_to=None):
        """
        Devuelve un diccionario con el detalle por tienda, separando encargos
        y pedidos de tienda.
        Formato: {tienda: {encargos: [pedido_vals], pedidos_tienda: [pedido_vals]}}
        """
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