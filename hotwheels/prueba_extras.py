# -*- coding: utf-8 -*-
"""Pruebas de hw_extras.py — se corren solas, sin internet."""
import io, os, sys, tempfile
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_extras as hx

fallos = []
def check(nombre, cond, detalle=""):
    if cond:
        print("  OK    %s" % nombre)
    else:
        print("  FALLA %s  %s" % (nombre, detalle))
        fallos.append(nombre)

tmp = tempfile.mkdtemp()

# --- 1. config ---
ruta_cfg = os.path.join(tmp, "config.env")
io.open(ruta_cfg, "w", encoding="utf-8").write(
    '# comentario\nTELEGRAM_BOT_TOKEN="123:ABC"\nENVIO_MXN = 300\nVACIO=\nMALA_LINEA\n')
cfg = hx.cargar_config(ruta_cfg)
check("config lee token", cfg.get("TELEGRAM_BOT_TOKEN") == "123:ABC", cfg)
check("config quita comillas y espacios", cfg.get("ENVIO_MXN") == "300", cfg)
check("config ignora lineas malas", "MALA_LINEA" not in cfg, cfg)
check("config archivo inexistente", hx.cargar_config("/no/existe") == {})
check("config_num convierte", hx.config_num(cfg, "ENVIO_MXN", 250.0) == 300.0)
check("config_num usa default si vacio", hx.config_num(cfg, "VACIO", 250.0) == 250.0)
check("config_num usa default si no existe", hx.config_num(cfg, "NADA", 7) == 7)

# --- 2. deseados (deseados.json) ---
import json as _json
ruta_des = os.path.join(tmp, "deseados.json")
io.open(ruta_des, "w", encoding="utf-8").write(_json.dumps([
    {"texto": "Datsun 510", "categoria": "Japoneses"},
    {"texto": "Porsche 911", "categoria": None},
    {"texto": "RLC", "categoria": None},
]))
des = hx.cargar_deseados(ruta_des)
check("deseados carga 3", len(des) == 3, des)
check("deseados con apostrofe", hx.es_deseado("Hot Wheels '71 Datsun 510 Wagon", des))
check("deseados con acento", hx.es_deseado("Porsche 911 Turbo", des))
check("deseados no coincide", not hx.es_deseado("Hot Wheels Character Car Batman", des))
check("deseados devuelve cual", hx.coincidencia_deseada("RLC Exclusive Camaro", des) == "rlc")
check("deseados vacio no truena", hx.es_deseado("lo que sea", []) is False)
check("deseados archivo inexistente", hx.cargar_deseados("/no/existe.json") == [])

# --- 2b. agregar/quitar deseado ---
ok, entrada = hx.agregar_deseado(ruta_des, "Skyline R34", categoria="Japoneses")
check("agregar_deseado agrega", ok and entrada["texto"] == "Skyline R34", entrada)
check("agregar_deseado ahora hay 4", len(hx.cargar_deseados(ruta_des)) == 4)
ok2, _ = hx.agregar_deseado(ruta_des, "skyline  r34")
check("agregar_deseado detecta duplicado normalizado", ok2 is False)
ok3, _ = hx.agregar_deseado(ruta_des, "   ")
check("agregar_deseado rechaza vacio", ok3 is False)
quitado = hx.quitar_deseado(ruta_des, "Datsun 510")
check("quitar_deseado quita", quitado is True)
check("quitar_deseado ahora hay 3", len(hx.cargar_deseados(ruta_des)) == 3)
check("quitar_deseado inexistente devuelve False", hx.quitar_deseado(ruta_des, "Ferrari F40") is False)

detalle = hx.listar_deseados_detalle(ruta_des)
check("listar_deseados_detalle conserva mayusculas", any(e["texto"] == "Porsche 911" for e in detalle), detalle)
check("listar_deseados_detalle conserva categoria",
      any(e["texto"] == "Skyline R34" and e["categoria"] == "Japoneses" for e in detalle), detalle)

# --- 2c. migracion desde deseados.txt viejo ---
ruta_txt_legacy = os.path.join(tmp, "deseados_legacy.txt")
ruta_json_nuevo = os.path.join(tmp, "deseados_migrado.json")
io.open(ruta_txt_legacy, "w", encoding="utf-8").write(
    "# encabezado\n\n# --- Japoneses ---\ndatsun 510\nskyline\n\n# --- Muscle ---\ncamaro\n")
n = hx.migrar_deseados_legacy(ruta_txt_legacy, ruta_json_nuevo)
check("migracion cuenta 3", n == 3, n)
migrados = hx.listar_deseados_detalle(ruta_json_nuevo)
check("migracion asigna categoria", any(e["texto"] == "skyline" and e["categoria"] == "Japoneses" for e in migrados), migrados)
check("migracion no repite si ya existe", hx.migrar_deseados_legacy(ruta_txt_legacy, ruta_json_nuevo) == 0)

# --- 3. historial ---
ruta_db = os.path.join(tmp, "historial.db")
conn = hx.abrir_historial(ruta_db)
check("historial abre", conn is not None)
prod = {"id": 999, "title": "Hot Wheels RLC Datsun 510", "handle": "rlc-datsun-510"}
hx.registrar_evento(conn, "nuevo", prod, precio_usd=25.0, precio_mxn=525.0,
                    impacto="Alto impacto", deseado=True)
hx.registrar_evento(conn, "agotado", prod, minutos_agotamiento=7)
hx.registrar_evento(conn, "restock", prod, precio_usd=25.0)
r = hx.resumen_historial(conn, dias=30)
check("historial cuenta 3", r["total"] == 3, r)
check("historial agrupa por tipo", r["por_tipo"].get("agotado") == 1, r)
check("historial saca mas rapidos", r["mas_rapidos"][0]["minutos"] == 7, r)
hx.registrar_evento(None, "nuevo", prod)  # no debe tronar
check("historial con conn None no truena", True)
check("resumen con conn None", hx.resumen_historial(None)["total"] == 0)

# --- 4. patron de drops ---
check("patron sin datos suficientes", hx.patron_de_drops(conn) is None)
ahora = datetime.now(timezone.utc)
for i in range(12):
    conn.execute("INSERT INTO eventos (ts_utc,fecha_mx,hora_mx,dia_semana,tipo,titulo)"
                 " VALUES (?,?,?,?,?,?)",
                 ((ahora - timedelta(days=i)).isoformat(), "2026-01-01", 11, 1, "nuevo", "x"))
for i in range(3):
    conn.execute("INSERT INTO eventos (ts_utc,fecha_mx,hora_mx,dia_semana,tipo,titulo)"
                 " VALUES (?,?,?,?,?,?)",
                 ((ahora - timedelta(days=i)).isoformat(), "2026-01-01", 15 + i, 4, "nuevo", "x"))
conn.commit()
pat = hx.patron_de_drops(conn)
check("patron detecta martes 11", pat and pat["dia_semana"] == 1 and pat["hora"] == 11, pat)
check("patron reporta confianza", pat and 0 < pat["confianza"] <= 1, pat)
txt = hx.proximo_drop(pat)
check("proximo drop en texto", txt and "11:00 CDMX" in txt, txt)
check("proximo drop sin patron", hx.proximo_drop(None) is None)
check("patron con conn None", hx.patron_de_drops(None) is None)

# --- 5. ganancia ---
g = hx.ganancia_neta(25.0, 60.0, 20.0, envio_mxn=250, impuestos_mxn=25, comision_pct=13)
# costo = 500 + 275 = 775 ; venta = 1200 ; neto = 1200 - 156 - 775 = 269
check("ganancia costo", g["costo_mxn"] == 775.0, g)
check("ganancia neta", g["ganancia_mxn"] == 269.0, g)
check("ganancia margen", abs(g["margen_pct"] - 34.7) < 0.2, g)
gp = hx.ganancia_neta(25.0, 26.0, 20.0)
check("ganancia negativa detectada", gp["ganancia_mxn"] < 0, gp)
check("ganancia sin datos", hx.ganancia_neta(None, 60.0, 20.0) is None)
check("texto ganancia dice Ganas", "Ganas" in hx.texto_ganancia(g), hx.texto_ganancia(g))
check("texto ganancia dice Pierdes", "Pierdes" in hx.texto_ganancia(gp))
check("texto ganancia vacio", hx.texto_ganancia(None) == "")

# --- 6. latido ---
ruta_lat = os.path.join(tmp, "latido.txt")
hx.latido(ruta_lat, "1234 productos")
m = hx.leer_latido(ruta_lat)
check("latido escribe y lee", m is not None and m < 1, m)
check("latido inexistente", hx.leer_latido("/no/existe") is None)

# --- 7. Mercado Libre (mockeado, sin red) ---
class _RespuestaML:
    def __init__(self, items):
        self._items = items
        self.status_code = 200   # _pedir_ml distingue 401/403 del resto
    def raise_for_status(self):
        pass
    def json(self):
        return {"results": self._items}

class _RequestsFalsoML:
    def __init__(self, items):
        self._items = items
    def get(self, url, params=None, timeout=None, headers=None):
        # headers: desde 2026-09-15 la API de ML exige Authorization (ver
        # hw_extras seccion 12), asi que el doble tiene que aceptarlo.
        return _RespuestaML(self._items)

hx.requests = _RequestsFalsoML([{"price": 500.0}, {"price": 520.0}, {"price": 480.0}, {"price": 510.0}])
hx._CACHE_MERCADOLIBRE.clear()
precio, n = hx.buscar_mercadolibre("datsun 510", token="token-de-prueba")
check("mercadolibre promedia con recorte", precio is not None and 490 <= precio <= 520, (precio, n))
check("mercadolibre cuenta resultados", n == 4, n)

hx.requests = _RequestsFalsoML([{"price": 50000.0}])  # fuera de rango, se descarta
hx._CACHE_MERCADOLIBRE.clear()
precio2, n2 = hx.buscar_mercadolibre("algo raro", token="token-de-prueba")
check("mercadolibre filtra fuera de rango", precio2 is None and n2 == 0, (precio2, n2))

hx.requests = None
hx._CACHE_MERCADOLIBRE.clear()
check("mercadolibre sin requests no truena", hx.buscar_mercadolibre("x", token="t") == (None, 0))
# Con requests disponible pero SIN token: debe apagarse y dejar dicho por que
# (antes devolvia (None, 0) en silencio y parecia "es que no hay datos").
hx.requests = _RequestsFalsoML([{"price": 500.0}])
hx._CACHE_MERCADOLIBRE.clear()
check("mercadolibre sin token se apaga y lo dice",
      hx.buscar_mercadolibre("x") == (None, 0) and "TOKEN" in (hx.MOTIVO_ML_PRECIOS or ""),
      hx.MOTIVO_ML_PRECIOS)

# --- 8. historial de precios por producto ---
conn2 = hx.abrir_historial(os.path.join(tmp, "historial_precios.db"))
for i, precio_mxn in enumerate([500.0, 520.0, 480.0]):
    hx.registrar_evento(conn2, "restock", {"id": 1, "title": "Hot Wheels RLC Datsun 510", "handle": "x"},
                        precio_mxn=precio_mxn)
serie = hx.historial_precios(conn2, "Hot Wheels RLC Datsun 510")
check("historial_precios trae 3 puntos", len(serie) == 3, serie)
check("historial_precios ordenado ascendente por fecha",
      serie[0]["ts"] <= serie[1]["ts"] <= serie[2]["ts"], serie)
check("historial_precios titulo sin datos", hx.historial_precios(conn2, "No existe") == [])
check("historial_precios conn None no truena", hx.historial_precios(None, "x") == [])
check("historial_precios sin titulo no truena", hx.historial_precios(conn2, "") == [])

print()
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
