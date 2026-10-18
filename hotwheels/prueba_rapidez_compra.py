# -*- coding: utf-8 -*-
"""Pruebas de la compra mas rapida (2026-10-18), con Chromium real y paginas
locales (set_content): nunca abre Mattel ni paga nada.

  1. Pop-ups y modal de Shop: si no estan, no se espera; si estan, se cierran
  2. Los iframes de la tarjeta: se sigue en cuanto cargan (sin 2 s fijos)
  3. Cronometro: cuanto tarda cada paso

Ejecutar:  python prueba_rapidez_compra.py
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time

DIR = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba_rapidez_")
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
os.environ["HOTWHEELS_DRY_RUN"] = "1"
sys.path.insert(0, TMP)
os.chdir(TMP)

import bot_logic as B  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

SEL = {"cookie_consent": "#truste-consent-button", "popup_close": "button[aria-label='Close dialog']"}
MODAL = "button[data-testid='authorize-modal-close-button']"


async def pruebas():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception:
            browser = await p.chromium.launch(headless=True, executable_path="/opt/pw-browsers/chromium")
        page = await browser.new_page()

        print("\n--- 1. Pop-ups: sin esperas cuando no estan ---")
        await page.set_content("<button class='product__add-to-cart'>Add to Bag</button>")
        t = time.monotonic()
        await B.dismiss_shop_modal(page)
        check("modal de Shop ausente: no espera (antes 3 s)", time.monotonic() - t < 0.5, time.monotonic() - t)
        t = time.monotonic()
        await B.dismiss_overlays(page, SEL)
        tardo = time.monotonic() - t
        check("pop-ups ausentes: <2 s (antes hasta 10 s)", tardo < 2.0, tardo)

        await page.set_content(
            "<div id='c'><button id='truste-consent-button' onclick=\"this.remove()\">OK</button></div>"
            "<button aria-label='Close dialog' onclick=\"this.remove()\">x</button>")
        await B.dismiss_overlays(page, SEL)
        check("cierra cookies y pop-up si estan",
              await page.locator("#truste-consent-button").count() == 0
              and await page.locator("button[aria-label='Close dialog']").count() == 0)

        await page.set_content(
            "<script>setTimeout(() => { const b = document.createElement('button');"
            "b.dataset.testid = 'authorize-modal-close-button'; b.textContent = 'x';"
            "b.onclick = () => b.remove(); document.body.appendChild(b); }, 300);</script>")
        cerrado = await B._cerrar_si_aparece(page, MODAL, 800)
        check("antes de pagar, el modal que sale tarde se cierra", cerrado and await page.locator(MODAL).count() == 0)

        print("\n--- 2. Iframes de la tarjeta ---")
        await page.set_content(
            "<script>setTimeout(() => { for (const m of ['number-ltr','expiry-ltr']) {"
            "const f = document.createElement('iframe'); f.src = 'data:text/html,' + m;"
            "document.body.appendChild(f); } }, 400);</script>")
        t = time.monotonic()
        listo = await B.esperar_frames(page, ("number-ltr", "expiry-ltr"))
        tardo = time.monotonic() - t
        check("sigue en cuanto cargan los iframes", listo and tardo < 1.5, tardo)
        t = time.monotonic()
        listo = await B.esperar_frames(page, ("no-existe",), timeout_ms=600)
        check("si no cargan, no se queda colgado", not listo and time.monotonic() - t < 1.5)
        await browser.close()

    print("\n--- 3. Cronometro ---")
    r = B.Cronometro()
    time.sleep(0.05)
    r.marca("navegador")
    time.sleep(0.05)
    r.marca("datos_envio")
    texto = r.texto()
    check("dice el total y cada paso", texto.startswith("⏱ 0.1 s (navegador 0.1 · datos envio 0.1)")
          or texto.startswith("⏱ 0.1 s (navegador 0.0 · datos envio 0.1)")
          or texto.startswith("⏱ 0.1 s (navegador 0.1 · datos envio 0.0)"), texto)


asyncio.run(pruebas())

print()
os.chdir(DIR)
shutil.rmtree(TMP, ignore_errors=True)
if fallos:
    print("FALLARON %d pruebas: %s" % (len(fallos), fallos))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
