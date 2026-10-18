# dashboard_bot.py
import asyncio
import os
import sqlite3
import sys
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from bot_logic import comprar_producto, notify, obtener_datos_producto, test_humo
import hallazgos as HALLAZGOS
import monitor_admin
import collecthub_bridge as COLLECTHUB
import coleccion as COLECCION
import limites as LIMITES
import precios as PRECIOS
import salud as SALUD
import telegram_control

app = Flask(__name__)
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
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

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
    resultado = await comprar_producto(url, cantidad=cantidad, dry_run=dry_run,
                                       permitir_pausa=permitir_pausa)
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
        notify(f"📋 Resumen semanal del bot: {len(mensajes)} corridas — "
               f"{exitos} pedidos completados, {carritos} agregados al carrito, "
               f"{fallos} fallidos.")
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
EVENTO_VENTANA_SEGUNDOS = 180
EVENTO_INTERVALO_SEGUNDOS = 15


async def _intentar_evento():
    urls = get_active_product_urls()
    if not urls:
        return False
    proxies = get_proxies()
    limite = datetime.now() + timedelta(seconds=EVENTO_VENTANA_SEGUNDOS)
    intentos = 0
    ultimo_por_url = {}
    while True:
        intentos += 1
        for i, url in enumerate(urls):
            proxy = proxies[i % len(proxies)] if proxies else None
            try:
                resultado = await comprar_producto(url, proxy, notificar=False)
            except Exception as e:
                resultado = f"❌ Error inesperado: {e}"
            ultimo_por_url[url] = resultado
            add_result(resultado)
            if "🎉" in resultado:
                marcar_producto_completado(url)
        if any(("✅" in r or "🎉" in r) for r in ultimo_por_url.values()):
            break
        if datetime.now() >= limite:
            break
        await asyncio.sleep(EVENTO_INTERVALO_SEGUNDOS)

    exitos = [r for r in ultimo_por_url.values() if "✅" in r or "🎉" in r]
    if exitos:
        notify(f"🎯 Evento puntual: {exitos[0]} (intento {intentos})")
    else:
        ultimo = next(iter(ultimo_por_url.values()), "sin resultado")
        notify(f"⏱️ Evento puntual: {intentos} intentos en "
               f"{EVENTO_VENTANA_SEGUNDOS}s, sin éxito. Último resultado: {ultimo}")
    return bool(exitos)

# --- Scheduler ---
scheduler = BackgroundScheduler()

def scheduled_run():
    ahora = datetime.now()

    # Evento puntual: una sola ejecucion exacta a fecha+hora+minuto configurados,
    # para drops que anuncian una hora especifica (ej. 10:03), no solo "en punto".
    evento = get_event()
    if evento and not evento["hecho"]:
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
def host_seguro(host, usuario, password):
    """El panel ahora puede COMPRAR: solo se deja escuchar fuera de esta PC
    (PANEL_HOST distinto de 127.0.0.1) si hay usuario y contraseña puestos.
    Devuelve (host, aviso)."""
    host = (host or "127.0.0.1").strip()
    if host in ("127.0.0.1", "localhost", "::1"):
        return "127.0.0.1", None
    if not usuario or not password:
        return "127.0.0.1", ("PANEL_HOST=%s ignorado: para abrir el panel a tu red hay que poner "
                             "DASHBOARD_USER y DASHBOARD_PASSWORD en .env. Sigue solo en esta PC." % host)
    return host, None


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
    host, aviso = host_seguro(os.environ.get("PANEL_HOST"), DASHBOARD_USER, DASHBOARD_PASSWORD)
    if aviso:
        print("⚠️ " + aviso)
    iniciar_servicios()
    app.run(debug=False, host=host, port=8000, use_reloader=False)
