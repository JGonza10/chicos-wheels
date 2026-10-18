# -*- coding: utf-8 -*-
"""
Inicia sesion en Mattel Creations UNA vez para que el bot pueda comprar piezas
RLC (Red Line Club), que piden membresia y sesion iniciada.

    python iniciar_sesion_mattel.py

1. Se abre Chromium con el perfil del bot (carpeta perfil_mattel/, fuera de git).
2. Entra con tu cuenta Red Line Club (correo + codigo, como siempre).
3. Cuando veas tu cuenta, cierra la ventana. La sesion queda guardada.
4. En .env pon HOTWHEELS_PERFIL_MATTEL=1 y reinicia la app.

La contraseña no se guarda en ningun lado: solo las cookies de la sesion,
igual que en tu Chrome. Si Mattel cierra la sesion (suele durar semanas),
vuelve a correr este script. Cierra la app antes: el perfil no se puede
abrir en dos ventanas a la vez.
"""

import asyncio
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

URL_LOGIN = "https://creations.mattel.com/en-mx/account"


async def main():
    from playwright.async_api import async_playwright
    import navegador
    from bot_logic import sesion_mattel_activa

    async with async_playwright() as p:
        try:
            ctx = await p.chromium.launch_persistent_context(navegador.PERFIL, headless=False)
        except Exception as e:
            print("❌ No se pudo abrir el perfil del bot. ¿La app (python app.py) está corriendo?")
            print("   Ciérrala, corre este script y vuelve a abrirla.")
            print(f"   Detalle: {e}")
            return 1
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URL_LOGIN, wait_until="domcontentloaded")
        print("👉 Inicia sesión con tu cuenta Red Line Club en la ventana que se abrió.")
        print("   Cuando veas tu cuenta, cierra la ventana.")
        activa = False
        while ctx.pages:
            try:
                activa = await sesion_mattel_activa(ctx.pages[0]) or activa
            except Exception:
                pass
            await asyncio.sleep(2)
        try:
            await ctx.close()
        except Exception:
            pass
    if activa:
        print("✅ Sesión guardada. Pon HOTWHEELS_PERFIL_MATTEL=1 en .env y reinicia la app.")
    else:
        print("⚠️ No vi la sesión iniciada. Si sí entraste, puede que Mattel no la muestre;")
        print("   prueba con HOTWHEELS_PERFIL_MATTEL=1 y un ensayo (HOTWHEELS_DRY_RUN=1).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
