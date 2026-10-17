# -*- coding: utf-8 -*-
"""Pruebas de las 5 integraciones del 2026-09-15:

  1. Mercado Libre como segunda tienda (con token; sin token se apaga solo)
  2. Gráfica de precio por producto (/api/precios)
  3. (Reporte de aciertos: retirado al fusionar; ahora sale de la tabla hallazgos)
  4. Ajustes editables desde el tablero (lista blanca, sin secretos)
  5. Aviso cuando una colección deja de responder

Todo en carpeta temporal y sin red real: las llamadas a Mercado Libre y al
bot de compra se sustituyen por dobles. Ejecutar:  python prueba_integraciones.py
"""

import io
import json
import os
import shutil
import sys
import tempfile

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

import hw_extras as EX  # noqa: E402

fallos = []


def check(nombre, condicion, detalle=""):
    if condicion:
        print("  OK    %s" % nombre)
    else:
        print("  FALLO %s  %s" % (nombre, detalle))
        fallos.append(nombre)


TMP = tempfile.mkdtemp(prefix="prueba_integr_")

# ============================================================
print("\n--- 4. Ajustes: lista blanca y validación ---")
# ============================================================
CFG = os.path.join(TMP, "config.env")
io.open(CFG, "w", encoding="utf-8").write(
    u"# Comentario que NO se debe perder\n"
    u"TELEGRAM_BOT_TOKEN=secreto-de-telegram\n"
    u"SEGUNDOS_CICLO_RAPIDO=15\n"
    u"ENVIO_MXN_ESTIMADO=250\n")

ajustes = EX.leer_ajustes(CFG)
check("lee los ajustes con su valor", any(a["clave"] == "SEGUNDOS_CICLO_RAPIDO" and a["valor"] == "15"
                                          for a in ajustes), ajustes)
check("el token de Telegram NO es ajustable",
      all(a["clave"] != "TELEGRAM_BOT_TOKEN" for a in ajustes))

g, r = EX.guardar_ajustes(CFG, {"SEGUNDOS_CICLO_RAPIDO": "25"})
check("guarda un valor válido", g.get("SEGUNDOS_CICLO_RAPIDO") == "25", (g, r))
texto = io.open(CFG, encoding="utf-8").read()
check("conserva el comentario", "# Comentario que NO se debe perder" in texto)
check("conserva el secreto intacto", "TELEGRAM_BOT_TOKEN=secreto-de-telegram" in texto)
check("escribió el valor nuevo", "SEGUNDOS_CICLO_RAPIDO=25" in texto)

g, r = EX.guardar_ajustes(CFG, {"TELEGRAM_BOT_TOKEN": "intento-de-robo"})
check("rechaza claves fuera de la lista blanca", not g and "TELEGRAM_BOT_TOKEN" in r, (g, r))
check("y el secreto sigue igual", "TELEGRAM_BOT_TOKEN=secreto-de-telegram"
      in io.open(CFG, encoding="utf-8").read())

g, r = EX.guardar_ajustes(CFG, {"SEGUNDOS_CICLO_RAPIDO": "99999"})
check("rechaza fuera de rango", not g and "rango" in r["SEGUNDOS_CICLO_RAPIDO"], (g, r))
g, r = EX.guardar_ajustes(CFG, {"SEGUNDOS_CICLO_RAPIDO": "hola"})
check("rechaza lo que no es número", not g and "número" in r["SEGUNDOS_CICLO_RAPIDO"], (g, r))

g, r = EX.guardar_ajustes(CFG, {"MINUTOS_MERCADOLIBRE": "20"})
check("agrega una clave que no existía", g and "MINUTOS_MERCADOLIBRE=20"
      in io.open(CFG, encoding="utf-8").read())
check("el valor nuevo se relee", EX.cargar_config(CFG)["MINUTOS_MERCADOLIBRE"] == "20")

# ============================================================
print("\n--- 1. Mercado Libre: sin token se apaga solo, con token funciona ---")
# ============================================================
ML = os.path.join(TMP, "busquedas_ml.json")
ok, e = EX.agregar_busqueda_ml(ML, "rlc datsun 510", precio_max="900")
check("agrega búsqueda", ok and e["termino"] == "rlc datsun 510", e)
check("guarda el tope como número", e["precio_max"] == 900.0, e)
check("no duplica (normalizado)", EX.agregar_busqueda_ml(ML, "RLC  Datsún 510")[0] is False)
ok, e2 = EX.agregar_busqueda_ml(ML, "rlc skyline")
check("tope vacío queda en None", e2["precio_max"] is None, e2)
check("lista trae 2", len(EX.listar_busquedas_ml(ML)) == 2)
check("quitar funciona", EX.quitar_busqueda_ml(ML, "rlc skyline") is True)

listados, motivo = EX.buscar_listados_ml("lo que sea", token="")
check("sin token no consulta", listados == [] and "MERCADOLIBRE_ACCESS_TOKEN" in motivo, motivo)
precio, n = EX.buscar_mercadolibre("algo", token="")
check("los precios de ML también se apagan", (precio, n) == (None, 0))
check("y dejan dicho por qué (antes fallaba callado)",
      EX.MOTIVO_ML_PRECIOS and "TOKEN" in EX.MOTIVO_ML_PRECIOS, EX.MOTIVO_ML_PRECIOS)


class _RespFalsa(object):
    def __init__(self, datos, status=200):
        self._datos = datos
        self.status_code = status

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("http %d" % self.status_code)


class _RequestsFalso(object):
    def __init__(self, datos=None, status=200):
        self.datos = datos or {}
        self.status = status
        self.ultima = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.ultima = {"url": url, "params": params, "headers": headers}
        return _RespFalsa(self.datos, self.status)


ITEMS = {"results": [
    {"id": "MLM111", "title": "Hot Wheels RLC Datsun 510", "price": 850,
     "permalink": "https://articulo.mercadolibre.com.mx/MLM111", "condition": "new",
     "thumbnail": "http://img/1.jpg", "shipping": {"free_shipping": True}},
    {"id": "MLM222", "title": "Hot Wheels RLC Datsun 510 chase", "price": 2400,
     "permalink": "https://articulo.mercadolibre.com.mx/MLM222", "condition": "new",
     "thumbnail": "https://img/2.jpg", "shipping": {"free_shipping": False}},
    {"id": "MLM333", "title": "Sin precio", "price": None,
     "permalink": "https://articulo.mercadolibre.com.mx/MLM333"},
]}
falso = _RequestsFalso(ITEMS)
EX.requests = falso
listados, motivo = EX.buscar_listados_ml("rlc datsun 510", token="token-de-prueba")
check("con token devuelve listados", motivo is None and len(listados) == 2, (motivo, listados))
check("manda el token en la cabecera",
      falso.ultima["headers"]["Authorization"] == "Bearer token-de-prueba", falso.ultima["headers"])
check("descarta publicaciones sin precio", all(l["precio_mxn"] > 0 for l in listados))
check("arregla imágenes http", listados[0]["imagen"].startswith("https://"), listados[0])
check("marca envío gratis", listados[0]["envio_gratis"] is True)

falso403 = _RequestsFalso({}, status=403)
EX.requests = falso403
listados, motivo = EX.buscar_listados_ml("x", token="token-vencido")
check("token rechazado se explica", listados == [] and "rechazó el token" in motivo, motivo)
check("el motivo NUNCA incluye el token", "token-vencido" not in (motivo or ""), motivo)

# ============================================================
print("\n--- 5. Colección que deja de responder ---")
# ============================================================
os.environ["HW_PRUEBA"] = "1"
import monitor as M  # noqa: E402

avisos = []
M.enviar_telegram_texto = lambda texto: avisos.append(texto)
M.FALLOS_ALERTA_COLECCION = 3
M._TS_ALERTA_COLECCION.clear()
estado = {}
for i in range(2):
    M.registrar_salud_coleccion(estado, "hot-wheels-premium", False, 0)
check("aún no avisa a los 2 fallos", avisos == [], avisos)
M.registrar_salud_coleccion(estado, "hot-wheels-premium", False, 0)
check("avisa al tercer fallo seguido", len(avisos) == 1, avisos)
check("el aviso dice cuál colección", "hot-wheels-premium" in avisos[0], avisos[0])
M.registrar_salud_coleccion(estado, "hot-wheels-premium", False, 0)
check("no repite el aviso dentro de la hora", len(avisos) == 1, avisos)
M.registrar_salud_coleccion(estado, "hot-wheels-premium", True, 42)
check("al responder se reinicia el contador",
      estado["salud_colecciones"]["hot-wheels-premium"]["fallos"] == 0)
check("y guarda cuántos productos trajo",
      estado["salud_colecciones"]["hot-wheels-premium"]["productos"] == 42)

# Una colección vacía NO es una colección caída.
M.hacer_request = lambda url, params=None, intentos=3: {"products": []}
productos, respondio = M.obtener_productos_coleccion("vacia")
check("colección vacía cuenta como que respondió", productos == [] and respondio is True)
M.hacer_request = lambda url, params=None, intentos=3: None
productos, respondio = M.obtener_productos_coleccion("caida")
check("colección caída cuenta como fallo", productos == [] and respondio is False)

# ============================================================
print("\n--- 1b. El ciclo de Mercado Libre del monitor ---")
# ============================================================
M.EX = EX
M.ML_TOKEN = "token-de-prueba"
M.ARCHIVO_BUSQUEDAS_ML = ML
M.HISTORIAL = None
EX.requests = _RequestsFalso(ITEMS)
mensajes = []
M.enviar_telegram = lambda texto, foto=None, link=None, compra=None: mensajes.append(texto)
M.NOTIFICACIONES_ENVIADAS.clear()

estado_ml = {}
n = M.revisar_mercadolibre(estado_ml)
check("la primera pasada NO avisa (calentamiento)", n == 0 and mensajes == [], (n, mensajes))
check("pero sí memoriza lo que ya estaba", len(estado_ml["ml_vistos"]["rlc datsun 510"]) == 2)

ITEMS2 = json.loads(json.dumps(ITEMS))
ITEMS2["results"].append({"id": "MLM444", "title": "Hot Wheels RLC Datsun 510 nuevo hallazgo",
                          "price": 700, "permalink": "https://articulo.mercadolibre.com.mx/MLM444",
                          "condition": "new", "thumbnail": "https://img/4.jpg",
                          "shipping": {"free_shipping": False}})
EX.requests = _RequestsFalso(ITEMS2)
n = M.revisar_mercadolibre(estado_ml)
check("avisa de la publicación nueva", n == 1, (n, mensajes))
check("el aviso dice que es nuevo", "NUEVO EN MERCADO LIBRE" in mensajes[-1], mensajes[-1])
check("queda en las alertas del tablero",
      estado_ml["alertas"][0]["fuente"] == "mercadolibre", estado_ml.get("alertas"))

# El de 2400 está arriba del tope de 900: nunca debe avisar.
check("respeta el precio máximo", all("2,400" not in m and "chase" not in m for m in mensajes), mensajes)

ITEMS3 = json.loads(json.dumps(ITEMS2))
ITEMS3["results"][0]["price"] = 600      # el de 850 baja a 600
EX.requests = _RequestsFalso(ITEMS3)
n = M.revisar_mercadolibre(estado_ml)
check("avisa de la bajada de precio", n == 1 and "BAJO DE PRECIO" in mensajes[-1], mensajes[-1])
check("dice el precio anterior", "850" in mensajes[-1], mensajes[-1])

EX.requests = _RequestsFalso(ITEMS3)
n = M.revisar_mercadolibre(estado_ml)
check("no repite lo ya avisado", n == 0, n)

M.ML_TOKEN = ""
check("sin token el ciclo ni se intenta", M.revisar_mercadolibre({}) == 0)

# ============================================================
print("\n--- 2 y 3. Rutas del tablero: precios, aciertos, ML y ajustes ---")
# ============================================================
APP = os.path.join(TMP, "app")
os.makedirs(APP)
for archivo in ("monitor_admin.py", "hw_extras.py"):
    shutil.copy(os.path.join(DIR, archivo), APP)
io.open(os.path.join(APP, "config.env"), "w", encoding="utf-8").write(
    u"PUERTO_DASHBOARD=5998\nTELEGRAM_BOT_TOKEN=t\nTELEGRAM_CHAT_ID=1\n"
    u"BOT_COMPRA_URL=http://127.0.0.1:9\nBOT_COMPRA_BRIDGE_KEY=llave\n")
io.open(os.path.join(APP, "estado.json"), "w", encoding="utf-8").write(json.dumps({
    "ultima_revision": "2030-01-01T00:00:00+00:00", "revisiones": 10,
    "stats": {"total": 50}, "stats_hoy": {"nuevos": 1},
    "alertas": [], "vigilancia": {},
    "salud_colecciones": {"hot-wheels-premium": {"fallos": 4, "ultimo_ok": None, "productos": 0}},
}))

# Historial de ejemplo, con dos oportunidades reales.
import sqlite3  # noqa: E402
conn = sqlite3.connect(os.path.join(APP, "historial.db"))
conn.execute("""CREATE TABLE eventos (id INTEGER PRIMARY KEY, ts_utc TEXT, fecha_mx TEXT,
                hora_mx INT, dia_semana INT, tipo TEXT, producto_id TEXT, handle TEXT,
                titulo TEXT, precio_usd REAL, precio_mxn REAL, impacto TEXT,
                minutos_agotamiento REAL, deseado INT)""")
from datetime import datetime, timezone, timedelta  # noqa: E402
ahora = datetime.now(timezone.utc)
filas = [
    (( ahora - timedelta(days=2)).isoformat(), "nuevo", "rlc-datsun-510", "RLC Datsun 510", 900.0, "Alto impacto", 1),
    (( ahora - timedelta(days=1)).isoformat(), "restock", "rlc-skyline", "RLC Skyline", 1100.0, "Alto impacto", 0),
    (( ahora - timedelta(days=1)).isoformat(), "nuevo", "carro-comun", "Carro comun", 300.0, "Bajo impacto", 0),
]
for ts, tipo, handle, titulo, precio, impacto, deseado in filas:
    conn.execute("INSERT INTO eventos (ts_utc, tipo, handle, titulo, precio_mxn, impacto, deseado) "
                 "VALUES (?,?,?,?,?,?,?)", (ts, tipo, handle, titulo, precio, impacto, deseado))
# Dos precios del mismo auto, para la gráfica
for dias, precio in ((10, 950.0), (5, 900.0)):
    conn.execute("INSERT INTO eventos (ts_utc, tipo, handle, titulo, precio_mxn) VALUES (?,?,?,?,?)",
                 ((ahora - timedelta(days=dias)).isoformat(), "cambio_precio",
                  "rlc-datsun-510", "RLC Datsun 510", precio))
conn.commit()
conn.close()

sys.path.insert(0, APP)
for mod in ("monitor_admin", "hw_extras", "monitor"):
    sys.modules.pop(mod, None)
os.chdir(APP)
import monitor_admin as D  # noqa: E402
from flask import Flask  # noqa: E402

_app = Flask(__name__)
_app.register_blueprint(D.bp)
cliente = _app.test_client()

# --- 2. Gráfica de precios ---
r = cliente.get("/api/monitor/precios?titulo=RLC Datsun 510")
d = r.get_json()
check("/api/monitor/precios responde", r.status_code == 200 and d["ok"])
check("trae la serie de precios", len(d["precios"]) >= 3, d["precios"])
check("viene ordenada de vieja a nueva",
      [p["precio_mxn"] for p in d["precios"]] == sorted(
          [p["precio_mxn"] for p in d["precios"]], reverse=True), d["precios"])
check("sin título responde vacío, no truena", cliente.get("/api/monitor/precios").get_json()["precios"] == [])
check("título inventado no truena",
      cliente.get("/api/monitor/precios?titulo=no-existe").get_json()["precios"] == [])

# --- 4b. Ajustes por API ---
d = cliente.get("/api/monitor/ajustes").get_json()
check("/api/ajustes responde", d["ok"] and len(d["ajustes"]) >= 5)
d = cliente.post("/api/monitor/ajustes/guardar", json={"cambios": {"MINUTOS_MERCADOLIBRE": "15"}}).get_json()
check("guarda por API", d["ok"] and d["guardados"]["MINUTOS_MERCADOLIBRE"] == "15", d)
d = cliente.post("/api/monitor/ajustes/guardar", json={"cambios": {"DASHBOARD_PASSWORD": "hackeado"}}).get_json()
check("no deja tocar la contraseña del panel", d["ok"] is False and d["rechazados"], d)

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
