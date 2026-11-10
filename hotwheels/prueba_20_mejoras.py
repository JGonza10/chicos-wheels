# prueba_20_mejoras.py
"""Pruebas de las 20 mejoras del 2026-11-10 (lo que no cubre
prueba_multicuenta.py). Todo en una carpeta temporal y con dobles: no toca
bot.db, los .env reales, Telegram, Facebook, Mercado Libre ni Mattel.

    python prueba_20_mejoras.py
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

ORIGEN = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_20_")
with open(os.path.join(TMP, "config.json"), "w") as f:
    json.dump({"notifications": {"email": {"enabled": False}, "whatsapp": {"enabled": False},
                                 "telegram": {"enabled": False}}}, f)
for f in os.listdir(ORIGEN):
    if f.endswith(".py") and not f.startswith("prueba_"):
        shutil.copy(os.path.join(ORIGEN, f), TMP)
for carpeta in ("templates", "static"):
    shutil.copytree(os.path.join(ORIGEN, carpeta), os.path.join(TMP, carpeta))
for k in list(os.environ):
    if k.startswith("HOTWHEELS_"):
        del os.environ[k]
os.environ["HOTWHEELS_DATOS"] = TMP
os.chdir(TMP)
sys.path.insert(0, TMP)

import cuentas as C  # noqa: E402
import drops as DR  # noqa: E402
import habilidades as H  # noqa: E402
import ml_auth as ML  # noqa: E402
import dashboard_bot as D  # noqa: E402
import telegram_control as T  # noqa: E402

fallos = []


def check(nombre, condicion, detalle=""):
    print(("  OK    " if condicion else "  FALLO ") + nombre + ("" if condicion else "  %s" % (detalle,)))
    if not condicion:
        fallos.append(nombre)


AVISOS, BOTONES = [], []
D.notify = lambda m: AVISOS.append(m)
D.notify_botones = lambda m, filas: BOTONES.append((m, filas)) or True

print("\n--- 1. PC despierta ---")
hasta = H.mantener_despierta(1)
check("queda despierta el plazo pedido", H.despierta_activa() and hasta > time.time() + 50)
check("un plazo más corto no recorta el largo", H.mantener_despierta(0.1) == hasta)

print("\n--- 2 y 3. Internet y reloj ---")


class Resp:
    def __init__(self, fecha):
        self.headers = {"Date": format_datetime(fecha, usegmt=True)}


ok = H.chequeo_sistema(pedir=lambda: Resp(datetime.now(timezone.utc)))
check("internet rápido y reloj exacto en verde", ok[0][0] is True and ok[1][0] is True, ok)
mal = H.chequeo_sistema(pedir=lambda: Resp(datetime.now(timezone.utc) - timedelta(seconds=45)))
check("reloj adelantado 45 s en rojo, con cómo arreglarlo", mal[1][0] is False and "Sincronizar" in mal[1][1], mal)
caida = H.chequeo_sistema(pedir=lambda: (_ for _ in ()).throw(OSError("sin red")))
check("sin internet en rojo", caida[0][0] is False and "no responde" in caida[0][1], caida)

print("\n--- 4 y 7. Captcha remoto y fila ---")
src = open(os.path.join(TMP, "bot_logic.py"), encoding="utf-8").read()
check("el aviso de captcha trae el link del escritorio remoto", "remotedesktop.google.com" in src and "Desde el celular" in src)
check("la fila del checkout avisa por Telegram", "te puso en la fila del checkout" in src)

print("\n--- 5. Ensayo semanal ---")
D.monitor_admin.producto_disponible_para_prueba = lambda: "https://creations.mattel.com/en-mx/products/prueba"
D.NAVEGADOR.obtener = lambda cuenta=None: None


async def ensayo(url, **kw):
    return "🧪 DRY RUN: checkout llenado, sin pagar: %s\n⏱ 40.0 s (navegador 1.0)" % url
D.comprar_producto = ensayo
AVISOS.clear()
D._job_ensayo_cuentas()
check("ensaya cada cuenta y lo reporta", AVISOS and "principal: llegó hasta antes de pagar" in AVISOS[-1], AVISOS)
check("deja la señal para Nexus", os.path.exists(os.path.join(TMP, "ensayo_ok.txt")))
check("y guarda el reporte", "Ensayo semanal" in (H.ultimo_reporte("ensayo", db=D.DB) or [""])[0])

print("\n--- 6. Víspera ---")
manana = datetime.now(timezone.utc) + timedelta(hours=14)
pid, _ = DR.proponer(D.DB, "https://creations.mattel.com/en-mx/products/rlc-manana", "RLC Mañana", manana)
AVISOS.clear()
BOTONES.clear()
D._job_vispera()
check("avisa lo que sale mañana", AVISOS and "Mañana salen" in AVISOS[-1] and "RLC Mañana" in AVISOS[-1], AVISOS)
check("con botón para programar lo pendiente", BOTONES and BOTONES[-1][1][0][0]["callback_data"] == "pd:%d" % pid)

print("\n--- 8. Reintento en cuanto hay stock ---")
D._disponible_ahora = lambda url: True
t0 = time.monotonic()
asyncio.run(D._esperar_reintento(["u"], 15))
check("reintenta a los ~6 s si ya está a la venta (no espera 15)", time.monotonic() - t0 < 8, time.monotonic() - t0)
t0 = time.monotonic()
D._disponible_ahora = lambda url: (_ for _ in ()).throw(AssertionError("no debe consultar"))
asyncio.run(D._esperar_reintento(["u"], 0.05))
check("con intervalos cortos no consulta a Mattel", time.monotonic() - t0 < 1)

print("\n--- 9. Agregar directo (solo no RLC) ---")
check("las piezas RLC siguen el camino del botón", "not es_pieza_rlc(url)" in src and "HOTWHEELS_AGREGAR_DIRECTO" in src)

print("\n--- 10. Elegir cuentas por drop ---")
hijo = C.crear("hijo")
with open(hijo.env, "a", encoding="utf-8") as f:
    f.write("HOTWHEELS_CARD_NUMBER=5555555555554444\nHOTWHEELS_CARD_EXPIRY=11/29\n")
os.makedirs(hijo.perfil, exist_ok=True)
with open(hijo.cookies, "w", encoding="utf-8") as f:
    json.dump([{"name": "x", "value": "y", "domain": ".mattel.com", "path": "/"}], f)
filas = D.botones_drop(pid)
check("con 2 cuentas ofrece 'Solo principal' y 'Solo hijo'",
      [b["callback_data"] for b in filas[1]] == ["pc:%d:principal" % pid, "pc:%d:hijo" % pid], filas)
D._datos_pieza = lambda url, html=None: ("RLC Mañana", 610.0, 2, "")
r = D.accion_drop_cuenta(pid, "hijo")
check("'Solo hijo' lo programa solo para esa cuenta", DR.obtener(D.DB, pid)["cuentas"] == "hijo" and "Solo: hijo" in r, r)
LLAMADAS = []


async def compra(url, proxy=None, cuenta=None, **kw):
    LLAMADAS.append(cuenta.nombre)
    return "❌ Producto agotado: %s" % url
D.comprar_producto = compra
D.EVENTO_VENTANA_SEGUNDOS = 0.1
D.EVENTO_INTERVALO_SEGUNDOS = 0.05
asyncio.run(D._intentar_evento(["https://creations.mattel.com/en-mx/products/rlc-manana"], solo="hijo"))
check("el disparo usa solo la cuenta elegida", set(LLAMADAS) == {"hijo"}, LLAMADAS)

print("\n--- 11. Publicar en Facebook con aprobación ---")
import sqlite3  # noqa: E402
D.COLLECTHUB.init_db()
conn = sqlite3.connect(D.DB)
conn.execute("INSERT INTO registros_collecthub (url, articulo_id_remoto, resultado) VALUES (?, ?, 'ok')",
             ("https://creations.mattel.com/en-mx/products/vendida", "art-77"))
conn.commit()
conn.close()
BOTONES.clear()
pub = D.ofrecer_publicacion("🔥 Texto", "https://creations.mattel.com/en-mx/products/vendida")
check("el borrador llega con el botón 'Publicar en Facebook'", BOTONES and BOTONES[-1][1][0][0]["callback_data"] == "fb:%d" % pub, BOTONES)
PEDIDOS = []


class R:
    status_code = 200
    content = b"1"

    def json(self):
        return {"ok": True, "link": "https://facebook.com/p/1"}


D.COLLECTHUB.pedir = lambda metodo, ruta, json=None, timeout=10: PEDIDOS.append((metodo, ruta, json)) or R()
r = D.accion_publicar(pub, True)
check("al aprobar publica en la pieza correcta del inventario",
      PEDIDOS and PEDIDOS[-1][1] == "/api/articulos/art-77/publicar-facebook" and PEDIDOS[-1][2]["texto"] == "🔥 Texto"
      and "Publicada" in r, (PEDIDOS, r))
check("no la vuelve a publicar", "Ya estaba publicada" in D.accion_publicar(pub, True))
pub2 = D.ofrecer_publicacion("otro", "https://creations.mattel.com/en-mx/products/vendida")
check("'No por ahora' la descarta sin publicar", "no la publico" in D.accion_publicar(pub2, False).lower()
      and len(PEDIDOS) == 1)

print("\n--- Multicuenta en el inventario ---")
REGISTROS = []
D.COLLECTHUB.registrar_compra = lambda **kw: REGISTROS.append(kw) or (True, "ok")
D.ofrecer_publicacion = lambda *a, **k: None
D._despues_de_comprar("https://creations.mattel.com/en-mx/products/demon", "🎉 Pedido realizado", C.obtener("hijo"))
check("la compra de otra cuenta se anota aparte", REGISTROS and REGISTROS[-1]["clave"].endswith("#cuenta=hijo"), REGISTROS)

print("\n--- 14. Reventa del inventario ---")
import monitor as MON  # noqa: E402


class Arts:
    status_code = 200

    def json(self):
        return [{"nombre": "RLC Demon", "tipo": "Hot Wheels", "estatus": "Disponible", "valor_estimado": 1000},
                {"nombre": "RLC Igual", "tipo": "Hot Wheels", "estatus": "Disponible", "valor_estimado": 1000},
                {"nombre": "Vendida", "tipo": "Hot Wheels", "estatus": "Vendido", "valor_estimado": 100}]


D.COLLECTHUB.pedir = lambda *a, **k: Arts()
MON.TIPO_CAMBIO = 20.0
MON.precio_reventa_estimado = lambda nombre: (75.0, 9) if nombre == "RLC Demon" else (51.0, 9)
D.time.sleep = lambda s: None
AVISOS.clear()
D._job_reventa_inventario()
check("avisa solo lo que subió 15% o más", AVISOS and "RLC Demon" in AVISOS[-1] and "+50%" in AVISOS[-1]
      and "Igual" not in AVISOS[-1] and "Vendida" not in AVISOS[-1], AVISOS)

print("\n--- 16. Reporte del drop ---")
texto, exito = H.resumen_drop("RLC X", {"principal": {"intentos": 3, "captchas": 1, "resultado": "🎉 Pedido\n⏱ 30.0 s (x)"},
                                        "hijo": {"intentos": 5, "captchas": 0, "resultado": "❌ Producto agotado: u"}},
                              db=D.DB)
check("dice intentos, captchas y tiempo por cuenta", "principal: 3 intento(s), 1 captcha(s) · ⏱ 30.0 s" in texto
      and "hijo: 5 intento(s)" in texto and exito, texto)
check("/reporte lo muestra", "Reporte" in D.atender_mensaje("/reporte")[0] or "Ensayo" in D.atender_mensaje("/reporte")[0])

print("\n--- 17. Token de Mercado Libre que se renueva ---")
with open(os.path.join(TMP, "config.env"), "w", encoding="utf-8") as f:
    f.write("ML_CLIENT_ID=123\nML_CLIENT_SECRET=abc\n")
ML.CONFIG = os.path.join(TMP, "config.env")
ML.ARCHIVO = os.path.join(TMP, "ml_token.json")
PIDE = []


class Tok:
    status_code = 200

    def __init__(self, n):
        self.n = n

    def json(self):
        return {"access_token": "AT%d" % self.n, "refresh_token": "RT%d" % self.n, "expires_in": 21600}


def post(url, data=None, **kw):
    PIDE.append(data)
    return Tok(len(PIDE))


ML.canjear_codigo("TG-1", post=post)
check("canjea el código por tokens", ML.token(post=post) == "AT1" and PIDE[0]["grant_type"] == "authorization_code")
check("cuando le quedan menos de 10 min, lo renueva con el refresh token",
      ML.token(post=post, ahora=time.time() + 21000) == "AT2" and PIDE[-1]["grant_type"] == "refresh_token"
      and PIDE[-1]["refresh_token"] == "RT1", PIDE)
check("y guarda el refresh token nuevo (se usa una sola vez)", json.load(open(ML.ARCHIVO))["refresh_token"] == "RT2")
check("el link de autorizar lleva la app y el redirect", "client_id=123" in ML.link_autorizar()
      and "kestrel-ia" in ML.link_autorizar())

print("\n--- 18. Respaldo de cuentas ---")
with open(os.path.join(TMP, ".env"), "w", encoding="utf-8") as f:
    f.write("HOTWHEELS_CARD_NUMBER=4111\n")
zipf = H.respaldar_cuentas(destino=os.path.join(TMP, "resp"), dir_bot=TMP)
nombres = zipfile.ZipFile(zipf).namelist()
check("respalda .env y sesiones de todas las cuentas (sin el perfil pesado)",
      ".env" in nombres and any(n.replace("\\", "/") == "cuentas/hijo/.env" for n in nombres)
      and any(n.endswith("cookies_sesion.json") for n in nombres) and len(nombres) <= 4, nombres)

print("\n--- 19 y 20. Nexus y panel web ---")
cliente = D.app.test_client()
r = cliente.get("/api/bot_resumen").get_json()
check("resumen sin secretos: cuentas y drops", {c["nombre"] for c in r["cuentas"]} >= {"principal", "hijo"}
      and "5555" not in json.dumps(r) and any(d["titulo"] == "RLC Mañana" for d in r["drops"]), r)
check("programar desde el panel", cliente.post("/api/drops/%d/programar" % pid, json={}).get_json()["ok"])
check("analizar sin link de Mattel avisa", cliente.post("/api/analizar", json={"url": "hola"}).status_code == 400)
html = cliente.get("/").get_data(as_text=True)
check("la pestaña Drops está en el panel", 'data-vista="drops"' in html and 'id="vista-drops"' in html)

print("\n--- Telegram: botones nuevos ---")
llamadas = []
acc = {"obtener": lambda hid: None, "comprar": lambda *a: {"ok": True}, "ignorar": lambda h: None,
       "drop_cuenta": lambda did, n: "solo %s %d" % (n, did), "publicar": lambda pid, si: "pub %d %s" % (pid, si)}
tg = T.Control("tok", 42, acc, llamar=lambda m, **p: llamadas.append((m, p)) or {"ok": True}, log=lambda *a: None)


def toque(datos):
    return {"callback_query": {"id": "1", "data": datos, "from": {"id": 42},
                               "message": {"chat": {"id": 42}, "date": int(time.time())}}}


check("'Solo hijo' llega al calendario", tg.procesar(toque("pc:9:hijo")) == "drop_cuenta"
      and llamadas[-1][1]["text"] == "solo hijo 9")
check("'Publicar en Facebook' llega a publicar", tg.procesar(toque("fb:4")) == "publicada" and llamadas[-1][1]["text"] == "pub 4 True")
check("'No por ahora' no publica", tg.procesar(toque("fn:4")) == "publicacion_descartada" and llamadas[-1][1]["text"] == "pub 4 False")

os.chdir(ORIGEN)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFALLARON %d pruebas: %s" % (len(fallos), fallos) if fallos else "\nTODAS LAS PRUEBAS PASARON")
sys.exit(1 if fallos else 0)
