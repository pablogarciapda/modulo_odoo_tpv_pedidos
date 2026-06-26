import logging
import os
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TpvBackupFile(models.Model):
    _name = 'tpv.backup.file'
    _description = 'Backup de informe de impresion'
    _order = 'date desc'

    name = fields.Char(string='Nombre', required=True)
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)
    date_pedido = fields.Date(string='Fecha pedido')
    filename = fields.Char(string='Nombre archivo')
    file_path = fields.Char(string='Ruta archivo', readonly=True)

    @api.model
    def _backup_dir(self):
        from odoo.tools import config as odoo_config
        data_dir = odoo_config['data_dir']
        path = os.path.join(data_dir, 'backups', 'tpv_pedidos')
        os.makedirs(path, exist_ok=True)
        return path

    @api.model
    def _save_pdf(self, pdf_data, filename):
        filepath = os.path.join(self._backup_dir(), filename)
        with open(filepath, 'wb') as f:
            f.write(pdf_data)
        return filepath

    def unlink(self):
        for rec in self:
            if rec.file_path and os.path.exists(rec.file_path):
                try:
                    os.remove(rec.file_path)
                except OSError as e:
                    _logger.warning('No se pudo eliminar %s: %s', rec.file_path, e)
        return super().unlink()

    @api.model
    def _cleanup_old_files(self, days=30):
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old = self.search([('date', '<', cutoff)])
        if old:
            _logger.info('Limpiando %d backups anteriores a %d dias', len(old), days)
            old.unlink()

    def action_download_selected(self):
        ids = self.env.context.get('active_ids', [])
        if not ids:
            raise UserError('Seleccione al menos un archivo.')
        return {
            'type': 'ir.actions.act_url',
            'url': '/tpv-pedidos/backup/download/%s' % ','.join(str(i) for i in ids),
            'target': 'self',
        }
