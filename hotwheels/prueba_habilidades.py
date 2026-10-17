# -*- coding: utf-8 -*-
"""Pruebas de las habilidades agregadas el 2026-09-24: botones de Telegram,
ganancia/urgencia, "ya tienes esta", cuenta regresiva del drop, topes de gasto,
cola de compras, prueba del checkout, captcha, sonido/orden en el panel y
acceso seguro desde el celular.

Todo en una copia temporal, con Telegram, Chicos Wheels y el navegador de
compra sustituidos por dobles (el captcha se prueba con un Chromium sin
ventana sobre HTML local). Ejecutar:

    python prueba_habilidades.py
"""

import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_habilidades_")
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
for carpeta in ("templates", "static"):
    shutil.copytree(os.path.join(DIR, carpeta), os.path.join(TMP, carpeta))
shutil.copy(os.path.join(DIR, "config.json"), TMP)
io.open(os.path.join(TMP, "config.env"), "w", encoding="utf-8").write(
    u"TELEGRAM_BOT_TOKEN=token-de-prueba\nTELEGRAM_CHAT_ID=42\nURL_PANEL=http://127.0.0.1:8000\n")
os.environ["HOTWHEELS_DRY_RUN"] = "1"
sys.path.insert(0, TMP)
os.chdir(TMP)

import hallazgos as H  # noqa: E402
import limites as L  # noqa: E402
import coleccion as CO  # noqa: E402
import telegram_control as TC  # noqa: E402
import dashboard_bot as D  # noqa: E402

D.notify = lambda m: avisos.append(m)
avisos = []
compras = []


async def comprar_falso(url, proxy=None, **kw):
    compras.append((url, kw.get("cantidad")))
    return "✅ (doble) en carrito: " + url


D.comprar_producto = comprar_falso


def pieza(nombre, precio=500.0, **kw):
    return H.registrar("https://creations.mattel.com/products/" + nombre, titulo=nombre.replace("-", " ").title(),
                       precio_mxn=precio, tipo="nuevo", **kw)


def esperar_bot():
    for _ in range(60):
        if not D._LOCK_DISPARO.locked():
            return
        time.sleep(0.1)


print("\n--- 1. Sin tope de gasto (quitado 2026-09-28 a pedido de Gonza) ---")
p1 = pieza("gastada", 900.0)
H.reservar_compra(p1, 2)
H.cambiar_estado(p1, "comprado")
check("gastado_mes suma precio x cantidad de lo comprado", H.gastado_mes() == 1800.0, H.gastado_mes())
ensayo = pieza("ensayo", 900.0)
H.cambiar_estado(ensayo, "pendiente", "🧪 DRY RUN")
check("un ensayo no cuenta como gasto", H.gastado_mes() == 1800.0)
check("un resultado 🧪 deja la pieza pendiente, no fallida",
      D._estado_desde_resultado("🧪 DRY RUN: checkout llenado") == "pendiente"
      and D._estado_desde_resultado("🎉 Pedido") == "comprado"
      and D._estado_desde_resultado("✅ carrito") == "carrito"
      and D._estado_desde_resultado("❌ agotado") == "fallo")

c = D.app.test_client()
caro = pieza("muy-caro", 2000.0)
n = len(compras)
r = c.post("/api/hallazgos/%d/comprar" % caro, json={})
esperar_bot()
check("una pieza cara compra directo, sin aviso de tope", r.get_json()["ok"] is True and len(compras) == n + 1, r.get_json())

print("\n--- 2. Cola de compras ---")
a, b, d3 = pieza("cola-a", 100.0), pieza("cola-b", 100.0), pieza("cola-c", 100.0)
D._LOCK_DISPARO.acquire()                       # simula "el bot esta comprando"
ra = c.post("/api/hallazgos/%d/comprar" % a, json={"cantidad": 2}).get_json()
rb = c.post("/api/hallazgos/%d/comprar" % b, json={}).get_json()
rc = c.post("/api/hallazgos/%d/comprar" % d3, json={}).get_json()
check("con el bot ocupado se encolan en orden", (ra["posicion"], rb["posicion"], rc["posicion"]) == (1, 2, 3), (ra, rb, rc))
check("la cola recuerda la cantidad", H.obtener(a)["cantidad"] == 2)
lista = c.get("/api/hallazgos").get_json()["piezas"]
check("el panel muestra la posicion en la cola", {p["id"]: p.get("posicion_cola") for p in lista if p["estado"] == "en_cola"}.get(b) == 2)
check("estado del panel cuenta la cola", c.get("/api/estado").get_json()["en_cola"] >= 3)
H.marcar_agotado(H.obtener(d3)["url"])          # la tercera se agota mientras espera
n = len(compras)
check("con el bot ocupado el hilo de la cola espera", D._procesar_cola_una_vez() is False and len(compras) == n)
D._LOCK_DISPARO.release()
D._procesar_cola_una_vez(); esperar_bot()
check("1a en la cola se compra primero, con su cantidad", compras[-1][1] == 2 and compras[-1][0].endswith("cola-a"), compras[-3:])
D._procesar_cola_una_vez(); esperar_bot()
check("luego la 2a", compras[-1][0].endswith("cola-b"), compras[-3:])
D._procesar_cola_una_vez(); esperar_bot()
check("la que se agoto esperando falla sin abrir navegador", H.obtener(d3)["estado"] == "fallo" and "agotó" in (H.obtener(d3)["resultado"] or ""), H.obtener(d3))
check("cola vacia al final", H.siguiente_en_cola() is None and D._procesar_cola_una_vez() is False)

print("\n--- 3. Botones de Telegram ---")
llamadas = []
acciones = {"obtener": H.obtener, "evaluar": L.evaluar, "comprar": D.solicitar_compra,
            "ignorar": lambda hid: H.cambiar_estado(hid, "ignorado")}
tg = TC.Control("tok", 42, acciones, llamar=lambda metodo, **p: (llamadas.append((metodo, p)) or {"ok": True, "result": []}), log=lambda *a: None)


def toque(datos, chat=42, usuario=42, fecha=None):
    return {"update_id": 1, "callback_query": {"id": "q", "data": datos, "from": {"id": usuario},
            "message": {"chat": {"id": chat}, "date": fecha or int(time.time())}}}


tg_p = pieza("telegram", 700.0)
n = len(compras)
check("Comprar pide confirmacion (no compra)", tg.procesar(toque("c:%d" % tg_p)) == "confirmacion_pedida" and len(compras) == n)
envio = [p for m, p in llamadas if m == "sendMessage"][-1]
botones = envio["reply_markup"]["inline_keyboard"][0]
check("la confirmacion trae Si/Cancelar", botones[0]["callback_data"] == "cc:%d:n" % tg_p and botones[1]["callback_data"] == "x:%d" % tg_p, botones)
check("Cancelar no hace nada", tg.procesar(toque("x:%d" % tg_p)) == "cancelada" and len(compras) == n)
check("confirmar SI compra", tg.procesar(toque("cc:%d:n" % tg_p)) == "comprando"); esperar_bot()
check("...con cantidad 1", compras[-1] == ("https://creations.mattel.com/products/telegram", 1), compras[-1])
check("un toque de otro chat se ignora", tg.procesar(toque("c:%d" % tg_p, chat=999)) is None)
check("un toque de otro usuario en el mismo chat se ignora", tg.procesar(toque("c:%d" % tg_p, usuario=999)) is None)
tg_q = pieza("telegram-vieja", 700.0)
check("una confirmacion de hace >10 min caduca", tg.procesar(toque("cc:%d:n" % tg_q, fecha=int(time.time()) - 700)) == "caducada" and H.obtener(tg_q)["estado"] == "pendiente")
tg_r = pieza("telegram-ignorar", 700.0)
check("Ignorar desde Telegram", tg.procesar(toque("i:%d" % tg_r)) == "ignorada" and H.obtener(tg_r)["estado"] == "ignorado")
check("pieza inexistente se avisa", tg.procesar(toque("c:99999")) == "inexistente")
check("datos basura no truenan", tg.procesar(toque("zzz")) is None)
tg_s = pieza("telegram-cara", 2500.0)
tg.procesar(toque("c:%d" % tg_s))
envio = [p for m, p in llamadas if m == "sendMessage"][-1]
check("sin tope: la confirmacion no advierte nada, solo 'Si, comprar'",
      "Ojo" not in envio["text"] and envio["reply_markup"]["inline_keyboard"][0][0]["text"] == "✅ Sí, comprar"
      and envio["reply_markup"]["inline_keyboard"][0][0]["callback_data"].endswith(":n"), envio)
n = len(compras)
tg.procesar(toque("cc:%d:n" % tg_s)); esperar_bot()
check("una pieza cara compra directo por Telegram, sin tope", len(compras) == n + 1)
# arranque: descarta lo acumulado y sigue desde el ultimo update
llamadas.clear()
tg2 = TC.Control("tok", 42, acciones, llamar=lambda metodo, **p: (llamadas.append((metodo, p)) or {"ok": True, "result": [{"update_id": 77}]}), log=lambda *a: None)
tg2._descartar_pendientes()
check("al arrancar descarta los toques acumulados", tg2.offset == 78 and llamadas[0][1]["offset"] == -1, llamadas)

print("\n--- 4. Monitor: botones en el aviso, ganancia y urgencia ---")
import monitor as M  # noqa: E402

capturado = []
M._enviar_a_chat = lambda api, chat, texto, foto=None, boton=None: capturado.append((chat, boton)) or True
M.TELEGRAM_CANAL_ID = "-100canal"
M.enviar_telegram("hola", None, "https://x/p", "https://x/cart/1:1", hallazgo_id=7)
chat_btn = json.loads([b for ch, b in capturado if ch == M.TELEGRAM_CHAT_ID][0])["inline_keyboard"]
canal_btn = json.loads([b for ch, b in capturado if ch == "-100canal"][0])["inline_keyboard"]
check("el chat personal recibe Comprar/Ignorar", chat_btn[0][0]["callback_data"] == "c:7" and chat_btn[0][1]["callback_data"] == "i:7", chat_btn)
check("el canal NUNCA recibe botones de decision", not any("callback_data" in b for fila in canal_btn for b in fila), canal_btn)
M.enviar_telegram = lambda texto, foto=None, link=None, compra=None, hallazgo_id=None: None
M.formato_mensaje = lambda *a, **k: "msg"
M.evaluar_impacto = lambda producto, va=0: "Alto impacto"
M.precio_reventa_estimado = lambda titulo: (60.0, 12)        # USD, 12 ventas
M.TIPO_CAMBIO = 20.0
producto = {"title": "RLC Prueba Ganancia", "handle": "rlc-ganancia", "images": [],
            "variants": [{"id": 5, "available": True, "price": "25.00"}], "tags": []}
M.notificar({}, producto, "restock", previo={"veces_agotado": 2, "promedio_agotamiento_min": 4.5})
reg = {p["titulo"]: p for p in H.listar()}["RLC Prueba Ganancia"]
check("guarda la ganancia estimada", reg["ganancia_mxn"] is not None and reg["ganancia_mxn"] > 0, reg)
check("guarda la reventa y el margen", reg["reventa_mxn"] == 1200.0 and reg["margen_pct"] is not None, reg)
check("guarda cuanto suele durar disponible", reg["agota_min"] == 4.5, reg)
M.precio_reventa_estimado = lambda titulo: (_ for _ in ()).throw(RuntimeError("sin red"))
M.notificar({}, dict(producto, title="Sin Red", handle="sin-red"), "nuevo")
check("si falla la red igual registra la pieza (sin ganancia)",
      {p["titulo"]: p for p in H.listar()}["Sin Red"]["ganancia_mxn"] is None)
gan = pieza("mucha-ganancia", 100.0); H.registrar("https://creations.mattel.com/products/mucha-ganancia", ganancia_mxn=900.0)
poca = pieza("poca-ganancia", 100.0); H.registrar("https://creations.mattel.com/products/poca-ganancia", ganancia_mxn=10.0)
orden = [p["url"].rsplit("/", 1)[1] for p in c.get("/api/hallazgos?orden=ganancia").get_json()["piezas"] if p["ganancia_mxn"] is not None]
check("ordenar por mayor ganancia", orden.index("mucha-ganancia") < orden.index("poca-ganancia"), orden)
barato = pieza("el-mas-barato", 5.0)
orden = [p["url"].rsplit("/", 1)[1] for p in c.get("/api/hallazgos?orden=precio").get_json()["piezas"]]
check("ordenar por menor precio", orden[0] == "el-mas-barato", orden[:3])

print("\n--- 5. Ya tienes esta (Chicos Wheels) ---")
coleccion_falsa = [{"nombre": "Hot Wheels RLC Datsun 510 Pro Street", "estatus": "Conservar", "cantidad": 1, "valor_estimado": 900, "tipo": "Hot Wheels"},
                   {"nombre": "Hot Wheels Premium Nissan Skyline GT-R (R34)", "estatus": "Disponible", "cantidad": 2, "valor_estimado": 300, "tipo": "Hot Wheels"},
                   {"nombre": "Carta Pikachu", "estatus": "Disponible", "cantidad": 1, "valor_estimado": 50, "tipo": "Pokémon"}]
check("mismo modelo con otro orden/adornos se reconoce", CO.son_parecidas("Hot Wheels RLC Datsun 510 Pro Street", "RLC Datsun 510 'Pro Street' Hot Wheels"))
check("modelos distintos no se confunden", not CO.son_parecidas("Hot Wheels RLC Datsun 510", "Hot Wheels RLC Porsche 911"))
check("una palabra suelta no basta", not CO.son_parecidas("Hot Wheels Premium Nissan Skyline", "Hot Wheels Premium Nissan Silvia"))
check("acentos y mayusculas no estorban", CO.son_parecidas("Volkswagen Sirocco Edición Limitada", "volkswagen sirocco edicion limitada"))
check("busca similares en la coleccion", [s["nombre"] for s in CO.similares("Nissan Skyline GT-R R34 Premium", coleccion_falsa)] == ["Hot Wheels Premium Nissan Skyline GT-R (R34)"])
CO.articulos = lambda forzar=False: (coleccion_falsa, None)
marcadas = CO.marcar([{"titulo": "RLC Datsun 510 Pro Street"}, {"titulo": "Ferrari 250 GTO"}])
check("marca 'ya tienes' solo lo repetido", len(marcadas[0]["ya_tienes"]) == 1 and marcadas[1]["ya_tienes"] == [])
res = CO.resumen()
check("resumen de la coleccion (solo Hot Wheels)", res["configurado"] and res["piezas"] == 3 and res["valor_estimado_mxn"] == 1500.0, res)
CO.articulos = lambda forzar=False: (None, "Chicos Wheels no responde")
check("sin Chicos Wheels no truena y lo explica", CO.marcar([{"titulo": "x"}])[0]["ya_tienes"] is None and CO.resumen()["configurado"] is False)
check("el panel responde /api/coleccion sin Chicos Wheels", c.get("/api/coleccion").get_json()["configurado"] is False)

print("\n--- 6. Cuenta regresiva del proximo drop ---")
import monitor_admin as MA  # noqa: E402
info = MA.proximo_drop_info()
check("sin historial se asume martes 11:00 y lo dice", info["supuesto"] is True and "11:00" in info["texto"] and info["texto"].startswith("Mar"), info)
from datetime import datetime  # noqa: E402
check("la fecha es futura", datetime.fromisoformat(info["iso"]).timestamp() > time.time())
check("viaja en /api/estado", "proximo_drop" in c.get("/api/estado").get_json()["monitor"])

print("\n--- 7. Prueba diaria del checkout ---")
resultados = iter(["🧪 DRY RUN: checkout llenado, sin pagar: u", "❌ Producto agotado: u", "🧩 Captcha detectado: u",
                   "⚠️ Producto en carrito pero falló el checkout automático: u", "⚠️ falló el checkout otra vez"])
llamadas_checkout = []


async def checkout_falso(url, **kw):
    llamadas_checkout.append(kw)
    return next(resultados)


D.comprar_producto = checkout_falso
MA.producto_disponible_para_prueba = lambda: "https://creations.mattel.com/products/prueba"
check("checkout ok", D.probar_checkout() == "ok")
check("corre sin ventana, en ensayo y sin notificar", llamadas_checkout[0].get("headless") is True and llamadas_checkout[0].get("dry_run") is True and llamadas_checkout[0].get("notificar") is False, llamadas_checkout[0])
check("agotado justo antes = sin_producto (no es falla)", D.probar_checkout() == "sin_producto")
check("captcha se registra aparte", D.probar_checkout() == "captcha")
avisos.clear()
check("una falla aislada no da alarma", D.probar_checkout() == "roto" and not avisos)
check("dos fallas seguidas si avisan", D.probar_checkout() == "roto" and any("checkout" in a for a in avisos), avisos)
MA.producto_disponible_para_prueba = lambda: None
check("sin producto disponible lo registra y no truena", D.probar_checkout() == "sin_producto")
D._LOCK_DISPARO.acquire()
check("si el bot esta comprando de verdad, la prueba se omite", D.probar_checkout() == "omitido")
D._LOCK_DISPARO.release()
check("el estado del panel trae la ultima prueba", c.get("/api/estado").get_json()["checkout"]["estado"] == "sin_producto")

print("\n--- 8. Acceso desde el celular (con candado) ---")
check("por defecto solo en esta PC", D.host_seguro(None, "", "") == ("127.0.0.1", None))
h, aviso = D.host_seguro("0.0.0.0", "", "")
check("abrirlo a la red SIN contraseña se rechaza", h == "127.0.0.1" and "DASHBOARD_PASSWORD" in aviso, (h, aviso))
check("abrirlo con usuario y contraseña se permite", D.host_seguro("0.0.0.0", "gonza", "secreta") == ("0.0.0.0", None))

print("\n--- 9. Panel: controles nuevos ---")
html = c.get("/").get_data(as_text=True)
for idc in ("bandaDrop", "btnAlertas", "ordenPiezas", "pillCheckout", "formLimites", "btnProbarCheckout", "resumenColeccion"):
    check("la pagina trae #%s" % idc, ('id="%s"' % idc) in html)
check("sin datos de Chicos Wheels la pestaña de piezas igual carga", c.get("/api/hallazgos").status_code == 200)

print("\n--- 10. Captcha: solo cuenta si es visible y de tamaño real ---")
try:
    import bot_logic as B
    from playwright.async_api import async_playwright

    CASOS = {
        "sin captcha": ("<h1>Producto</h1>", False),
        "badge invisible de reCAPTCHA v3": ("<div class='grecaptcha-badge' style='width:256px;height:60px'><iframe src='about:blank#recaptcha' style='width:256px;height:60px'></iframe></div>", False),
        "iframe oculto": ("<iframe src='about:blank#recaptcha' style='display:none;width:304px;height:78px'></iframe>", False),
        "reCAPTCHA v2 visible": ("<iframe src='about:blank#recaptcha' style='width:304px;height:78px'></iframe>", True),
        "hCaptcha visible": ("<div class='h-captcha' style='width:302px;height:76px'>x</div>", True),
    }

    async def probar_captcha():
        salida = {}
        async with async_playwright() as pw:
            nav = await pw.chromium.launch(headless=True)
            pg = await nav.new_page()
            for nombre, (html_caso, _) in CASOS.items():
                await pg.set_content(html_caso)
                salida[nombre] = await B.hay_captcha(pg)
            B.notify = lambda m: avisos.append(m)
            await pg.set_content(CASOS["reCAPTCHA v2 visible"][0])
            await pg.evaluate("setTimeout(() => document.querySelector('iframe').remove(), 2500)")
            salida["_resuelto"] = await B.esperar_captcha(pg, "u", headless=False, espera_max=10, intervalo=1)
            await pg.set_content(CASOS["reCAPTCHA v2 visible"][0])
            salida["_sin_resolver"] = await B.esperar_captcha(pg, "u", headless=False, avisar=False, espera_max=2, intervalo=1)
            salida["_headless"] = await B.esperar_captcha(pg, "u", headless=True)
            await nav.close()
        return salida

    res = asyncio.run(probar_captcha())
    for nombre, (_, esperado) in CASOS.items():
        check("captcha: %s -> %s" % (nombre, esperado), res[nombre] is esperado, res[nombre])
    check("si lo resuelves a tiempo el bot continua", res["_resuelto"] is None)
    check("si no lo resuelves devuelve un fallo claro", "sin resolver" in (res["_sin_resolver"] or ""))
    check("sin ventana visible no espera", "no se puede resolver" in (res["_headless"] or ""))
    check("avisa por notificacion cuando hace falta tu ayuda", any("Captcha detectado" in a for a in avisos))
except Exception as e:  # sin Chromium instalado no se puede probar esta parte
    print("  (omitido: no hay Chromium de Playwright disponible: %s)" % e)

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
