# Plan de Informes — TPV Pedidos

## Visión General

Sistema de informes web con visualización, filtros y descarga de pedidos.
El obrador imprime automáticamente 4 bloques en la ventana 00:01-03:00.
Además se envía por email como PDF.

## Menú
- `Pedidos Obrador > Informes` — página web con filtros

## Tipos de Pedido

| Tipo | Origen | Pago | Entrega | Fecha |
|------|--------|------|---------|-------|
| **Pedido Tienda** | TPV (este módulo) | — | Obrador → Tienda | Día siguiente al pedido |
| **Encargo Tienda** | TPV (este módulo) | — | Obrador → Tienda (prioritario) | Fecha seleccionada por tienda |
| **Cliente VIP** | Web (usuario registrado) | Sin pago (factura) | Tienda / Obrador / Domicilio (>25€) | Fecha seleccionada por cliente |
| **Cliente Tarjeta** | Web (público) | Tarjeta | Tienda / Obrador | Fecha seleccionada por cliente |

## Fechas Clave

- **Fecha de pedido**: cuando se realiza el pedido (date_order)
- **Fecha de entrega**: cuando el cliente/tienda quiere recibirlo (NUEVO: fecha_entrega)
- **Reporte**: imprime los pedidos que se fabrican el día del reporte

### Lógica por tipo de pedido

| Tipo | Fecha entrega | Aparece en reporte del día |
|------|--------------|---------------------------|
| **Pedido Tienda** | `date_pedido + 1` (automático) | Día de **fecha_entrega** (se fabrica esa mañana) |
| **Encargo Tienda** | Seleccionada por la tienda | Día de **fecha_entrega - 1** (se fabrica el día antes) |
| **Cliente VIP** | Seleccionada por el cliente | Día de **fecha_entrega - 1** (se fabrica el día antes) |
| **Cliente Tarjeta** | Seleccionada por el cliente | Día de **fecha_entrega - 1** (se fabrica el día antes) |

**Ejemplo:**
- Encargo con fecha_entrega = 15/06 → aparece en reporte del **14/06** (se fabrica el 14 para entregar el 15)
- Pedido tienda del 05/06 con fecha_entrega = 06/06 → aparece en reporte del **06/06**
- Cliente web con entrega el 15/06 → aparece en reporte del **14/06**

### Ventana de Impresión Automática

- El cron corre cada hora
- Si la hora actual está entre **00:01 y 03:00** → procesa
- Busca pedidos con **fecha_entrega = hoy**
- Genera los 4 bloques
- Imprime + envía email PDF

## Modelo de Datos — Campo Nuevo

**`tpv.pedido`** → añadir campo:
```python
fecha_entrega = fields.Date(string='Fecha de entrega')
```
- Para pedidos tienda: fecha_entrega = date_pedido + 1 día (automático)
- Para encargos: fecha_entrega = la que seleccione la tienda
- Para clientes web: fecha_entrega = la que seleccione el cliente

## Estructura del Reporte Automático (4 Bloques)

## Estructura del Reporte Automático (4 Bloques)

### Bloque 1 — Totales por Familia Principal
*Una hoja por categoría principal de producto*

```
=== SALADOS (Categoría Principal) ===
Producto              Total  Exterior  TiendaCentro  TiendaNorte  ...
Croissant jamón        120      30         50           40
Napolitana            80       20         30           30
...
```

- Productos ordenados por cantidad total descendente
- Columna "Exterior" suma web + VIP + tarjeta
- Cada tienda en su columna (incluye sus encargos en la misma línea)
- Sirve para fabricación y reparto de rutas

### Bloque 2 — Clientes Externos
*Una página por cliente*

```
Cliente: Panadería Pérez (VIP)
Teléfono: 612345678
Dirección: Calle Mayor 5
Entrega: Domicilio (>25€) / Tienda / Obrador
--- Productos ---
Croissant jamón        12 uds.
Napolitana             6 uds.
...
```

- Clientes VIP (sin pago, factura)
- Clientes tarjeta (pagaron online)
- Si total > 25€ → envío a domicilio (excepto si eligió recoger)
- Se colocan en cajas blancas identificadas

### Bloque 3 — Encargos Tienda (NO Pastelería)
*Por tienda, cada encargo en un bloque*

```
--- Tienda Centro ---
ENCARGO #PED/2026/0030
Nota: Para el cumpleaños del sábado
  - Croissant jamón    20 uds
  - Napolitana         10 uds
  - [Nota: Con más chocolate]

ENCARGO #PED/2026/0031
Nota: Evento corporativo
  - Minipizzas         50 uds
...
```

- Todo lo que NO sea pastelería (categoría)

### Bloque 4 — Encargos Tienda (Pastelería)
*Mismo formato que Bloque 3 pero SOLO productos de pastelería*

- Para el obrador de pastelería (taller separado)

## Arquitectura Técnica

### 1. Web de Informes (Página tipo backend)

Será una vista tree/search personalizada con:

```
[Filtros]  [Generar Informe]  [Descargar PDF]
╔══════════════════════════════════════════╗
║ Tienda: [▼ Todas]  Tipo: [▼ Todos]      ║
║ Fecha desde: [📅]  hasta: [📅]           ║
║ Cliente: [____________]                  ║
║ Bloque: [▼ 1-Totales | 2-Clientes | ...]║
╚══════════════════════════════════════════╝

[Datos del informe seleccionado]
```

- **Modelo**: No hace falta modelo nuevo. Los datos vienen de:
  - `tpv.pedido` (pedidos desde TPV)
  - `sale.order` con `tipo_pedido_tag != False` (TPV + web)
  - `sale.order.line` (productos)
  - `product.product` → `pos_categ_ids` (categorías)

- **Controller**: Endpoints HTTP que devuelven HTML o JSON
- **QWeb Report**: Template por cada bloque

### 2. Impresión Automática + Email

**Ventana de impresión** (00:01 - 03:00):
```python
@api.model
def _cron_generar_informes(self):
    from datetime import datetime
    now = datetime.now()
    hora = now.hour + now.minute / 60.0
    if hora < 0.01 or hora > 3.0:  # fuera de ventana 00:01-03:00
        return
    
    config = self.env['tpv.pedido.config'].search([], limit=1)
    if not config or not config.printer_ip:
        return
    
    # Pedidos con fecha_entrega = hoy
    pedidos = self.search([('fecha_entrega', '=', fields.Date.today())])
    # + clientes web con fecha_entrega = hoy
    web_orders = self.env['sale.order'].search([
        ('fecha_entrega', '=', fields.Date.today()),
        ('estado', '=', 'sale'),
    ])
    
    pdf = self._generar_pdf_4_bloques(pedidos, web_orders)
    self._enviar_impresora(config, pdf)
    self._enviar_email(config, pdf)
```

- Corre cada hora, pero solo ejecuta dentro de la ventana 00:01-03:00
- Genera PDF con los 4 bloques
- Envía a impresora de red
- Envía por email como adjunto

### 3. Reporte QWeb (4 bloques en 1 PDF)

- Template único `tpv_pedidos.report_obrador` con 4 secciones
- Cada sección se renderiza solo si hay datos
- Orden: Bloque 1 → Bloque 2 → Bloque 3 → Bloque 4

### 4. Clasificación Pastelería vs No Pastelería

- Usar `pos.category` para marcar categorías como "pastelería"
- Nuevo campo `es_pasteleria` en `pos.category` (herencia)
- O usar un grupo de categorías predefinido

## Datos de Configuración

```
tpv.pedido.config (ampliar):
├── printer_ip, port, type (ya existen)
├── print_hour (ya existe)
├── print_email_to (nuevo) → email del obrador
├── print_email_active (nuevo) → activar envío por email
├── category_pasteleria_ids (nuevo) → categorías consideradas pastelería
├── category_principal_ids (nuevo) → categorías principales para Bloque 1
```

## Tareas de Implementación

### Fase 1 — Backend
1. Ampliar `tpv.pedido.config` con campos de email y categorías
2. Crear métodos de obtención de datos para cada bloque
3. Modificar reporte QWeb con los 4 bloques
4. Añadir envío por email al cron

### Fase 2 — Web de Informes
5. Crear vista tree/search con filtros
6. Crear controller HTTP para renderizar página
7. Añadir descarga PDF

### Fase 3 — Ajustes
8. Probar con datos reales
9. Ajustar formato de impresión según usuario
10. Documentar
