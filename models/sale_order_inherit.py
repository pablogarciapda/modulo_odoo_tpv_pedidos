# -*- coding: utf-8 -*-

from odoo import fields, models


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
        ],
        string='Tipo de Pedido',
        tracking=True,
    )