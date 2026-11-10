# -*- coding: utf-8 -*-
"""
Habilidades de apoyo del bot (2026-11-10, tras el drop del Challenger).

  - PC despierta durante un drop (Windows no se suspende ni apaga la pantalla).
  - Chequeo del sistema: internet hacia Mattel y reloj de la PC contra el de
    Mattel (un reloj atrasado dispara tarde).
  - Publicaciones pendientes de aprobar para Facebook (boton en Telegram).
  - Reportes de cada drop y de cada ensayo (tabla drop_reportes).
  - Respaldo diario de las cuentas (sus .env y cookies de sesion).
  - Señales para Nexus (archivos de latido).

Nada de esto compra ni publica solo: lo que sale de la PC lo aprueba Gonza.
"""

import json
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DIR, "bot.db")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


# --- 1. PC despierta --------------------------------------------------------
_DESPIERTA = {"hasta": 0.0, "hilo": None}
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _marcar_actividad():
    """Le dice a Windows que hay actividad (sin ES_CONTINUOUS: se renueva
    cada 30 s mientras dure el drop y luego se suelta solo)."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(
            ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED))
    except Exception:
        return False


def _bucle_despierta():
    while True:
        if time.time() < _DESPIERTA["hasta"]:
            _marcar_actividad()
        time.sleep(30)


def mantener_despierta(minutos):
    """Que la PC no se suspenda ni apague la pantalla en los proximos
    `minutos` (se puede llamar varias veces: gana el plazo mas largo)."""
    _DESPIERTA["hasta"] = max(_DESPIERTA["hasta"], time.time() + minutos * 60)
    if _DESPIERTA["hilo"] is None or not _DESPIERTA["hilo"].is_alive():
        _DESPIERTA["hilo"] = threading.Thread(target=_bucle_despierta, name="pc_despierta", daemon=True)
        _DESPIERTA["hilo"].start()
    _marcar_actividad()
    return _DESPIERTA["hasta"]


def despierta_activa():
    return time.time() < _DESPIERTA["hasta"]


# --- 2 y 3. Internet y reloj -------------------------------------------------
def chequeo_sistema(pedir=None):
    """[(ok, texto)] de internet hacia Mattel y del reloj de la PC."""
    import requests
    pedir = pedir or (lambda: requests.head("https://creations.mattel.com/en-mx",
                                            headers={"User-Agent": UA}, timeout=10, allow_redirects=True))
    puntos = []
    try:
        t0 = time.monotonic()
        r = pedir()
        ms = (time.monotonic() - t0) * 1000
        puntos.append((True if ms < 1500 else None,
                       "internet: Mattel responde en %d ms%s" % (ms, "" if ms < 1500 else
                                                                 " (lento: considera los datos del celular)")))
        fecha = r.headers.get("Date") if r is not None else None
        if fecha:
            desfase = (datetime.now(timezone.utc) - parsedate_to_datetime(fecha)).total_seconds()
            ok = True if abs(desfase) <= 5 else (None if abs(desfase) <= 30 else False)
            puntos.append((ok, "reloj de la PC: %s%.0f s contra Mattel%s" % (
                "+" if desfase >= 0 else "", desfase,
                "" if ok else " (sincroniza la hora de Windows: Configuración > Hora > Sincronizar ahora)")))
    except Exception as e:
        puntos.append((False, "internet: Mattel no responde (%s). Revisa tu conexión" % type(e).__name__))
    return puntos


# --- Tablas: publicaciones y reportes ---------------------------------------
def crear_tablas(db=DB):
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS publicaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        articulo_id TEXT, url TEXT, texto TEXT NOT NULL, imagen TEXT,
        estado TEXT NOT NULL DEFAULT 'pendiente', resultado TEXT,
        creado TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS drop_reportes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL, url TEXT, resumen TEXT NOT NULL, exito INTEGER NOT NULL DEFAULT 0,
        creado TEXT NOT NULL)""")
    conn.commit()
    conn.close()


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def guardar_publicacion(texto, articulo_id=None, url=None, imagen=None, db=DB):
    crear_tablas(db)
    conn = sqlite3.connect(db)
    cur = conn.execute("INSERT INTO publicaciones (articulo_id, url, texto, imagen, creado) VALUES (?,?,?,?,?)",
                       (articulo_id, url, texto, imagen, _ahora()))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def obtener_publicacion(pub_id, db=DB):
    crear_tablas(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM publicaciones WHERE id = ?", (pub_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def marcar_publicacion(pub_id, estado, resultado=None, db=DB):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE publicaciones SET estado = ?, resultado = ? WHERE id = ?", (estado, resultado, pub_id))
    conn.commit()
    conn.close()


def guardar_reporte(tipo, resumen, url=None, exito=False, db=DB):
    crear_tablas(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO drop_reportes (tipo, url, resumen, exito, creado) VALUES (?,?,?,?,?)",
                 (tipo, url, resumen, 1 if exito else 0, _ahora()))
    conn.commit()
    conn.close()


def ultimo_reporte(tipo=None, db=DB):
    crear_tablas(db)
    conn = sqlite3.connect(db)
    if tipo:
        r = conn.execute("SELECT resumen, creado FROM drop_reportes WHERE tipo = ? ORDER BY id DESC LIMIT 1",
                         (tipo,)).fetchone()
    else:
        r = conn.execute("SELECT resumen, creado FROM drop_reportes ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return r


def contar_reportes(dias=90, db=DB):
    """(drops, con_exito) de los ultimos `dias`, para comparar."""
    crear_tablas(db)
    conn = sqlite3.connect(db)
    r = conn.execute("SELECT COUNT(*), COALESCE(SUM(exito),0) FROM drop_reportes WHERE tipo = 'drop' "
                     "AND creado >= datetime('now', ?)", ("-%d days" % dias,)).fetchone()
    conn.close()
    return int(r[0] or 0), int(r[1] or 0)


# --- Reporte de un drop ------------------------------------------------------
def resumen_drop(nombre, por_cuenta, dias_historial=90, db=DB):
    """Texto del reporte de un drop. `por_cuenta`: {cuenta: {"intentos",
    "captchas", "resultado", "segundos"}}."""
    lineas = ["📊 Reporte del drop: %s" % nombre]
    exito = False
    for cuenta, d in por_cuenta.items():
        r = d.get("resultado") or ""
        icono = "🎉" if "🎉" in r else ("🛒" if "✅" in r else "❌")
        exito = exito or "🎉" in r
        reloj = ""
        for linea in r.splitlines():
            if linea.startswith("⏱"):
                reloj = " · " + linea
        lineas.append("%s %s: %d intento(s), %d captcha(s)%s" % (
            icono, cuenta, d.get("intentos", 0), d.get("captchas", 0), reloj))
        if "🎉" not in r:
            lineas.append("   └ " + r.splitlines()[0][:160] if r else "   └ sin resultado")
    drops, buenos = contar_reportes(dias_historial, db)
    if drops:
        lineas.append("📈 Últimos %d días: %d de %d drops con compra" % (dias_historial, buenos, drops))
    return "\n".join(lineas), exito


# --- 18. Respaldo de cuentas --------------------------------------------------
CONSERVAR_RESPALDOS = 14


def respaldar_cuentas(destino=None, dir_bot=DIR):
    """Zip diario con los .env de las cuentas y sus cookies de sesion (sin el
    resto del perfil de Chromium, que pesa cientos de MB). Queda en la PC,
    junto a los respaldos de la app. Devuelve la ruta o None."""
    destino = destino or os.path.join(os.path.dirname(dir_bot), "datos", "respaldos", "bot")
    os.makedirs(destino, exist_ok=True)
    archivo = os.path.join(destino, "cuentas-%s.zip" % datetime.now().strftime("%Y-%m-%d"))
    incluir = []
    for rel in (".env", os.path.join("perfil_mattel", "cookies_sesion.json")):
        if os.path.exists(os.path.join(dir_bot, rel)):
            incluir.append(rel)
    dir_cuentas = os.path.join(dir_bot, "cuentas")
    if os.path.isdir(dir_cuentas):
        for nombre in os.listdir(dir_cuentas):
            for rel in (os.path.join("cuentas", nombre, ".env"),
                        os.path.join("cuentas", nombre, "perfil_mattel", "cookies_sesion.json")):
                if os.path.exists(os.path.join(dir_bot, rel)):
                    incluir.append(rel)
    if not incluir:
        return None
    tmp = archivo + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in incluir:
            z.write(os.path.join(dir_bot, rel), rel)
    os.replace(tmp, archivo)
    viejos = sorted(f for f in os.listdir(destino) if f.startswith("cuentas-") and f.endswith(".zip"))
    for f in viejos[:-CONSERVAR_RESPALDOS]:
        try:
            os.remove(os.path.join(destino, f))
        except OSError:
            pass
    return archivo


# --- 19. Señales para Nexus ----------------------------------------------------
def tocar_senal(nombre, detalle="", dir_bot=DIR):
    """Escribe un archivo de latido que Nexus vigila (nexus-latidos.json)."""
    ruta = os.path.join(dir_bot, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("%s %s\n" % (_ahora(), detalle))
    return ruta


def resumen_json(cuentas_mod, drops_mod, db=DB):
    """Estado del bot para paneles (Nexus, /bot): sin secretos."""
    salida = {"cuentas": [], "drops": [], "pc_despierta": despierta_activa()}
    for c in cuentas_mod.listar(solo_activas=False):
        ok, motivo = c.lista_para_comprar()
        d = c.datos()
        salida["cuentas"].append({"nombre": c.nombre, "lista": ok, "motivo": motivo,
                                  "cvv": bool(d["tarjeta1"]["cvv"]),
                                  "sesion_guardada": os.path.exists(c.cookies)})
    for d in drops_mod.proximos(db):
        salida["drops"].append({"id": d["id"], "titulo": d["titulo"], "url": d["url"],
                                "cuando": d["cuando"].isoformat(), "estado": d["estado"],
                                "cantidad": d["cantidad"], "cuentas": d.get("cuentas") or ""})
    r = ultimo_reporte(db=db)
    salida["ultimo_reporte"] = {"resumen": r[0], "creado": r[1]} if r else None
    return salida


def copiar_si_existe(origen, destino):
    if os.path.exists(origen):
        shutil.copy2(origen, destino)
        return True
    return False


def a_json(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)
