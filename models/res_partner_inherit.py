# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    es_obrador = fields.Boolean(
        string='Es Obrador',
        default=False,
        help='Marca este contacto como el cliente genérico del obrador '
             'para los pedidos desde TPV.',
    )