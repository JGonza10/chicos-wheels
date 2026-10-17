# prueba_evento_reintentos.py
"""Pruebas de la ventana de reintentos del evento puntual (mejora 2026-09-16).

Nunca tocan el bot.db real ni abren un navegador: se corre todo en una
carpeta temporal, comprar_producto se reemplaza por un doble, y la ventana
(180s) / el intervalo (15s) se acortan a milisegundos via monkeypatch para
que la prueba corra en segundos. Ejecutar:

    venv\\Scripts\\activate
    python prueba_evento_reintentos.py
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile

ORIGEN = os.path.dirname(os.path.abspath(__file__))

TMP = tempfile.mkdtemp(prefix="prueba_evento_")
with open(os.path.join(ORIGEN, "config.json")) as f:
    cfg = json.load(f)
for canal in cfg.get("notifications", {}).values():
    if isinstance(canal, dict):
        canal["enabled"] = False
with open(os.path.join(TMP, "config.json"), "w") as f:
    json.dump(cfg, f)
# La base vive junto al codigo: se prueba sobre una copia para no tocar la real.
for f in os.listdir(ORIGEN):
    if f.endswith(".py") and not f.startswith("prueba_"):
        shutil.copy(os.path.join(ORIGEN, f), TMP)
for carpeta in ("templates", "static"):
    shutil.copytree(os.path.join(ORIGEN, carpeta), os.path.join(TMP, carpeta))
os.chdir(TMP)
sys.path.insert(0, TMP)

import dashboard_bot as DB  # noqa: E402  (crea bot.db en TMP, no en el proyecto)

# Ventana/intervalo reales en segundos (180/15) tardarian minutos en probar.
DB.EVENTO_VENTANA_SEGUNDOS = 0.3
DB.EVENTO_INTERVALO_SEGUNDOS = 0.05

fallos = []


def check(nombre, condicion, detalle=""):
    if condicion:
        print(f"  OK  {nombre}")
    else:
        print(f"  FALLO  {nombre}  {detalle}")
        fallos.append(nombre)


AVISOS = []
DB.notify = lambda msg: AVISOS.append(msg)

RESPUESTAS = []  # cola de resultados que ira devolviendo el doble
LLAMADAS = []


async def _compra_falsa(url, proxy=None, cantidad=None, dry_run=None,
                        permitir_pausa=True, notificar=True):
    LLAMADAS.append({"url": url, "notificar": notificar})
    if RESPUESTAS:
        return RESPUESTAS.pop(0)
    return f"❌ Producto agotado: {url}"


DB.comprar_producto = _compra_falsa

URL = "https://creations.mattel.com/products/evento-test"


def preparar(respuestas):
    RESPUESTAS.clear()
    RESPUESTAS.extend(respuestas)
    LLAMADAS.clear()
    AVISOS.clear()


print("\n--- 1. Sin productos activos: no hace nada, no notifica ---")
preparar([])
resultado = asyncio.run(DB._intentar_evento())
check("no encontro exito", resultado is False)
check("no llamo a comprar_producto", LLAMADAS == [], LLAMADAS)
check("no notifico nada", AVISOS == [], AVISOS)

print("\n--- 2. Exito en el primer intento: un solo intento, un solo aviso ---")
DB.add_product(URL)
preparar([f"✅ Producto agregado al carrito (cantidad: 1): {URL}"])
resultado = asyncio.run(DB._intentar_evento())
check("encontro exito", resultado is True)
check("un solo intento", len(LLAMADAS) == 1, LLAMADAS)
check("nunca pidio que comprar_producto notificara (el bucle avisa solo)",
     all(not l["notificar"] for l in LLAMADAS), LLAMADAS)
check("un solo aviso final", len(AVISOS) == 1, AVISOS)
check("el aviso es de exito", "🎯" in AVISOS[0] and "✅" in AVISOS[0], AVISOS)

print("\n--- 3. Falla dos veces y acierta a la tercera: reintenta, un solo aviso ---")
preparar([
    f"❌ Producto agotado: {URL}",
    f"❌ Producto agotado: {URL}",
    f"✅ Producto agregado al carrito (cantidad: 1): {URL}",
])
resultado = asyncio.run(DB._intentar_evento())
check("encontro exito", resultado is True)
check("reintento hasta 3 veces", len(LLAMADAS) == 3, LLAMADAS)
check("nunca notifico en un intento fallido intermedio", len(AVISOS) == 1, AVISOS)
check("el aviso final es de exito", "🎯" in AVISOS[0], AVISOS)

print("\n--- 4. Nunca hay stock: se acaba la ventana, un solo aviso de fallo ---")
preparar([])  # siempre "agotado" (el default del doble)
resultado = asyncio.run(DB._intentar_evento())
check("no encontro exito", resultado is False)
check("reintento varias veces dentro de la ventana", len(LLAMADAS) >= 2, LLAMADAS)
check("un solo aviso final (no uno por intento)", len(AVISOS) == 1, AVISOS)
check("el aviso final es de fallo, no de exito", "⏱️" in AVISOS[0] and "🎯" not in AVISOS[0], AVISOS)

print("\n--- 5. scheduled_run dispara el reintento (no run_all) en el minuto exacto ---")
import sqlite3  # noqa: E402
from datetime import datetime  # noqa: E402

ahora = datetime.now()
conn = sqlite3.connect("bot.db")
conn.execute("DELETE FROM evento_puntual")
conn.execute(
    "INSERT INTO evento_puntual (fecha, hora, minuto, hecho) VALUES (?, ?, ?, 0)",
    (ahora.strftime("%Y-%m-%d"), ahora.hour, ahora.minute),
)
conn.commit()
conn.close()

LLAMADO_INTENTAR_EVENTO = []
_intentar_evento_original = DB._intentar_evento


async def _intentar_evento_doble():
    LLAMADO_INTENTAR_EVENTO.append(True)
    return True


DB._intentar_evento = _intentar_evento_doble
DB.scheduled_run()
check("llamo a _intentar_evento (no a run_all)", LLAMADO_INTENTAR_EVENTO == [True])
evento = DB.get_event()
check("marco el evento como hecho de inmediato", evento["hecho"] is True, evento)
DB._intentar_evento = _intentar_evento_original

print()
os.chdir(ORIGEN)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("Todas las pruebas de la ventana de reintentos pasaron.")
