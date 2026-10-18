"""
Bot Hot Wheels dentro de Chicos Wheels (solo en esta PC).

Excepción: el MONITOR (no el bot de compra) también puede correr en Railway
como relevo, con HOTWHEELS_MONITOR_NUBE=1. Ahí vigila siempre, pero se queda
callado mientras la PC le mande su latido (POST /api/bot/latido-pc tras cada
barrido bueno); si la PC deja de mandarlo, Railway avisa por Telegram.

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
_NUBE = None              # módulo monitor cuando corre como relevo en Railway
_AVISO_RELEVO = {"ts": None, "fallo": False}   # PC: estado del último latido
HORAS_AVISO_RELEVO_CIEGO = 6
MINUTOS_RELEVO_CIEGO = 30

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


@bp.post("/latido-pc")
@requiere_sesion
def latido_pc():
    """La PC avisa que sigue vigilando: el monitor de Railway se queda callado."""
    if _email_de_sesion() not in _duenos():
        raise ErrorApp("Esta cuenta no tiene acceso al bot", 403)
    if _NUBE is None:
        raise ErrorApp("El monitor de relevo no está activo aquí", 404)
    return jsonify(ok=True, **_NUBE.registrar_latido_pc())


def iniciar_monitor_nube() -> bool:
    """Railway: arranca solo el monitor, en modo relevo (sin panel ni compras).

    Necesita HOTWHEELS_MONITOR_NUBE=1, TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID y,
    para que sus datos sobrevivan a cada redespliegue, HOTWHEELS_DATOS en el
    volumen (/app/datos/hotwheels). En la PC (HOTWHEELS_ACTIVO=1) no hace nada:
    ahí corre el monitor completo con iniciar_servicios().
    """
    global _NUBE
    if _NUBE is not None:
        return True
    if os.environ.get("HOTWHEELS_MONITOR_NUBE") != "1" or activo():
        return False
    if str(CARPETA) not in sys.path:
        sys.path.insert(0, str(CARPETA))
    import monitor

    if not monitor._tomar_instancia_unica():
        print("  Monitor de relevo: otra copia ya lo corre.")
        return False
    monitor._tomar_instancia_unica = lambda: True
    monitor.activar_relevo()
    threading.Thread(target=monitor.main, name="monitor_relevo", daemon=True).start()
    _NUBE = monitor
    print("  Monitor de relevo activo: vigila Mattel y avisa solo si la PC calla.")
    return True


def _enviar_latido(monitor):
    """PC: le dice a Railway que sigue vigilando. Va en un hilo para no frenar
    al monitor; si Railway no contesta, se avisa una sola vez en la consola."""
    import collecthub_bridge

    def enviar():
        try:
            r = collecthub_bridge.pedir("POST", "/api/bot/latido-pc", timeout=8)
            if r.status_code != 200:
                raise RuntimeError(f"Railway respondió {r.status_code}")
            datos = r.json() or {}
            _AVISO_RELEVO["fallo"] = False
        except Exception as e:
            if not _AVISO_RELEVO["fallo"]:
                print(f"  [relevo] Railway no recibió el latido ({e}); se reintenta en el próximo barrido")
            _AVISO_RELEVO["fallo"] = True
            return
        # El relevo solo sirve si Railway de verdad ve la tienda.
        ciego = (datos.get("revisiones", 0) > 0
                 and (datos.get("minutos_sin_ver") or 0) > MINUTOS_RELEVO_CIEGO)
        ultimo = _AVISO_RELEVO["ts"]
        if ciego and (ultimo is None or datetime.now(timezone.utc) - ultimo
                      > timedelta(hours=HORAS_AVISO_RELEVO_CIEGO)):
            _AVISO_RELEVO["ts"] = datetime.now(timezone.utc)
            monitor.enviar_telegram_texto(
                "⚠️ <b>EL RELEVO EN RAILWAY ESTÁ CIEGO</b>\n\n"
                f"Lleva {int(datos['minutos_sin_ver'])} min sin poder leer Mattel. "
                "La PC sigue vigilando bien, pero si se apaga, Railway no vería nada. "
                "Puede ser un bloqueo a la IP de Railway: revisa sus logs.")

    threading.Thread(target=enviar, name="latido_railway", daemon=True).start()


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


def destino_local() -> bool:
    """True si las compras van a esta misma app (en memoria); False si COLLECTHUB_URL
    apunta a otra (Railway, desde 2026-10-18: ahí vive el inventario real)."""
    url = os.environ.get("COLLECTHUB_URL", "").strip().lower()
    return not url or "://localhost" in url or "://127.0.0.1" in url


def montar(app) -> bool:
    """Monta el panel en /bot. Devuelve False si el bot no está activo."""
    if not activo():
        return False
    if str(CARPETA) not in sys.path:
        sys.path.insert(0, str(CARPETA))
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    import dashboard_bot      # primero: su bot_logic carga hotwheels/.env
    import collecthub_bridge  # lee COLLECTHUB_URL/EMAIL/PASSWORD al importarse

    if destino_local():
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
    if not destino_local():
        # El inventario vive en Railway: ahí también corre el monitor de relevo.
        monitor.AL_BARRIDO_OK = lambda: _enviar_latido(monitor)
    dashboard_bot.iniciar_servicios()
    threading.Thread(target=monitor.main, name="monitor_hw", daemon=True).start()
    return True
