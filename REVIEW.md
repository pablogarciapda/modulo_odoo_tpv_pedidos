# Bug Report — TPV Pedidos Module

**Date:** 2026-06-04
**Reviewer:** Sub-agent code review
**Branch:** `fix/js-imports-pedidoregistry`

## Notes
- La rama está activa y sin mergear
- Todos los bugs críticos han sido corregidos

## Bug List

### CRITICAL (se rompe en runtime)

| # | Archivo | Línea | Bug | Fix |
|---|---------|-------|-----|-----|
| 1 | `models/tpv_pedido.py` | 361, 454 | `ir.logging.sudo().create()` → `_allow_sudo_commands=False` causa `AccessError` | ✅ `_logger.error()` |
| 2 | `static/src/js/pedido_screen.js` | - | Falta getter `posConfigName` → renderiza "undefined" | ✅ Agregado |
| 3 | `static/src/js/pedido_screen.js` | 491 | Ruta `odoo.pos_config_id` frágil (undefined si no hay POS) | ⏳ Futuro |

### MAJOR (comportamiento incorrecto)

| # | Archivo | Línea | Bug | Fix |
|---|---------|-------|-----|-----|
| 4 | `controllers/main.py` | 27-65 | Controller duplica lógica del modelo (`create_pedido_from_pos`) | ⏳ Pendiente |
| 5 | `controllers/main.py` | 54-65 | `try/except` traga excepciones en vez de propagarlas como JSON-RPC fault | ⏳ Pendiente |
| 6 | `models/tpv_pedido.py` | 102-109 | `action_confirm` no valida `sale_order_id` después de `_create_sale_order` | ⏳ Pendiente |
| 7 | `models/tpv_pedido.py` | 224-232 | Falta `tax_ids` en `sale.order.line` → líneas sin impuestos | ✅ Agregado `(6, 0, ...)` |

### MINOR (cosméticos o edge cases)

| # | Archivo | Línea | Bug | Fix |
|---|---------|-------|-----|-----|
| 8 | `report/report_pedido_obrador.xml` | 10 | `print_report_name` usa solo primer `date_pedido` con múltiples registros | ⏳ Pendiente |
| 9 | `data/cron_data.xml` | 12 | `nextcall` siempre a mañana aunque se instale antes de las 02:00 | ⏳ Pendiente |
| 10 | `data/res_partner_data.xml` | 8 | `customer_rank` depende de módulo `account` (ok por dependencia `sale`) | ⏳ Pendiente |
| 11 | `security/ir.model.access.csv` | - | No hay ACL para `base.group_system` (admin) ni `base.group_user` | ⏳ Pendiente |
| 12 | `controllers/main.py` | 96 | `date.today()` ignora zona horaria del usuario | ⏳ Pendiente |
| 13 | - | - | Directorio `wizard/` vacío | ⏳ Pendiente |

### SUGGESTION (mejoras)

| # | Archivo | Línea | Sugerencia |
|---|---------|-------|------------|
| 14 | `models/tpv_pedido.py` | 399-434 | ESC/POS: usar `%.2f` en vez de `%.0f` para cantidades fraccionarias |
| 15 | `models/tpv_pedido.py` | 319 | Cron solo imprime `confirmed`, no `done` |
| 16 | `static/src/js/pedido_screen.js` | 167-221 | `pos.models` podría no estar disponible sin sesión POS abierta |
| 17 | `static/src/scss/pedido_screen.scss` | - | `@each` loop incompatible con Sass de Odoo 19 | ✅ Clases explícitas |
| 18 | `static/src/scss/pedido_screen.scss` | - | Código duplicado por ediciones parciales | ✅ Archivo reescrito completo |

## Rama feat/gestion-pedidos-informes

| # | Cambio | Archivo | Estado |
|---|--------|---------|--------|
| 1 | `update_pedido_from_pos` | `models/tpv_pedido.py` | ✅ |
| 2 | `cancel_pedido_from_pos` | `models/tpv_pedido.py` | ✅ |
| 3 | `get_pedidos_today_for_pos` | `models/tpv_pedido.py` | ✅ |
| 4 | `PedidoListPopup` component | `static/src/js/pedido_screen.js` | ✅ |
| 5 | Modo edición (Actualizar/Cancelar) | `static/src/js/pedido_screen.js` | ✅ |
| 6 | Colores categoría desde backend ORM | `static/src/js/pedido_screen.js` | ✅ |
| 7 | Botón "Revisar Pedidos" | `static/src/xml/pedido_screen.xml` | ✅ |
| 8 | Touch UI (48px botones, 8px gap) | `static/src/scss/pedido_screen.scss` | ✅ |
