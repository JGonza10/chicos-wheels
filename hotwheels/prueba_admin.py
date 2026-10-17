# -*- coding: utf-8 -*-
"""Pruebas de lo que se administra desde el panel (colecciones y productos
sueltos) y de las rutas del Blueprint monitor_admin (/api/monitor/...).

Todo corre en una carpeta temporal: nunca toca el estado.json, el
historial.db ni las listas reales. Ejecutar:

    python prueba_admin.py
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


TMP = tempfile.mkdtemp(prefix="prueba_admin_")
COLS = os.path.join(TMP, "colecciones.json")
VIG = os.path.join(TMP, "vigilar.json")

print("\n--- 1. Handles: acepta URL pegada del navegador, no solo el handle ---")
check("handle suelto", EX._handle_limpio("hot-wheels-premium") == "hot-wheels-premium")
check("URL completa de coleccion",
      EX._handle_limpio("https://creations.mattel.com/collections/hot-wheels-premium")
      == "hot-wheels-premium")
check("URL con parametros y barra final",
      EX._handle_limpio("https://creations.mattel.com/products/rlc-datsun-510/?variant=42")
      == "rlc-datsun-510")
check("normaliza mayusculas y espacios", EX._handle_limpio("  Hot Wheels  Premium ")
      == "hot-wheels-premium")
check("vacio devuelve vacio", EX._handle_limpio("   ") == "")
check("None no truena", EX._handle_limpio(None) == "")

print("\n--- 2. Siembra: el cambio no altera lo que ya se vigilaba ---")
n = EX.sembrar_colecciones(COLS)
check("siembra las 5 de siempre", n == 5, n)
handles = EX.cargar_colecciones(COLS)
check("son exactamente las del codigo viejo",
      handles == ["hot-wheels-collectors", "hot-wheels-premium",
                  "hot-wheels-red-line-club", "hot-wheels-elite-64", "new-arrivals"], handles)
check("new-arrivals sigue siendo la rapida",
      EX.cargar_colecciones(COLS, solo_rapidas=True) == ["new-arrivals"])
check("no vuelve a sembrar si ya existe", EX.sembrar_colecciones(COLS) == 0)

print("\n--- 3. Agregar, apagar y quitar colecciones ---")
ok, entrada = EX.agregar_coleccion(COLS, "https://creations.mattel.com/collections/hot-wheels-boulevard")
check("agrega desde URL", ok and entrada["handle"] == "hot-wheels-boulevard", entrada)
check("nace activa", entrada["activa"] is True)
check("no duplica", EX.agregar_coleccion(COLS, "hot-wheels-boulevard")[0] is False)
check("rechaza vacio", EX.agregar_coleccion(COLS, "   ")[0] is False)

cambiada, e = EX.cambiar_coleccion(COLS, "hot-wheels-boulevard", activa=False)
check("apagar funciona", cambiada and e["activa"] is False, e)
check("apagada ya no la vigila el monitor",
      "hot-wheels-boulevard" not in EX.cargar_colecciones(COLS))
check("pero sigue en la lista del panel",
      any(c["handle"] == "hot-wheels-boulevard" for c in EX.listar_colecciones(COLS)))
check("cambiar una que no existe avisa",
      EX.cambiar_coleccion(COLS, "no-existe", activa=True)[0] is False)

EX.cambiar_coleccion(COLS, "hot-wheels-boulevard", activa=True, rapida=True)
check("puede moverse al ciclo rapido",
      "hot-wheels-boulevard" in EX.cargar_colecciones(COLS, solo_rapidas=True))
check("quitar funciona", EX.quitar_coleccion(COLS, "hot-wheels-boulevard") is True)
check("quitar dos veces devuelve False", EX.quitar_coleccion(COLS, "hot-wheels-boulevard") is False)
check("quedaron las 5 originales", len(EX.listar_colecciones(COLS)) == 5)

print("\n--- 4. Productos sueltos ---")
ok, v = EX.agregar_vigilado(VIG, "https://creations.mattel.com/products/rlc-skyline", nota="el que vi en X")
check("agrega desde URL", ok and v["handle"] == "rlc-skyline", v)
check("guarda la nota", v["nota"] == "el que vi en X")
check("no duplica", EX.agregar_vigilado(VIG, "rlc-skyline")[0] is False)
check("lista devuelve 1", len(EX.listar_vigilados(VIG)) == 1)
check("quitar funciona", EX.quitar_vigilado(VIG, "rlc-skyline") is True)
check("lista vacia", EX.listar_vigilados(VIG) == [])

print("\n--- 5. Archivos corruptos no tumban el tablero ---")
malo = os.path.join(TMP, "roto.json")
io.open(malo, "w", encoding="utf-8").write(u"{ esto no es json")
check("json roto devuelve lista vacia", EX.listar_colecciones(malo) == [])
io.open(malo, "w", encoding="utf-8").write(u'{"no": "es una lista"}')
check("json que no es lista devuelve vacio", EX.listar_colecciones(malo) == [])
check("vigilados con json roto tampoco truena", EX.listar_vigilados(malo) == [])

print("\n--- 6. El monitor sincroniza los vigilados a mano ---")
os.environ["HW_PRUEBA"] = "1"
import monitor as M  # noqa: E402

M.ARCHIVO_VIGILAR = VIG
EX.agregar_vigilado(VIG, "rlc-datsun-510")
EX.agregar_vigilado(VIG, "rlc-mustang")
estado = {"vigilancia": {"algo-viejo": {"motivo": "coming_soon", "desde": "2020-01-01T00:00:00+00:00"}}}
agregados = M.sincronizar_vigilados_manuales(estado)
check("agrega los dos", agregados == 2, agregados)
check("quedan marcados como manual",
      estado["vigilancia"]["rlc-datsun-510"]["motivo"] == "manual")
check("no toca los automaticos", "algo-viejo" in estado["vigilancia"])

EX.quitar_vigilado(VIG, "rlc-mustang")
M.sincronizar_vigilados_manuales(estado)
check("quitar del tablero lo saca de la vigilancia",
      "rlc-mustang" not in estado["vigilancia"])
check("el otro manual sigue", "rlc-datsun-510" in estado["vigilancia"])

M.limpiar_vigilancia(estado)
check("los manuales NO vencen", "rlc-datsun-510" in estado["vigilancia"])
check("los automaticos viejos si se limpian", "algo-viejo" not in estado["vigilancia"])

print("\n--- 7. Rutas del tablero ---")
# El dashboard lee su carpeta al importarse: se corre desde una copia limpia.
TMP_APP = os.path.join(TMP, "app")
os.makedirs(TMP_APP)
for archivo in ("monitor_admin.py", "hw_extras.py"):
    shutil.copy(os.path.join(DIR, archivo), TMP_APP)
io.open(os.path.join(TMP_APP, "config.env"), "w", encoding="utf-8").write(
    u"PUERTO_DASHBOARD=5999\nTELEGRAM_BOT_TOKEN=token-de-prueba\nTELEGRAM_CHAT_ID=1\n")
io.open(os.path.join(TMP_APP, "estado.json"), "w", encoding="utf-8").write(json.dumps({
    "ultima_revision": "2030-01-01T00:00:00+00:00",
    "revisiones": 42,
    "tipo_cambio": 19.5,
    "stats": {"total": 120, "disponibles": 3, "agotados": 100},
    "stats_hoy": {"fecha": "2026-09-15", "nuevos": 2, "restocks": 1},
    "alertas": [], "pocas_unidades": [],
    "vigilancia": {"algo": {"motivo": "coming_soon", "desde": "2026-09-15T00:00:00+00:00"}},
}))

sys.path.insert(0, TMP_APP)
for mod in ("monitor_admin", "hw_extras", "monitor"):
    sys.modules.pop(mod, None)
os.chdir(TMP_APP)
import monitor_admin as D  # noqa: E402
from flask import Flask  # noqa: E402

_app = Flask(__name__)
_app.register_blueprint(D.bp)
cliente = _app.test_client()

r = cliente.get("/api/monitor/colecciones")
d = r.get_json()
check("GET /api/colecciones responde", r.status_code == 200 and d["ok"], d)
check("sembro solo al abrir el tablero", len(d["entradas"]) == 5, d)

r = cliente.post("/api/monitor/colecciones/agregar", json={"handle": "hot-wheels-boulevard"})
check("agregar por API", r.status_code == 200 and r.get_json()["ok"])
check("repetida devuelve 409",
      cliente.post("/api/monitor/colecciones/agregar", json={"handle": "hot-wheels-boulevard"}).status_code == 409)
check("handle vacio devuelve 409",
      cliente.post("/api/monitor/colecciones/agregar", json={"handle": ""}).status_code == 409)
r = cliente.post("/api/monitor/colecciones/cambiar", json={"handle": "hot-wheels-boulevard", "activa": False})
check("cambiar por API", r.status_code == 200 and r.get_json()["entrada"]["activa"] is False)
check("cambiar inexistente da 404",
      cliente.post("/api/monitor/colecciones/cambiar", json={"handle": "nada"}).status_code == 404)
check("quitar por API",
      cliente.post("/api/monitor/colecciones/quitar", json={"handle": "hot-wheels-boulevard"}
                   ).get_json()["quitada"] is True)

r = cliente.post("/api/monitor/vigilar/agregar", json={"handle": "rlc-datsun-510", "nota": "ojo"})
check("vigilar por API", r.status_code == 200 and r.get_json()["ok"])
check("vigilar lista", len(cliente.get("/api/monitor/vigilar").get_json()["entradas"]) == 1)
check("vigilar quitar",
      cliente.post("/api/monitor/vigilar/quitar", json={"handle": "rlc-datsun-510"}
                   ).get_json()["quitado"] is True)

check("las listas de deseados siguen funcionando",
      cliente.get("/api/monitor/lista/deseados").get_json()["ok"] is True)
check("una lista inventada sigue dando 404",
      cliente.get("/api/monitor/lista/inventada").status_code == 404)

r = cliente.get("/api/monitor/estado")
d = r.get_json()
check("GET /api/monitor/estado responde", r.status_code == 200, d)
check("trae revisiones y tipo de cambio", d["revisiones"] == 42 and d["tipo_cambio"] == 19.5, d)
check("cuenta lo de hoy", d["hoy"]["nuevos"] == 2 and d["hoy"]["restocks"] == 1, d["hoy"])
check("sin latido el semaforo es sin_datos", d["semaforo"] == "sin_datos", d)

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
