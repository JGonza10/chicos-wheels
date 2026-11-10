# dashboard_bot.py
import asyncio
import os
import sqlite3
import sys
import threading
import time
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from bot_logic import comprar_producto, notify, notify_botones, obtener_datos_producto, test_humo
import hallazgos as HALLAZGOS
import monitor_admin
import collecthub_bridge as COLLECTHUB
import coleccion as COLECCION
import limites as LIMITES
import precios as PRECIOS
import salud as SALUD
import telegram_control
import navegador as NAVEGADOR
import cuentas as CUENTAS
import drops as DROPS

app = Flask(__name__)
# Panel solo local (http): cookie de Flask cerrada, pero sin Secure para que funcione en 127.0.0.1.
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                  SESSION_COOKIE_SECURE=bool(os.environ.get("RAILWAY_ENVIRONMENT")))
# La base vive junto al codigo: no depende de desde donde se arranque.
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

@app.context_processor
def _anio_kestrel():
    # © Kestrel con el año en curso en el pie (regla de Gonza, 2026-10-09).
    from datetime import date
    return {"anio_actual": date.today().year}


# --- Autenticacion minima del panel (mejora #5) ---
# Opcional a proposito: si no se configuran estas dos variables, el panel
# sigue abierto igual que siempre (no rompe instalaciones existentes). En
# cuanto el bridge del monitor (mejora #4) obliga a exponer este dashboard
# mas alla de localhost, conviene configurarlas.

# --- Inicializar BD ---
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    image_url TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server TEXT NOT NULL,
                    username TEXT,
                    password TEXT
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_hour INTEGER,
                    end_hour INTEGER
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS evento_puntual (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    hora INTEGER NOT NULL,
                    minuto INTEGER NOT NULL,
                    hecho INTEGER NOT NULL DEFAULT 0
                )""")
    conn.commit()
    DROPS.crear_tabla(DB)

    # products puede venir de una version anterior sin estas columnas.
    c.execute("PRAGMA table_info(products)")
    columnas = [row[1] for row in c.fetchall()]
    if "active" not in columnas:
        c.execute("ALTER TABLE products ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    if "image_url" not in columnas:
        c.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
        conn.commit()
    if "titulo" not in columnas:
        # Solo se llena cuando la URL llega por el puente del monitor (mejora
        # #4): asi luego se puede cruzar "cuantos Alto impacto detectados se
        # compraron a tiempo" sin tener que volver a scrapear el titulo.
        c.execute("ALTER TABLE products ADD COLUMN titulo TEXT")
        conn.commit()
    if "impacto" not in columnas:
        c.execute("ALTER TABLE products ADD COLUMN impacto TEXT")
        conn.commit()
    if "origen" not in columnas:
        c.execute("ALTER TABLE products ADD COLUMN origen TEXT")  # 'manual' o 'monitor'
        conn.commit()

    conn.close()

init_db()
HALLAZGOS.init_db()
LIMITES.init_db()
COLLECTHUB.init_db()
PRECIOS.init_db()
SALUD.init_db()

# --- Funciones BD ---
def get_products():
    """Todas las URLs (activas e inactivas) — se usa para mostrarlas en el panel."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, url, active, image_url FROM products ORDER BY id")
    productos = [
        {"id": row[0], "url": row[1], "active": bool(row[2]), "image_url": row[3]}
        for row in c.fetchall()
    ]
    conn.close()
    return productos

def set_product_image(product_id, image_url):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE products SET image_url = ? WHERE id = ?", (image_url, product_id))
    conn.commit()
    conn.close()

def get_active_product_urls():
    """Solo las URLs activas — las que sí debe procesar el cron/Run."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT url FROM products WHERE active = 1")
    urls = [row[0] for row in c.fetchall()]
    conn.close()
    return urls

def marcar_producto_completado(url):
    """Se llama cuando un resultado es una compra 100% realizada (🎉), para
    que el cron no vuelva a intentar comprar el mismo producto cada día."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE products SET active = 0 WHERE url = ?", (url,))
    conn.commit()
    conn.close()

def set_product_active(product_id, active):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE products SET active = ? WHERE id = ?", (1 if active else 0, product_id))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

def get_proxies():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT server, username, password FROM proxies")
    proxies = [{"server": row[0], "username": row[1], "password": row[2]} for row in c.fetchall()]
    conn.close()
    return proxies

def get_results():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT message, created_at FROM results ORDER BY id DESC")
    results = [f"{row[1]} - {row[0]}" for row in c.fetchall()]
    conn.close()
    return results

def add_product(url):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO products (url, origen) VALUES (?, 'manual')", (url,))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def add_proxy(server, username, password):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO proxies (server, username, password) VALUES (?, ?, ?)", (server, username, password))
    conn.commit()
    conn.close()

def add_result(message):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO results (message) VALUES (?)", (message,))
    conn.commit()
    conn.close()

def clear_results():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM results")
    conn.commit()
    conn.close()

def set_schedule(start_hour, end_hour):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM schedule")
    c.execute("INSERT INTO schedule (start_hour, end_hour) VALUES (?, ?)", (start_hour, end_hour))
    conn.commit()
    conn.close()

def get_schedule():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT start_hour, end_hour FROM schedule LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row if row else (1, 0)  # (1,0): ventana imposible = desactivada por defecto

def set_event(fecha, hora, minuto):
    """Programa una ejecucion puntual (una sola vez) para un drop con hora
    exacta anunciada, ej. un lanzamiento a las 10:03. Reemplaza cualquier
    evento puntual anterior."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM evento_puntual")
    c.execute(
        "INSERT INTO evento_puntual (fecha, hora, minuto, hecho) VALUES (?, ?, ?, 0)",
        (fecha, hora, minuto),
    )
    conn.commit()
    conn.close()

def get_event():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, fecha, hora, minuto, hecho FROM evento_puntual ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "fecha": row[1], "hora": row[2], "minuto": row[3], "hecho": bool(row[4])}

def clear_event():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM evento_puntual")
    conn.commit()
    conn.close()

def marcar_evento_hecho(event_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE evento_puntual SET hecho = 1 WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()

# --- Bot ---
_ULTIMA_ALERTA_FALLO_BOT = None
UMBRAL_FALLOS_SEGUIDOS = 5  # mismo espiritu que "MONITOR CIEGO" del monitor: silencio no es lo mismo que exito

def _resultados_recientes(n):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT message FROM results ORDER BY id DESC LIMIT ?", (n,))
    filas = [row[0] for row in c.fetchall()]
    conn.close()
    return filas

def _revisar_fallos_seguidos():
    """Si el bot lleva varias corridas seguidas sin ni un exito, algo se
    rompio en silencio (ej. Mattel cambio un selector) — igual de peligroso
    que el 'MONITOR CIEGO' del otro proyecto, y hasta ahora nadie avisaba."""
    global _ULTIMA_ALERTA_FALLO_BOT
    recientes = _resultados_recientes(UMBRAL_FALLOS_SEGUIDOS)
    if len(recientes) < UMBRAL_FALLOS_SEGUIDOS:
        return
    if any(("✅" in m or "🎉" in m) for m in recientes):
        return
    ahora = datetime.now()
    if _ULTIMA_ALERTA_FALLO_BOT and (ahora - _ULTIMA_ALERTA_FALLO_BOT).total_seconds() < 3600:
        return  # maximo un aviso por hora, para no volverse otra molestia
    _ULTIMA_ALERTA_FALLO_BOT = ahora
    notify(f"⚠️ BOT DE COMPRA FALLANDO: los ultimos {UMBRAL_FALLOS_SEGUIDOS} intentos "
           "no lograron ni un carrito. Puede ser un selector cambiado en la tienda, "
           "revisa capturas_error/.")

async def run_one(url, cantidad=None, dry_run=None, permitir_pausa=False):
    """Compra UNA sola URL — la que el usuario eligio en el panel.

    Deliberadamente NO reusa run_all(): run_all compra todas las URLs activas
    de la tabla, y "Comprar" en una pieza debe comprar solo esa pieza.
    """
    # Navegador caliente (si esta prendido): la pagina puede estar ya cargada
    # (precalentar) y, con el perfil de Mattel, con tu sesion RLC iniciada.
    resultado = await comprar_producto(url, cantidad=cantidad, dry_run=dry_run,
                                       permitir_pausa=permitir_pausa,
                                       navegador=NAVEGADOR.obtener())
    add_result(resultado)
    if "🎉" in resultado:
        marcar_producto_completado(url)
    return resultado


# Un disparo automatico a la vez: comprar_producto abre un Chromium visible
# (headless=False, a proposito por los captchas). Dos ventanas peleandose en
# un drop es peor que perder el drop.
_LOCK_DISPARO = threading.Lock()


def _estado_desde_resultado(resultado):
    """Traduce el texto que devuelve comprar_producto al estado de la pieza.
    Un ensayo (🧪) no compra nada: la pieza sigue pendiente para poder
    decidir de verdad."""
    if "🎉" in resultado:
        return "comprado"
    if "🧪" in resultado:
        return "pendiente"
    if "✅" in resultado:
        return "carrito"
    return "fallo"


def _comprar_pedido_por_usuario(url, titulo, precio_mxn, cantidad, hallazgo_id=None):
    """El usuario pulso "Comprar" (en una pieza encontrada, en Telegram o en uno
    de sus links). Corre la compra en un hilo aparte para no dejar colgada la
    peticion HTTP (un checkout tarda ~30s). Un solo navegador a la vez
    (_LOCK_DISPARO, ya tomado por quien llama; el hilo lo libera)."""
    def _trabajo():
        try:
            resultado = asyncio.run(run_one(url, cantidad=cantidad, permitir_pausa=True))
            if hallazgo_id:
                HALLAZGOS.cambiar_estado(hallazgo_id, _estado_desde_resultado(resultado), resultado)
            notify(f"🛒 Compra pedida desde el panel: {resultado}")
            # Pedido pagado de verdad (no ensayo): se anota solo en Chicos Wheels.
            if "🎉" in resultado and os.environ.get("HOTWHEELS_DRY_RUN") != "1":
                ok_ch, msg_ch = COLLECTHUB.registrar_compra(
                    url=url, titulo=titulo, precio_mxn=precio_mxn, origen="panel",
                    cantidad=cantidad, pedido=str(resultado)[:300])
                if not ok_ch:
                    notify(f"⚠️ Se compró, pero no se pudo anotar en Chicos Wheels: {msg_ch}")
                try:
                    texto, _ = borrador_publicacion(titulo or url, precio_mxn, _reventa_conocida(url), cantidad)
                    notify("📝 Borrador para Facebook/Instagram (cópialo y ajusta el precio):\n\n" + texto)
                except Exception as e:
                    print(f"⚠️ No se pudo armar el borrador: {e}")
        except Exception as e:  # nunca tumbar el hilo en silencio
            if hallazgo_id:
                HALLAZGOS.cambiar_estado(hallazgo_id, "fallo", f"❌ Error: {e}")
        finally:
            _LOCK_DISPARO.release()

    threading.Thread(target=_trabajo, daemon=True).start()


def solicitar_compra(hallazgo_id, cantidad=1, forzar=False):
    """Punto unico para "Comprar una pieza" (panel y Telegram). Devuelve un dict
    {ok, error?, en_cola?, posicion?, codigo?}.

    Sin tope de gasto (quitado 2026-09-28 a pedido de Gonza): comprar nunca se
    detiene por precio, solo por disponibilidad o porque ya se esta comprando.
    - Si el bot ya esta comprando otra cosa, la pieza entra a la cola en vez de
      rebotar; el hilo de la cola la toma cuando el bot quede libre.
    """
    pieza = HALLAZGOS.obtener(hallazgo_id)
    if not pieza:
        return {"ok": False, "error": "no existe esa pieza", "codigo": 404}
    if not pieza["disponible"]:
        return {"ok": False, "error": "esa pieza ya está agotada", "codigo": 409}
    if pieza["estado"] in ("comprando", "comprado"):
        return {"ok": False, "error": "esa pieza ya se está comprando o ya se compró", "codigo": 409}
    # 0 = "Comprar el máximo" (Telegram): el límite que pone la página.
    if cantidad == 0:
        cantidad = _datos_pieza(pieza["url"])[2] or 1
    try:
        cantidad = max(1, min(int(cantidad or 1), 10))
    except (TypeError, ValueError):
        cantidad = 1

    if not _LOCK_DISPARO.acquire(blocking=False):
        posicion = HALLAZGOS.encolar(hallazgo_id, cantidad)
        if posicion is None:
            return {"ok": False, "error": "no se pudo poner en la cola", "codigo": 409}
        return {"ok": True, "en_cola": True, "posicion": posicion}
    if not HALLAZGOS.reservar_compra(hallazgo_id, cantidad):
        _LOCK_DISPARO.release()
        return {"ok": False, "error": "esa pieza ya se está comprando o ya se compró", "codigo": 409}
    try:
        _comprar_pedido_por_usuario(pieza["url"], pieza["titulo"], pieza["precio_mxn"],
                                    cantidad, hallazgo_id=hallazgo_id)
    except Exception as e:
        _LOCK_DISPARO.release()
        HALLAZGOS.cambiar_estado(hallazgo_id, "fallo", f"❌ No se pudo iniciar: {e}")
        return {"ok": False, "error": str(e), "codigo": 500}
    return {"ok": True}


def _procesar_cola_una_vez():
    """Si el bot esta libre y hay algo en la cola, arranca la siguiente compra.
    Devuelve True si hizo algo (para las pruebas)."""
    if _LOCK_DISPARO.locked():
        return False
    siguiente = HALLAZGOS.siguiente_en_cola()
    if not siguiente or not _LOCK_DISPARO.acquire(blocking=False):
        return False
    if not siguiente["disponible"]:
        HALLAZGOS.cambiar_estado(siguiente["id"], "fallo", "Se agotó mientras esperaba en la cola")
        _LOCK_DISPARO.release()
        return True
    if not HALLAZGOS.reservar_compra(siguiente["id"], siguiente["cantidad"]):
        _LOCK_DISPARO.release()
        return True
    try:
        _comprar_pedido_por_usuario(siguiente["url"], siguiente["titulo"], siguiente["precio_mxn"],
                                    siguiente["cantidad"] or 1, hallazgo_id=siguiente["id"])
    except Exception as e:
        _LOCK_DISPARO.release()
        HALLAZGOS.cambiar_estado(siguiente["id"], "fallo", f"❌ No se pudo iniciar: {e}")
    return True


def _bucle_cola():
    while True:
        try:
            _procesar_cola_una_vez()
        except Exception as e:
            print(f"⚠️ Error en la cola de compras: {e}")
        time.sleep(2)


# --- Prueba diaria del checkout completo (ensayo: llena todo, NO paga) ---
def probar_checkout():
    """Recorre carrito + checkout con un producto disponible real, sin ventana
    y sin pagar, para enterarse con horas de anticipacion si el pago se rompio.
    Devuelve el estado registrado: ok | roto | sin_producto | captcha | omitido."""
    if not _LOCK_DISPARO.acquire(blocking=False):
        return "omitido"          # el bot esta comprando de verdad: no estorbar
    try:
        url = monitor_admin.producto_disponible_para_prueba()
        if not url:
            SALUD.registrar_checkout("sin_producto", "el monitor no vio nada disponible para probar")
            return "sin_producto"
        try:
            resultado = asyncio.run(comprar_producto(
                url, dry_run=True, cantidad=1, permitir_pausa=False, notificar=False, headless=True))
        except Exception as e:
            resultado = f"❌ Error inesperado: {e}"
        if "🧪" in resultado:
            estado = "ok"
        elif "agotado" in resultado.lower():
            estado = "sin_producto"          # se agoto justo antes de probarlo: no es falla
        elif "🧩" in resultado:
            estado = "captcha"
        else:
            estado = "roto"
        SALUD.registrar_checkout(estado, resultado[:400], url)
        if estado == "roto" and SALUD.checkout_roto_seguido():
            notify("🩺 La prueba del checkout falló 2 veces seguidas: el proceso de pago podría "
                   "estar roto. Revisa capturas_error/ y prueba a mano antes del próximo drop.\n"
                   + resultado[:300])
        return estado
    finally:
        _LOCK_DISPARO.release()


def _job_checkout_diario():
    try:
        probar_checkout()
    except Exception as e:
        print(f"⚠️ Error en la prueba diaria del checkout: {e}")


@app.route("/api/probar_checkout", methods=["POST"])
def api_probar_checkout():
    threading.Thread(target=_job_checkout_diario, daemon=True).start()
    return jsonify({"ok": True})


def _job_smoke_diario():
    """Test de humo diario (mejora 2026-09-16): visita cada producto activo
    SIN comprar, para detectar un selector roto de la tienda con horas de
    anticipacion. Corre en un hilo aparte del disparo de compras, nunca debe
    tumbar el scheduler si algo sale mal."""
    try:
        urls = get_active_product_urls()
        for url in urls:
            try:
                ok, detalle = asyncio.run(test_humo(url))
            except Exception as e:
                ok, detalle = False, f"error inesperado: {e}"
            SALUD.registrar(url, ok, detalle)
            if not ok:
                notify(f"🩺 Test de humo fallo para {url}: {detalle}")
    except Exception as e:
        print(f"⚠️ Error corriendo el test de humo diario: {e}")


@app.route("/run_smoke", methods=["POST"])
def run_smoke_route():
    """Disparo manual del test de humo, para validar selectores antes de un
    drop sin esperar al job de las 8:30."""
    threading.Thread(target=_job_smoke_diario, daemon=True).start()
    return redirect(url_for("index"))


def texto_resumen_semanal(mensajes, exitos, carritos, fallos, escapadas, rep):
    """Resumen de la semana: lo que hizo el bot, cuanto tardo, lo que se te
    escapo y (si el inventario contesta) cuanto te dejo."""
    import re as _re
    tiempos = [float(t) for m in mensajes for t in _re.findall(r"⏱ ([\d.]+) s", m or "")]
    lineas = [f"📋 Resumen semanal del bot: {len(mensajes)} corridas — "
              f"{exitos} pedidos completados, {carritos} agregados al carrito, {fallos} fallidos."]
    if tiempos:
        lineas.append(f"⏱ Compra promedio: {sum(tiempos) / len(tiempos):.1f} s (la más rápida {min(tiempos):.1f} s).")
    if escapadas:
        lineas.append(f"😬 Se agotaron {len(escapadas)} pieza(s) que te avisó el monitor sin que las compraras: "
                      + ", ".join(e["titulo"] or "?" for e in escapadas[:5]) + ("…" if len(escapadas) > 5 else ""))
    if rep and rep.get("compradas"):
        lineas.append(f"💰 Esta semana compró {rep['compradas']} pieza(s) por ${rep['invertido']:,.0f}; "
                      f"de lo comprado en la semana ya vendiste {rep['vendidas']} con ganancia neta "
                      f"${rep['ganancia']:,.0f}.")
    return "\n".join(lineas)


def _job_resumen_semanal():
    """Resumen semanal por notificacion (mejora 2026-09-16): que se intento,
    que se compro y que se perdio en los ultimos 7 dias."""
    try:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("""SELECT message FROM results
                     WHERE created_at >= datetime('now', '-7 days')""")
        mensajes = [row[0] for row in c.fetchall()]
        conn.close()
        exitos = sum(1 for m in mensajes if "🎉" in m)
        carritos = sum(1 for m in mensajes if "✅" in m)
        fallos = len(mensajes) - exitos - carritos
        notify(texto_resumen_semanal(mensajes, exitos, carritos, fallos,
                                     HALLAZGOS.escapadas(7), COLLECTHUB.reporte_bot(7)))
    except Exception as e:
        print(f"⚠️ Error armando el resumen semanal: {e}")


def _job_reintentar_collecthub():
    """Cada 10 min: anota en Chicos Wheels las compras que no se pudieron registrar."""
    try:
        n = COLLECTHUB.reintentar_pendientes()
        if n:
            notify(f"📦 Se anotaron {n} compra(s) pendientes en Chicos Wheels.")
    except Exception as e:
        print(f"⚠️ Error reintentando registros de Chicos Wheels: {e}")


async def _leer_texto(url):
    """Texto visible de una pagina, en Chromium sin ventana. Con el perfil de
    Mattel activo se usa el navegador caliente (la pagina del pedido puede
    pedir la sesion y el perfil no se puede abrir dos veces)."""
    nav = NAVEGADOR.obtener() if NAVEGADOR.perfil_activo() else None
    if nav is not None:
        async def leer():
            ctx = await nav._contexto()
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return await page.inner_text("body")
            finally:
                await page.close()
        return await asyncio.wrap_future(nav.enviar(leer()))
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return await page.inner_text("body")
        finally:
            await browser.close()


def seguimiento_envios():
    """Abre la pagina de estado de cada pedido en camino y pasa al inventario
    la guia y la fecha de llegada. Devuelve cuantas piezas cambiaron."""
    import pedidos_mattel
    cambiaron = 0
    for fila in COLLECTHUB.pendientes_de_envio():
        try:
            texto = asyncio.run(_leer_texto(fila["url_estado"]))
        except Exception as e:
            print(f"⚠️ No se pudo abrir el estado del pedido de {fila.get('titulo')}: {e}")
            continue
        aviso = COLLECTHUB.aplicar_envio(fila, pedidos_mattel.leer_envio(texto))
        if aviso:
            cambiaron += 1
            notify(aviso)
    return cambiaron


def _job_seguimiento_envios():
    """Cada 6 h: guia y fecha de llegada de lo que compro el bot."""
    if _LOCK_DISPARO.locked():
        return                    # comprando de verdad: no estorbar
    try:
        seguimiento_envios()
    except Exception as e:
        print(f"⚠️ Error en el seguimiento de envíos: {e}")


def _job_apartados_por_vencer():
    """Todos los días 9:00: avisa por Telegram los apartados que vencen hoy o mañana."""
    try:
        avisos = COLLECTHUB.apartados_por_vencer()
        if avisos:
            notify("📅 Apartados por vencer en Chicos Wheels:\n" + "\n".join(avisos))
    except Exception as e:
        print(f"⚠️ Error avisando apartados por vencer: {e}")


def _job_reporte_chicos_wheels():
    """Domingo 20:05: manda por Telegram el PDF semanal de Chicos Wheels."""
    pdf = COLLECTHUB.reporte_semanal_pdf()
    if not pdf:
        return
    try:
        from bot_logic import _telegram_del_monitor
        token, chat = _telegram_del_monitor()
        if not token or not chat:
            return
        resp = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                             data={"chat_id": chat, "caption": "📊 Reporte semanal de Chicos Wheels"},
                             files={"document": (f"reporte-{datetime.now():%Y-%m-%d}.pdf", pdf, "application/pdf")},
                             timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ No se pudo mandar el reporte semanal por Telegram: {e}")


async def run_all():
    urls = get_active_product_urls()
    proxies = get_proxies()
    tasks = []
    for i, url in enumerate(urls):
        proxy = proxies[i % len(proxies)] if proxies else None
        tasks.append(comprar_producto(url, proxy))
    resultados = await asyncio.gather(*tasks, return_exceptions=True)
    for url, r in zip(urls, resultados):
        if isinstance(r, Exception):
            mensaje = f"❌ Error inesperado: {r}"
            add_result(mensaje)
            notify(mensaje)
        else:
            add_result(r)
            if "🎉" in r:
                marcar_producto_completado(url)
    if urls:
        _revisar_fallos_seguidos()


# Ventana de reintentos del evento puntual (mejora 2026-09-16): si Mattel
# publica el stock unos segundos despues de la hora exacta anunciada, un
# solo intento en el minuto exacto lo pierde. NO cambia CUANDO dispara el
# evento (sigue siendo una sola vez, en el minuto configurado) — solo cambia
# QUE PASA una vez que dispara: en vez de un intento, reintenta cada
# EVENTO_INTERVALO_SEGUNDOS durante EVENTO_VENTANA_SEGUNDOS, o hasta el
# primer exito. Nunca notifica en cada intento fallido intermedio (serian
# hasta 12 avisos en 3 minutos si algo esta roto) — solo notifica UNA vez al
# final con el desenlace real. Deliberadamente NO llama a
# _revisar_fallos_seguidos(): "agotado" repetido cada 15s durante un drop es
# esperado, no la señal de un selector roto que esa funcion busca detectar.
EVENTO_VENTANA_SEGUNDOS = 300  # 5 min: el drop RLC del 10/11 se agotó después de los 3 min
EVENTO_INTERVALO_SEGUNDOS = 15


async def _intentar_evento(urls=None, cantidad=None):
    """Disparo programado: compra `urls` (por defecto las activas) con TODAS
    las cuentas activas a la vez (multicuenta, 2026-11-10): un navegador por
    cuenta, cada una con su sesion, tarjeta y direccion. Devuelve True si
    alguna cuenta logro algo."""
    urls = urls or get_active_product_urls()
    if not urls:
        return False
    lista, fuera = CUENTAS.para_disparo()
    for cuenta, motivo in fuera:
        notify(f"⚪ [{cuenta.nombre}] no entra a este disparo: {motivo}.")
    varias = len(lista) > 1
    resultados = await asyncio.gather(
        *[_intentar_evento_cuenta(urls, c, cantidad, varias) for c in lista],
        return_exceptions=True)
    return any(r is True for r in resultados)


async def _intentar_evento_cuenta(urls, cuenta, cantidad=None, varias=False):
    proxies = get_proxies()
    limite = datetime.now() + timedelta(seconds=EVENTO_VENTANA_SEGUNDOS)
    intentos = 0
    ultimo_por_url = {}
    quien = f"[{cuenta.nombre}] " if varias else ""
    while True:
        intentos += 1
        for i, url in enumerate(urls):
            if "🎉" in ultimo_por_url.get(url, ""):
                continue
            proxy = proxies[i % len(proxies)] if proxies else None
            inicio_intento = datetime.now()
            try:
                # Con el navegador caliente de la cuenta (precalentado antes
                # del drop y con su sesion) cuando no hay proxy de por medio.
                nav = None if proxy else NAVEGADOR.obtener(cuenta)
                resultado = await comprar_producto(url, proxy, cantidad=cantidad, notificar=False,
                                                   navegador=nav, cuenta=cuenta)
            except Exception as e:
                resultado = f"❌ Error inesperado: {e}"
            if "🧩" in resultado:
                # El tiempo esperando a que Gonza resuelva un captcha no se
                # descuenta de la ventana de reintentos (drop 2026-11-10).
                limite += datetime.now() - inicio_intento
            ultimo_por_url[url] = resultado
            add_result(quien + resultado)
            if "🎉" in resultado:
                marcar_producto_completado(url)
                _despues_de_comprar(url, resultado, cuenta, origen="disparo")
        if all(("✅" in r or "🎉" in r) for r in ultimo_por_url.values()):
            break
        if datetime.now() >= limite:
            break
        await asyncio.sleep(EVENTO_INTERVALO_SEGUNDOS)

    exitos = [r for r in ultimo_por_url.values() if "✅" in r or "🎉" in r]
    if exitos:
        notify(f"🎯 {quien}Evento puntual: {exitos[0]} (intento {intentos})")
    else:
        ultimo = next(iter(ultimo_por_url.values()), "sin resultado")
        # Si se agoto, queda vigilada para el restock (antes era a mano). Va
        # en el mismo aviso final: un solo mensaje por disparo.
        vigiladas = [url for url, r in ultimo_por_url.items()
                     if ("Producto agotado" in r or "sold out" in r.lower()) and _vigilar_restock(url)]
        notify(f"⏱️ {quien}Evento puntual: {intentos} intentos en "
               f"{EVENTO_VENTANA_SEGUNDOS}s, sin éxito. Último resultado: {ultimo}"
               + ("\n👀 Queda vigilada para el restock (te aviso con el botón Comprar)." if vigiladas else ""))
    return bool(exitos)


# --- Despues de comprar: inventario y borrador para Facebook/Instagram ------
def _datos_pieza(url, html=None):
    """(titulo, precio_mxn, limite, imagen) desde el .js de Shopify, con un
    reintento; si Mattel responde con su pagina de proteccion en vez del
    JSON, se leen de la pagina (meta og y "Limit N Per Customer"). Nunca lanza."""
    import re as _re
    from bot_logic import limite_desde_datos
    base = url.split("?")[0].split("#")[0].rstrip("/")
    for intento in range(2):
        try:
            r = requests.get(base + ".js", timeout=15, headers={"User-Agent": CUENTAS.UA})
            d = r.json()
            img = d.get("featured_image") or ""
            if img.startswith("//"):
                img = "https:" + img
            return (d.get("title"), (d.get("price") or 0) / 100 or None,
                    limite_desde_datos(d.get("tags")), img)
        except Exception:
            if intento == 0:
                time.sleep(1.5)
    try:
        if html is None:
            html = CUENTAS.principal()._sesion_http().get(base, timeout=20).text
        def meta(prop):
            m = _re.search(r'<meta property="%s" content="([^"]+)"' % _re.escape(prop), html or "")
            return m.group(1) if m else None
        precio = meta("og:price:amount") or meta("product:price:amount")
        try:
            precio = float(precio.replace(",", "")) if precio else None
        except ValueError:
            precio = None
        return meta("og:title"), precio, limite_desde_datos([], _re.sub(r"<[^>]+>", " ", html or "")), meta("og:image")
    except Exception:
        return None, None, None, None


def _reventa_conocida(url):
    """Precio de reventa que ya calculo el monitor (eBay/Mercado Libre)."""
    handle = url.split("/products/")[-1].split("?")[0]
    try:
        conn = sqlite3.connect(DB)
        r = conn.execute("SELECT reventa_mxn FROM hallazgos WHERE url LIKE ? AND reventa_mxn IS NOT NULL "
                         "ORDER BY id DESC LIMIT 1", (f"%{handle}%",)).fetchone()
        conn.close()
        return r[0] if r else None
    except Exception:
        return None


def borrador_publicacion(titulo, costo_mxn, reventa_mxn=None, piezas=1):
    """Texto listo para Facebook/Instagram. Precio sugerido: la reventa que
    vio el monitor; si no hay, costo x 1.8 redondeado a 50. Contacto solo por
    Messenger e Instagram (regla de Erik G)."""
    sugerido = reventa_mxn or (round(costo_mxn * 1.8 / 50) * 50 if costo_mxn else None)
    lineas = [f"🔥 ¡NUEVO EN ERIK G! 🔥", f"{titulo}"]
    if sugerido:
        lineas.append(f"💲 ${sugerido:,.0f} MXN")
    if piezas and piezas > 1:
        lineas.append(f"📦 {piezas} piezas disponibles")
    lineas += ["🚚 Entrega el sábado en Balderas",
               "📩 Apártala por Messenger o Instagram",
               "#HotWheels #RedLineClub #ColeccionHotWheels #ErikG"]
    return "\n".join(lineas), sugerido


def _despues_de_comprar(url, resultado, cuenta=None, origen="disparo"):
    """Tras un pago real: anota en el inventario (antes el disparo programado
    no lo hacia) y manda el borrador de la publicacion."""
    if os.environ.get("HOTWHEELS_DRY_RUN") == "1" or "🎉" not in (resultado or ""):
        return
    titulo, precio, limite, imagen = _datos_pieza(url)
    piezas = limite or 1
    try:
        ok_ch, msg_ch = COLLECTHUB.registrar_compra(
            url=url, titulo=titulo, precio_mxn=precio, imagen=imagen, origen=origen,
            cantidad=piezas, pedido=(f"[{cuenta.nombre}] " if cuenta else "") + str(resultado)[:280])
        if not ok_ch:
            notify(f"⚠️ Se compró, pero no se pudo anotar en Chicos Wheels: {msg_ch}")
    except Exception as e:
        notify(f"⚠️ Se compró, pero no se pudo anotar en Chicos Wheels: {e}")
    texto, _ = borrador_publicacion(titulo or url, precio, _reventa_conocida(url), piezas)
    notify("📝 Borrador para Facebook/Instagram (cópialo y ajusta el precio):\n\n" + texto
           + (f"\n\nFoto: {imagen}" if imagen else ""))


def _vigilar_restock(url):
    try:
        import hw_extras as EX
        datos = os.environ.get("HOTWHEELS_DATOS") or os.path.dirname(os.path.abspath(__file__))
        handle = url.split("/products/")[-1].split("?")[0]
        nuevo, _ = EX.agregar_vigilado(os.path.join(datos, "vigilar.json"), handle,
                                       "Restock: se agotó en el disparo del %s" % datetime.now().strftime("%d/%m"))
        return bool(nuevo)
    except Exception as e:
        print(f"⚠️ No se pudo dejar en vigilancia {url}: {e}")
        return False


# --- Scheduler ---
scheduler = BackgroundScheduler()

MINUTOS_PRECALENTAR_EVENTO = 2
_EVENTO_PRECALENTADO = {"id": None}


def _precalentar(urls, motivo):
    """Abre la pieza en el navegador caliente de cada cuenta activa."""
    abiertas = 0
    for cuenta in CUENTAS.para_disparo()[0] or [CUENTAS.principal()]:
        nav = NAVEGADOR.obtener(cuenta)
        if nav is None:
            continue
        for url in urls:
            try:
                nav.precalentar(url)
                abiertas += 1
            except Exception as e:
                print(f"  ⚠️ No se pudo precalentar {url}: {e}")
    if abiertas:
        notify(f"🔥 {motivo}: navegador listo ({abiertas} ventana(s)). Si ves una verificación "
               "de Cloudflare en la ventana, resuélvela ya.")
    return abiertas


def _precalentar_evento(evento, ahora):
    """2 min antes del disparo abre el navegador caliente con la pagina de
    cada pieza (2026-11-10): el disparo ya no pierde ~15 s cargando, y si
    Cloudflare pide verificar, sale ANTES del drop y Gonza lo resuelve con
    calma. Una sola vez por evento."""
    if _EVENTO_PRECALENTADO["id"] == evento["id"]:
        return
    try:
        cuando = datetime.strptime(evento["fecha"], "%Y-%m-%d").replace(
            hour=evento["hora"], minute=evento["minuto"])
    except Exception:
        return
    faltan = (cuando - ahora).total_seconds()
    if not (0 < faltan <= MINUTOS_PRECALENTAR_EVENTO * 60 + 30):
        return
    urls = get_active_product_urls()
    if not urls:
        return
    _EVENTO_PRECALENTADO["id"] = evento["id"]
    _precalentar(urls, f"Disparo de las {evento['hora']:02d}:{evento['minuto']:02d}")


# --- Calendario de drops (drops.py) -------------------------------------------
def chequeo_cuentas(titulo="Chequeo"):
    """Semaforo de todas las cuentas: sesion, tarjeta, CVV, RFC, telefono y
    carrito, mas el modo de pago. Devuelve el texto (y lo usa el drop a -30)."""
    partes = [f"🩺 {titulo}"]
    partes.append("💳 Modo: " + ("🧪 ENSAYO (no paga)" if os.environ.get("HOTWHEELS_DRY_RUN") == "1"
                                  else "pago real"))
    for cuenta in CUENTAS.listar() or [CUENTAS.principal()]:
        try:
            partes.append(CUENTAS.texto_chequeo(cuenta, CUENTAS.chequeo(cuenta)))
        except Exception as e:
            partes.append(f"👤 {cuenta.nombre}\n  🟡 no se pudo revisar ({e})")
    return "\n".join(partes)


def _agenda_drops(ahora_utc=None):
    """Corre cada minuto: los pasos de cada drop programado y el disparo."""
    for d in DROPS.programados(DB):
        pasos, disparar = DROPS.pasos_pendientes(d, ahora_utc)
        nombre = d["titulo"] or d["url"]
        for paso in pasos:
            if not DROPS.marcar_hecho(DB, d["id"], paso):
                continue
            try:
                if paso == "chequeo":
                    notify(chequeo_cuentas(f"Faltan 30 min para {nombre} ({DROPS.hora_local(d['cuando'])})"))
                elif paso == "cvv":
                    for cuenta in CUENTAS.para_disparo()[0] or [CUENTAS.principal()]:
                        if not cuenta.datos()["tarjeta1"]["cvv"]:
                            notify(f"💳 [{cuenta.nombre}] Faltan 5 min para {nombre}: pon tu CVV en "
                                   f"hotwheels/{os.path.relpath(cuenta.env, CUENTAS.DIR).replace(os.sep, '/')} "
                                   "(HOTWHEELS_CARD_CVV) y guarda.")
                elif paso == "precalentar":
                    _precalentar([d["url"]], f"{nombre} sale a las {DROPS.hora_local(d['cuando'])}")
            except Exception as e:
                print(f"⚠️ Paso {paso} del drop {d['id']}: {e}")
        if disparar:
            DROPS.cambiar_estado(DB, d["id"], "hecho")
            asyncio.run(_intentar_evento([d["url"]], cantidad=d["cantidad"]))


def accion_drop(drop_id, programar):
    """Boton de Telegram del calendario. Devuelve el texto de respuesta."""
    d = DROPS.obtener(DB, drop_id)
    if not d:
        return "Ese lanzamiento ya no existe."
    if not programar:
        DROPS.cambiar_estado(DB, drop_id, "descartado")
        return f"Ok, no programo {d['titulo'] or d['url']}."
    if d["cuando"] <= datetime.now(timezone.utc):
        return "Ese lanzamiento ya pasó."
    _, _, limite, _ = _datos_pieza(d["url"])
    DROPS.cambiar_estado(DB, drop_id, "programado", cantidad=limite)
    cuentas_txt = ", ".join(c.nombre for c in CUENTAS.listar()) or "principal"
    return (f"✅ Disparo programado: {d['titulo'] or d['url']}\n"
            f"🕐 {DROPS.hora_local(d['cuando'])} · {limite or 'el máximo de la página'} pieza(s) por cuenta\n"
            f"👤 Cuentas: {cuentas_txt}\n"
            "Agenda: chequeo a -30 min, aviso de CVV a -5, navegador listo a -2 y disparo a la hora.")


MAX_REVISIONES_CALENDARIO = 30


def _candidatos_calendario():
    """Piezas a las que vale la pena buscarles fecha de lanzamiento: las que
    vigilas a mano, las "coming soon" del monitor y los deseados recientes."""
    import json as _json
    import hw_extras as EX
    datos = os.environ.get("HOTWHEELS_DATOS") or os.path.dirname(os.path.abspath(__file__))
    handles = [e["handle"] for e in EX.listar_vigilados(os.path.join(datos, "vigilar.json"))]
    try:
        with open(os.path.join(datos, "estado.json"), encoding="utf-8") as f:
            vig = (_json.load(f) or {}).get("vigilancia") or {}
        handles += [h for h, v in vig.items() if (v or {}).get("motivo") == "coming_soon"]
    except Exception:
        pass
    try:
        conn = sqlite3.connect(DB)
        desde = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
        for (u,) in conn.execute("SELECT url FROM hallazgos WHERE ultima_vez >= ? AND "
                                 "(deseado = 1 OR impacto LIKE 'Alto%' OR url LIKE '%rlc%')", (desde,)):
            handles.append(u.split("/products/")[-1].split("?")[0])
        conn.close()
    except Exception:
        pass
    vistos, salida = set(), []
    for h in handles:
        if h and h not in vistos:
            vistos.add(h)
            salida.append(h)
    return salida[:MAX_REVISIONES_CALENDARIO]


def revisar_calendario(obtener_html=None):
    """Busca fechas de lanzamiento y propone el disparo por Telegram (una
    vez por lanzamiento). Devuelve los drops nuevos (para las pruebas)."""
    import re as _re
    sesion = CUENTAS.principal()._sesion_http() if obtener_html is None else None
    nuevos = []
    for handle in _candidatos_calendario():
        url = f"https://creations.mattel.com/en-mx/products/{handle}"
        try:
            html = obtener_html(url) if obtener_html else sesion.get(url, timeout=20).text
        except Exception:
            continue
        cuando = DROPS.leer_lanzamiento(html)
        if not cuando or cuando <= datetime.now(timezone.utc) + timedelta(minutes=5):
            continue
        m = _re.search(r'<meta property="og:title" content="([^"]+)"', html or "")
        titulo = (m.group(1) if m else handle).strip()
        drop_id, es_nuevo = DROPS.proponer(DB, url, titulo, cuando)
        if not es_nuevo:
            continue
        nuevos.append(drop_id)
        notify_botones(f"📅 Lanzamiento detectado\n{titulo}\n🕐 {DROPS.hora_local(cuando)} (hora local)\n{url}\n\n"
                       "¿Programo el disparo con todas tus cuentas?",
                       [[{"text": "📅 Programar disparo", "callback_data": f"pd:{drop_id}"},
                         {"text": "No", "callback_data": f"pn:{drop_id}"}]])
    return nuevos


# --- Mensajes de Telegram: comandos y links de Mattel (2026-11-10) -----------
AYUDA_TELEGRAM = (
    "🤖 Bot Hot Wheels — lo que entiendo:\n"
    "• Pega un link de creations.mattel.com: te digo precio, límite, si está a la venta "
    "o cuándo sale, con el botón para comprar o programar el disparo.\n"
    "• /estado — semáforo de tus cuentas (sesión, tarjeta, CVV, RFC, carrito) y del monitor.\n"
    "• /drops — próximos lanzamientos detectados y programados.\n"
    "• /ayuda — esto.")

_RE_LINK_MATTEL = None


def _link_mattel(texto):
    import re as _re
    global _RE_LINK_MATTEL
    if _RE_LINK_MATTEL is None:
        _RE_LINK_MATTEL = _re.compile(r"https?://creations\.mattel\.com/(?:[a-z]{2}-[a-z]{2}/)?products/([a-z0-9-]+)", _re.I)
    m = _RE_LINK_MATTEL.search(texto or "")
    return ("https://creations.mattel.com/en-mx/products/" + m.group(1).lower()) if m else None


def analizar_pieza(url, obtener_html=None):
    """Lo que Gonza necesita saber de una pieza para decidir. Devuelve
    (texto, filas_de_botones)."""
    import re as _re
    titulo, precio, limite, imagen = _datos_pieza(url)
    try:
        if obtener_html:
            html = obtener_html(url)
        else:
            html = CUENTAS.principal()._sesion_http().get(url, timeout=20).text
    except Exception:
        html = ""
    if not titulo:
        m = _re.search(r'<meta property="og:title" content="([^"]+)"', html or "")
        titulo = m.group(1) if m else None
    if not titulo and not html:
        return "No pude abrir esa pieza en Mattel. Revisa el link o prueba en un momento.", None
    cuando = DROPS.leer_lanzamiento(html)
    lineas = [f"🔎 {titulo or url}"]
    if precio:
        lineas.append(f"💲 ${precio:,.0f} MXN")
    if limite:
        lineas.append(f"📦 Límite {limite} por cliente")
    if "rlc" in url:
        lineas.append("🔐 Red Line Club: pide membresía y sesión")
    ahora = datetime.now(timezone.utc)

    if cuando and cuando > ahora + timedelta(minutes=2):
        drop_id, _ = DROPS.proponer(DB, url, titulo or url, cuando)
        d = DROPS.obtener(DB, drop_id)
        lineas.append(f"🕐 Sale el {DROPS.hora_local(cuando)} (hora local)")
        if d and d["estado"] == "programado":
            lineas.append("✅ El disparo ya está programado.")
            return "\n".join(lineas), None
        return "\n".join(lineas), [[{"text": "📅 Programar disparo", "callback_data": f"pd:{drop_id}"},
                                     {"text": "No", "callback_data": f"pn:{drop_id}"}]]

    disponible = _disponible_ahora(url)
    if disponible:
        hid = HALLAZGOS.registrar(url, titulo=titulo, imagen=imagen, precio_mxn=precio, tipo="manual",
                                  deseado=True)
        lineas.append("🟢 A la venta ahora")
        if hid:
            return "\n".join(lineas), [[{"text": "🛒 Comprar con el bot", "callback_data": f"c:{hid}"},
                                        {"text": "🙈 Ignorar", "callback_data": f"i:{hid}"}]]
        return "\n".join(lineas), None
    nuevo = _vigilar_restock(url)
    lineas.append("🔴 Agotada" + (": la dejo vigilada y te aviso si hay restock (con el botón Comprar)."
                                  if nuevo else ": ya estaba vigilada para el restock."))
    return "\n".join(lineas), None


def _disponible_ahora(url):
    """True si Shopify la tiene a la venta (variante disponible) y la página
    no dice "Coming Soon" con fecha futura."""
    try:
        base = url.split("?")[0].rstrip("/")
        d = requests.get(base + ".js", timeout=15, headers={"User-Agent": CUENTAS.UA}).json()
        return bool(d.get("available"))
    except Exception:
        return False


def texto_estado():
    partes = [chequeo_cuentas("Estado ahora")]
    try:
        latido = os.path.join(os.environ.get("HOTWHEELS_DATOS") or os.path.dirname(os.path.abspath(__file__)),
                              "latido.txt")
        minutos = (time.time() - os.path.getmtime(latido)) / 60
        partes.append(("🟢" if minutos < 10 else "🔴") + f" Monitor: último barrido hace {minutos:.0f} min")
    except OSError:
        partes.append("🟡 Monitor: sin latido todavía")
    prog = DROPS.programados(DB)
    partes.append(f"📅 Disparos programados: {len(prog)}" + "".join(
        f"\n  • {DROPS.hora_local(d['cuando'])} {d['titulo'] or d['url']}" for d in prog[:5]))
    return "\n".join(partes)


def texto_drops():
    lista = DROPS.proximos(DB)
    if not lista:
        return "📅 No hay lanzamientos próximos detectados. Pégame el link de una pieza para revisarla."
    marca = {"programado": "✅", "propuesto": "❔", "hecho": "✔️"}
    return "📅 Próximos lanzamientos:\n" + "\n".join(
        f"{marca.get(d['estado'], '•')} {DROPS.hora_local(d['cuando'])} · {d['titulo'] or d['url']}" for d in lista)


def atender_mensaje(texto):
    """Mensaje de Gonza en Telegram -> (respuesta, botones)."""
    t = (texto or "").strip()
    url = _link_mattel(t)
    if url:
        return analizar_pieza(url)
    comando = t.split()[0].lower().split("@")[0] if t else ""
    if comando in ("/estado", "/status", "estado"):
        return texto_estado(), None
    if comando in ("/drops", "/calendario", "drops"):
        return texto_drops(), None
    if comando in ("/ayuda", "/start", "/help", "ayuda"):
        return AYUDA_TELEGRAM, None
    if t.startswith("/"):
        return "No conozco ese comando.\n\n" + AYUDA_TELEGRAM, None
    return None, None


def _job_calendario():
    try:
        revisar_calendario()
    except Exception as e:
        print(f"⚠️ Error en el calendario de drops: {e}")


def _job_revisar_sesiones():
    """2 veces al dia: si la sesion de Mattel de una cuenta vencio, avisa
    con tiempo (y no el dia del drop)."""
    for cuenta in CUENTAS.listar():
        if cuenta.es_principal and os.environ.get("HOTWHEELS_PERFIL_MATTEL") != "1":
            continue
        try:
            ok, detalle = cuenta.revisar_sesion()
        except Exception as e:
            ok, detalle = None, str(e)
        if ok is False:
            cmd = "python iniciar_sesion_mattel.py" + ("" if cuenta.es_principal else f" --cuenta {cuenta.nombre}")
            notify(f"🔐 [{cuenta.nombre}] {detalle}. Con la app cerrada corre: {cmd}")


def scheduled_run():
    ahora = datetime.now()

    # Drops del calendario (programados desde Telegram).
    try:
        _agenda_drops()
    except Exception as e:
        print(f"⚠️ Error en la agenda de drops: {e}")

    # Evento puntual: una sola ejecucion exacta a fecha+hora+minuto configurados,
    # para drops que anuncian una hora especifica (ej. 10:03), no solo "en punto".
    evento = get_event()
    if evento and not evento["hecho"]:
        _precalentar_evento(evento, ahora)
        if (
            ahora.strftime("%Y-%m-%d") == evento["fecha"]
            and ahora.hour == evento["hora"]
            and ahora.minute == evento["minuto"]
        ):
            marcar_evento_hecho(evento["id"])
            asyncio.run(_intentar_evento())
            return

    # Ventana de horas recurrente (se revisa solo en el minuto 0 para no
    # disparar 60 veces por hora ahora que el cron corre cada minuto).
    if ahora.minute == 0:
        start_hour, end_hour = get_schedule()
        if start_hour <= ahora.hour <= end_hour:
            asyncio.run(run_all())

scheduler.add_job(scheduled_run, "cron", minute="*")
# Calendario de drops: busca fechas de lanzamiento cada 30 min (2026-11-10).
scheduler.add_job(_job_calendario, "cron", minute="7,37")
# Sesion de Mattel de cada cuenta: 2 veces al dia, para enterarse antes del drop.
scheduler.add_job(_job_revisar_sesiones, "cron", hour="9,20", minute=5)
# Test de humo a las 8:30 — antes de cualquier drop matutino tipico, para
# avisar con horas de anticipacion si un selector se rompio.
scheduler.add_job(_job_smoke_diario, "cron", hour=8, minute=30)
# Prueba del checkout completo (ensayo) a las 8:45.
scheduler.add_job(_job_checkout_diario, "cron", hour=8, minute=45)
# Resumen semanal los domingos a las 20:00.
scheduler.add_job(_job_resumen_semanal, "cron", day_of_week="sun", hour=20, minute=0)
scheduler.add_job(_job_reintentar_collecthub, "cron", minute="*/10")
scheduler.add_job(_job_apartados_por_vencer, "cron", hour=9, minute=0)
scheduler.add_job(_job_reporte_chicos_wheels, "cron", day_of_week="sun", hour=20, minute=5)
scheduler.add_job(_job_seguimiento_envios, "cron", hour="7,13,19", minute=20)

# --- API para gráficos ---
@app.route("/chart_data")
def chart_data():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT created_at, message FROM results")
    rows = c.fetchall()
    conn.close()

    success = {}
    fail = {}
    for created_at, message in rows:
        date = created_at.split(" ")[0]
        if "✅" in message or "🎉" in message:
            success[date] = success.get(date, 0) + 1
        else:
            fail[date] = fail.get(date, 0) + 1

    return jsonify({"success": success, "fail": fail})

# --- Rutas Flask ---
@app.route("/")
def index():
    start_hour, end_hour = get_schedule()
    productos = get_products()
    salud_por_url = SALUD.ultimo_por_url()
    precios_por_url = {p["url"]: PRECIOS.resumen(p["url"]) for p in productos}
    return render_template(
        "index.html",
        products=productos,
        proxies=get_proxies(),
        results=get_results(),
        start_hour=start_hour,
        end_hour=end_hour,
        event=get_event(),
        dry_run=os.environ.get("HOTWHEELS_DRY_RUN") == "1",
        collecthub_registros=COLLECTHUB.ultimos(5),
        salud=salud_por_url,
        precios=precios_por_url,
    )

# --- Piezas encontradas por el monitor: el usuario decide ---
app.register_blueprint(monitor_admin.bp)


@app.route("/api/estado")
def api_estado():
    """Todo lo que la cabecera del panel necesita en una sola llamada."""
    hall = HALLAZGOS.resumen(30)
    ultimo_checkout = (SALUD.ultimos_checkout(1) or [None])[0]
    return jsonify({
        "monitor": monitor_admin.estado_monitor(),
        "comprando": _LOCK_DISPARO.locked(),
        "en_cola": hall.get("en_cola", 0),
        "hallazgos": hall,
        "checkout": ultimo_checkout,
        "limites": LIMITES.obtener(),
        "ensayo": os.environ.get("HOTWHEELS_DRY_RUN") == "1",
        "navegador": NAVEGADOR._NAVEGADOR.estado() if NAVEGADOR._NAVEGADOR else None,
        # Como respondio el monitor de relevo de Railway al ultimo latido.
        "relevo": dict(getattr(sys.modules.get("monitor"), "ESTADO_RELEVO", None) or {}) or None,
    })


@app.route("/api/limites", methods=["GET", "POST"])
def api_limites():
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        ok, mensaje = LIMITES.guardar(d.get("tope_pieza_mxn"), d.get("tope_mensual_mxn"))
        if not ok:
            return jsonify({"ok": False, "error": mensaje}), 400
    return jsonify({"ok": True, **LIMITES.obtener()})


@app.route("/api/coleccion")
def api_coleccion():
    return jsonify({"ok": True, **COLECCION.resumen()})


@app.route("/api/hallazgos")
def api_hallazgos():
    ver = request.args.get("ver", "pendientes")
    if ver == "pendientes":
        estados = ("pendiente", "en_cola", "comprando")
    else:  # historial: lo ya resuelto
        estados = ("comprado", "carrito", "fallo", "ignorado")
    piezas = HALLAZGOS.listar(estados)
    if ver == "pendientes":
        orden = request.args.get("orden", "recientes")
        if orden == "ganancia":
            piezas.sort(key=lambda p: (not p["disponible"], -(p["ganancia_mxn"] if p["ganancia_mxn"] is not None else -1e9)))
        elif orden == "precio":
            piezas.sort(key=lambda p: (not p["disponible"], p["precio_mxn"] if p["precio_mxn"] is not None else 1e9))
        COLECCION.marcar(piezas)
    for p in piezas:
        if p["estado"] == "en_cola":
            p["posicion_cola"] = HALLAZGOS.posicion_en_cola(p["id"])
    return jsonify({"ok": True, "piezas": piezas})


@app.route("/api/hallazgos/<int:hallazgo_id>/comprar", methods=["POST"])
def api_hallazgo_comprar(hallazgo_id):
    d = request.get_json(silent=True) or {}
    r = solicitar_compra(hallazgo_id, d.get("cantidad", 1), bool(d.get("forzar")))
    return jsonify(r), (200 if r.get("ok") else r.get("codigo", 400))


@app.route("/api/hallazgos/<int:hallazgo_id>/ignorar", methods=["POST"])
def api_hallazgo_ignorar(hallazgo_id):
    if not HALLAZGOS.obtener(hallazgo_id):
        return jsonify({"ok": False, "error": "no existe esa pieza"}), 404
    HALLAZGOS.cambiar_estado(hallazgo_id, "ignorado")
    return jsonify({"ok": True})


@app.route("/api/hallazgos/<int:hallazgo_id>/restaurar", methods=["POST"])
def api_hallazgo_restaurar(hallazgo_id):
    if not HALLAZGOS.obtener(hallazgo_id):
        return jsonify({"ok": False, "error": "no existe esa pieza"}), 404
    HALLAZGOS.cambiar_estado(hallazgo_id, "pendiente")
    return jsonify({"ok": True})


@app.route("/api/hallazgos/<int:hallazgo_id>/ya_comprada", methods=["POST"])
def api_hallazgo_ya_comprada(hallazgo_id):
    """El usuario compro por su cuenta (ej. con el link del carrito): queda
    marcada y se anota en Chicos Wheels."""
    pieza = HALLAZGOS.obtener(hallazgo_id)
    if not pieza:
        return jsonify({"ok": False, "error": "no existe esa pieza"}), 404
    ok, mensaje = COLLECTHUB.registrar_compra(
        url=pieza["url"], titulo=pieza["titulo"], precio_mxn=pieza["precio_mxn"],
        imagen=pieza["imagen"], origen="manual")
    HALLAZGOS.cambiar_estado(hallazgo_id, "comprado", "Marcada como comprada a mano")
    return jsonify({"ok": True, "chicos_wheels": ok, "mensaje": mensaje})


@app.route("/comprar_url/<int:product_id>", methods=["POST"])
def comprar_url_route(product_id):
    """Boton Comprar de uno de "mis links" (los que el usuario agrego a mano)."""
    producto = next((p for p in get_products() if p["id"] == product_id), None)
    if not producto:
        return jsonify({"ok": False, "error": "no existe ese link"}), 404
    if not _LOCK_DISPARO.acquire(blocking=False):
        return jsonify({"ok": False, "error": "ya hay una compra en curso, espera a que termine"}), 409
    try:
        _comprar_pedido_por_usuario(producto["url"], None, None, 1)
    except Exception as e:
        _LOCK_DISPARO.release()
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/add_url", methods=["POST"])
def add_url():
    url = request.form.get("url")
    if url:
        new_id = add_product(url)
        try:
            datos = asyncio.run(obtener_datos_producto(url))
            if datos["image_url"]:
                set_product_image(new_id, datos["image_url"])
            PRECIOS.registrar(url, datos["precio_mxn"])
        except Exception:
            pass  # sin imagen/precio no bloquea el registro del producto
    return redirect(url_for("index"))

@app.route("/refresh_image/<int:product_id>", methods=["POST"])
def refresh_image_route(product_id):
    productos = get_products()
    producto = next((p for p in productos if p["id"] == product_id), None)
    if producto:
        try:
            datos = asyncio.run(obtener_datos_producto(producto["url"]))
            set_product_image(product_id, datos["image_url"])
            PRECIOS.registrar(producto["url"], datos["precio_mxn"])
        except Exception:
            pass
    return redirect(url_for("index"))

@app.route("/toggle_product/<int:product_id>", methods=["POST"])
def toggle_product_route(product_id):
    activar = request.form.get("active") == "1"
    set_product_active(product_id, activar)
    return redirect(url_for("index"))

@app.route("/delete_product/<int:product_id>", methods=["POST"])
def delete_product_route(product_id):
    delete_product(product_id)
    return redirect(url_for("index"))

@app.route("/add_proxy", methods=["POST"])
def add_proxy_route():
    server = request.form.get("server")
    username = request.form.get("username")
    password = request.form.get("password")
    if server:
        add_proxy(server, username, password)
    return redirect(url_for("index"))

@app.route("/set_schedule", methods=["POST"])
def set_schedule_route():
    start_hour = int(request.form.get("start_hour"))
    end_hour = int(request.form.get("end_hour"))
    set_schedule(start_hour, end_hour)
    return redirect(url_for("index"))

@app.route("/set_event", methods=["POST"])
def set_event_route():
    fecha = request.form.get("fecha")
    hora = int(request.form.get("hora"))
    minuto = int(request.form.get("minuto"))
    if fecha:
        set_event(fecha, hora, minuto)
    return redirect(url_for("index"))

@app.route("/clear_event", methods=["POST"])
def clear_event_route():
    clear_event()
    return redirect(url_for("index"))

@app.route("/clear_results", methods=["POST"])
def clear_results_route():
    clear_results()
    return redirect(url_for("index"))

@app.route("/run", methods=["POST"])   # POST: un simple enlace/prefetch nunca debe disparar compras
def run_bot():
    asyncio.run(run_all())
    return redirect(url_for("index"))

# --- Punto de entrada ---
def host_seguro(host):
    """El panel puede COMPRAR y este modo suelto no pide contraseña: siempre escucha solo en esta PC.
    Para usarlo desde otro equipo se entra por Chicos Wheels (/bot/, con la sesión de su login).
    Devuelve (host, aviso)."""
    host = (host or "127.0.0.1").strip()
    if host in ("127.0.0.1", "localhost", "::1"):
        return "127.0.0.1", None
    return "127.0.0.1", ("PANEL_HOST=%s ignorado: el panel suelto solo abre en esta PC. "
                         "Desde otro equipo entra por Chicos Wheels (/bot/)." % host)


def nota_pago():
    """Para la confirmacion de Telegram: que tarjetas puede usar esta compra."""
    from bot_logic import tarjetas_configuradas
    n = len(tarjetas_configuradas())
    if n <= 1:
        return ""
    return (f"💳 Si Mattel rechaza la tarjeta 1, se intenta con la siguiente "
            f"({n - 1} de respaldo). Solo si la rechaza: nunca se paga dos veces.")


def precalentar(url):
    """Abre la pieza en el navegador caliente para que la compra arranque con
    la pagina lista. Nunca truena ni frena a quien la llama."""
    try:
        nav = NAVEGADOR.obtener()
        if nav is not None and url:
            nav.precalentar(url)
    except Exception as e:
        print(f"  ⚠️ No se pudo precalentar: {e}")


# Lo pone collecthub/bot.py cuando el inventario vive en Railway: trae una
# pieza que encontro el monitor de relevo (boton "Comprar con el bot (PC)").
IMPORTAR_RELEVO = None


def _importar_relevo(pid):
    return IMPORTAR_RELEVO(pid) if IMPORTAR_RELEVO else None


def iniciar_servicios():
    """Hilos de fondo (solo cuando corre como programa, no al importar en pruebas):
    la cola de compras, el scheduler de trabajos programados y los botones
    de Telegram."""
    scheduler.start()
    threading.Thread(target=_bucle_cola, name="cola_compras", daemon=True).start()
    token, chat = telegram_token_y_chat()
    if token and chat:
        try:
            telegram_control.Control(token, chat, {
                "obtener": HALLAZGOS.obtener,
                "evaluar": LIMITES.evaluar,
                "comprar": solicitar_compra,
                "ignorar": lambda hid: HALLAZGOS.cambiar_estado(hid, "ignorado"),
                "importar_relevo": _importar_relevo,
                "precalentar": precalentar,
                "nota_pago": nota_pago,
                "drop": accion_drop,
                "mensaje": atender_mensaje,
            }).iniciar_hilo()
            print("  Botones de Telegram (Comprar/Ignorar): activos")
        except Exception as e:
            print(f"⚠️ No se pudo iniciar el control por Telegram: {e}")


def telegram_token_y_chat():
    from bot_logic import _telegram_del_monitor
    token = os.environ.get("HOTWHEELS_TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("HOTWHEELS_TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        token, chat = _telegram_del_monitor()
    return token, chat


if __name__ == "__main__":
    # Lo normal es correr "python app.py" del 02: monta este panel en /bot y
    # arranca el monitor. Esto queda solo para revisar el panel suelto.
    host, aviso = host_seguro(os.environ.get("PANEL_HOST"))
    if aviso:
        print("⚠️ " + aviso)
    iniciar_servicios()
    app.run(debug=False, host=host, port=8000, use_reloader=False)
