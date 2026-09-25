"""Catálogo en PDF con fotos y precios, para compartir por Facebook o WhatsApp.

Solo entran piezas que se pueden vender hoy (disponibles, no "Conservar", no las que
aún están "Por recibir"). Las fotos locales se leen del disco; las de URL externa solo
de tiendas conocidas, con tope de tamaño y de tiempo, para que el servidor nunca
descargue una dirección arbitraria.
"""
import io
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlparse

from fpdf import FPDF
from PIL import Image, ImageOps

from .db import RUTA_BD, todos
from .reporte import AZUL, GRIS, _t
from .util import ErrorApp

MAX_PIEZAS = 60
MAX_BYTES = 2 * 1024 * 1024
HOSTS_FOTO = ("cdn.shopify.com", "creations.mattel.com", "shop.mattel.com", "images.pokemontcg.io", "assets.tcgdex.net")
_UA = {"User-Agent": "Mozilla/5.0 (ChicosWheels)"}


def _host_permitido(url: str) -> bool:
    p = urlparse(url)
    h = (p.hostname or "").lower()
    return p.scheme == "https" and any(h == d or h.endswith("." + d) for d in HOSTS_FOTO)


def _bytes_foto(a: dict, usuario_id: str):
    foto = a.get("foto") or ""
    try:
        if foto.startswith("local:"):
            nombre = foto[len("local:"):]
            ruta = RUTA_BD.parent / "fotos" / usuario_id / nombre
            from .rutas.articulos import NOMBRE_FOTO_VALIDO
            return ruta.read_bytes() if NOMBRE_FOTO_VALIDO.match(nombre) and ruta.is_file() else None
        if _host_permitido(foto):
            req = urllib.request.Request(foto, headers=_UA)
            with urllib.request.urlopen(req, timeout=6) as r:  # noqa: S310 (host validado arriba)
                return r.read(MAX_BYTES)
    except Exception:
        return None
    return None


def _miniatura(datos):
    """JPEG cuadrado de 480 px con fondo claro; None si no es una imagen válida."""
    if not datos:
        return None
    try:
        with Image.open(io.BytesIO(datos)) as im:
            im = ImageOps.pad(im.convert("RGB"), (480, 480), color=(246, 247, 249), method=Image.LANCZOS)
            salida = io.BytesIO()
            im.save(salida, "JPEG", quality=82)
            return salida.getvalue()
    except Exception:
        return None


def _recortar(pdf, texto, ancho, max_lineas):
    """Parte el texto en renglones que caben en `ancho`; el último se corta con '...'."""
    palabras, lineas, actual = _t(texto).split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if pdf.get_string_width(prueba) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        while lineas[-1] and pdf.get_string_width(lineas[-1] + "...") > ancho:
            lineas[-1] = lineas[-1][:-1]
        lineas[-1] += "..."
    return lineas


def generar_catalogo(usuario_id: str, config: dict) -> bytes:
    ids = config.get("ids")
    tipo = config.get("tipo")
    piezas = [a for a in todos("SELECT * FROM v_articulos WHERE usuario_id=? AND disponible>0 AND estatus='Disponible'",
                               (usuario_id,))
              if (a.get("ubicacion") or "").strip().lower() != "por recibir"
              and (tipo in (None, "", "todos") or a["tipo"] == tipo)
              and (not isinstance(ids, list) or a["id"] in ids)]
    if not piezas:
        raise ErrorApp("No hay piezas disponibles para el catálogo")
    if len(piezas) > MAX_PIEZAS:
        raise ErrorApp(f"Un catálogo lleva máximo {MAX_PIEZAS} piezas; filtra o selecciona algunas ({len(piezas)} encontradas)")
    piezas.sort(key=lambda a: (a["tipo"], a["nombre"].lower()))

    with ThreadPoolExecutor(max_workers=8) as ex:
        fotos = list(ex.map(lambda a: _miniatura(_bytes_foto(a, usuario_id)), piezas))

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    ancho_card, alto_card, sep = 60, 78, 5
    x0, y0 = 10, 30

    def encabezado():
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(*AZUL)
        pdf.set_xy(10, 10)
        pdf.cell(0, 9, "Catalogo Chicos Wheels", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GRIS)
        pdf.set_x(10)
        pdf.cell(0, 5, _t(f"Hot Wheels y cartas Pokemon  |  {date.today().isoformat()}  |  "
                          "Entrega en persona en Balderas (sabados)"))
        pdf.set_y(-12)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, "Apartalas por mensaje. Precios sujetos a disponibilidad.", align="C")

    for i, (a, foto) in enumerate(zip(piezas, fotos)):
        pos = i % 9
        if pos == 0:
            encabezado()
        x = x0 + (pos % 3) * (ancho_card + sep)
        y = y0 + (pos // 3) * (alto_card + sep)
        pdf.set_draw_color(200, 206, 216)
        pdf.rect(x, y, ancho_card, alto_card)
        if foto:
            pdf.image(io.BytesIO(foto), x=x + 2, y=y + 2, w=ancho_card - 4, h=ancho_card - 4)
        else:
            pdf.set_fill_color(240, 242, 246)
            pdf.rect(x + 2, y + 2, ancho_card - 4, ancho_card - 4, style="F")
            pdf.set_xy(x + 2, y + 2 + (ancho_card - 4) / 2 - 3)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*GRIS)
            pdf.cell(ancho_card - 4, 6, "sin foto", align="C")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(30, 36, 51)
        ty = y + ancho_card
        for linea in _recortar(pdf, a["nombre"], ancho_card - 4, 2):
            pdf.set_xy(x + 2, ty)
            pdf.cell(ancho_card - 4, 3.6, linea)
            ty += 3.6
        det = a["serie"] if a["tipo"] == "Hot Wheels" else a["expansion"]
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*GRIS)
        pdf.set_xy(x + 2, y + alto_card - 8.5)
        pdf.cell(ancho_card - 26, 4, _t(" - ".join(x_ for x_ in (a["numero"], det) if x_))[:34])
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*AZUL)
        pdf.set_xy(x + ancho_card - 26, y + alto_card - 9)
        pdf.cell(24, 6, f"${a['valor_estimado']:,.0f}", align="R")
    return bytes(pdf.output())
