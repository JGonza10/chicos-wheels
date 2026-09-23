"""Convierte MANUAL.md a HTML imprimible y PDF, desde el mismo parser, para
que ambos formatos salgan siempre identicos entre si. Basado en el script
`generar_manual_pdf.py` de 08_Rastreador_Productos (mismo criterio: parser de
Markdown a mano, sin la libreria `markdown` ni pandoc/libreoffice — cero
dependencias nuevas salvo reportlab, que ya es pura Python).

Uso: python generar_manual.py [origen.md] [carpeta_salida]
Por defecto: MANUAL.md -> MANUAL.html + MANUAL.pdf (misma carpeta que origen.md)
"""
import html as html_lib
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, Preformatted,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

ORIGEN = sys.argv[1] if len(sys.argv) > 1 else "MANUAL.md"
CARPETA_SALIDA = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(ORIGEN))
NOMBRE_BASE = os.path.splitext(os.path.basename(ORIGEN))[0]
DESTINO_HTML = os.path.join(CARPETA_SALIDA, f"{NOMBRE_BASE}.html")
DESTINO_PDF = os.path.join(CARPETA_SALIDA, f"{NOMBRE_BASE}.pdf")

AZUL = colors.HexColor("#0078d7")
GRIS_TEXTO = colors.HexColor("#333333")
GRIS_SUAVE = colors.HexColor("#6b7280")
GRIS_CLARO = colors.HexColor("#f3f4f6")

RE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2705\u274C\u2B50]+",
    flags=re.UNICODE,
)
TRADUCCION_ASCII = str.maketrans({
    "│": "|", "─": "-", "▼": "v", "▲": "^", "▶": ">", "◀": "<",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
    "┬": "+", "┴": "+", "┼": "+", "→": "->", "←": "<-", "↔": "<->",
})
REEMPLAZOS_EMOJI_TEXTO = {
    "\U0001F7E2": "[OK]", "\U0001F6AB": "[BLOQUEAR]", "⏭️": "[SKIP]", "⏭": "[SKIP]",
}
RE_EMOJI_AMPLIO = re.compile(
    "[\U0001F000-\U0001FFFF\u2300-\u23FF\u2600-\u27BF\uFE00-\uFE0F]+",
    flags=re.UNICODE,
)
GLIFOS_EXTRA_OK = set("–—''""…•™°")


def limpiar_emoji(texto):
    return RE_EMOJI.sub("", texto).strip()


def a_ascii(texto):
    """Solo para el PDF: Courier base-14 no trae glifos Unicode de lineas/emoji."""
    for emoji, reemplazo in REEMPLAZOS_EMOJI_TEXTO.items():
        texto = texto.replace(emoji, reemplazo)
    texto = RE_EMOJI_AMPLIO.sub("", texto)
    texto = texto.translate(TRADUCCION_ASCII)
    return "".join(
        c if (ord(c) < 0x180 or c in GLIFOS_EXTRA_OK or c in "\n\t") else "?"
        for c in texto
    )


def inline_pdf(texto):
    texto = a_ascii(texto)
    texto = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    texto = re.sub(r"`([^`]+)`", r'<font face="Courier" size="9" color="#0078d7">\1</font>', texto)
    return texto


def inline_html(texto):
    texto = html_lib.escape(texto)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)
    texto = re.sub(r"`([^`]+)`", r"<code>\1</code>", texto)
    return texto


# ───────────────────────────── Parser comun (bloques) ──────────────────────

def es_separador_tabla(linea):
    return bool(re.fullmatch(r"\|?[\s:\-\|]+\|?", linea.strip()))


def parsear_bloques(lineas):
    """Devuelve una lista de bloques (dicts) independiente del formato de
    salida — tanto el render a PDF como a HTML consumen la misma lista."""
    bloques = []
    i = 0
    n = len(lineas)
    buffer_lista = []
    tipo_lista_actual = None

    def cerrar_lista():
        nonlocal buffer_lista, tipo_lista_actual
        if buffer_lista:
            bloques.append({"tipo": "lista", "estilo": tipo_lista_actual, "items": buffer_lista})
            buffer_lista, tipo_lista_actual = [], None

    def continua_item(siguiente):
        return bool(siguiente) and not (
            siguiente == "---" or siguiente.startswith("#")
            or siguiente.startswith("```") or siguiente.startswith("|")
            or siguiente.startswith(">") or re.match(r"^[-*]\s+", siguiente)
            or re.match(r"^\d+\.\s+", siguiente)
        )

    while i < n:
        linea = lineas[i].rstrip("\n")
        cruda = linea.strip()

        if not cruda:
            cerrar_lista()
            i += 1
            continue

        if cruda == "---":
            cerrar_lista()
            bloques.append({"tipo": "regla"})
            i += 1
            continue

        if cruda.startswith("```"):
            cerrar_lista()
            i += 1
            codigo = []
            while i < n and not lineas[i].strip().startswith("```"):
                codigo.append(lineas[i].rstrip("\n"))
                i += 1
            i += 1
            bloques.append({"tipo": "codigo", "texto": "\n".join(codigo)})
            continue

        if cruda.startswith("#"):
            cerrar_lista()
            nivel = len(cruda) - len(cruda.lstrip("#"))
            texto = limpiar_emoji(cruda.lstrip("#").strip())
            bloques.append({"tipo": "encabezado", "nivel": min(nivel, 3), "texto": texto})
            i += 1
            continue

        if cruda.startswith("|"):
            cerrar_lista()
            filas_tabla = []
            while i < n and lineas[i].strip().startswith("|"):
                fila_cruda = lineas[i].strip()
                if not es_separador_tabla(fila_cruda):
                    filas_tabla.append([c.strip() for c in fila_cruda.strip("|").split("|")])
                i += 1
            if filas_tabla:
                bloques.append({"tipo": "tabla", "encabezado": filas_tabla[0], "filas": filas_tabla[1:]})
            continue

        m_bullet = re.match(r"^[-*]\s+(.*)", cruda)
        m_numero = re.match(r"^\d+\.\s+(.*)", cruda)
        if m_bullet or m_numero:
            estilo = "bullet" if m_bullet else "numero"
            if tipo_lista_actual and tipo_lista_actual != estilo:
                cerrar_lista()
            tipo_lista_actual = estilo
            texto_item = [(m_bullet or m_numero).group(1)]
            i += 1
            while i < n and continua_item(lineas[i].rstrip("\n").strip()):
                texto_item.append(lineas[i].rstrip("\n").strip())
                i += 1
            buffer_lista.append(" ".join(texto_item))
            continue

        if cruda.startswith(">"):
            cerrar_lista()
            bloques.append({"tipo": "cita", "texto": cruda.lstrip(">").strip()})
            i += 1
            continue

        cerrar_lista()
        buffer_parrafo = [cruda]
        i += 1
        while i < n:
            siguiente = lineas[i].rstrip("\n").strip()
            if not continua_item(siguiente):
                break
            buffer_parrafo.append(siguiente)
            i += 1
        bloques.append({"tipo": "parrafo", "texto": " ".join(buffer_parrafo)})

    cerrar_lista()
    return bloques


def separar_portada(lineas):
    """Primer H1 + linea de subtitulo en _italica_ se tratan aparte."""
    titulo, subtitulo = None, None
    resto = lineas
    if resto and resto[0].startswith("# "):
        titulo = limpiar_emoji(resto[0].lstrip("#").strip())
        resto = resto[1:]
        while resto and not resto[0].strip():
            resto = resto[1:]
        if resto and resto[0].strip().startswith("_") and resto[0].strip().endswith("_"):
            subtitulo = resto[0].strip().strip("_")
            resto = resto[1:]
    return titulo, subtitulo, resto


# ───────────────────────────────── Render PDF ───────────────────────────────

def construir_pdf(titulo, subtitulo, bloques):
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("TituloManual", parent=estilos["Title"], fontSize=22, textColor=AZUL, spaceAfter=4)
    estilo_subtitulo = ParagraphStyle("Subtitulo", parent=estilos["Normal"], fontSize=10, textColor=GRIS_SUAVE, spaceAfter=18, fontName="Helvetica-Oblique")
    estilo_h = {
        1: ParagraphStyle("H1", parent=estilos["Heading1"], fontSize=16, textColor=AZUL, spaceBefore=18, spaceAfter=8),
        2: ParagraphStyle("H2", parent=estilos["Heading2"], fontSize=13, textColor=GRIS_TEXTO, spaceBefore=14, spaceAfter=6),
        3: ParagraphStyle("H3", parent=estilos["Heading3"], fontSize=11.5, textColor=GRIS_TEXTO, spaceBefore=10, spaceAfter=4),
    }
    estilo_parrafo = ParagraphStyle("Parrafo", parent=estilos["Normal"], fontSize=10, leading=15, textColor=GRIS_TEXTO, spaceAfter=8)
    estilo_item = ParagraphStyle("Item", parent=estilo_parrafo, leftIndent=16, bulletIndent=4, spaceAfter=3)
    estilo_codigo = ParagraphStyle("Codigo", parent=estilos["Code"], fontSize=8, leading=11, backColor=GRIS_CLARO, borderPadding=8, textColor=GRIS_TEXTO)
    estilo_cita = ParagraphStyle("Cita", parent=estilo_parrafo, leftIndent=14, textColor=GRIS_SUAVE, fontName="Helvetica-Oblique")
    estilo_celda = ParagraphStyle("Celda", parent=estilo_parrafo, fontSize=9, spaceAfter=0)
    estilo_celda_header = ParagraphStyle("CeldaHeader", parent=estilo_celda, textColor=colors.white, fontName="Helvetica-Bold")

    flujos = []
    if titulo:
        flujos.append(Paragraph(titulo, estilo_titulo))
    if subtitulo:
        flujos.append(Paragraph(subtitulo, estilo_subtitulo))

    for b in bloques:
        t = b["tipo"]
        if t == "encabezado":
            flujos.append(Paragraph(inline_pdf(b["texto"]), estilo_h[b["nivel"]]))
        elif t == "parrafo":
            flujos.append(Paragraph(inline_pdf(b["texto"]), estilo_parrafo))
        elif t == "lista":
            for idx, item in enumerate(b["items"], start=1):
                marca = "•" if b["estilo"] == "bullet" else f"{idx}."
                flujos.append(Paragraph(f"{marca}&nbsp;&nbsp;{inline_pdf(item)}", estilo_item))
            flujos.append(Spacer(1, 6))
        elif t == "codigo":
            flujos.append(Preformatted(a_ascii(b["texto"]), estilo_codigo))
            flujos.append(Spacer(1, 8))
        elif t == "cita":
            flujos.append(Paragraph(inline_pdf(b["texto"]), estilo_cita))
        elif t == "regla":
            flujos.append(Spacer(1, 4))
            flujos.append(HRFlowable(width="100%", color=colors.HexColor("#d1d5db"), thickness=0.75))
            flujos.append(Spacer(1, 8))
        elif t == "tabla":
            ancho_col = (17 * cm) / len(b["encabezado"])
            datos = [[Paragraph(inline_pdf(c), estilo_celda_header) for c in b["encabezado"]]]
            for fila in b["filas"]:
                datos.append([Paragraph(inline_pdf(c), estilo_celda) for c in fila])
            tabla = Table(datos, colWidths=[ancho_col] * len(b["encabezado"]), repeatRows=1)
            tabla.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            flujos.append(tabla)
            flujos.append(Spacer(1, 10))

    doc = SimpleDocTemplate(
        DESTINO_PDF, pagesize=LETTER,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title=titulo or NOMBRE_BASE,
    )
    doc.build(flujos)


# ───────────────────────────────── Render HTML ──────────────────────────────

def construir_html(titulo, subtitulo, bloques):
    partes = []
    for b in bloques:
        t = b["tipo"]
        if t == "encabezado":
            # El H1 del .md ya se separo como portada (titulo de la pagina);
            # el resto de niveles mapea directo: ## -> <h2>, ### -> <h3>.
            nivel_html = min(max(b["nivel"], 2), 4)
            partes.append(f"<h{nivel_html}>{inline_html(b['texto'])}</h{nivel_html}>")
        elif t == "parrafo":
            partes.append(f"<p>{inline_html(b['texto'])}</p>")
        elif t == "lista":
            etiqueta = "ul" if b["estilo"] == "bullet" else "ol"
            items = "".join(f"<li>{inline_html(it)}</li>" for it in b["items"])
            partes.append(f"<{etiqueta}>{items}</{etiqueta}>")
        elif t == "codigo":
            partes.append(f"<pre><code>{html_lib.escape(b['texto'])}</code></pre>")
        elif t == "cita":
            partes.append(f"<blockquote>{inline_html(b['texto'])}</blockquote>")
        elif t == "regla":
            partes.append("<hr>")
        elif t == "tabla":
            encabezado = "".join(f"<th>{inline_html(c)}</th>" for c in b["encabezado"])
            filas = "".join(
                "<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in fila) + "</tr>"
                for fila in b["filas"]
            )
            partes.append(f"<table><thead><tr>{encabezado}</tr></thead><tbody>{filas}</tbody></table>")

    cuerpo = "\n".join(partes)
    titulo_pagina = html_lib.escape(titulo or NOMBRE_BASE)
    subtitulo_html = f'<p class="subtitulo">{html_lib.escape(subtitulo)}</p>' if subtitulo else ""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo_pagina}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 860px; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; color: #24292f; line-height: 1.6; background: #fff; }}
  h1 {{ color: #0078d7; font-size: 1.9rem; margin-bottom: .2rem; }}
  h2 {{ color: #0078d7; font-size: 1.35rem; margin-top: 2rem; border-bottom: 1px solid #e1e4e8; padding-bottom: .3rem; }}
  h3 {{ font-size: 1.1rem; margin-top: 1.4rem; }}
  h4 {{ font-size: 1rem; margin-top: 1.2rem; }}
  .subtitulo {{ color: #6b7280; font-style: italic; margin-top: 0; }}
  code {{ background: #f3f4f6; padding: .1rem .35rem; border-radius: 4px; font-size: .9em; color: #0078d7; }}
  pre {{ background: #f3f4f6; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: .85rem; }}
  pre code {{ background: none; padding: 0; color: inherit; }}
  blockquote {{ border-left: 3px solid #0078d7; margin-left: 0; padding-left: 1rem; color: #6b7280; font-style: italic; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem; }}
  th, td {{ border: 1px solid #d1d5db; padding: .5rem .6rem; text-align: left; vertical-align: top; }}
  th {{ background: #0078d7; color: #fff; }}
  tr:nth-child(even) {{ background: #f9fafb; }}
  hr {{ border: none; border-top: 1px solid #d1d5db; margin: 1.5rem 0; }}
  .imprimir {{ margin: 1.5rem 0; }}
  .imprimir button {{ background: #0078d7; color: #fff; border: none; padding: .6rem 1.2rem; border-radius: 6px; font-size: .95rem; cursor: pointer; }}
  @media print {{ .imprimir {{ display: none; }} body {{ max-width: none; }} }}
</style>
</head>
<body>
<div class="imprimir"><button onclick="window.print()">🖨️ Imprimir / Guardar como PDF</button></div>
<h1>{titulo_pagina}</h1>
{subtitulo_html}
{cuerpo}
</body>
</html>
"""


def main():
    with open(ORIGEN, "r", encoding="utf-8") as archivo:
        lineas = archivo.readlines()

    titulo, subtitulo, resto = separar_portada(lineas)
    bloques = parsear_bloques(resto)

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    construir_pdf(titulo, subtitulo, bloques)
    with open(DESTINO_HTML, "w", encoding="utf-8") as f:
        f.write(construir_html(titulo, subtitulo, bloques))

    print(f"HTML generado: {DESTINO_HTML}")
    print(f"PDF generado: {DESTINO_PDF}")


if __name__ == "__main__":
    main()
