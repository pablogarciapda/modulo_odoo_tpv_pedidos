# -*- coding: utf-8 -*-

from odoo import api, fields, models


class TpvPedidoLinea(models.Model):
    _name = 'tpv.pedido.linea'
    _description = 'Línea de Pedido al Obrador'
    _order = 'sequence, id'

    pedido_id = fields.Many2one(
        'tpv.pedido',
        string='Pedido',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
    )
    qty = fields.Float(
        string='Cantidad',
        default=1.0,
        digits='Product Unit of Measure',
        required=True,
    )
    nota_linea = fields.Text(
        string='Nota en Línea',
        help='Nota libre para esta línea de pedido.',
    )
    nota_categoria_id = fields.Many2one(
        'tpv.nota.categoria',
        string='Categoría de Nota',
        domain="[('activa', '=', True)]",
    )
    precio_unitario = fields.Float(
        string='Precio Unitario',
        digits='Product Price',
        compute='_compute_precio_unitario',
        store=True,
        readonly=False,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unidad de Medida',
        compute='_compute_product_uom',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='pedido_id.company_id',
        store=True,
    )

    @api.depends('product_id')
    def _compute_precio_unitario(self):
        for line in self:
            if line.product_id:
                line.precio_unitario = line.product_id.lst_price
            else:
                line.precio_unitario = 0.0

    @api.depends('product_id')
    def _compute_product_uom(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
            else:
                line.product_uom_id = False

    def _get_sale_line_name(self):
        """Genera el nombre para la línea del sale.order."""
        self.ensure_one()
        name = self.product_id.display_name
        if self.nota_categoria_id:
            name += ' [%s]' % self.nota_categoria_id.name
        if self.nota_linea:
            name += ' - %s' % self.nota_linea
        return name