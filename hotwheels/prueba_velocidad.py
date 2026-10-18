# -*- coding: utf-8 -*-
"""Pruebas de las mejoras de velocidad del monitor (2026-10-18):

  1. Aviso express: lo urgente sale antes de consultar eBay/Mercado Libre
  2. Francotirador: deseados y vigilados a mano primero
  3. Modo drop: ventana alrededor del dia y hora del drop
  4. Sesion reutilizable, datos frescos (sin cache) y pausa ante un 429
  5. Telegram: titulos escapados y respaldo en texto plano
  + avisos de coleccion caida / monitor ciego en la primera hora de la PC

Todo en una copia temporal y sin red: Telegram y Mattel se sustituyen por
dobles. Nunca compra ni manda mensajes. Ejecutar:  python prueba_velocidad.py
"""

import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

DIR = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_velocidad_")
fallos = []


def check(nombre, condicion, detalle=""):
    if condicion:
        print("  OK    %s" % nombre)
    else:
        print("  FALLO %s  %s" % (nombre, detalle))
        fallos.append(nombre)


for f in os.listdir(DIR):
    if f.endswith(".py") and not f.startswith("prueba_"):
        shutil.copy(os.path.join(DIR, f), TMP)
io.open(os.path.join(TMP, "config.env"), "w", encoding="utf-8").write(
    u"TELEGRAM_BOT_TOKEN=token-de-prueba\nTELEGRAM_CHAT_ID=1\n")
os.environ["HOTWHEELS_DRY_RUN"] = "1"
sys.path.insert(0, TMP)
os.chdir(TMP)

import hallazgos as H  # noqa: E402
import monitor as M  # noqa: E402


class Resp:
    def __init__(self, status=200, datos=None, headers=None):
        self.status_code = status
        self._datos = datos or {}
        self.headers = headers or {}

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP %d" % self.status_code)


class SesionFalsa:
    """Doble de requests.Session: anota cada llamada y responde lo que se le diga."""

    def __init__(self, respuestas=None):
        self.llamadas = []
        self.respuestas = list(respuestas or [])

    def _resp(self):
        r = self.respuestas.pop(0) if self.respuestas else Resp()
        return r(self.llamadas[-1]) if callable(r) else r

    def get(self, url, params=None, timeout=None, **kw):
        self.llamadas.append(("GET", url, dict(params or {}), kw))
        return self._resp()

    def post(self, url, data=None, timeout=None, **kw):
        self.llamadas.append(("POST", url, dict(data or {}), kw))
        return self._resp()


def producto(titulo, handle, disponible=True, precio="20.00"):
    return {"id": abs(hash(handle)) % 10 ** 9, "title": titulo, "handle": handle,
            "variants": [{"id": 111, "available": disponible, "price": precio}],
            "images": [{"src": "https://cdn/x_800x.jpg"}], "tags": []}


# ============================================================
print("\n--- 1. Aviso express antes del calculo lento ---")
# ============================================================
orden = []
M.SESION_TG = SesionFalsa()
M.SESION_TG.post = lambda url, data=None, timeout=None, **kw: (orden.append(("express", data)), Resp())[1]
M.precio_reventa_estimado = lambda titulo: (orden.append(("ebay", titulo)), (None, 0))[1]
M.enviar_telegram = lambda texto, foto=None, link=None, compra=None, hallazgo_id=None: orden.append(("tarjeta", hallazgo_id))
M.DESEADOS = ["skyline"]
M.BLOQUEADOS = []

estado = {}
M.notificar(estado, producto("Nissan Skyline GT-R & Friends", "skyline-r34"), "restock")
pasos = [o[0] for o in orden]
check("el express sale ANTES de consultar eBay", pasos.index("express") < pasos.index("ebay"), pasos)
check("la tarjeta completa sale despues", pasos.index("express") < pasos.index("tarjeta"), pasos)
express = [o[1] for o in orden if o[0] == "express"][0]
check("el express es solo texto (sin foto ni vista previa)", "photo" not in express and express["disable_web_page_preview"], express)
check("el express escapa el titulo", "&amp;" in express["text"], express["text"])
botones = json.loads(express["reply_markup"])["inline_keyboard"]
url_p = M.BASE_URL + "/products/skyline-r34"
pieza = {p["url"]: p for p in H.listar()}[url_p]
check("el express trae Comprar/Ignorar de la pieza registrada",
      botones[0][0]["callback_data"] == "c:%d" % pieza["id"], botones)
check("y el carrito listo", any(b.get("url", "").endswith("/cart/111:1") for fila in botones for b in fila), botones)
tarjeta_id = [o[1] for o in orden if o[0] == "tarjeta"][0]
check("la tarjeta usa la misma pieza (no duplica)", tarjeta_id == pieza["id"], (tarjeta_id, pieza["id"]))
check("se cuenta como vista una sola vez", pieza["veces_visto"] == 1, pieza["veces_visto"])

orden.clear()
M.notificar(estado, producto("Auto cualquiera", "auto-x"), "nuevo")
check("lo que no es urgente NO manda express", "express" not in [o[0] for o in orden], orden)

orden.clear()
M.notificar(estado, producto("Skyline agotado", "sky-agot", disponible=False), "restock")
check("sin disponibilidad no hay express", "express" not in [o[0] for o in orden], orden)

orden.clear()
M.BLOQUEADOS = ["porsche"]
estado["vigilancia"] = {"porsche-raro": {"motivo": "manual"}}
M.notificar(estado, producto("Porsche raro", "porsche-raro"), "nuevo")
check("lo bloqueado no sale express aunque se vigile", "express" not in [o[0] for o in orden], orden)
M.BLOQUEADOS = []
orden.clear()
M.notificar(estado, producto("Porsche raro", "porsche-raro"), "nuevo")
check("lo vigilado a mano sale express", "express" in [o[0] for o in orden], orden)

M.CACHE_EBAY["exacto:rlc elite 64 ferrari f40"] = (300.0, 10)
check("alto impacto con eBay en cache = urgente sin red",
      M.es_urgente({}, producto("RLC Elite 64 Ferrari F40", "f40", precio="30.00"), "nuevo", False, False) == "alto impacto")
check("sin cache usa la regla local (sin red)",
      M.es_urgente({}, producto("Taza Hot Wheels", "taza"), "nuevo", False, False) == "")

# ============================================================
print("\n--- 2. Francotirador: lo de Gonza primero ---")
# ============================================================
M.MAX_FRANCOTIRADOR = 3
M._IDX_FRANCOTIRADOR.clear()
M.DESEADOS = ["skyline"]
vig = {"agotado-%02d" % i: {"motivo": "restock"} for i in range(30)}
vig.update({"coming-1": {"motivo": "coming_soon"}, "mi-manual": {"motivo": "manual"},
            "skyline-r34": {"motivo": "restock"}})
est = {"vigilancia": vig, "productos": {"1": {"handle": "skyline-r34", "titulo": "Nissan Skyline R34"}}}
sel = M._siguientes_francotirador(est)
check("deseados y manuales van en cada ciclo", "skyline-r34" in sel and "mi-manual" in sel, sel)
check("luego los coming soon", "coming-1" in sel, sel)
for _ in range(10):
    sel = M._siguientes_francotirador(est)
    if not ("skyline-r34" in sel and "mi-manual" in sel):
        break
check("el deseado nunca espera turno", "skyline-r34" in sel and "mi-manual" in sel, sel)
M.MAX_FRANCOTIRADOR = 4
vistos = set()
for _ in range(30):
    vistos.update(M._siguientes_francotirador(est))
check("los agotados normales siguen rotando", len([h for h in vistos if h.startswith("agotado-")]) == 30, len(vistos))
M.MAX_FRANCOTIRADOR = 1
est2 = {"vigilancia": {"a": {"motivo": "manual"}, "b": {"motivo": "manual"}}, "productos": {}}
turnos = {M._siguientes_francotirador(est2)[0] for _ in range(4)}
check("si hay mas deseados que cupo, se turnan entre ellos", turnos == {"a", "b"}, turnos)

# ============================================================
print("\n--- 3. Modo drop ---")
# ============================================================
MX = timezone(timedelta(hours=-6))
M.PATRON_DROPS = None
M.MINUTOS_ANTES_DROP, M.MINUTOS_DESPUES_DROP = 10, 45
martes = datetime(2026, 10, 20, 11, 0, tzinfo=MX)
check("sin patron: martes 11:00 es drop", M.en_ventana_drop(martes))
check("10 min antes ya es drop", M.en_ventana_drop(martes - timedelta(minutes=10)))
check("11 min antes todavia no", not M.en_ventana_drop(martes - timedelta(minutes=11)))
check("45 min despues sigue", M.en_ventana_drop(martes + timedelta(minutes=45)))
check("46 min despues ya no", not M.en_ventana_drop(martes + timedelta(minutes=46)))
check("miercoles 11:00 no es drop", not M.en_ventana_drop(martes + timedelta(days=1)))
M.PATRON_DROPS = {"dia_semana": 3, "hora": 0, "confianza": 0.9}   # jueves 00:00
jueves = datetime(2026, 10, 22, 0, 0, tzinfo=MX)
check("patron aprendido: la ventana cruza la medianoche", M.en_ventana_drop(jueves - timedelta(minutes=5)))
check("y deja de usar martes 11am", not M.en_ventana_drop(martes))
M.PATRON_DROPS = None

# ============================================================
print("\n--- 4. Sesion, datos frescos y pausa ante 429 ---")
# ============================================================
check("hay una sesion reutilizable con la huella del navegador",
      M.SESION.headers.get("User-Agent") == M.HEADERS["User-Agent"])
ses = SesionFalsa([Resp(200, {"product": {"id": 1}})])
M.SESION = ses
M.obtener_producto_individual("algo")
check("el francotirador pide datos frescos (rompe cache)", "_" in ses.llamadas[0][2], ses.llamadas)
ses = SesionFalsa([Resp(200, {"products": []})])
M.SESION = ses
M.obtener_productos_coleccion("hot-wheels-collectors")
check("el barrido completo no agrega el parametro", "_" not in ses.llamadas[0][2], ses.llamadas)
ses = SesionFalsa([Resp(429, headers={"Retry-After": "30"}), Resp(200, {"products": []})])
M.SESION = ses
M._PAUSA_HASTA = 0.0
r = M.hacer_request("https://x/products.json", intentos=3)
check("ante 429 no reintenta en caliente", r is None and len(ses.llamadas) == 1, ses.llamadas)
check("y pausa el tiempo que pide Mattel", 25 < M._PAUSA_HASTA - __import__("time").monotonic() <= 30, M._PAUSA_HASTA)
M._PAUSA_HASTA = 0.0

# ============================================================
print("\n--- 5. Telegram: escapado y respaldo en texto plano ---")
# ============================================================
M.formato_mensaje.__globals__["evaluar_impacto"] = lambda p, va=0: "Impacto medio"
msg = M.formato_mensaje(producto("Fast & Furious <Premium>", "ff"), "nuevo")
check("el titulo va escapado en el HTML", "Fast &amp; Furious &lt;Premium&gt;" in msg, msg)
ses = SesionFalsa([Resp(400), Resp(400)])
M.SESION_TG = ses
ok = M._enviar_a_chat("https://api/bot", 1, "<b>NUEVO</b> Fast &amp; Furious", None, None)
check("si Telegram rechaza el HTML, reintenta en texto plano", ok is False and len(ses.llamadas) == 2
      and "parse_mode" not in ses.llamadas[1][2] and ses.llamadas[1][2]["text"] == "NUEVO Fast & Furious",
      ses.llamadas)

# ============================================================
print("\n--- 6. Avisos en la primera hora despues de prender la PC ---")
# ============================================================
avisos = []
M.enviar_telegram_texto = lambda t: avisos.append(t)
M._TS_ALERTA_COLECCION.clear()
M.FALLOS_ALERTA_COLECCION = 1
reloj_real = M.time.monotonic
M.time.monotonic = lambda: 120.0     # PC prendida hace 2 minutos
M.registrar_salud_coleccion({}, "hot-wheels-premium", False, 0)
M.time.monotonic = reloj_real
check("avisa de coleccion caida aunque la PC lleve <1 h prendida", len(avisos) == 1, avisos)

# ============================================================
print("\n--- 7. Segundo restock dentro de los 15 min ---")
# ============================================================
avisados = []
M.notificar = lambda estado, p, tipo, precio_anterior=None, previo=None: avisados.append(tipo)
M.NOTIFICACIONES_ENVIADAS.clear()
p_disp, p_agot = producto("RLC Vuelve", "rlc-vuelve"), producto("RLC Vuelve", "rlc-vuelve", disponible=False)
cat = {}


def paso(p):
    previos = dict(cat)
    nuevo = dict(previos)
    M._procesar_producto({}, p, previos, nuevo, None,
                         {k: 0 for k in ("nuevos", "restocks", "proximamente", "cambios_precio",
                                         "pocas_unidades", "agotados", "rebajas")}, False)
    cat.clear()
    cat.update(nuevo)


paso(p_agot)                              # ya conocido, agotado
for p in (p_disp, p_agot, p_disp, p_agot, p_disp):
    paso(p)
check("restock -> agotado -> restock avisa los dos restocks", avisados.count("restock") == 3, avisados)
check("y cada agotado (el panel se entera)", avisados.count("agotado") == 2, avisados)
avisados.clear()
paso(p_disp)
check("sin cambio real no repite aviso", avisados == [], avisados)

# ============================================================
print("\n--- 8. Barrido incompleto: se procesa lo que si llego ---")
# ============================================================
previos = {str(i): {"titulo": "Auto %d" % i, "disponible": False, "handle": "a%d" % i} for i in range(10)}
llego = producto("Auto 1", "a1")
llego["id"] = 1
todos_original = M.obtener_todos_los_productos
M.obtener_todos_los_productos = lambda estado=None: ([llego], ["hot-wheels-collectors"])
avisados.clear()
est = {"productos": dict(previos), "revisiones": 5, "pocas_unidades": ["se queda"], "stats": {"total": 10}}
est, cambios = M.revisar(est)
check("el restock de lo que si respondio se avisa", avisados == ["restock"], avisados)
check("lo que no llego conserva su estado", est["productos"]["3"] == previos["3"], est["productos"]["3"])
check("no rearma totales ni pocas unidades con datos parciales",
      est["pocas_unidades"] == ["se queda"] and est["stats"] == {"total": 10}, est)
avisados.clear()
est = {"productos": dict(previos), "revisiones": 0}
est, cambios = M.revisar(est)
check("en el calentamiento se salta como antes", avisados == [] and est["revisiones"] == 0, (avisados, est))

# ============================================================
print("\n--- 9. eBay: precios con coma y piezas caras ---")
# ============================================================
html_ebay = "Vendido $1,250.00 · $45.99 + $5.00 envio · $12,500.00 · $2.00 · $999.50"
check("lee $1,250.00 y $999.50", M.extraer_precios_ebay(html_ebay) == [1250.0, 45.99, 5.0, 999.5],
      M.extraer_precios_ebay(html_ebay))

# ============================================================
print("\n--- 10. Colecciones en paralelo, mismo resultado ---")
# ============================================================
import threading  # noqa: E402
import time as _t  # noqa: E402
hilos = set()


def coleccion_falsa(nombre):
    hilos.add(threading.get_ident())
    _t.sleep(0.2)
    if nombre == "caida":
        return [], False
    return [{"id": 1, "title": "repetido"}, {"id": hash(nombre) % 1000 + 10, "title": nombre}], True


M.obtener_productos_coleccion = coleccion_falsa
M.COLECCIONES = ["c1", "c2", "caida", "c3"]
M.obtener_todos_los_productos = todos_original
M.enviar_telegram_texto = lambda t: None
salud = {}
inicio = _t.monotonic()
prods, fallaron = M.obtener_todos_los_productos(salud)
tardo = _t.monotonic() - inicio
check("consulta varias colecciones a la vez", len(hilos) > 1 and tardo < 0.7, (len(hilos), tardo))
check("sin duplicados", sorted(p["id"] for p in prods) == sorted(set(p["id"] for p in prods)) and len(prods) == 4, prods)
check("reporta cual fallo", fallaron == ["caida"], fallaron)
check("y lleva la salud de cada coleccion", salud["salud_colecciones"]["caida"]["fallos"] == 1, salud)

# ============================================================
print("\n--- 11. Relevo PC <-> Railway ---")
# ============================================================
textos = []
import importlib  # noqa: E402
M = importlib.reload(M)   # monitor limpio: las secciones de arriba sustituyeron funciones
M.SESION_TG = SesionFalsa()
M.SESION_TG.post = lambda url, data=None, timeout=None, **kw: (textos.append(data["text"]), Resp())[1]
check("en la PC nunca se calla", M.pc_vigilando() is False)
M.activar_relevo()
check("Railway arranca callado (espera el latido de la PC)", M.pc_vigilando() and M.HALLAZGOS is None)
M.enviar_telegram("aviso", None, "https://x/p", "https://x/cart/1:1")
check("mientras la PC vigila, Railway no manda avisos", textos == [], textos)
M._PC_LATIDO = M.time.monotonic() - 6 * 60
M.revisar_relevo()
check("si la PC calla 5 min, avisa que toma el relevo", len(textos) == 1 and "RELEVO" in textos[0], textos)
M.revisar_relevo()
check("ese aviso sale una sola vez", len(textos) == 1, textos)
M.enviar_telegram_texto("resumen")
check("y ya manda los avisos normales", textos[-1] == "resumen", textos)
r = M.registrar_latido_pc()
check("el latido devuelve como ve la tienda Railway", "minutos_sin_ver" in r and r["relevo"] is True, r)
M.revisar_relevo()
check("cuando la PC vuelve, avisa y se calla", "volvió" in textos[-1] and M.pc_vigilando(), textos)

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
