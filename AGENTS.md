# TPV Pedidos — Guía Técnica de Desarrollo (AGENTS)

## Módulo: `tpv_pedidos` (Odoo 19)

### Propósito
Pedidos desde tiendas (TPV) al obrador. Dos flujos: **ENCARGO** (prioritario, para cliente) y **PEDIDO TIENDA** (reposición diaria). Sin apertura de caja necesaria.

### Hard Rules del Módulo

1. **NUNCA** nombrar un archivo Python igual que el modelo heredado. `pos_config_inherit.py` (no `pos_config.py`), `sale_order_inherit.py` (no `sale_order.py`).
2. **NUNCA** usar `string` como selector XPath — es traducible y causa ParseError.
3. **Root tags**: XML backend → `<odoo>`. QWeb frontend (`static/src/xml/`) → `<templates xml:space="preserve">`.
4. **SIEMPRE** verificar campos del modelo destino antes de escribir `<record>` en XML.
5. **NO** usar `attrs` ni `states` en vistas (deprecados en Odoo 19). Usar `invisible="state != 'done'"` directo.
6. Los componentes OWL del POS se inyectan en el bundle `point_of_sale._assets_pos`.
7. El cliente genérico OBRADOR es `noupdate=1` — NO se sobreescribe al actualizar el módulo.

### Modelo de Datos

```
tpv.pedido (header)
├── name                    # Secuencia: PED/{year}/0001
├── pos_config_id           # → pos.config (tienda origen)
├── tipo_pedido             # encargo | pedido_tienda
├── partner_id              # → res.partner (OBRADOR por defecto)
├── state                   # draft | confirmed | done | cancelled
├── nota_general            # Text: nota libre
├── date_pedido             # Date
├── sale_order_id           # → sale.order (generado)
├── es_encargo              # Boolean compute
└── line_ids                # → tpv.pedido.linea

tpv.pedido.linea
├── pedido_id               # → tpv.pedido (cascade)
├── product_id              # → product.product
├── qty                     # Float
├── nota_linea              # Text: nota libre por línea
├── nota_categoria_id       # → tpv.nota.categoria
└── precio_unitario         # Float compute (product_id.lst_price)

tpv.nota.categoria
├── name                    # Char
├── activa                  # Boolean
└── sequence                # Integer
```

### Herencias

- `pos.config`: + `tpv_pedido_printer_ip`, `tpv_pedido_printer_port`, `tpv_pedido_printer_type`
- `sale.order`: + `tpv_pedido_id`, `tipo_pedido_tag`
- `res.partner`: + `es_obrador`

### Flujo del Frontend (OWL)

1. **LoginScreen** → Patch añade botón "Pedido a Obrador"
2. Click → `pos.navigate('PedidoScreen')` (sin abrir sesión)
3. **PedidoScreen** → Products + Categories (usa `pos.models` del POS)
4. Añadir productos→ `PedidoOrder` local (carrito)
5. Nota por línea → Popup con categorías + texto libre
6. Click "Encargo" o "Pedido Obrador" → **PedidoConfirmPopup** con nota general
7. Controller JSON-RPC → crea `tpv.pedido` + `sale.order` confirmado
8. Volver a LoginScreen

### Impresión (Cron 02:00)

- `_cron_imprimir_resumen_obrador()` en `tpv.pedido`
- Busca pedidos confirmed del día anterior
- Genera resumen por productos (totales + notas debajo)
- Genera detalle por tienda (encargos y pedidos separados)
- Envía por socket (ESC/POS o PDF raw) a la IP/puerto configurada

### Convenciones de Código

- **Archivos Python**: snake_case, sufijo `_inherit` para herencias
- **Componentes OWL**: PascalCase (`PedidoScreen`, `PedidoConfirmPopup`)
- **Templates QWeb**: `tpv_pedidos.PedidoScreen`, `tpv_pedidos.PedidoConfirmPopup`
- **IDs XML**: prefijo `tpv_pedido_` (ej: `tpv_pedido_view_form`)
- **Secuencias**: código `tpv.pedido`

### Dependencias

```python
depends = ['point_of_sale', 'sale']
```

### Asset Bundles

```python
'point_of_sale._assets_pos': [
    'tpv_pedidos/static/src/js/*.js',
    'tpv_pedidos/static/src/xml/*.xml',
],
'web.assets_backend': [
    'tpv_pedidos/static/src/scss/pedido_screen.scss',
],
```

### Tests

```bash
./odoo-bin -d testdb -i tpv_pedidos --test-enable --stop-after-init
```

### Referencias del Source Code (Odoo 19 POS)

- LoginScreen: `point_of_sale/static/src/app/screens/login_screen/`
- OpeningControlPopup: `point_of_sale/static/src/app/components/popups/opening_control_popup/`
- POS models: `point_of_sale/models/` (pos_session, pos_order, pos_config)
- POS registry: `registry.category("pos_pages")` para pantallas
- patch pattern: `patch(ClassName.prototype, { ... })`

### Estructura de Reportes

El reporte QWeb (`report_pedido_obrador.xml`) tiene dos secciones dentro de `t-call="web.external_layout"`:

1. **Resumen por Productos**: agrupado por `product_id`, ordenado por `qty_total` desc. Cada producto muestra total sin nota y debajo las líneas individuales con nota.
2. **Detalle por Tienda**: agrupado por `pos_config_id.name`, dentro separa ENCARGOS y PEDIDOS TIENDA. Cada pedido muestra nombre, líneas y nota general.

### Estado del Desarrollo

- [x] Estructura de directorios
- [x] `__manifest__.py`
- [x] Modelos Python (tpv_pedido, tpv_pedido_linea, tpv_nota_categoria, herencias)
- [x] Security (ACL + reglas por tienda)
- [x] Data (secuencia, cron, partner OBRADOR, categorías notas)
- [x] Cron _cron_imprimir_resumen_obrador + métodos ESC/POS
- [ ] Controller JSON-RPC para frontend OWL
- [ ] Componentes OWL (LoginScreen patch, PedidoScreen, popups)
- [ ] Templates QWeb para componentes OWL
- [ ] SCSS para PedidoScreen
- [ ] Vistas backend (form/tree/search + menú)
- [ ] Reporte QWeb
- [ ] Tests