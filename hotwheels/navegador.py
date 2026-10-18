# -*- coding: utf-8 -*-
"""
Navegador caliente: un Chromium que vive en su propio hilo para comprar sin
arrancar desde cero.

Sin esto, cada compra abre Chromium, carga la pagina del producto y cierra
cookies/pop-ups: 5-10 s antes de poder dar "Add to Bag". Con el navegador
caliente, en cuanto llega el aviso de una pieza urgente (o tocas "Comprar" en
Telegram) la pagina se abre en segundo plano; al confirmar, el bot compra
sobre esa pagina ya cargada.

Sesion de Mattel (piezas RLC): con HOTWHEELS_PERFIL_MATTEL=1 el navegador usa
un perfil guardado en esta PC (carpeta perfil_mattel/, fuera de git) donde
iniciaste sesion UNA vez con iniciar_sesion_mattel.py. La contraseña nunca se
guarda: solo las cookies de la sesion, como en tu propio Chrome.

Reglas:
  - Playwright exige usar sus objetos en el mismo event loop: todo pasa por
    el loop de este hilo (enviar()).
  - Una pagina precalentada se usa una sola vez y se cierra despues de comprar.
  - Antes de agregar al carrito se vacia (el carrito vive entre compras).
  - Las paginas que nadie uso se cierran a los MINUTOS_PAGINA y el navegador
    entero a los MINUTOS_NAVEGADOR sin uso: no queda una ventana eterna.
"""

import asyncio
import os
import threading
import time

DIR = os.path.dirname(os.path.abspath(__file__))
PERFIL = os.path.join(DIR, "perfil_mattel")
MINUTOS_PAGINA = 10
MINUTOS_NAVEGADOR = 20
SEGUNDOS_RECARGA = 60      # una pagina precalentada mas vieja que esto se recarga al comprar


def precalentar_activo():
    return os.environ.get("HOTWHEELS_PRECALENTAR", "1") != "0"


def perfil_activo():
    return os.environ.get("HOTWHEELS_PERFIL_MATTEL") == "1"


class NavegadorCaliente:
    def __init__(self, headless=False, perfil=None, iniciar=None, log=print):
        self.headless = headless
        self.perfil = perfil
        self._iniciar = iniciar          # para pruebas: fabrica de (playwright, contexto)
        self.log = log
        self._loop = None
        self._hilo = None
        self._pw = None
        self._browser = None
        self.contexto = None
        self.paginas = {}                # url -> (page, cuando se cargo)
        self._ultimo_uso = time.monotonic()
        self._listo = threading.Event()

    # --- hilo y loop propios -----------------------------------------------
    def _asegurar_hilo(self):
        if self._hilo and self._hilo.is_alive():
            return
        self._listo.clear()

        def correr():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.call_soon(self._listo.set)
            self._loop.create_task(self._limpieza_periodica())
            self._loop.run_forever()

        self._hilo = threading.Thread(target=correr, name="navegador_caliente", daemon=True)
        self._hilo.start()
        self._listo.wait(10)

    def enviar(self, coro):
        """Corre una corrutina en el loop del navegador. Devuelve un
        concurrent.futures.Future (usa .result() o asyncio.wrap_future)."""
        self._asegurar_hilo()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # --- navegador ---------------------------------------------------------
    async def _contexto(self):
        if self.contexto is not None:
            return self.contexto
        if self._iniciar:
            self._pw, self.contexto = await self._iniciar()
            return self.contexto
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        if self.perfil:
            os.makedirs(self.perfil, exist_ok=True)
            self.contexto = await self._pw.chromium.launch_persistent_context(
                self.perfil, headless=self.headless)
        else:
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self.contexto = await self._browser.new_context()
        self.log("  🔥 Navegador caliente abierto" + (" (con tu sesión de Mattel)" if self.perfil else ""))
        return self.contexto

    async def cerrar(self):
        for page, _ in list(self.paginas.values()):
            try:
                await page.close()
            except Exception:
                pass
        self.paginas.clear()
        for cosa in (self.contexto, self._browser):
            try:
                if cosa is not None:
                    await cosa.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                await self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self.contexto = None

    async def _limpieza_periodica(self):
        while True:
            await asyncio.sleep(30)
            try:
                await self.limpiar()
            except Exception as e:
                self.log(f"  ⚠️ Limpieza del navegador caliente: {e}")

    async def limpiar(self, ahora=None):
        ahora = ahora if ahora is not None else time.monotonic()
        for url, (page, cuando) in list(self.paginas.items()):
            if ahora - cuando > MINUTOS_PAGINA * 60:
                self.paginas.pop(url, None)
                try:
                    await page.close()
                except Exception:
                    pass
        if (self.contexto is not None and not self.paginas
                and ahora - self._ultimo_uso > MINUTOS_NAVEGADOR * 60):
            self.log("  💤 Navegador caliente cerrado por falta de uso")
            await self.cerrar()

    # --- precalentar y comprar ---------------------------------------------
    async def _precalentar(self, url):
        from bot_logic import dismiss_overlays
        from store_selectors import get_selector
        self._ultimo_uso = time.monotonic()
        if url in self.paginas:
            return "ya"
        selector = get_selector(url)
        if selector is None:
            return "no_soportada"
        ctx = await self._contexto()
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await dismiss_overlays(page, selector)
        except Exception as e:
            try:
                await page.close()
            except Exception:
                pass
            self.log(f"  ⚠️ No se pudo precalentar {url}: {e}")
            return "error"
        self.paginas[url] = (page, time.monotonic())
        self.log(f"  🔥 Pieza lista en el navegador: {url}")
        return "ok"

    def precalentar(self, url):
        """Abre la pagina de la pieza en segundo plano. No espera."""
        return self.enviar(self._precalentar(url))

    async def _tomar_pagina(self, url):
        """(pagina, ya_cargada). Usa la precalentada si existe; si es vieja la
        recarga (la conexion y la cache ya estan calientes, sale rapido)."""
        self._ultimo_uso = time.monotonic()
        ctx = await self._contexto()
        guardada = self.paginas.pop(url, None)
        if guardada:
            page, cuando = guardada
            if not page.is_closed():
                if time.monotonic() - cuando > SEGUNDOS_RECARGA:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                return page, True
        return await ctx.new_page(), False

    async def _comprar(self, url, **kw):
        import bot_logic as B
        selector = B.get_selector(url)
        if selector is None:
            return f"❌ Tienda no soportada: {url}"
        dry = kw.get("dry_run")
        dry = dry if dry is not None else os.environ.get("HOTWHEELS_DRY_RUN") == "1"
        pausa = kw.get("permitir_pausa", True) and os.environ.get("HOTWHEELS_DRY_RUN_KEEP_OPEN") == "1"
        cantidad = kw.get("cantidad")
        reloj = B.Cronometro()
        page = None
        try:
            page, cargada = await self._tomar_pagina(url)
            reloj.marca("navegador (caliente)" if cargada else "navegador")
            return await B._comprar_en(page, url, selector, reloj, dry,
                                       B.MAX_QUANTITY if cantidad is None else cantidad,
                                       kw.get("notificar", True), self.headless, pausa,
                                       ya_cargada=cargada, limpiar_carrito=True)
        except Exception as e:
            await B.guardar_captura_error(page, url, "general")
            resultado = f"❌ Error inesperado con {url} | Error: {e}"
            if not dry and kw.get("notificar", True):
                B.notify(resultado)
            return resultado
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
            self._ultimo_uso = time.monotonic()

    def comprar(self, url, **kw):
        """Compra en el navegador caliente. Devuelve un Future con el texto
        de siempre (✅ / 🎉 / 🧪 / ❌), igual que comprar_producto."""
        return self.enviar(self._comprar(url, **kw))

    def estado(self):
        return {"abierto": self.contexto is not None, "paginas": len(self.paginas),
                "con_sesion": bool(self.perfil)}


_NAVEGADOR = None
_LOCK = threading.Lock()


def obtener():
    """El navegador caliente del proceso (None si esta apagado)."""
    global _NAVEGADOR
    if not precalentar_activo() and not perfil_activo():
        return None
    with _LOCK:
        if _NAVEGADOR is None:
            _NAVEGADOR = NavegadorCaliente(perfil=PERFIL if perfil_activo() else None)
        return _NAVEGADOR
