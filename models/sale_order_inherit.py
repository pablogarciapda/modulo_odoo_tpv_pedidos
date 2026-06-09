# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models


class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    tpv_pedido_id = fields.Many2one(
        'tpv.pedido',
        string='Pedido TPV Origen',
        readonly=True,
        copy=False,
    )
    tipo_pedido_tag = fields.Selection(
        [
            ('encargo', 'ENCARGO'),
            ('pedido_tienda', 'Pedido Tienda'),
            ('vip', 'VIP'),
            ('web', 'Web'),
        ],
        string='Tipo de Pedido',
        tracking=True,
    )
    fecha_entrega = fields.Date(
        string='Fecha de entrega',
        compute='_compute_fecha_entrega',
        store=True,
        readonly=False,
        help='Fecha en que el cliente necesita recibir el pedido. '
             'Por defecto: fecha de pedido + 1 dia.',
    )

    @api.depends('date_order')
    def _compute_fecha_entrega(self):
        for rec in self:
            if not rec.fecha_entrega and rec.date_order:
                rec.fecha_entrega = rec.date_order.date() + timedelta(days=1)