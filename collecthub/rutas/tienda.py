"""La landing page para clientes, servida en /tienda. Pública a propósito.

Los archivos de la página viven en `landing page/` (sitio aparte, sin build).
Solo `stock.js` y las fotos salen de la base, y únicamente con los campos que
permite `collecthub/landing.py`.
"""
import html
import json
import re

from flask import Blueprint, Response, jsonify, redirect, request, send_file, send_from_directory

from .. import asistente, landing
from ..util import ErrorApp

bp = Blueprint("tienda", __name__)

ID_PUBLICO = re.compile(r"^[0-9a-f]{16}$")


@bp.get("/tienda")
def inicio_sin_diagonal():
    # Con la diagonal final, las rutas relativas de la página (CW.css, stock.js…) resuelven bien.
    return redirect("/tienda/", code=301)


def _pagina(pieza: dict | None = None) -> Response:
    """index.html con las etiquetas de vista previa (Open Graph) que Facebook, Messenger
    e Instagram leen al pegar el link. Con `pieza`, la vista previa es esa pieza y la
    página la abre sola al cargar (meta cw-pieza, la lee CW.js)."""
    texto = (landing.CARPETA_LANDING / "index.html").read_text(encoding="utf-8")
    raiz = request.url_root.rstrip("/")
    if pieza:
        titulo = f"{pieza['nombre']} · ${pieza['precio']:,.0f} MXN · Chicos Wheels"
        desc = " · ".join(str(x) for x in (pieza.get("serie") or pieza.get("expansion"), pieza.get("anio"),
                                             "Entrega los sábados en Balderas") if x)
        foto = pieza.get("foto") or ""
        imagen = f"{raiz}/tienda/{foto}" if foto.startswith("foto/") else foto
        extra = f'<meta name="cw-pieza" content="{html.escape(pieza["id"])}">'
    else:
        titulo = "Chicos Wheels · Hot Wheels, Pokémon y más"
        desc = "Piezas de colección en stock. Aparta y recoge el sábado en Balderas."
        imagen = f"{raiz}/tienda/img/portada.png" if (landing.CARPETA_LANDING / "img" / "portada.png").exists() else ""
        extra = ""
    e = lambda v: html.escape(str(v), quote=True)
    metas = [f'<base href="/tienda/">', extra,
             f'<meta property="og:type" content="website">',
             f'<meta property="og:site_name" content="Chicos Wheels">',
             f'<meta property="og:title" content="{e(titulo)}">',
             f'<meta property="og:description" content="{e(desc)}">',
             f'<meta property="og:url" content="{e(request.url)}">',
             f'<meta name="twitter:card" content="summary_large_image">']
    if imagen:
        metas.append(f'<meta property="og:image" content="{e(imagen)}">')
    texto = texto.replace("<head>", "<head>\n  " + "\n  ".join(m for m in metas if m), 1)
    resp = Response(texto, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/tienda/")
def inicio():
    return _pagina()


@bp.get("/tienda/p/<pid>")
def pieza(pid):
    """Link de una pieza para compartir en Facebook: vista previa con foto y precio."""
    dueno = landing.dueno()
    p = None
    if dueno and ID_PUBLICO.match(pid):
        p = next((landing.publica(a) for a in landing.todos(landing.SQL_STOCK, (dueno,))
                  if landing.id_publico(a["id"]) == pid), None)
    return _pagina(p)   # vendida o inexistente: la tienda normal


@bp.get("/tienda/stock.js")
def stock_js():
    dueno = landing.dueno()
    if dueno is None:
        # Sin LANDING_EMAIL: las piezas de ejemplo que trae la carpeta.
        resp = send_from_directory(landing.CARPETA_LANDING, "stock.js", mimetype="text/javascript")
    else:
        datos = json.dumps(landing.stock(dueno), ensure_ascii=False)
        resp = Response(f"window.CW_STOCK = {datos};\n", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/tienda/foto/<pid>.jpg")
def foto(pid):
    dueno = landing.dueno()
    ruta = landing.archivo_foto(dueno, pid) if dueno and ID_PUBLICO.match(pid) else None
    if ruta is None:
        raise ErrorApp("Esa foto no existe", 404)
    resp = send_file(ruta, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


# ---------- Asistente (chat de la tienda) ----------
# Públicas a propósito (las usa cualquier visitante). Con límite por IP en
# crear_app(); solo existen con LANDING_EMAIL configurado.

def _dueno_o_503():
    dueno = landing.dueno()
    if dueno is None:
        raise ErrorApp("El asistente no está disponible en este momento", 503)
    return dueno


def _cuerpo():
    b = request.get_json(silent=True) or {}
    if b.get("sitio"):  # campo trampa invisible: solo lo llena un bot
        raise ErrorApp("No se pudo procesar", 400)
    return b


@bp.post("/tienda/api/asistente")
def asistente_responder():
    return jsonify(asistente.responder(_dueno_o_503(), _cuerpo().get("mensaje")))


@bp.post("/tienda/api/apartar")
def asistente_apartar():
    return jsonify(asistente.apartar(_dueno_o_503(), _cuerpo())), 201


@bp.post("/tienda/api/avisame")
def asistente_avisame():
    return jsonify(asistente.avisame(_dueno_o_503(), _cuerpo())), 201


@bp.get("/tienda/<path:recurso>")
def estatico(recurso):
    # send_from_directory rechaza rutas fuera de la carpeta (../).
    if recurso.lower().endswith(".md"):
        raise ErrorApp("Esa ruta no existe", 404)
    return send_from_directory(landing.CARPETA_LANDING, recurso)
