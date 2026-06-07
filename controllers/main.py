# -*- coding: utf-8 -*-

import logging

from datetime import datetime

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


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
        """Web page with order reports and filters. Accessible to backend users only."""
        if not request.env.user._is_internal():
            return request.redirect('/web')

        Pedido = request.env['tpv.pedido'].sudo()
        today = datetime.now().strftime('%Y-%m-%d')

        # Get filters from request
        fecha_desde = kwargs.get('fecha_desde', today)
        fecha_hasta = kwargs.get('fecha_hasta', today)
        tienda_id = kwargs.get('tienda_id', '')
        tipo_pedido = kwargs.get('tipo_pedido', '')

        # Base domain for tpv.pedido
        domain = [('state', '=', 'confirmed')]
        if fecha_desde:
            domain.append(('fecha_entrega', '>=', fecha_desde))
        if fecha_hasta:
            domain.append(('fecha_entrega', '<=', fecha_hasta))
        if tienda_id:
            domain.append(('pos_config_id', '=', int(tienda_id)))
        if tipo_pedido:
            domain.append(('tipo_pedido', '=', tipo_pedido))

        all_pedidos = Pedido.search(domain, order='fecha_entrega, pos_config_id, name')

        # Web orders (sale.order) with same date filter
        web_domain = [
            ('state', '=', 'sale'),
        ]
        if fecha_desde:
            web_domain.append(('fecha_entrega', '>=', fecha_desde))
        if fecha_hasta:
            web_domain.append(('fecha_entrega', '<=', fecha_hasta))
        web_orders = request.env['sale.order'].sudo().search(web_domain)

        # Get config for titles and active modules
        config = request.env['tpv.pedido.config'].sudo().search([], limit=1)

        # Build report data using same methods as PDF report
        data = {
            'fecha': today,
            'bloque1': Pedido._get_bloque1_data(all_pedidos, web_orders) if config and config.module1_active else {},
            'bloque2': Pedido._get_bloque2_data(web_orders) if config and config.module2_active else {},
            'bloque3': Pedido._get_bloque3_data(all_pedidos) if config and config.module3_active else {},
            'bloque4': Pedido._get_bloque4_data(all_pedidos) if config and config.module4_active else {},
            'bloque5': Pedido._get_bloque5_data(all_pedidos, web_orders) if config and config.module5_active else {},
            'module1_title': config.module1_title if config else 'Totales por Familia Principal',
            'module2_title': config.module2_title if config else 'Encargos de Tiendas',
            'module3_title': config.module3_title if config else 'Pedidos de Clientes',
            'module4_title': config.module4_title if config else 'Encargos Especificos',
            'module5_title': config.module5_title if config else 'Pedidos Personalizados',
        }

        return request.render('tpv_pedidos.web_informes_page', {
            'data': data,
            'categories': request.env['pos.category'].sudo().search_read([], ['id', 'name']),
            'tiendas': request.env['pos.config'].sudo().search_read([], ['id', 'name']),
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'tienda_id': tienda_id,
            'tipo_pedido': tipo_pedido,
        })
