"""
Chicos Wheels (CollectHub) · aplicación Flask.

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

    # Tope al tamaño de cualquier petición (también acota la carga de la
    # plantilla .xlsx de inventario): sin esto, Flask acepta un cuerpo de
    # cualquier tamaño y una petición gigante puede agotar memoria/disco.
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

    crear_esquema()
    app.teardown_appcontext(cerrar_bd)

    # CORS: sin CORS_ORIGIN configurado, NO se manda Access-Control-Allow-Origin.
    # La app ya sirve su propio frontend desde el mismo origen (no lo necesita
    # para funcionar); dejar "*" por defecto expondría la API a que cualquier
    # sitio externo la llame. Define CORS_ORIGIN solo si de verdad necesitas
    # que otro dominio consuma esta API.
    origen = os.environ.get("CORS_ORIGIN", "")

    @app.after_request
    def cabeceras(resp):
        if origen:
            resp.headers["Access-Control-Allow-Origin"] = origen
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        # Cabeceras de seguridad básicas. El CSP permite lo que la app realmente
        # usa: Google Fonts, el CDN de qrcodejs, y los estilos inline con los
        # que arma sus vistas app.js (quitar 'unsafe-inline' de style-src
        # rompería casi toda la interfaz).
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Strict-Transport-Security"] = "max-age=15552000; includeSubDomains"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        return resp

    # Límite simple de peticiones por IP: frena fuerza bruta y abuso, sin
    # dependencias extra. Dos niveles: uno estricto para login/registro
    # (donde importa más), y uno amplio para el resto de la API.
    intentos_auth = defaultdict(lambda: {"n": 0, "desde": 0.0})
    peticiones_api = defaultdict(lambda: {"n": 0, "desde": 0.0})

    def _excedido(registro, ip, ventana_seg, tope):
        reg = registro[ip]
        ahora = time.time()
        if ahora - reg["desde"] > ventana_seg:
            reg["n"], reg["desde"] = 0, ahora
        reg["n"] += 1
        return reg["n"] > tope

    def _limpiar_viejos(registro, ventana_seg):
        # Evita que el diccionario crezca sin límite con IPs que ya no vuelven.
        ahora = time.time()
        vencidas = [ip for ip, reg in registro.items() if ahora - reg["desde"] > ventana_seg * 2]
        for ip in vencidas:
            del registro[ip]

    @app.before_request
    def limitar():
        from flask import request
        if not request.path.startswith("/api/"):
            return None

        ip = request.remote_addr or "desconocida"

        if request.path in ("/api/auth/login", "/api/auth/registro") and request.method == "POST":
            if len(intentos_auth) > 5000:
                _limpiar_viejos(intentos_auth, 900)
            if _excedido(intentos_auth, ip, 900, 10):
                return jsonify(error="Demasiados intentos. Espera 15 minutos."), 429

        if len(peticiones_api) > 5000:
            _limpiar_viejos(peticiones_api, 300)
        if _excedido(peticiones_api, ip, 300, 300):
            return jsonify(error="Demasiadas peticiones. Espera unos minutos."), 429

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
