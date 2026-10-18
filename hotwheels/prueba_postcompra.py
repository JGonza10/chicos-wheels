# -*- coding: utf-8 -*-
"""Pruebas de lo que pasa despues de pagar (2026-10-18):

  1. Leer la confirmacion de Mattel (pedido y total) y la pagina del envio
  2. El inventario guarda lo que de verdad se cobro (MXN y USD)
  3. Seguimiento del envio: guia y fecha de llegada al inventario
  4. Resumen semanal: cronometro, piezas que se escaparon y dinero

Todo en una copia temporal (bot.db propio) y sin red: el inventario es un
doble en memoria. Ejecutar:  python prueba_postcompra.py
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import date

DIR = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_postcompra_")
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
sys.path.insert(0, TMP)
os.chdir(TMP)

import collecthub_bridge as CB  # noqa: E402
import pedidos_mattel as P  # noqa: E402

print("\n--- 1. Lectores ---")
c = P.leer_confirmacion("Thank you!\nOrder #MX12345\nSubtotal $1,100.00\nShipping $150.00\nTotal MXN $1,250.00")
check("pedido y total (el ultimo Total, no el Subtotal)", c == {"pedido": "MX12345", "total": 1250.0, "moneda": "MXN"}, c)
c = P.leer_confirmacion("Pedido número: 98765\nSubtotal $40.00 USD\nTotal $45.50 USD")
check("en español y en dolares", c == {"pedido": "98765", "total": 45.5, "moneda": "USD"}, c)
check("si no lo ve, no inventa", P.leer_confirmacion("Gracias por tu compra") == {"pedido": None, "total": None, "moneda": None})
e = P.leer_envio("On its way\nDHL Express\nTracking number: 1234567890\nEstimated delivery: Oct 24", hoy=date(2026, 10, 18))
check("guia, paqueteria y llegada", e == {"guia": "1234567890", "paqueteria": "DHL", "llega": "2026-10-24", "entregado": False}, e)
e = P.leer_envio("Paquetería: Estafeta. Número de guía: 8055912345678901. Llega el 3 de noviembre", hoy=date(2026, 10, 18))
check("en español", e["guia"] == "8055912345678901" and e["llega"] == "2026-11-03" and e["paqueteria"] == "Estafeta", e)
check("enero leido en diciembre es el año que entra",
      P.leer_envio("Estimated delivery: Jan 5", hoy=date(2026, 12, 30))["llega"] == "2027-01-05")
check("entregado", P.leer_envio("Delivered")["entregado"] is True)
check("una palabra sin numeros no es guia", P.leer_envio("Tracking: PENDIENTE")["guia"] is None)

print("\n--- 2. Costo real en el inventario ---")
creados, parches, notas_actuales = [], [], {}


class R:
    def __init__(self, datos, status=200):
        self.status_code, self._d = status, datos

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def inventario(metodo, ruta, cuerpo=None):
    if metodo == "POST" and ruta == "/api/articulos":
        creados.append(cuerpo)
        notas_actuales["A%d" % len(creados)] = cuerpo["notas"]
        return R({"id": "A%d" % len(creados)}, 201)
    if metodo == "GET" and ruta.startswith("/api/articulos/"):
        return R({"notas": notas_actuales[ruta.rsplit("/", 1)[1]]})
    if metodo == "PATCH":
        parches.append((ruta, cuerpo))
        return R({})
    return R({}, 404)


CB.EN_PROCESO = inventario
CB.init_db()
resultado = ("🎉 Pedido realizado para: https://creations.mattel.com/en-mx/products/rwb | "
             "Pedido #MX777 | Cobrado MXN $2,500.00 | Estado: https://creations.mattel.com/x/orders/tok\n⏱ 20.0 s")
ok, msg = CB.registrar_compra("https://creations.mattel.com/en-mx/products/rwb", "RLC RWB Porsche 930",
                              1800.0, origen="panel", cantidad=2, pedido=resultado)
alta = creados[-1]
check("se registra", ok, msg)
check("precio de compra = lo cobrado ÷ piezas", alta["precio_compra"] == 1250.0, alta["precio_compra"])
check("las notas dicen pedido, cobro y estado",
      "Pedido Mattel #MX777" in alta["notas"] and "Cobrado MXN $2,500.00" in alta["notas"]
      and "Estado del pedido: https://creations.mattel.com/x/orders/tok" in alta["notas"]
      and "Origen: bot (panel)" in alta["notas"], alta["notas"])

sys.modules["monitor"] = type(sys)("monitor")
sys.modules["monitor"].TIPO_CAMBIO = 20.0
CB.registrar_compra("https://creations.mattel.com/products/usd", "Pieza USD", 999.0, cantidad=1,
                    pedido="🎉 Pedido realizado | Cobrado USD $50.00")
check("en dolares se convierte con el tipo de cambio del monitor", creados[-1]["precio_compra"] == 1000.0,
      creados[-1]["precio_compra"])
del sys.modules["monitor"]
CB.registrar_compra("https://creations.mattel.com/products/usd2", "Pieza USD sin TC", 999.0, cantidad=1,
                    pedido="🎉 Pedido realizado | Cobrado USD $50.00")
check("sin tipo de cambio se queda el estimado (y lo avisa)", creados[-1]["precio_compra"] == 999.0
      and "Costo estimado por el monitor" in creados[-1]["notas"], creados[-1])
CB.registrar_compra("https://creations.mattel.com/products/viejo", "Sin confirmacion", 700.0, pedido="🎉 Pedido realizado")
check("sin confirmacion usa el precio de siempre", creados[-1]["precio_compra"] == 700.0)

print("\n--- 3. Seguimiento del envio ---")
pend = CB.pendientes_de_envio()
check("solo los que tienen pagina de estado", [p["url"] for p in pend] == ["https://creations.mattel.com/en-mx/products/rwb"], pend)
fila = pend[0]
aviso = CB.aplicar_envio(fila, {"guia": "1234567890", "paqueteria": "DHL", "llega": "2026-10-24", "entregado": False})
check("avisa la guia y la llegada", aviso and "1234567890" in aviso and "2026-10-24" in aviso, aviso)
ruta, cambios = parches[-1]
check("actualiza 'Por llegar' con la fecha real", ruta == "/api/articulos/A1" and cambios["fecha_llegada"] == "2026-10-24", parches)
check("y deja la guia en las notas sin borrar lo que habia",
      cambios["notas"].startswith(alta["notas"].rstrip()) and "Guía: 1234567890 (DHL)" in cambios["notas"], cambios["notas"])
check("recien revisado: no se vuelve a abrir en 5 h", CB.pendientes_de_envio() == [])
n = len(parches)
check("sin cambios no molesta", CB.aplicar_envio(dict(fila, guia="1234567890", llegada="2026-10-24"),
                                                 {"guia": "1234567890", "llega": "2026-10-24"}) is None and len(parches) == n)
aviso = CB.aplicar_envio(dict(fila, guia="1234567890", llegada="2026-10-24"), {"entregado": True})
check("entregado: lo avisa y no cambia la ubicacion", "entregó" in aviso and "ubicacion" not in parches[-1][1], parches[-1])

print("\n--- 4. Resumen semanal ---")
import hallazgos as H  # noqa: E402
H.registrar("https://creations.mattel.com/products/se-fue", titulo="Datsun que se fue", tipo="nuevo")
H.marcar_agotado("https://creations.mattel.com/products/se-fue")
i = H.registrar("https://creations.mattel.com/products/ignorada", titulo="Ignorada", tipo="nuevo")
H.cambiar_estado(i, "ignorado")
H.marcar_agotado("https://creations.mattel.com/products/ignorada")
esc = H.escapadas(7)
check("se escaparon: solo las que nadie decidio", [e["titulo"] for e in esc] == ["Datsun que se fue"], esc)

with open(os.path.join(TMP, "config.json"), "w") as f:
    json.dump({"notifications": {"email": {"enabled": False}, "whatsapp": {"enabled": False}}}, f)
os.environ["HOTWHEELS_DRY_RUN"] = "1"
import dashboard_bot as D  # noqa: E402
texto = D.texto_resumen_semanal(["🎉 Pedido realizado\n⏱ 20.0 s", "✅ carrito\n⏱ 30.0 s", "❌ agotado"],
                                1, 1, 1, esc, {"compradas": 2, "invertido": 2500, "vendidas": 1, "ganancia": 900})
check("cronometro promedio", "Compra promedio: 25.0 s (la más rápida 20.0 s)" in texto, texto)
check("lo que se escapo", "Datsun que se fue" in texto, texto)
check("y el dinero", "compró 2 pieza(s) por $2,500" in texto and "ganancia neta $900" in texto, texto)
check("sin inventario no truena", "Resumen semanal" in D.texto_resumen_semanal([], 0, 0, 0, [], None))

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
