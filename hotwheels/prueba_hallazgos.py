# -*- coding: utf-8 -*-
"""Pruebas del flujo fusionado monitor -> piezas encontradas -> panel -> compra.

Todo corre en una copia temporal del proyecto (su propio bot.db) y con el
navegador/Telegram sustituidos por dobles: nunca compra, nunca manda mensajes
y nunca toca el bot.db ni el estado.json reales. Ejecutar:

    python prueba_hallazgos.py
"""

import io
import os
import shutil
import sys
import tempfile
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_hallazgos_")
fallos = []


def check(nombre, condicion, detalle=""):
    if condicion:
        print("  OK    %s" % nombre)
    else:
        print("  FALLO %s  %s" % (nombre, detalle))
        fallos.append(nombre)


# Copia del codigo + plantillas (sin datos reales ni secretos).
for f in os.listdir(DIR):
    if f.endswith(".py") and not f.startswith("prueba_"):
        shutil.copy(os.path.join(DIR, f), TMP)
for carpeta in ("templates", "static"):
    shutil.copytree(os.path.join(DIR, carpeta), os.path.join(TMP, carpeta))
shutil.copy(os.path.join(DIR, "config.json"), TMP)   # no sensible (solo flags de notificacion)
io.open(os.path.join(TMP, "config.env"), "w", encoding="utf-8").write(
    u"TELEGRAM_BOT_TOKEN=token-de-prueba\nTELEGRAM_CHAT_ID=1\nURL_PANEL=http://127.0.0.1:8000\n")
os.environ["HOTWHEELS_DRY_RUN"] = "1"
sys.path.insert(0, TMP)
os.chdir(TMP)

import hallazgos as H  # noqa: E402

print("\n--- 1. Tabla de hallazgos: alta, refresco y reapertura ---")
U = "https://creations.mattel.com/products/rlc-prueba"
i = H.registrar(U, titulo="RLC Prueba", precio_mxn=900, tipo="nuevo", impacto="Alto impacto", deseado=True)
check("alta devuelve id", isinstance(i, int))
check("nace pendiente y disponible", H.obtener(i)["estado"] == "pendiente" and H.obtener(i)["disponible"] == 1)
check("misma URL no duplica", H.registrar(U, titulo="RLC Prueba", precio_mxn=880, tipo="restock") == i)
check("refresca precio y cuenta veces visto", H.obtener(i)["precio_mxn"] == 880 and H.obtener(i)["veces_visto"] == 2)
H.cambiar_estado(i, "ignorado")
H.registrar(U, titulo="RLC Prueba", tipo="restock")
check("ignorada que reaparece al instante NO se reabre sola", H.obtener(i)["estado"] == "ignorado")
H.marcar_agotado(U)
check("agotado se refleja", H.obtener(i)["disponible"] == 0)
H.registrar(U, titulo="RLC Prueba", tipo="restock")
check("agotada que vuelve = oportunidad nueva (pendiente otra vez)", H.obtener(i)["estado"] == "pendiente")
H.cambiar_estado(i, "comprado")
H.marcar_agotado(U)
H.registrar(U, tipo="restock")
check("una pieza comprada nunca se reabre sola", H.obtener(i)["estado"] == "comprado")
try:
    H.cambiar_estado(i, "inventado")
    check("estado invalido se rechaza", False)
except ValueError:
    check("estado invalido se rechaza", True)

print("\n--- 2. Anti doble compra ---")
j = H.registrar("https://creations.mattel.com/products/otra", titulo="Otra", tipo="nuevo")
check("primera reserva gana", H.reservar_compra(j) is True)
check("segunda reserva pierde", H.reservar_compra(j) is False)

print("\n--- 3. monitor.notificar registra lo comprable y silencia el ruido ---")
import monitor as M  # noqa: E402

enviados = []
M.enviar_telegram = lambda texto, foto=None, link=None, compra=None, hallazgo_id=None: enviados.append((texto, hallazgo_id))
M.precio_reventa_estimado = lambda titulo: (None, 0)   # sin red
M.formato_mensaje = lambda *a, **k: "mensaje de prueba"
M.evaluar_impacto = lambda producto, va=0: ("Bajo interes" if "gorra" in producto["title"].lower() else "Alto impacto")


def producto(titulo, handle, disponible=True, precio="20.00"):
    return {"title": titulo, "handle": handle, "variants": [{"id": 111, "available": disponible, "price": precio}],
            "images": [{"src": "https://cdn/x_800x.jpg"}], "tags": []}


estado = {}
M.notificar(estado, producto("RLC Datsun", "rlc-datsun"), "restock")
piezas = {p["url"]: p for p in H.listar()}
url_d = M.BASE_URL + "/products/rlc-datsun"
check("restock disponible queda registrado", url_d in piezas, list(piezas))
check("guarda el carrito directo", piezas[url_d]["url_carrito"].endswith("/cart/111:1"), piezas[url_d])
check("precio en pesos calculado", (piezas[url_d]["precio_mxn"] or 0) > 0, piezas[url_d]["precio_mxn"])
check("el aviso de Telegram apunta al panel", "http://127.0.0.1:8000" in enviados[-1][0], enviados[-1])
check("el aviso lleva el id de la pieza (botones Comprar/Ignorar)", enviados[-1][1] == piezas[url_d]["id"], enviados[-1])
n_antes = len(H.listar())
M.notificar(estado, producto("Gorra Hot Wheels", "gorra"), "nuevo")
check("bajo interes se silencia y no se registra", len(H.listar()) == n_antes)
M.notificar(estado, producto("Otro auto", "otro-auto", disponible=False), "proximamente")
check("lo no disponible no se registra", len(H.listar()) == n_antes)
M.notificar(estado, producto("RLC Datsun", "rlc-datsun", disponible=False), "agotado")
check("agotado marca la tarjeta como agotada", {p["url"]: p for p in H.listar()}[url_d]["disponible"] == 0)

print("\n--- 4. Panel: rutas y compra con doble del navegador ---")
import dashboard_bot as D  # noqa: E402

compras = []


async def comprar_falso(url, proxy=None, **kw):
    compras.append((url, kw.get("cantidad")))
    return "✅ (doble) en carrito: " + url


D.comprar_producto = comprar_falso
D.notify = lambda m: None
c = D.app.test_client()


def esperar_bot():
    for _ in range(50):
        if not D._LOCK_DISPARO.locked():
            return
        time.sleep(0.1)


r = c.get("/")
check("la pagina principal se sirve", r.status_code == 200)
html = r.get_data(as_text=True)
check("trae las 4 pestañas", all(('data-vista="%s"' % v) in html for v in ("piezas", "links", "historial", "ajustes")))
check("ya no trae el disparo automatico", "Armar" not in html and "/armar" not in html)
check("rutas del puente viejo ya no existen",
      c.post("/api/queue_priority", json={"url": "x"}).status_code in (404, 405))

e = c.get("/api/estado").get_json()
check("/api/estado trae monitor, bot y conteos", {"monitor", "comprando", "hallazgos", "ensayo"} <= set(e), e)
check("modo ensayo detectado del entorno", e["ensayo"] is True)

k = H.registrar("https://creations.mattel.com/products/comprable", titulo="Comprable", precio_mxn=500, tipo="nuevo")
pend = c.get("/api/hallazgos").get_json()["piezas"]
check("lista las piezas por decidir", any(p["id"] == k for p in pend))
r = c.post("/api/hallazgos/%d/comprar" % k, json={"cantidad": 3})
check("comprar responde ok", r.get_json()["ok"] is True, r.get_json())
esperar_bot()
check("compro esa URL con la cantidad pedida",
      bool(compras) and compras[-1] == ("https://creations.mattel.com/products/comprable", 3), compras)
check("compro UNA sola URL (no run_all)", len(compras) == 1, compras)
check("estado final = carrito (el doble devolvio ✅)", H.obtener(k)["estado"] == "carrito", H.obtener(k))
check("candado liberado", not D._LOCK_DISPARO.locked())
check("comprar una pieza inexistente da 404", c.post("/api/hallazgos/9999/comprar", json={}).status_code == 404)

k2 = H.registrar("https://creations.mattel.com/products/ocupado", titulo="Ocupado", tipo="nuevo")
D._LOCK_DISPARO.acquire()
r = c.post("/api/hallazgos/%d/comprar" % k2, json={})
check("con una compra en curso la pieza entra a la cola (no rebota)",
      r.get_json().get("en_cola") is True and H.obtener(k2)["estado"] == "en_cola", r.get_json())
D._LOCK_DISPARO.release()
c.post("/api/hallazgos/%d/restaurar" % k2, json={})
check("sacar de la cola la deja pendiente", H.obtener(k2)["estado"] == "pendiente")
ok_ign = c.post("/api/hallazgos/%d/ignorar" % k2, json={}).get_json()["ok"] and H.obtener(k2)["estado"] == "ignorado"
ok_res = c.post("/api/hallazgos/%d/restaurar" % k2, json={}).get_json()["ok"] and H.obtener(k2)["estado"] == "pendiente"
check("ignorar y restaurar", ok_ign and ok_res)
hist = c.get("/api/hallazgos?ver=historial").get_json()["piezas"]
check("el historial trae lo ya resuelto", any(p["id"] == k for p in hist) and not any(p["id"] == k2 for p in hist))

pid = D.add_product("https://creations.mattel.com/products/mi-link")
r = c.post("/comprar_url/%d" % pid, json={})
esperar_bot()
check("comprar desde 'Mis links' funciona", r.get_json()["ok"] and compras[-1][0].endswith("mi-link"), compras)

print("\n--- 5. Piezas y ajustes conviven en la misma API ---")
check("administrar colecciones desde el panel", len(c.get("/api/monitor/colecciones").get_json()["entradas"]) >= 1)

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
