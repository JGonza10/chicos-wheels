"""
Bot Hot Wheels dentro de Chicos Wheels (solo en esta PC).

El panel del bot (hotwheels/dashboard_bot.py) se monta tal cual bajo /bot en el
mismo proceso, y aquí arrancan el monitor de Mattel, el scheduler, la cola de
compras y los botones de Telegram. Sin HOTWHEELS_ACTIVO=1 (Railway) nada de
esto existe: /bot no se monta y el enlace del menú no aparece.

Acceso: solo las cuentas de BOT_EMAILS. El SPA pide POST /api/bot/entrar con
su token y recibe una cookie HttpOnly limitada a /bot; el panel la exige en
cada petición.
"""
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from flask import Blueprint, current_app, g, jsonify, make_response, redirect, request

from .auth import SECRETO, firmar, requiere_sesion
from .db import conectar, uno
from .util import ErrorApp

CARPETA = Path(__file__).resolve().parent.parent / "hotwheels"
COOKIE = "bot_sesion"
HORAS_SESION = 12

bp = Blueprint("bot_acceso", __name__)


def activo() -> bool:
    return os.environ.get("HOTWHEELS_ACTIVO") == "1"


def _duenos() -> set:
    lista = os.environ.get("BOT_EMAILS", "juangonza@live.com.mx")
    return {e.strip().lower() for e in lista.split(",") if e.strip()}


def _email_de_sesion() -> str:
    fila = uno("SELECT email FROM usuarios WHERE id=?", (g.usuario_id,))
    return ((fila or {}).get("email") or "").lower()


@bp.get("/disponible")
@requiere_sesion
def disponible():
    montado = bool(current_app.config.get("BOT_MONTADO"))
    return jsonify(disponible=montado and _email_de_sesion() in _duenos())


@bp.post("/entrar")
@requiere_sesion
def entrar():
    if not current_app.config.get("BOT_MONTADO"):
        raise ErrorApp("Esa ruta no existe", 404)
    email = _email_de_sesion()
    if email not in _duenos():
        raise ErrorApp("Esta cuenta no tiene acceso al bot", 403)
    carga = {"uid": g.usuario_id, "email": email, "aud": "bot",
             "exp": datetime.now(timezone.utc) + timedelta(hours=HORAS_SESION)}
    resp = make_response(jsonify(ok=True, url="/bot/"))
    resp.set_cookie(COOKIE, jwt.encode(carga, SECRETO, algorithm="HS256"),
                    max_age=HORAS_SESION * 3600, path="/bot", httponly=True,
                    samesite="Strict", secure=request.is_secure)
    return resp


def _proteger(panel):
    """Cada petición al panel exige la cookie de /api/bot/entrar."""
    @panel.before_request
    def _exigir_sesion():
        try:
            carga = jwt.decode(request.cookies.get(COOKIE, ""), SECRETO,
                               algorithms=["HS256"], audience="bot")
            if (carga.get("email") or "").lower() in _duenos():
                return None
        except jwt.PyJWTError:
            pass
        if request.method == "GET" and request.path == "/":
            return redirect("/#bot")  # Chicos Wheels renueva la cookie y regresa aquí
        return jsonify(ok=False, error="Entra al bot desde el menú de Chicos Wheels"), 401

    @panel.after_request
    def _cabeceras(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Cache-Control"] = "no-store"
        return resp


class _Respuesta:
    """Lo que el puente del bot espera de una respuesta de requests."""

    def __init__(self, r):
        self._r = r
        self.status_code = r.status_code
        self.content = r.data
        self.ok = r.status_code < 400

    def json(self):
        return self._r.get_json()

    def raise_for_status(self):
        if not self.ok:
            error = (self._r.get_json(silent=True) or {}).get("error", "")
            raise RuntimeError(f"Chicos Wheels respondió {self.status_code}: {error}")


def _transporte(app):
    """Llamadas del bot a la API, atendidas en memoria con la cuenta COLLECTHUB_EMAIL."""
    cuenta = {}

    def llamar(metodo, ruta, cuerpo=None):
        if not cuenta:
            email = os.environ.get("COLLECTHUB_EMAIL", "").strip().lower()
            con = conectar()
            try:
                fila = con.execute("SELECT id, email FROM usuarios WHERE lower(email)=?",
                                   (email,)).fetchone()
            finally:
                con.close()
            if not fila:
                raise RuntimeError(f"no existe la cuenta {email or '(sin COLLECTHUB_EMAIL)'} en Chicos Wheels")
            cuenta["token"] = firmar({"id": fila["id"], "email": fila["email"]})
        r = app.test_client().open(ruta, method=metodo, json=cuerpo,
                                   headers={"Authorization": "Bearer " + cuenta["token"]})
        return _Respuesta(r)

    return llamar


def montar(app) -> bool:
    """Monta el panel en /bot. Devuelve False si el bot no está activo."""
    if not activo():
        return False
    if str(CARPETA) not in sys.path:
        sys.path.insert(0, str(CARPETA))
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    import collecthub_bridge
    import dashboard_bot

    collecthub_bridge.EN_PROCESO = _transporte(app)
    _proteger(dashboard_bot.app)
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/bot": dashboard_bot.app})
    app.config["BOT_MONTADO"] = True
    return True


def iniciar_servicios() -> bool:
    """Scheduler, cola de compras, Telegram y el monitor de Mattel (hilo aparte).

    El candado del monitor (monitor.lock) cubre todo: si otra copia de la app ya
    los corre (Nexus, el Agente Testing, otro PORT), esta solo sirve el panel;
    si no, habría avisos, compras programadas y botones de Telegram duplicados.
    """
    import dashboard_bot
    import monitor

    if not monitor._tomar_instancia_unica():
        print("  Bot Hot Wheels: otra copia ya corre el monitor; aquí solo el panel.")
        return False
    monitor._tomar_instancia_unica = lambda: True   # este proceso ya tiene el candado
    dashboard_bot.iniciar_servicios()
    threading.Thread(target=monitor.main, name="monitor_hw", daemon=True).start()
    return True
