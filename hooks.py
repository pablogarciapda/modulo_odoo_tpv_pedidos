# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def _check_weasyprint_deps(cr, registry):
    """Verifica dependencias de WeasyPrint y muestra comandos si faltan."""
    try:
        import weasyprint
        try:
            from weasyprint import HTML
            pdf = HTML(string='<html><body><p>t</p></body></html>').write_pdf()
            if pdf and len(pdf) > 100:
                _logger.info('WeasyPrint %s OK - PDF generado (%d bytes)',
                             weasyprint.__version__, len(pdf))
                return
        except OSError:
            _logger.info('WeasyPrint instalado pero faltan librerias del sistema.')
        except Exception:
            _logger.info('WeasyPrint instalado pero fallo la generacion de PDF.')
    except ImportError:
        _logger.info('WeasyPrint no instalado.')

    # Si llegamos aqui, falta algo. Mostrar comandos.
    _logger.warning(
        '=== DEPENDENCIAS WEYASPRINT ===\n'
        'Faltan dependencias para generar PDFs.\n'
        '\n'
        'En DOCKER (como root):\n'
        '  docker exec -u root NOMBRE_CONTENEDOR pip3 install weasyprint --break-system-packages\n'
        '  docker exec -u root NOMBRE_CONTENEDOR apt-get install -y '
        'libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info\n'
        '\n'
        'En VPS (con sudo):\n'
        '  pip3 install weasyprint --break-system-packages\n'
        '  sudo apt-get install -y '
        'libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info\n'
        '\n'
        'Verificar:\n'
        '  python3 -c "import weasyprint; print(weasyprint.__version__)"\n'
        '==============================='
    )
