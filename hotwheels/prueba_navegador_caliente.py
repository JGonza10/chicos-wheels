# -*- coding: utf-8 -*-
"""Pruebas del navegador caliente y la sesion de Mattel (2026-10-18).

Chromium real contra una tienda Mattel FALSA: todas las peticiones a
creations.mattel.com y al iframe de la tarjeta se contestan desde aqui
(context.route). Nunca sale a internet ni paga: todo en DRY RUN.

  1. Precalentar deja la pieza cargada; comprar la usa ya lista
  2. El carrito con sobras de otro intento se vacia antes de agregar
  3. Con sesion (sin campo de correo ni direccion) el checkout no se atora
  4. Telegram y el monitor piden precalentar
  5. Piezas RLC sin sesion: el error dice que hacer

Ejecutar:  python prueba_navegador_caliente.py
"""

import json
import os
import shutil
import sys
import tempfile
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_caliente_")
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
with open(os.path.join(TMP, "config.json"), "w") as f:
    json.dump({"notifications": {"email": {"enabled": False}, "whatsapp": {"enabled": False}}}, f)
os.environ.update({"HOTWHEELS_DRY_RUN": "1", "HOTWHEELS_USER_EMAIL": "prueba@x.mx",
                   "HOTWHEELS_CARD_NUMBER": "4111111111111111", "HOTWHEELS_CARD_EXPIRY": "12/30",
                   "HOTWHEELS_CARD_CVV": "123", "HOTWHEELS_CARD_NAME": "Prueba",
                   "HOTWHEELS_SHIP_STATE": "Ciudad de Mexico"})
sys.path.insert(0, TMP)
os.chdir(TMP)

import bot_logic as B  # noqa: E402
import navegador as N  # noqa: E402

B.notify = lambda m: None

# ---------------- tienda falsa ----------------
TIENDA = {"carrito": 2, "con_sesion": False, "visitas_producto": 0, "limpiezas": 0}

PRODUCTO = """<html><body>
<a class="header__cart-count-wrapper">{n}</a>
<script>window.__st = {{cid: {cid}}};</script>
<button class="product__add-to-cart" onclick="fetch('/en-mx/cart/add.js',{{method:'POST'}}).then(r=>r.json()).then(c=>{{document.querySelector('.header__cart-count-wrapper').textContent=c.item_count}})">Add to Bag</button>
</body></html>"""
CARRITO = """<html><body><button class="cart__checkout" onclick="location.href='/checkouts/cn/abc'">Checkout</button></body></html>"""
CHECKOUT = """<html><body>
{email}
<select name="countryCode"><option>Mexico</option></select>
{direccion}
<input type="checkbox" id="basic-creditCards">
<script>setTimeout(() => {{ for (const m of ['number-ltr','expiry-ltr','verification_value-ltr','name-ltr']) {{
 const f = document.createElement('iframe'); f.src = 'https://checkout.pci.shopifyinc.com/' + m; document.body.appendChild(f); }} }}, 300);</script>
<button id="checkout-pay-button" onclick="location.href='/checkouts/cn/abc/thank_you'">Pagar</button>
</body></html>"""
DIRECCION = """<input name="firstName"><input name="lastName"><input name="address1"><input name="address2">
<input name="city"><input name="postalCode"><input name="phone">
<select name="zone"><option>Jalisco</option><option>Ciudad de Mexico</option></select>"""
CAMPO_TARJETA = {"number-ltr": "number", "expiry-ltr": "expiry",
                 "verification_value-ltr": "verification_value", "name-ltr": "name"}


async def responder(route):
    url = route.request.url
    html = lambda cuerpo: route.fulfill(status=200, content_type="text/html", body=cuerpo)  # noqa: E731
    js = lambda datos: route.fulfill(status=200, content_type="application/json", body=json.dumps(datos))  # noqa: E731
    if "checkout.pci.shopifyinc.com" in url:
        campo = CAMPO_TARJETA[url.rsplit("/", 1)[1]]
        return await html(f"<input name='{campo}'>")
    if url.endswith("/cart.js"):
        return await js({"item_count": TIENDA["carrito"]})
    if url.endswith("/cart/clear.js"):
        TIENDA["carrito"] = 0
        TIENDA["limpiezas"] += 1
        return await js({"item_count": 0})
    if url.endswith("/cart/add.js"):
        TIENDA["carrito"] += 1
        return await js({"item_count": TIENDA["carrito"]})
    if "/products/" in url:
        TIENDA["visitas_producto"] += 1
        return await html(PRODUCTO.format(n=TIENDA["carrito"], cid=123 if TIENDA["con_sesion"] else "null"))
    if url.endswith("/cart"):
        return await html(CARRITO)
    if url.endswith("/thank_you"):
        return await html("<h1>Thank you!</h1><p>Confirmation #MX777</p><p>Subtotal $1,100.00</p>"
                          "<p>Shipping $150.00</p><p>Total MXN $1,250.00</p>")
    if "/checkouts/" in url:
        sesion = TIENDA["con_sesion"]
        return await html(CHECKOUT.format(email="" if sesion else '<input id="email">',
                                          direccion="" if sesion else DIRECCION))
    return await route.fulfill(status=404, body="")


async def iniciar_falso():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
    except Exception:
        browser = await pw.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
    ctx = await browser.new_context()
    await ctx.route("https://creations.mattel.com/**", responder)
    await ctx.route("https://checkout.pci.shopifyinc.com/**", responder)
    return pw, ctx


URL = "https://creations.mattel.com/en-mx/products/hot-wheels-rlc-exclusive-rwb-porsche-930-jjy69"
nav = N.NavegadorCaliente(headless=True, iniciar=iniciar_falso, log=lambda *a: None)

print("\n--- 1. Precalentar y comprar sobre la pagina lista ---")
check("precalentar abre la pieza", nav.precalentar(URL).result(60) == "ok", nav.paginas)
check("queda una pagina lista", URL in nav.paginas and nav.estado()["paginas"] == 1)
check("precalentar otra vez no abre otra", nav.precalentar(URL).result(30) == "ya" and TIENDA["visitas_producto"] == 1)
visitas = TIENDA["visitas_producto"]
t = time.monotonic()
r = nav.comprar(URL, cantidad=1, permitir_pausa=False).result(90)
tardo = time.monotonic() - t
check("el ensayo llega hasta antes de pagar", r.startswith("🧪 DRY RUN"), r)
check("usa la pagina precalentada", "navegador (caliente)" in r, r)

print("\n--- 2. Carrito con sobras ---")
check("vacia lo que quedo de otro intento", TIENDA["limpiezas"] == 1, TIENDA)
check("y recarga para no confundir el contador", TIENDA["visitas_producto"] == visitas + 1, TIENDA)
check("el carrito queda solo con esta pieza", TIENDA["carrito"] == 1, TIENDA)
check("la pagina usada se cierra", URL not in nav.paginas)
print("    (ensayo completo con pagina caliente: %.1f s en Chromium local)" % tardo)

print("\n--- 3. Checkout con sesion de Mattel ---")
TIENDA.update(carrito=0, con_sesion=True)
r = nav.comprar(URL, cantidad=1, permitir_pausa=False).result(90)
check("sin campo de correo ni direccion no se atora", r.startswith("🧪 DRY RUN"), r)
check("sin pagina precalentada abre una nueva", "navegador " in r and "caliente" not in r.split("(", 1)[1], r)


async def ver_sesion():
    page = await nav.contexto.new_page()
    await page.goto(URL)
    activa = await B.sesion_mattel_activa(page)
    await page.close()
    return activa
check("detecta la sesion iniciada", nav.enviar(ver_sesion()).result(30) is True)

print("\n--- 4. Quien pide precalentar ---")
import telegram_control as TC  # noqa: E402
pedidas = []
tg = TC.Control("tok", 42, {"obtener": lambda hid: {"titulo": "RWB", "disponible": 1, "url": URL},
                            "precalentar": pedidas.append},
                llamar=lambda metodo, **p: {"ok": True}, log=lambda *a: None)
tg.procesar({"callback_query": {"id": "q", "data": "c:7", "from": {"id": 42}, "message": {"chat": {"id": 42}}}})
check("al tocar Comprar en Telegram se precalienta", pedidas == [URL], pedidas)

io_cfg = os.path.join(TMP, "config.env")
open(io_cfg, "w").write("TELEGRAM_BOT_TOKEN=t\nTELEGRAM_CHAT_ID=1\n")
import monitor as M  # noqa: E402
M.enviar_express = lambda *a, **k: True
M.enviar_telegram = lambda *a, **k: None
M.precio_reventa_estimado = lambda titulo: (None, 0)
M.HALLAZGOS = None
M.DESEADOS = ["rwb"]
precalentadas = []
M.AL_URGENTE = precalentadas.append
M.notificar({}, {"id": 1, "title": "RLC RWB Porsche 930", "handle": "rlc-rwb", "tags": [], "images": [],
                 "variants": [{"id": 9, "available": True, "price": "40.00"}]}, "nuevo")
check("aviso urgente del monitor -> navegador listo", precalentadas == [M.BASE_URL + "/products/rlc-rwb"], precalentadas)

print("\n--- 5. Pieza RLC sin sesion ---")
TIENDA.update(con_sesion=False)
PRODUCTO_SIN_BOTON = "<html><body><p>Members only {n}</p><script>window.__st={{cid:{cid}}}</script></body></html>"
PRODUCTO_ORIGINAL = PRODUCTO
PRODUCTO = PRODUCTO_SIN_BOTON
r = nav.comprar(URL, cantidad=1, permitir_pausa=False).result(90)
check("explica que falta la sesion RLC", "iniciar_sesion_mattel.py" in r, r)
PRODUCTO = PRODUCTO_ORIGINAL
check("solo para piezas RLC", B.es_pieza_rlc(URL) and not B.es_pieza_rlc("https://creations.mattel.com/products/hw-datsun"))

print("\n--- 6. Pago (tienda falsa): lee pedido y total ---")
TIENDA.update(carrito=0, con_sesion=False)
r = nav.comprar(URL, cantidad=1, dry_run=False, permitir_pausa=False, notificar=False).result(90)
check("el resultado trae el pedido y lo cobrado", "🎉" in r and "Pedido #MX777" in r and "Cobrado MXN $1,250.00" in r, r)
check("y la liga del estado del pedido", "Estado: https://creations.mattel.com/checkouts/cn/abc/thank_you" in r, r)
import pedidos_mattel as PM  # noqa: E402
check("el inventario lo puede volver a leer", PM.datos_del_resultado(r)["total"] == 1250.0)

print("\n--- 7. Limpieza ---")
nav.precalentar(URL).result(30)
nav.enviar(nav.limpiar(ahora=time.monotonic() + N.MINUTOS_PAGINA * 60 + 1)).result(30)
check("la pagina que nadie uso se cierra", not nav.paginas)
nav._ultimo_uso = time.monotonic() - N.MINUTOS_NAVEGADOR * 60 - 1
nav.enviar(nav.limpiar()).result(30)
check("y el navegador sin uso tambien", nav.estado()["abierto"] is False)

os.environ["HOTWHEELS_PRECALENTAR"] = "0"
check("se puede apagar", N.obtener() is None)

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
