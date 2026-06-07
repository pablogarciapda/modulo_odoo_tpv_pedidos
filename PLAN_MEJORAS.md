# Plan de Mejoras — Informes TPV Pedidos

## 1. Diseño del Reporte (Módulo 1 - Totales)

### Estilo deseado
- Hoja A4 por cada categoría principal
- Diseño limpio, solo datos necesarios
- Sin decimales (cantidades enteras)
- Si una categoría tiene N copias → N hojas A4 idénticas

### Columnas del Bloque 1
```
[Producto]  [Total Uds]  [Ext]  [Tienda1]  [Tienda2]  ...
```

- Sin decimales en cantidades
- Productos ordenados alfabéticamente o por cantidad descendente

### Productos por docenas
- Algunos productos usan UoM "Docena(s)" (factor=12 sobre "Unidad(es)")
- En el reporte: si `product.uom_id.factor > 1`, multiplicar qty por el factor
- Así "1 Docena" → 12 unidades en el reporte
- No hace falta campo nuevo, se lee de la UoM del producto

## 2. Personalización del Diseño del Reporte

El usuario quiere poder diseñar el informe como desee.

**Opciones:**
- A) Template QWeb parametrizable con opciones de diseño
- B) Editor de informes tipo drag & drop (complejo)
- C) Configuración de columnas visibles por módulo

**Propuesta inicial (A):** Parametrizar el template QWeb con opciones:
- Mostrar/Ocultar columnas (Ext, Tiendas)
- Ordenación (alfabético / por cantidad)
- Agrupación (por categoría / por tienda)
- Formato de cantidades (unidades / docenas)

## 3. Productos por Docenas

### Implementación
1. Campo nuevo: `product.template.tpv_dozen` (Boolean, default=False)
2. En reporte: si `tpv_dozen` es True, qty = qty * 12
3. Mostrar "ud" o "doc" según corresponda

### Archivos afectados
- `models/product_template_inherit.py` (nuevo)
- `models/__init__.py`
- `models/tpv_pedido.py` (lógica de reporte)
- `report/report_pedido_obrador.xml` (template)

## 4. Diseño Modular

Cada módulo del reporte podría tener su propio subtemplate QWeb:
- `tpv_pedidos.report_bloque1`
- `tpv_pedidos.report_bloque2`
- etc.

Esto permite personalizar cada bloque por separado.

## Orden de Implementación

1. Crear campo `tpv_dozen` en product.template
2. Modificar `_get_bloque1_data` para multiplicar por 12 cuando corresponda
3. Actualizar template QWeb: formato sin decimales, A4 por categoría
4. Añadir opciones de diseño parametrizables

## Notas
- El usuario intentó compartir un diseño de imagen pero el chat no soporta imágenes
- Preguntar al usuario si quiere compartir el diseño por otro medio
