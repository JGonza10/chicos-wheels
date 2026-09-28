"""La landing page para clientes, servida en /tienda. Pública a propósito.

Los archivos de la página viven en `landing page/` (sitio aparte, sin build).
Solo `stock.js` y las fotos salen de la base, y únicamente con los campos que
permite `collecthub/landing.py`.
"""
import json
import re

from flask import Blueprint, Response, redirect, send_file, send_from_directory

from .. import landing
from ..util import ErrorApp

bp = Blueprint("tienda", __name__)

ID_PUBLICO = re.compile(r"^[0-9a-f]{16}$")


@bp.get("/tienda")
def inicio_sin_diagonal():
    # Con la diagonal final, las rutas relativas de la página (CW.css, stock.js…) resuelven bien.
    return redirect("/tienda/", code=301)


@bp.get("/tienda/")
def inicio():
    return send_from_directory(landing.CARPETA_LANDING, "index.html")


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


@bp.get("/tienda/<path:recurso>")
def estatico(recurso):
    # send_from_directory rechaza rutas fuera de la carpeta (../).
    if recurso.lower().endswith(".md"):
        raise ErrorApp("Esa ruta no existe", 404)
    return send_from_directory(landing.CARPETA_LANDING, recurso)
