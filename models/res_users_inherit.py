# -*- coding: utf-8 -*-

from odoo import api, models


class ResUsersInherit(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        # Extract pos_config_ids from vals before user creation
        pos_config_ids_vals = []
        for vals in vals_list:
            pos_config_ids_vals.append(vals.pop('pos_config_ids', False))

        # Create users first (so user and its employee exist)
        users = super().create(vals_list)

        # Now assign POS configs after user exists
        for user, pos_ids in zip(users, pos_config_ids_vals):
            if pos_ids:
                # pos_ids is a list of commands like [(4, id), (6, 0, [ids])]
                user.write({'pos_config_ids': pos_ids})

        return users
