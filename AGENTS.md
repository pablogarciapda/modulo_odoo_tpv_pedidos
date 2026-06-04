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
8. **NO** usar `@tpv_pedidos/js/` imports en JS — el bundler de Odoo 19 no los resuelve. Fusionar TODO el JS en `pedido_screen.js`.
9. **NO** usar `async/await` en JS para POS — puede causar errores de sintaxis en el bundler. Usar `.then()/.catch()`.
10. Los **ACL** para `tpv.pedido` deben tener `perm_write=1` para POS users (necesitan confirmar pedidos).
11. Al crear `sale.order` programáticamente: usar `sudo()`, incluir `product_uom_id`, `pricelist_id`, `warehouse_id`, `partner_invoice_id`, `partner_shipping_id`.
12. **Categorías**: usar `getAllChildren()` para incluir subcategorías en el filtro de productos.

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
- [x] Controller JSON-RPC
- [x] Vistas backend (form/tree/search + menú)
- [x] Componentes OWL fusionados en pedido_screen.js
- [x] LoginScreen patch (botón "Pedido a Obrador")
- [x] Categorías jerárquicas (padre→hijo con getAllChildren)
- [x] SCSS para PedidoScreen
- [x] Reporte QWeb (resumen por productos + detalle por tienda)
- [x] Tests básicos
- [x] Icono del módulo

## Errores Encontrados y Solucionados

### Error 1: `JsonResponse` no existe en `odoo.http`
- **Síntoma**: `ImportError: cannot import name 'JsonResponse'`
- **Causa**: No existe en Odoo 19
- **Fix**: Solo importar `from odoo.http import request`

### Error 2: `category_id` no existe en `res.groups` de Odoo 19
- **Síntoma**: `ValueError: External ID not found: point_of_sale.module_category_point_of_sale`
- **Causa**: Odoo 19 eliminó `category_id` de `res.groups`. Usa `res.groups.privilege`
- **Fix**: Crear `res.groups.privilege` con su `category_id`, y en `res.groups` usar `privilege_id`

### Error 3: `numbercall`, `hour`, `minute` no existen en `ir.cron`
- **Síntoma**: `ValueError: Invalid field 'numbercall' in 'ir.cron'`
- **Causa**: Odoo 19 eliminó esos campos
- **Fix**: Usar `nextcall` con `eval="(DateTime.now().replace(hour=2, minute=0) + timedelta(days=1)).strftime(...)"`

### Error 4: `allowed_session_ids` no existe en `pos.config`
- **Síntoma**: `ParseError: Invalid field pos.config.allowed_session_ids`
- **Causa**: el campo no existe
- **Fix**: Simplificar dominio de regla de seguridad

### Error 5: `<search string="">` + `<group>` + `<separator>` deprecados
- **Síntoma**: `ParseError: Vista no disponible`
- **Causa**: Odoo 19 eliminó `string` en `<search>`, no usa `<group>` ni `<separator>` dentro
- **Fix**: Filtros directamente dentro de `<search>`, sin group/separator

### Error 6: `t-name` en herencia OWL crea template nuevo
- **Síntoma**: Botón "Pedido a Obrador" nunca aparece
- **Causa**: `t-name="tpv_pedidos.LoginScreen"` crea template nuevo, no parcha el original
- **Fix**: Usar solo `t-inherit` sin `t-name`

### Error 7: `disabled` sin valor en XML (XHTML strict)
- **Síntoma**: `Error: 'Invalid XML template: Specification mandates value for attribute disabled`
- **Causa**: En XML, `disabled` debe tener valor explícito
- **Fix**: Usar `disabled="disabled"`

### Error 8: Import JS `@tpv_pedidos/static/src/js/` incorrecto
- **Síntoma**: `Cannot find key "PedidoScreen" in "pos_pages" registry`
- **Causa**: `@module_name` mapea a `module_name/static/src/`, el path no debe repetir `static/src/`
- **Fix**: Usar `@tpv_pedidos/js/x` (no `@tpv_pedidos/static/src/js/x`)

### Error 9: `@tpv_pedidos/js/` no resuelto por el bundler
- **Síntoma**: `missing ) after argument list` en bundle minificado
- **Causa**: El bundler de Odoo 19 no resuelve imports entre archivos del mismo módulo custom
- **Fix**: Fusionar TODO el JS en un solo archivo. No usar imports entre archivos del mismo módulo.

### Error 10: `async/await` causa error en bundler
- **Síntoma**: `await is only valid in async functions`
- **Causa**: Restos de `await` en funciones no-async después de refactors
- **Fix**: Usar `.then()/.catch()` en lugar de async/await

### Error 11: `product_uom` no existe en `sale.order.line`
- **Síntoma**: `Invalid field 'product_uom' on model 'sale.order.line'`
- **Causa**: El campo se llama `product_uom_id`
- **Fix**: Usar `product_uom_id`

### Error 12: Falta `warehouse_id` en `sale.order`
- **Síntoma**: `You must set a warehouse on your sale order to proceed` (con sale_stock)
- **Causa**: `sale_stock` requiere warehouse para productos storable
- **Fix**: Buscar y asignar `warehouse_id` antes de crear el sale.order

### Error 13: ACL sin permiso de escritura para POS users
- **Síntoma**: `Access Denied by ACLs for operation: write, uid: 24, model: tpv.pedido`
- **Causa**: `perm_write=0` en `access_tpv_pedido_user`
- **Fix**: Cambiar a `perm_write=1` y en regla de seguridad también

### Error 14: `sale.order.create()` sin `sudo()` — cajero no tiene permisos
- **Síntoma**: `Access Denied by ACLs for operation: create, uid: 24, model: sale.order`
- **Causa**: El cajero POS no tiene permisos de ventas
- **Fix**: Usar `self.env['sale.order'].sudo().create(...)`

### Error 15: `res.company` no tiene `default_pricelist_id`
- **Síntoma**: `AttributeError: 'res.company' object has no attribute 'default_pricelist_id'`
- **Causa**: El campo no existe en `res.company`
- **Fix**: Buscar pricelist directamente con `self.env['product.pricelist'].search([...])`