# -*- coding: utf-8 -*-

import csv
import io
import logging

from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

def _build_category_path(product):
    """Helper: build ' > ' joined category path from product's pos_categ_ids."""
    if product.pos_categ_ids:
        cat_names = [c.name for c in product.pos_categ_ids[:3]]
        return ' > '.join(cat_names)
    return ''


class TpvPedidoController(http.Controller):

    @http.route('/tpv_pedidos/create', type='json', auth='user', methods=['POST'])
    def create_pedido(self, pos_config_id, tipo_pedido, lines, nota_general='', partner_id=False):
        """
        Crea un pedido desde el frontend del TPV.

        :param pos_config_id: ID del pos.config (tienda)
        :param tipo_pedido: 'encargo' o 'pedido_tienda'
        :param lines: lista de dicts [{product_id, qty, nota_linea, nota_categoria_id}]
        :param nota_general: texto libre
        :param partner_id: ID del cliente (opcional, default OBRADOR)
        :return: dict con {pedido_id, name, sale_order_id}
        """
        Pedido = request.env['tpv.pedido'].sudo()

        # Cliente por defecto: OBRADOR
        if not partner_id:
            obrador = request.env.ref('tpv_pedidos.partner_obrador', raise_if_not_found=False)
            if obrador:
                partner_id = obrador.id

        # Validar líneas
        if not lines:
            return {'error': 'El pedido debe tener al menos una línea.'}

        line_vals = []
        for line in lines:
            line_vals.append((0, 0, {
                'product_id': line.get('product_id'),
                'qty': line.get('qty', 1.0),
                'nota_linea': line.get('nota_linea', ''),
                'nota_categoria_id': line.get('nota_categoria_id', False),
            }))

        pedido_vals = {
            'pos_config_id': pos_config_id,
            'tipo_pedido': tipo_pedido,
            'partner_id': partner_id,
            'nota_general': nota_general,
            'line_ids': line_vals,
        }

        try:
            pedido = Pedido.create(pedido_vals)
            # Confirmar automáticamente → crea sale.order
            pedido.action_confirm()
            return {
                'pedido_id': pedido.id,
                'name': pedido.name,
                'sale_order_id': pedido.sale_order_id.id,
            }
        except Exception as e:
            _logger.error('Error creando pedido TPV: %s', str(e))
            return {'error': str(e)}

    @http.route('/tpv_pedidos/get_nota_categorias', type='json', auth='user', methods=['POST'])
    def get_nota_categorias(self):
        """Devuelve las categorías de notas activas para el frontend."""
        categorias = request.env['tpv.nota.categoria'].sudo().search([
            ('activa', '=', True),
        ], order='sequence, name')
        return [{
            'id': c.id,
            'name': c.name,
        } for c in categorias]

    @http.route('/tpv_pedidos/get_partner_obrador', type='json', auth='user', methods=['POST'])
    def get_partner_obrador(self):
        """Devuelve el ID del partner OBRADOR para el frontend."""
        obrador = request.env.ref('tpv_pedidos.partner_obrador', raise_if_not_found=False)
        if obrador:
            return {'partner_id': obrador.id, 'name': obrador.name}
        # Fallback: buscar por nombre
        partner = request.env['res.partner'].sudo().search([
            ('name', '=', 'OBRADOR'),
        ], limit=1)
        return {'partner_id': partner.id if partner else False, 'name': partner.name if partner else ''}

    @http.route('/tpv_pedidos/get_pedidos_today', type='json', auth='user', methods=['POST'])
    def get_pedidos_today(self, pos_config_id=False):
        """
        Devuelve los pedidos del día para una tienda específica
        o todas las tiendas si no se especifica.
        """
        from datetime import date
        domain = [
            ('date_pedido', '=', date.today()),
            ('state', 'in', ['draft', 'confirmed']),
        ]
        if pos_config_id:
            domain.append(('pos_config_id', '=', pos_config_id))

        pedidos = request.env['tpv.pedido'].sudo().search(domain, order='id desc')
        result = []
        for p in pedidos:
            result.append({
                'id': p.id,
                'name': p.name,
                'tipo_pedido': p.tipo_pedido,
                'state': p.state,
                'partner_id': p.partner_id.id,
                'partner_name': p.partner_id.name,
                'pos_config_name': p.pos_config_id.name,
                'nota_general': p.nota_general or '',
                'line_count': len(p.line_ids),
            })
        return result

    @http.route('/tpv_pedidos/informes', type='http', auth='user', methods=['GET', 'POST'])
    def web_informes(self, **kwargs):
        """Web page with order reports and powerful filters. Independent from config modules."""
        if not request.env.user._is_internal():
            return request.redirect('/web')

        Pedido = request.env['tpv.pedido'].sudo()
        today = datetime.now().strftime('%Y-%m-%d')

        # Get filters from request
        fecha_desde = kwargs.get('fecha_desde', today)
        fecha_hasta = kwargs.get('fecha_hasta', today)
        tienda_id = kwargs.get('tienda_id', '')
        tipo_pedido = kwargs.get('tipo_pedido', '')
        product_id = kwargs.get('product_id', '')
        category_id = kwargs.get('category_id', '')

        # Build domain for tpv.pedido
        domain = [('state', '=', 'confirmed')]
        if fecha_desde:
            domain.append(('fecha_entrega', '>=', fecha_desde))
        if fecha_hasta:
            domain.append(('fecha_entrega', '<=', fecha_hasta))
        if tienda_id:
            domain.append(('pos_config_id', '=', int(tienda_id)))
        if tipo_pedido and tipo_pedido != 'ext':
            domain.append(('tipo_pedido', '=', tipo_pedido))
        elif tipo_pedido == 'ext':
            # Only show web orders, no TPV pedidos
            domain.append(('id', '=', 0))  # No results from tpv.pedido

        all_pedidos = Pedido.search(domain, order='fecha_entrega, pos_config_id, name')

        # Build flat order data (not using module blocks)
        orders_data = []
        for p in all_pedidos:
            for line in p.line_ids:
                # Filter by product
                if product_id and line.product_id.id != int(product_id):
                    continue
                # Filter by category
                if category_id:
                    cat_ids = [c.id for c in line.product_id.pos_categ_ids]
                    if int(category_id) not in cat_ids:
                        continue
                orders_data.append({
                    'pedido': p.name,
                    'fecha_pedido': str(p.date_pedido or ''),
                'fecha_entrega': str(p.fecha_entrega or ''),
                    'tienda': p.pos_config_id.name or '',
                    'tipo': dict(p._fields['tipo_pedido'].selection).get(p.tipo_pedido, ''),
                    'cliente': p.pos_config_id.name or '',
                    'producto': line.product_id.display_name,
                    'categoria': ', '.join([c.name for c in line.product_id.pos_categ_ids][:3]),
                    'cantidad': line.qty,
                    'nota': line.nota_linea or '',
                    'nota_general': p.nota_general or '',
                })

        # Also include web orders (sale.order) — only when tipo_pedido is 'ext' or no filter
        if tipo_pedido in ('', 'ext'):
            web_domain = [('state', '=', 'sale')]
            if fecha_desde:
                web_domain.append(('fecha_entrega', '>=', fecha_desde))
            if fecha_hasta:
                web_domain.append(('fecha_entrega', '<=', fecha_hasta))
            web_orders = request.env['sale.order'].sudo().search(web_domain)
            for so in web_orders:
                for line in so.order_line:
                    if product_id and line.product_id.id != int(product_id):
                        continue
                    if category_id:
                        cat_ids = [c.id for c in line.product_id.pos_categ_ids]
                        if int(category_id) not in cat_ids:
                            continue
                    orders_data.append({
                        'pedido': so.name,
                        'fecha_pedido': str(so.date_order.date() if so.date_order else ''),
                        'fecha_entrega': str(so.fecha_entrega or ''),
                        'tienda': 'Web',
                        'tipo': 'Web',
                        'cliente': so.partner_id.name,
                        'producto': line.product_id.display_name,
                        'categoria': ', '.join([c.name for c in line.product_id.pos_categ_ids][:3]),
                        'cantidad': line.product_uom_qty,
                        'nota': '',
                        'nota_general': so.note or '',
                    })

        return request.render('tpv_pedidos.web_informes_page', {
            'orders': orders_data,
            'tiendas': request.env['pos.config'].sudo().search_read([], ['id', 'name']),
            'productos': request.env['product.product'].sudo().search_read(
                [('available_in_pos', '=', True)], ['id', 'display_name']),
            'categorias': request.env['pos.category'].sudo().search_read([], ['id', 'name']),
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'tienda_id': tienda_id,
            'tipo_pedido': tipo_pedido,
            'product_id': product_id,
            'category_id': category_id,
        })

    @http.route('/tpv_pedidos/informes/pdf', type='http', auth='user', methods=['GET'])
    def web_informes_pdf(self, **kwargs):
        """Descarga el PDF de informes con los mismos filtros."""
        if not request.env.user._is_internal():
            return request.redirect('/web')

        config = request.env['tpv.pedido.config'].sudo().search([], limit=1)
        if not config:
            return request.not_found()

        # Call the print method and redirect to the generated attachment
        action = config.action_print_report()
        if action and action.get('url'):
            return request.redirect(action['url'])
        return request.not_found()

    @http.route('/tpv_pedidos/informes/csv', type='http', auth='user', methods=['GET'])
    def web_informes_csv(self, **kwargs):
        """Descarga CSV con los mismos datos que la web."""
        if not request.env.user._is_internal():
            return request.redirect('/web')

        # Reuse the same logic as web_informes to get orders_data
        Pedido = request.env['tpv.pedido'].sudo()
        today = datetime.now().strftime('%Y-%m-%d')

        fecha_desde = kwargs.get('fecha_desde', today)
        fecha_hasta = kwargs.get('fecha_hasta', today)
        tienda_id = kwargs.get('tienda_id', '')
        tipo_pedido = kwargs.get('tipo_pedido', '')

        domain = [('state', '=', 'confirmed')]
        if fecha_desde:
            domain.append(('fecha_entrega', '>=', fecha_desde))
        if fecha_hasta:
            domain.append(('fecha_entrega', '<=', fecha_hasta))
        if tienda_id:
            domain.append(('pos_config_id', '=', int(tienda_id)))
        if tipo_pedido and tipo_pedido != 'ext':
            domain.append(('tipo_pedido', '=', tipo_pedido))
        elif tipo_pedido == 'ext':
            domain.append(('id', '=', 0))

        all_pedidos = Pedido.search(domain, order='fecha_entrega, pos_config_id, name')

        # Build CSV rows
        rows = []
        headers = ['Pedido', 'Fecha Entrega', 'Tienda', 'Tipo', 'Cliente', 'Producto', 'Categoria', 'Cantidad', 'Nota Linea', 'Nota General']
        rows.append(headers)

        for p in all_pedidos:
            for line in p.line_ids:
                cat_path = _build_category_path(line.product_id)
                rows.append([
                    p.name,
                    str(p.fecha_entrega or ''),
                    p.pos_config_id.name or '',
                    dict(p._fields['tipo_pedido'].selection).get(p.tipo_pedido, ''),
                    p.pos_config_id.name or '',
                    line.product_id.display_name,
                    cat_path,
                    str(int(line.qty)),
                    line.nota_linea or '',
                    p.nota_general or '',
                ])

        # Include web orders if applicable
        if tipo_pedido in ('', 'ext'):
            web_domain = [('state', '=', 'sale')]
            if fecha_desde:
                web_domain.append(('fecha_entrega', '>=', fecha_desde))
            if fecha_hasta:
                web_domain.append(('fecha_entrega', '<=', fecha_hasta))
            web_orders = request.env['sale.order'].sudo().search(web_domain)
            for so in web_orders:
                for line in so.order_line:
                    cat_path = _build_category_path(line.product_id)
                    rows.append([
                        so.name,
                        str(so.fecha_entrega or ''),
                        'Web',
                        'Exterior',
                        so.partner_id.name,
                        line.product_id.display_name,
                        cat_path,
                        str(int(line.product_uom_qty)),
                        '',
                        so.note or '',
                    ])

        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
        for row in rows:
            writer.writerow(row)

        csv_content = output.getvalue()
        output.close()

        filename = 'informe_pedidos_%s.csv' % today
        return request.make_response(
            csv_content,
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', 'attachment; filename=' + filename),
            ],
        )
