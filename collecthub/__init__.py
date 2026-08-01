"""
CollectHub · aplicación Flask.

Sirve la API bajo /api y el frontend (HTML, CSS y JS planos) desde /static.
"""
import os
import time
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from .auth import requiere_sesion
from .db import cerrar_bd, crear_esquema
from .util import ErrorApp

RAIZ = Path(__file__).resolve().parent.parent
ESTATICOS = RAIZ / "static"


def crear_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["JSON_SORT_KEYS"] = False

    crear_esquema()
    app.teardown_appcontext(cerrar_bd)

    # CORS: en desarrollo acepta cualquier origen; en producción, el dominio que definas.
    origen = os.environ.get("CORS_ORIGIN", "*")

    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = origen
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp

    # Límite simple de intentos de login: frena la fuerza bruta sin dependencias extra.
    intentos = defaultdict(lambda: {"n": 0, "desde": 0.0})

    @app.before_request
    def limitar_login():
        from flask import request
        if request.path != "/api/auth/login" or request.method != "POST":
            return None
        reg = intentos[request.remote_addr]
        ahora = time.time()
        if ahora - reg["desde"] > 900:
            reg["n"], reg["desde"] = 0, ahora
        reg["n"] += 1
        if reg["n"] > 10:
            return jsonify(error="Demasiados intentos. Espera 15 minutos."), 429
        return None

    # ---------- API ----------
    from .rutas.auth import bp as bp_auth
    from .rutas.articulos import bp as bp_articulos
    from .rutas.movimientos import bp as bp_movimientos
    from .rutas.catalogos import bp as bp_catalogos
    from .rutas.estado import bp as bp_estado

    app.register_blueprint(bp_auth, url_prefix="/api/auth")
    app.register_blueprint(bp_articulos, url_prefix="/api/articulos")
    app.register_blueprint(bp_movimientos, url_prefix="/api")
    app.register_blueprint(bp_catalogos, url_prefix="/api")
    app.register_blueprint(bp_estado, url_prefix="/api")

    # Todo lo que no sea /auth ni /salud exige sesión. Envolver aquí, en un solo
    # lugar, evita el riesgo de olvidar el decorador al agregar una ruta nueva.
    PROTEGIDOS = ("articulos.", "movimientos.", "catalogos.", "estado.")
    for endpoint, vista in list(app.view_functions.items()):
        if endpoint.startswith(PROTEGIDOS):
            app.view_functions[endpoint] = requiere_sesion(vista)

    @app.get("/api/salud")
    def salud():
        from .db import RUTA_BD
        return jsonify(ok=True, base=RUTA_BD.name, hora=time.strftime("%Y-%m-%dT%H:%M:%S"))

    # ---------- Frontend ----------
    @app.get("/")
    def inicio():
        return send_from_directory(ESTATICOS, "index.html")

    @app.get("/<path:recurso>")
    def estatico(recurso):
        if recurso.startswith("api/"):
            return jsonify(error="Esa ruta no existe"), 404
        archivo = ESTATICOS / recurso
        if archivo.is_file():
            return send_from_directory(ESTATICOS, recurso)
        return send_from_directory(ESTATICOS, "index.html")

    # ---------- Errores ----------
    @app.errorhandler(ErrorApp)
    def error_app(e):
        return jsonify(error=e.mensaje), e.codigo

    @app.errorhandler(404)
    def no_encontrado(_e):
        return jsonify(error="Esa ruta no existe"), 404

    @app.errorhandler(Exception)
    def error_inesperado(e):
        import sqlite3
        import traceback
        if isinstance(e, sqlite3.IntegrityError):
            return jsonify(error="La base de datos rechazó ese dato. "
                                 "Revisa cantidades y montos."), 409
        traceback.print_exc()
        return jsonify(error="Algo falló de nuestro lado. Intenta de nuevo."), 500

    return app
