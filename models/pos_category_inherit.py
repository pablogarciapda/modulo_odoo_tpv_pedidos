# -*- coding: utf-8 -*-
from odoo import fields, models


class PosCategoryInherit(models.Model):
    _inherit = 'pos.category'

    tpv_print_copies = fields.Integer(
        string='Copias a imprimir',
        default=1,
        help='Numero de copias que se imprimen en el Bloque 1 '
             '(totales por familia principal). Util para repartir '
             'a diferentes puestos de trabajo.',
    )
    tpv_es_principal = fields.Boolean(
        string='Categoria principal',
        default=False,
        help='Marcar si esta categoria es una familia principal '
             'para el reporte del obrador.',
    )
