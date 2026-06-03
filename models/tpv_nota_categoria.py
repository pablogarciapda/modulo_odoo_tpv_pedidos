# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TpvNotaCategoria(models.Model):
    _name = 'tpv.nota.categoria'
    _description = 'Categoría de Nota en Línea de Pedido'
    _order = 'sequence, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )
    activa = fields.Boolean(
        string='Activa',
        default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )