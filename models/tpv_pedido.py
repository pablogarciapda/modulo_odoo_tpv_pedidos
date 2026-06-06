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
                'fecha_entrega': p.fecha_entrega,
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
        """Cron que corre cada hora. Procesa solo entre 00:01 y 03:00."""
        from datetime import datetime
        now = datetime.now()
        hora_actual = now.hour + now.minute / 60.0

        # Ventana de impresion: 00:01 - 03:00
        if hora_actual < 0.01 or hora_actual > 3.0:
            return

        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config or not config.printer_ip:
            return

        today = fields.Date.today()

        # Obtener pedidos a fabricar HOY
        # Pedidos tienda: fecha_entrega = today
        pedidos_tienda = self.search([
            ('state', '=', 'confirmed'),
            ('tipo_pedido', '=', 'pedido_tienda'),
            ('fecha_entrega', '=', today),
        ])

        # Encargos: fecha_entrega - 1 = today (se fabrican el dia antes)
        pedidos_encargo = self.search([
            ('state', '=', 'confirmed'),
            ('tipo_pedido', '=', 'encargo'),
            ('fecha_entrega', '=', today + timedelta(days=1)),
        ])

        # Clientes web (sale.order con fecha_entrega = today+1 para fabricar hoy)
        web_orders = self.env['sale.order'].search([
            ('fecha_entrega', '=', today + timedelta(days=1)),
            ('state', '=', 'sale'),
        ])

        all_pedidos = pedidos_tienda + pedidos_encargo

        if not all_pedidos and not web_orders:
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
        Genera el PDF con los 4 modulos del reporte.
        Construye el diccionario de datos y lo pasa a _render_qweb_pdf.
        Incluye titulos configurables de cada modulo.
        Returns PDF bytes.
        """
        config = self.env['tpv.pedido.config'].search([], limit=1)

        data = {
            'fecha': fecha,
            'bloque1': self._get_bloque1_data(pedidos, web_orders),
            'bloque2': self._get_bloque2_data(web_orders),
            'bloque3': self._get_bloque3_data(pedidos),
            'bloque4': self._get_bloque4_data(pedidos),
            'module1_title': config.module1_title if config else 'Totales por Familia Principal',
            'module2_title': config.module2_title if config else 'Encargos de Tiendas',
            'module3_title': config.module3_title if config else 'Pedidos de Clientes',
            'module4_title': config.module4_title if config else 'Encargos de Pasteleria',
        }
        data['docs'] = pedidos
        data['web_orders'] = web_orders

        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            'tpv_pedidos.action_report_pedido_obrador',
            res_ids=pedidos.ids,
            data=data,
        )
        return pdf_content

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

        module1_lines = config.report_line_ids.filtered(lambda l: l.module == '1')
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
        for child in category.child_id:
            ids.extend(self._get_all_subcategory_ids(child))
        return ids

    @api.model
    def _get_bloque2_data(self, web_orders):
        """
        Bloque 2: Clientes externos.
        Returns: [{name, phone, address, delivery, total_amount, products: [{name, qty}]}]
        """
        result = []
        for so in web_orders:
            products = []
            for line in so.order_line:
                products.append({
                    'name': line.product_id.display_name,
                    'qty': line.product_uom_qty,
                })
            # Determine delivery method
            total = so.amount_total
            if total > 25:
                delivery = 'Envio a domicilio'
            else:
                delivery = 'Recoger en tienda'
            if so.warehouse_id:
                delivery = 'Recoger en obrador'

            result.append({
                'name': so.partner_id.name,
                'phone': so.partner_id.phone or so.partner_id.mobile or '',
                'address': so.partner_id.contact_address or '',
                'delivery': delivery,
                'total_amount': total,
                'products': products,
            })
        return result

    @api.model
    def _get_bloque3_data(self, pedidos):
        """
        Bloque 3 -> Modulo 2: Encargos de tiendas (excluye pasteleria).
        Uses config.report_line_ids filtered by module='2'.
        Products whose categories overlap with module='4' are excluded.
        Returns: {tienda_name: [{pedido_name, nota, lines: [{name, qty, nota}]}]}
        """
        config = self.env['tpv.pedido.config'].search([], limit=1)
        if not config:
            return {}

        module2_lines = config.report_line_ids.filtered(lambda l: l.module == '2')
        module4_lines = config.report_line_ids.filtered(lambda l: l.module == '4')

        # Build sets of all subcategory IDs for each module
        module2_cat_ids = set()
        for l in module2_lines:
            module2_cat_ids.update(self._get_all_subcategory_ids(l.category_id))

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
                in_module2 = any(cid in module2_cat_ids for cid in prod_cat_ids)
                in_module4 = any(cid in module4_cat_ids for cid in prod_cat_ids)

                # Include if in Module 2 AND NOT in Module 4
                if in_module2 and not in_module4:
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

        module4_lines = config.report_line_ids.filtered(lambda l: l.module == '4')

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
            'email_from': self.env.user.email or self.env.company.email,
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