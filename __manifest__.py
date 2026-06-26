{
    'name': 'TPV Pedidos',
    'version': '19.0.5.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Pedidos TPV al obrador. Requiere: pip3 install weasyprint --break-system-packages',
    'description': """
TPV Pedidos - Pedidos desde Tiendas al Obrador
===============================================

Módulo para gestionar pedidos desde tiendas (TPV) al obrador,
con dos tipos de pedido: ENCARGOS (prioritarios) y PEDIDOS TIENDA.

Características principales:
- PedidoScreen dentro del POS (sin abrir caja)
- Categorías jerárquicas con colores del POS
- Gestión de pedidos: crear, editar, cancelar
- Fecha de entrega seleccionable
- Informes PDF profesionales con WeasyPrint (5 módulos)
- Web de informes con filtros y descarga CSV/PDF
- Impresión automática programable
- Envío de informes por email

═══════════════════════════════════════
DEPENDENCIA: WeasyPrint
═══════════════════════════════════════
Para generar informes PDF es necesario instalar WeasyPrint.

En DOCKER:
  docker exec -u root NOMBRE_CONTENEDOR pip3 install weasyprint --break-system-packages
  docker exec -u root NOMBRE_CONTENEDOR apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info

En VPS:
  pip3 install weasyprint --break-system-packages
  sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info

Verificar:
  python3 -c "import weasyprint; print(weasyprint.__version__)"
    """,
    'author': 'Pablo García Fernández',
    'website': 'https://github.com/pablogarciapda',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security_rules.xml',
        'data/sequence_data.xml',
        'data/res_partner_data.xml',
        'data/tpv_nota_categoria_data.xml',
        'data/cron_data.xml',
        'data/initial_config_data.xml',
        'views/tpv_nota_categoria_views.xml',
        'views/tpv_pedido_views.xml',
        'views/tpv_pedido_config_views.xml',
        'views/tpv_backup_file_views.xml',
        'views/pos_category_views.xml',
        'views/menu_views.xml',
        'views/web_informes_templates.xml',
        'report/report_pedido_obrador.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'tpv_pedidos/static/src/js/login_screen_patch.js',
            'tpv_pedidos/static/src/js/pedido_screen.js',
            'tpv_pedidos/static/src/xml/login_screen_patch.xml',
            'tpv_pedidos/static/src/xml/pedido_screen.xml',
            'tpv_pedidos/static/src/xml/nota_linea_popup.xml',
            'tpv_pedidos/static/src/xml/pedido_confirm_popup.xml',
            'tpv_pedidos/static/src/scss/pedido_screen.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}