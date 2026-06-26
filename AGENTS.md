# TPV Pedidos — Guía Técnica de Desarrollo (AGENTS)

## Módulo: `tpv_pedidos` (Odoo 19)

## Skills Relacionadas
- `weasyprint-odoo-reports` (`skills/weasyprint-odoo-reports/SKILL.md`): Generación de informes PDF con WeasyPrint en Odoo. Templates HTML+CSS, A4 landscape/portrait, merge de PDFs.

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
9. **NO** usar `async/await` en JS del POS — causa errores de sintaxis en el bundler. Usar `.then()/.catch()`.
10. **NO** usar `@each` loops en SCSS — el compilador Sass de Odoo 19 no soporta ciertas sintaxis de mapas. Usar `nth()` con listas de pares, o clases explícitas.
11. Los **ACL** para `tpv.pedido` deben tener `perm_write=1` para POS users (necesitan confirmar pedidos).
12. Al crear `sale.order` programáticamente: usar `sudo()`, incluir `product_uom_id`, `pricelist_id`, `warehouse_id`, `partner_invoice_id`, `partner_shipping_id`, `tax_ids`.
13. **Categorías**: usar `getAllChildren()` para incluir subcategorías en el filtro de productos.
14. **ir.logging**: tiene `_allow_sudo_commands = False` — NO usar `.sudo().create()` en él, usar `_logger.error()`.
15. **Colores de categoría**: El modelo `PosCategory` en JS del POS NO carga `color` por defecto. Hacer llamada ORM adicional para obtenerlos. Fallback: `(cat.id % 12)`.
16. **Edición de pedidos**: Al cargar un pedido existente, los botones cambian a "Actualizar" / "Cancelar Pedido". El método `update_pedido_from_pos` reemplaza líneas y reconfirma si estaba en borrador.

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

### Impresión (Cron cada 1 min)

- `_cron_imprimir_resumen_obrador()` en `tpv.pedido`
- Corre cada 1 minuto, solo ejecuta si la hora España coincide con la configurada (hora+minuto)
- `print_hour` (Selection 00-23) + `print_minute` (Selection 00-59) en `tpv.pedido.config`
- Usa `pytz.timezone('Europe/Madrid')` para comparar hora actual con la configurada
- Busca pedidos confirmed del día anterior
- Busca pedidos web con `fecha_entrega = today`
- Genera resumen por productos (totales + notas debajo)
- Genera detalle por tienda (encargos y pedidos separados)
- Envía por socket (ESC/POS o PDF raw) a la IP/puerto configurada
- Guarda automáticamente un backup del PDF en disco (`/mnt/extra-addons/tpv_pedidos/backups/`), referencia en `tpv.backup.file`
- Limpieza automática: borra backups con más de 30 días al generar uno nuevo
- Los backups se gestionan desde el menú "Backups de impresión"

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
- [x] `__manifest__.py` v19.0.2.0.0
- [x] Modelos Python (tpv_pedido, tpv_pedido_linea, tpv_nota_categoria, herencias, config, report_line)
- [x] Security (ACL + reglas por tienda)
- [x] Data (secuencia, cron, partner OBRADOR, categorías notas, config inicial)
- [x] Cron _cron_imprimir_resumen_obrador + métodos ESC/POS + email
- [x] Controller JSON-RPC + HTTP (informes web)
- [x] Vistas backend (form/tree/search + menú)
- [x] Componentes OWL fusionados en pedido_screen.js
- [x] LoginScreen patch (botón "Pedido a Obrador")
- [x] Categorías jerárquicas (padre→hijo con getAllChildren)
- [x] SCSS para PedidoScreen
- [x] Reporte QWeb (5 módulos, landscape/portrait, A4)
- [x] Web de informes con filtros + PDF + CSV
- [x] Config singleton (tpv.pedido.config)
- [x] Gestión de pedidos: crear, editar, cancelar
- [x] Fecha de entrega (default tomorrow)
- [x] Productos por docenas (UoM factor)
- [x] Tests básicos
- [x] Icono del módulo

## Rama activa
- `feat/gestion-pedidos-informes` — gestión de pedidos + colores + UI táctil
- `fix/js-imports-pedidoregistry` — ya mergeada a main ✅

## Regla Elemental: Odoo 19 No Usa `<tree>` para Listas

En Odoo 19, el tag `<tree>` **no existe** como tipo de vista. Se usa `<list>`.

```
INCORRECTO: <tree> → ParseError: "Invalid view type: 'tree'"
CORRECTO:   <list> → Funciona
```

Además:
- `<button>` va como **hijo directo** de `<list>`, no envuelto en `<header>`.
- `<header>` dentro de `<list>` tampoco funciona.
- **`@route(type='json')` deprecado**: En Odoo 19 usar `type='jsonrpc'`. NO usar `type='json'`.
- Tipos válidos en Odoo 19: `list, form, graph, pivot, calendar, kanban, search, qweb, hierarchy, activity`

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

### Error 16: `ir.logging.sudo().create()` causa AccessError
- **Síntoma**: `AccessError` al ejecutar el cron de impresión
- **Causa**: `ir.logging` tiene `_allow_sudo_commands = False` en Odoo 19
- **Fix**: Reemplazar con `_logger.error(...)`

### Error 17: SCSS `@each` loop incompatible con compilador Sass de Odoo 19
- **Síntoma**: `Error: Invalid CSS after "    }": expected selector or at-rule, was "}"`
- **Causa**: La sintaxis `@each $i, $color in (0: #..., ...)` no es soportada
- **Fix**: Usar lista de pares con `nth($pair, 1)` y `nth($pair, 2)`, o clases CSS explícitas

### Error 18: Código duplicado en SCSS por ediciones parciales
- **Síntoma**: Múltiples bloques `.open-pedido-btn`, `.pedido-order-panel` duplicados
- **Causa**: Ediciones que solo reemplazaron parte del archivo
- **Fix**: Reescribir el archivo SCSS completo en vez de editar secciones

### Error 19: Cancelar pedido con sale.order confirmado
- **Síntoma**: `No se puede cancelar un pedido cuyo pedido de venta ya está confirmado`
- **Causa**: `action_cancel` bloqueaba si sale.order tenía state 'sale'
- **Fix**: Cancelar el sale.order primero con `sudo().action_cancel()` si está en 'sale', luego cancelar el pedido

### Error 20: `child_id` vs `child_ids` en campo relacional
- **Síntoma**: `AttributeError: 'pos.category' object has no attribute 'child_id'`
- **Causa**: El subagente escribió `child_id` en vez de `child_ids`
- **Fix**: Usar `category.child_ids`

### Error 21: `_()` import con UnboundLocalError
- **Síntoma**: `UnboundLocalError: cannot access local variable '_'`
- **Causa**: `_` importada de odoo pero conflicto con variable local en el mismo scope
- **Fix**: Usar string sin `_()` o importar de otra forma

### Error 22: Reporte QWeb sin `<main>` tag
- **Síntoma**: `IndexError: list index out of range` en `_prepare_html`
- **Causa**: `t-call="web.external_layout"` no generaba `<main>` cuando docs estaba vacío
- **Fix**: Reemplazar `t-call` por `<main>` directo en el template

### Error 23: Stat button overlay en formulario de pedido
- **Síntoma**: Al abrir un pedido, el `oe_button_box` flota sobre el formulario tapando los campos.
- **Causa**: `widget="statinfo"` dentro de `oe_stat_button` + `oe_button_box` con `position: absolute` en Odoo 19.
- **Fix**: Eliminar el `oe_button_box`. Botón en header, campo `sale_order_id` en group.

### Error 24: Cron diario con `nextcall` en UTC y ventana hardcodeada en CEST
- **Síntoma**: El cron de impresión saltaba pero se salía inmediatamente: `hora_actual=4.00 fuera de ventana 00:01-03:00`.
- **Causa 1**: El `nextcall` se insertaba como hora local pero Odoo la interpreta como UTC. A las 02:00 UTC son 04:00 CEST.
- **Causa 2**: La ventana horaria (00:01-03:00) estaba hardcodeada en el código y no usaba el campo `print_hour` de la config.
- **Fix**: Reemplazar `print_hour` (Selection simple) por `print_hour` + `print_minute` (Selection 00-23/00-59). El cron ahora corre cada 1 minuto y compara la hora España actual contra los valores de config. La ventana hardcodeada se eliminó.

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 19.0.4.0.0 | 2026-06-23 | **Fix cron impresión + backups PDF**: `print_hour`/`print_minute` como Selection 00-23/00-59. Cron cada 1 min, compara hora España con config. Nuevo modelo `tpv.backup.file` con backups automáticos al imprimir. Menú "Backups de impresión" con descarga ZIP + borrado automático. |
| 19.0.3.1.0 | 2026-06-21 | Debug logs en cron. AGENTS.md completo. |
| 19.0.3.0.0 | 2026-06-08 | WeasyPrint reports for all 5 modules. Landscape Module 1, portrait 2-5. HTML+CSS templates. |
| 19.0.2.0.0 | 2026-06-07 | Web informes with filters, CSV, PDF download. Fecha entrega. |
| 19.0.1.0.0 | 2026-06-03 | Initial version. POS pedidos, basic reports. |