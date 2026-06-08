---
name: weasyprint-odoo-reports
description: "Trigger: generar informes PDF con WeasyPrint en Odoo, reportes personalizados HTML+CSS, diseno de informes A4. Complete guide for generating beautiful PDF reports in Odoo using WeasyPrint."
license: LGPL-3
---

# WeasyPrint + Odoo Report Generation

## Instalacion en servidor

```bash
pip3 install weasyprint --break-system-packages
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info
```

Verificar:
```python
import weasyprint; print(weasyprint.__version__)
```

## Arquitectura

WeasyPrint convierte HTML+CSS a PDF. En Odoo el flujo es:
1. Templates HTML en `report/templates/`
2. Metodo Python lee template, reemplaza placeholders
3. `weasyprint.HTML(string=html).write_pdf()` genera PDF
4. Se crea `ir.attachment` y se devuelve URL de descarga

## Estructura de Template

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
@page { size: A4 landscape; margin: 1.2cm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10px; }
table { width: 100%; border-collapse: collapse; }
th { background: #2c2c2c; color: #fff; padding: 4px; }
td { padding: 3px 4px; border-bottom: 1px solid #ddd; }
.page-break { page-break-before: always; }
</style>
</head>
<body>
<h1>{TITLE}</h1>
<p>{FECHA}</p>
{MODULE_CONTENT}
</body>
</html>
```

## Patron Python

```python
@api.model
def _render_weasy_template(self, template_name, title, fecha, content_html):
    import weasyprint
    import os
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'report', 'templates', template_name
    )
    with open(template_path, 'r') as f:
        template = f.read()
    html = template.replace('{TITLE}', title)
    html = html.replace('{FECHA}', str(fecha))
    html = html.replace('{MODULE_CONTENT}', content_html)
    return weasyprint.HTML(string=html).write_pdf()
```

## Notas Importantes

1. **Fuentes**: WeasyPrint incluye DejaVu Sans. Para fuentes custom, instalarlas en el sistema.
2. **@page**: `size: A4 landscape` o `size: A4 portrait` para orientacion.
3. **Saltos de pagina**: `<div class="page-break"></div>` con `page-break-before: always`.
4. **Colores**: Usar hex. Backgrounds funcionan correctamente.
5. **Imagenes**: SVG funciona mejor. PNG/JPG con rutas absolutas.
6. **Tablas**: `border-collapse: collapse` para tablas limpias.
7. **Merge PDFs**: Usar `PyPDF2.PdfMerger` o `pypdf.PdfMerger` para combinar PDFs.
8. **Templates**: Guardar en `report/templates/`, leer con `open()`.
9. **Placeholders**: Usar `{PLACEHOLDER}` con `str.replace()`.

## CSS Comun para Reportes

```css
@page { size: A4 portrait; margin: 1.5cm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10px; color: #222; }
.title { font-size: 16px; font-weight: bold; }
.section-title { font-size: 13px; font-weight: bold; border-bottom: 2px solid #333; }
.item-box { border: 1px solid #ddd; border-radius: 4px; padding: 6px; margin-bottom: 6px; background: #fafafa; }
.item-name { font-weight: bold; font-size: 10px; }
.item-line { padding: 2px 0; border-bottom: 1px dotted #eee; }
td.r { text-align: right; }
tr:nth-child(even) { background-color: #f7f7f7; }
.page-break { page-break-before: always; }
```

## Instalacion de la Skill

Para usar esta skill en OpenCode, anadir al `opencode.json` del proyecto o usuario:
```json
"skills": {
    "enabled": ["weasyprint-odoo-reports"]
}
```
