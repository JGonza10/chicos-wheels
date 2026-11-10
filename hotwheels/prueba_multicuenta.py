# prueba_multicuenta.py
"""Pruebas de lo integrado el 2026-11-10 tras el drop del Challenger:

  - cuentas.py: varias cuentas de Mattel, datos leidos al momento, CVV que
    se borra al pagar, semaforo y sesion sin abrir navegador.
  - drops.py: hora de lanzamiento desde la pagina, propuesta unica, agenda
    (-30 chequeo, -5 CVV, -2 navegador, disparo).
  - dashboard_bot: disparo EN PARALELO con todas las cuentas, restock
    automatico, borrador para Facebook/Instagram y botones de Telegram.

Todo en una carpeta temporal: no toca bot.db, los .env reales, Telegram ni
Mattel. Ejecutar:  python prueba_multicuenta.py
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

ORIGEN = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_multicuenta_")
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
import dashboard_bot as D  # noqa: E402
import navegador as N  # noqa: E402
import telegram_control as T  # noqa: E402

fallos = []


def check(nombre, condicion, detalle=""):
    print(("  OK    " if condicion else "  FALLO ") + nombre + ("" if condicion else "  %s" % (detalle,)))
    if not condicion:
        fallos.append(nombre)


AVISOS = []
D.notify = lambda m: AVISOS.append(m)
BOTONES = []
D.notify_botones = lambda m, filas: BOTONES.append((m, filas)) or True

# ---------------- 1. Cuentas ----------------
print("\n--- 1. Cuentas ---")
with open(os.path.join(TMP, ".env"), "w", encoding="utf-8") as f:
    f.write("HOTWHEELS_CARD_NUMBER=4111111111111111\nHOTWHEELS_CARD_EXPIRY=12/30\n"
            "HOTWHEELS_CARD_CVV=\nHOTWHEELS_CARD_NAME=Gonza\nHOTWHEELS_SHIP_PHONE=5512345678\n"
            "HOTWHEELS_RFC=GOGJ800101AB1\n")
p = C.principal()
check("la principal se lee de hotwheels/.env", p.datos()["tarjeta1"]["number"].endswith("1111"))
check("sin CVV no hay tarjeta lista para pagar", p.datos()["tarjetas"] == [])
with open(p.env, encoding="utf-8") as f:
    txt = f.read()
with open(p.env, "w", encoding="utf-8") as f:
    f.write(txt.replace("HOTWHEELS_CARD_CVV=\n", "HOTWHEELS_CARD_CVV=987\n"))
check("el CVV se toma sin reiniciar", len(p.datos()["tarjetas"]) == 1)
check("borrar_cvv lo vacía después de pagar", p.borrar_cvv() == 1 and p.datos()["tarjetas"] == []
      and "4111111111111111" in open(p.env, encoding="utf-8").read())

hijo = C.crear("hijo")
check("crear una cuenta deja la plantilla .env", os.path.exists(hijo.env) and "HOTWHEELS_CARD_CVV=" in open(hijo.env, encoding="utf-8").read())
check("crear no pisa un .env que ya existe", C.crear("hijo").env == hijo.env)
check("nombre de cuenta inválido se rechaza", not C.nombre_valido("../malo") and not C.nombre_valido("Con Espacio"))
with open(hijo.env, "a", encoding="utf-8") as f:
    f.write("HOTWHEELS_CARD_NUMBER=5555555555554444\nHOTWHEELS_CARD_EXPIRY=11/29\nHOTWHEELS_CARD_CVV=321\n")
check("listar trae principal e hijo", [c.nombre for c in C.listar()] == ["principal", "hijo"])
check("la cuenta extra NO hereda variables del proceso", (os.environ.__setitem__("HOTWHEELS_RFC", "X") or True)
      and C.obtener("hijo").datos()["rfc"] == "")
del os.environ["HOTWHEELS_RFC"]
ok, det = hijo.revisar_sesion()
check("sin cookies la sesión se marca como no iniciada", ok is False and "--cuenta hijo" in det, det)
semaforo = dict((t, ok) for ok, t in C.chequeo(p, revisar_red=False))
check("semáforo: tarjeta verde, CVV amarillo, RFC y teléfono verdes",
      semaforo.get("tarjeta •••• 1111 con vencimiento") is True
      and semaforo.get("CVV pendiente (ponlo antes del drop)") is None
      and semaforo.get("RFC válido") is True and semaforo.get("teléfono •••• 5678") is True, semaforo)
check("un navegador por cuenta", N.obtener(hijo) is N.obtener(C.obtener("hijo"))
      and N.obtener(hijo).perfil == hijo.perfil)

# ---------------- 2. Calendario ----------------
print("\n--- 2. Calendario de drops ---")
html = ('<meta property="og:title" content="Hot Wheels RLC Demon 170">'
        '<p>Coming Soon</p><p>Launches November 10, 2026 9:00 am PT</p>'
        '<div data-coming-soon-date="October 6 2026, 09:00:30 PDT"></div>')
check("lee 'Launches ... 9:00 am PT' (noviembre = PST)", DR.leer_lanzamiento(html) == datetime(2026, 11, 10, 17, 0, tzinfo=timezone.utc))
check("con horario de verano usa PDT", DR.leer_lanzamiento("Launches July 3, 2027 9:00 am PT") == datetime(2027, 7, 3, 16, 0, tzinfo=timezone.utc))
check("sin 'Launches' usa el atributo", DR.leer_lanzamiento('data-coming-soon-date="November 10 2026, 09:00:30 PST"')
      == datetime(2026, 11, 10, 17, 0, 30, tzinfo=timezone.utc))
check("página sin fecha -> None", DR.leer_lanzamiento("<h1>Add to Bag</h1>") is None)

futuro = datetime.now(timezone.utc) + timedelta(days=2)
html_f = html.replace("Launches November 10, 2026 9:00 am PT",
                      futuro.strftime("Launches %B %d, %Y ") + "9:00 am PT")
import hw_extras as EX  # noqa: E402
EX.agregar_vigilado(os.path.join(TMP, "vigilar.json"), "hot-wheels-rlc-demon-170", "prueba")
nuevos = D.revisar_calendario(obtener_html=lambda url: html_f)
check("propone el lanzamiento con botones por Telegram", len(nuevos) == 1 and BOTONES
      and BOTONES[-1][1][0][0]["callback_data"] == "pd:%d" % nuevos[0], BOTONES[-1:] if BOTONES else None)
check("no lo vuelve a proponer", D.revisar_calendario(obtener_html=lambda url: html_f) == [])
D._datos_pieza = lambda url: ("Demon 170", 610.0, 2, "")
r = D.accion_drop(nuevos[0], True)
d = DR.obtener(D.DB, nuevos[0])
check("'Programar disparo' lo deja programado con el límite de la página", d["estado"] == "programado"
      and d["cantidad"] == 2 and "principal, hijo" in r, r)

drop = dict(d, cuando=datetime(2026, 12, 1, 17, 0, tzinfo=timezone.utc), hechos=set())
en = lambda minutos: datetime(2026, 12, 1, 17, 0, tzinfo=timezone.utc) - timedelta(minutes=minutos)  # noqa: E731
check("a -40 min no hay pasos", DR.pasos_pendientes(drop, en(40)) == ([], False))
check("a -30 toca el chequeo", DR.pasos_pendientes(drop, en(30)) == (["chequeo"], False))
check("a -2 tocan chequeo, CVV y navegador si no corrieron",
      DR.pasos_pendientes(drop, en(2)) == (["chequeo", "cvv", "precalentar"], False))
check("en el minuto del drop dispara", DR.pasos_pendientes(dict(drop, hechos={"chequeo", "cvv", "precalentar"}),
                                                           en(0.25))[1] is True)
check("'No' lo descarta", "no programo" in D.accion_drop(D.DROPS.proponer(D.DB, "https://x/products/otra", "Otra", futuro)[0], False).lower())

# ---------------- 3. Disparo en paralelo ----------------
print("\n--- 3. Disparo en paralelo con todas las cuentas ---")
D.EVENTO_VENTANA_SEGUNDOS = 0.2
D.EVENTO_INTERVALO_SEGUNDOS = 0.05
D.NAVEGADOR.obtener = lambda cuenta=None: None
LLAMADAS = []


async def compra_lenta(url, proxy=None, cantidad=None, notificar=True, navegador=None, cuenta=None, **kw):
    LLAMADAS.append((cuenta.nombre, cantidad, time.monotonic()))
    await asyncio.sleep(1.0)
    return "🎉 Pedido realizado para: %s" % url


D.comprar_producto = compra_lenta
D.COLLECTHUB.registrar_compra = lambda **kw: (True, "ok")
AVISOS.clear()
t0 = time.monotonic()
ok = asyncio.run(D._intentar_evento(["https://creations.mattel.com/en-mx/products/demon"], cantidad=2))
tardo = time.monotonic() - t0
check("compra con las 2 cuentas", sorted(n for n, _, _ in LLAMADAS) == ["hijo", "principal"], LLAMADAS)
check("al mismo tiempo (no una tras otra)", tardo < 1.8, "%.1f s" % tardo)
check("con la cantidad del drop", all(c == 2 for _, c, _ in LLAMADAS))
check("cada aviso dice de qué cuenta es", any("[hijo]" in a for a in AVISOS) and any("[principal]" in a for a in AVISOS), AVISOS)
check("manda el borrador para Facebook/Instagram", any("Borrador para Facebook/Instagram" in a for a in AVISOS))

LLAMADAS.clear()
AVISOS.clear()


async def agotado(url, proxy=None, **kw):
    return "❌ Producto agotado: %s" % url
D.comprar_producto = agotado
asyncio.run(D._intentar_evento(["https://creations.mattel.com/en-mx/products/se-agoto-x"]))
vig = [e["handle"] for e in EX.listar_vigilados(os.path.join(TMP, "vigilar.json"))]
check("si se agota queda vigilada para el restock", "se-agoto-x" in vig, vig)
check("y lo dice en el aviso final, uno por cuenta", len(AVISOS) == 2 and any("restock" in a for a in AVISOS), AVISOS)
AVISOS.clear()


async def con_error(url, proxy=None, **kw):
    return "❌ Error inesperado: agotado() falló"
D.comprar_producto = con_error
asyncio.run(D._intentar_evento(["https://creations.mattel.com/en-mx/products/solo-error"]))
check("un error que menciona 'agotado' no la manda a restock",
      "solo-error" not in [e["handle"] for e in EX.listar_vigilados(os.path.join(TMP, "vigilar.json"))])

# ---------------- 4. Borrador ----------------
print("\n--- 4. Borrador de publicación ---")
texto, sugerido = D.borrador_publicacion("RLC Demon 170", 610.0, None, 2)
check("precio sugerido = costo x 1.8 redondeado a 50", sugerido == 1100, sugerido)
check("usa la reventa conocida si existe", D.borrador_publicacion("x", 610.0, 1450.0)[1] == 1450.0)
check("contacto por Messenger/Instagram, nunca WhatsApp", "Messenger" in texto and "Instagram" in texto
      and "whatsapp" not in texto.lower())

# ---------------- 5. Telegram ----------------
print("\n--- 5. Botones de Telegram ---")
llamadas = []
compras = []
acciones = {"obtener": lambda hid: {"titulo": "Pieza", "url": "u", "disponible": True, "precio_mxn": 600},
            "comprar": lambda hid, cant, forzar: compras.append(cant) or {"ok": True},
            "ignorar": lambda hid: None, "drop": lambda did, prog: ("programado %d" % did) if prog else "no"}
tg = T.Control("tok", 42, acciones, llamar=lambda m, **p: llamadas.append((m, p)) or {"ok": True}, log=lambda *a: None)


def toque(datos):
    return {"callback_query": {"id": "1", "data": datos, "from": {"id": 42},
                               "message": {"chat": {"id": 42}, "date": int(time.time())}}}


check("'Programar disparo' llama al calendario", tg.procesar(toque("pd:5")) == "drop_programado"
      and any(p.get("text") == "programado 5" for m, p in llamadas if m == "sendMessage"))
check("'No' lo descarta", tg.procesar(toque("pn:5")) == "drop_descartado")
tg.procesar(toque("c:1"))
filas = [p for m, p in llamadas if m == "sendMessage"][-1]["reply_markup"]["inline_keyboard"]
check("la confirmación ofrece 'Comprar el máximo'", filas[0][1]["callback_data"] == "cm:1", filas)
tg.procesar(toque("cm:1"))
check("'Comprar el máximo' pide cantidad 0 (= límite de la página)", compras[-1] == 0, compras)
tg.procesar(toque("cc:1:n"))
check("'Sí, comprar 1' sigue pidiendo 1", compras[-1] == 1, compras)

os.chdir(ORIGEN)
shutil.rmtree(TMP, ignore_errors=True)
print("\nFALLARON %d pruebas: %s" % (len(fallos), fallos) if fallos else "\nTODAS LAS PRUEBAS PASARON")
sys.exit(1 if fallos else 0)
