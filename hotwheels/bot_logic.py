import json
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv
import requests
from twilio.rest import Client
from playwright.async_api import async_playwright

from store_selectors import get_selector

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_DIR, ".env"))

with open(os.path.join(_DIR, "config.json"), "r") as f:
    config = json.load(f)

USER_EMAIL = os.environ.get("HOTWHEELS_USER_EMAIL", "")
CARD_NUMBER = os.environ.get("HOTWHEELS_CARD_NUMBER", "")
CARD_EXPIRY = os.environ.get("HOTWHEELS_CARD_EXPIRY", "")
CARD_CVV = os.environ.get("HOTWHEELS_CARD_CVV", "")
CARD_NAME = os.environ.get("HOTWHEELS_CARD_NAME", "")
SHIP_FIRST_NAME = os.environ.get("HOTWHEELS_SHIP_FIRST_NAME", "")
SHIP_LAST_NAME = os.environ.get("HOTWHEELS_SHIP_LAST_NAME", "")
SHIP_ADDRESS1 = os.environ.get("HOTWHEELS_SHIP_ADDRESS1", "")
SHIP_ADDRESS2 = os.environ.get("HOTWHEELS_SHIP_ADDRESS2", "")
SHIP_CITY = os.environ.get("HOTWHEELS_SHIP_CITY", "")
SHIP_POSTAL_CODE = os.environ.get("HOTWHEELS_SHIP_POSTAL_CODE", "")
SHIP_STATE = os.environ.get("HOTWHEELS_SHIP_STATE", "")
SHIP_PHONE = os.environ.get("HOTWHEELS_SHIP_PHONE", "")
RFC = os.environ.get("HOTWHEELS_RFC", "")
MAX_QUANTITY = int(os.environ.get("HOTWHEELS_MAX_QUANTITY", "1"))
NOTIFICATIONS = config["notifications"]

def send_email(message):
    if NOTIFICATIONS["email"]["enabled"]:
        smtp_server = NOTIFICATIONS["email"]["smtp_server"]
        smtp_port = NOTIFICATIONS["email"]["smtp_port"]
        sender = NOTIFICATIONS["email"]["sender"]
        password = os.environ.get("HOTWHEELS_SMTP_PASSWORD", "")
        recipient = NOTIFICATIONS["email"]["recipient"]

        msg = MIMEText(message)
        msg["Subject"] = "Bot Mattel - Notificación"
        msg["From"] = sender
        msg["To"] = recipient

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

def send_whatsapp(message):
    if NOTIFICATIONS["whatsapp"]["enabled"]:
        client = Client(os.environ.get("HOTWHEELS_TWILIO_SID", ""), os.environ.get("HOTWHEELS_TWILIO_TOKEN", ""))
        client.messages.create(
            body=message,
            from_=NOTIFICATIONS["whatsapp"]["from_number"],
            to=NOTIFICATIONS["whatsapp"]["to_number"]
        )

CAPTURAS_DIR = os.path.join(_DIR, "capturas_error")
os.makedirs(CAPTURAS_DIR, exist_ok=True)

async def guardar_captura_error(page, url, etiqueta):
    """
    Guarda screenshot + HTML con timestamp cuando comprar_producto() falla,
    para poder diagnosticar sin tener que reproducir el error a mano
    (como se tuvo que hacer manualmente el 2026-08-25).
    """
    if page is None:
        return
    try:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", url)[-40:]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{CAPTURAS_DIR}/{ts}_{etiqueta}_{slug}"
        await page.screenshot(path=f"{base}.png", full_page=True)
        with open(f"{base}.html", "w", encoding="utf-8") as f:
            f.write(await page.content())
    except Exception as e:
        print(f"⚠️ No se pudo guardar la captura de error ({etiqueta}): {e}")

def _telegram_del_monitor():
    """Token/chat de Telegram del monitor (config.env, junto a este archivo)."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env")
    datos = {}
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    datos[k.strip()] = v.strip()
    except OSError:
        pass
    return datos.get("TELEGRAM_BOT_TOKEN", ""), datos.get("TELEGRAM_CHAT_ID", "")

def send_telegram(message):
    if NOTIFICATIONS.get("telegram", {}).get("enabled"):
        token = os.environ.get("HOTWHEELS_TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("HOTWHEELS_TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            # Proyecto fusionado (2026-09-23): si no hay un bot propio, se usa el
            # mismo de las alertas del monitor (config.env) -- un solo chat.
            token, chat_id = _telegram_del_monitor()
        if not token or not chat_id:
            return
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message}, timeout=10,
        )
        resp.raise_for_status()

def notify(message):
    try:
        send_email(message)
    except Exception as e:
        print(f"⚠️ No se pudo enviar el email de notificación: {e}")
    try:
        send_whatsapp(message)
    except Exception as e:
        print(f"⚠️ No se pudo enviar el WhatsApp de notificación: {e}")
    try:
        send_telegram(message)
    except Exception as e:
        print(f"⚠️ No se pudo enviar el Telegram de notificación: {e}")

async def dismiss_shop_modal(page):
    """
    Mattel/Shopify a veces dispara en automático (sin que el bot haga nada)
    el modal "Sign in with Shop" con un reto de verificación cuando el
    correo ya tiene cuenta Shop asociada. El bot compra como invitado y
    nunca necesita ese login, así que si aparece, solo se cierra.
    """
    try:
        close_btn = await page.wait_for_selector(
            "button[data-testid='authorize-modal-close-button']", timeout=3000
        )
        await close_btn.click()
    except Exception:
        pass

async def dismiss_overlays(page, selector):
    """
    Cierra banners de cookies y pop-ups promocionales que puedan tapar
    el botón de compra. Cada intento es best-effort: si el overlay no
    aparece, se ignora sin detener la corrida.
    """
    for key in ("cookie_consent", "popup_close"):
        overlay_selector = selector.get(key)
        if not overlay_selector:
            continue
        try:
            button = await page.wait_for_selector(overlay_selector, timeout=5000)
            await button.click()
        except Exception:
            pass

    # Fallback genérico: algunos pop-ups de suscripción (p.ej. Klaviyo en Mattel)
    # aparecen de forma intermitente sin un selector fijo detectado. Escape cierra
    # la mayoría de esos modales; si no, se busca cualquier botón de cierre visible
    # por aria-label, sin depender de la plataforma específica del pop-up.
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        close_generico = page.locator("[aria-label*='close' i], [aria-label*='cerrar' i]")
        if await close_generico.count() > 0 and await close_generico.first.is_visible():
            await close_generico.first.click(timeout=2000)
    except Exception:
        pass

async def set_quantity(page, selector, desired_max):
    """
    Sube la cantidad haciendo clic en '+' hasta desired_max, o hasta que
    la propia página muestre que se llegó a su límite (de stock o por
    pedido), lo que ocurra primero. Nunca pide más de desired_max.
    """
    quantity_increase = selector.get("quantity_increase")
    quantity_input = selector.get("quantity_input")
    if not quantity_increase or not quantity_input or desired_max <= 1:
        return 1

    quantity_limit = selector.get("quantity_limit")
    for _ in range(desired_max - 1):
        try:
            btn = await page.wait_for_selector(quantity_increase, timeout=3000)
            await btn.click(timeout=3000)
            await page.wait_for_timeout(300)
        except Exception:
            break
        if quantity_limit:
            try:
                if await page.locator(quantity_limit).first.is_visible():
                    break
            except Exception:
                pass

    try:
        value = await page.input_value(quantity_input, timeout=2000)
        return int(value)
    except Exception:
        return 1

async def obtener_datos_producto(url):
    """
    Extrae imagen (miniatura) y precio del producto para el panel y el
    historial de precios (precios.py). Usa Playwright (headless) en vez de
    requests porque sitios como Mattel Creations bloquean peticiones sin
    navegador real (Cloudflare/Forter) — ver bloqueo del 2026-08-21.
    Prioriza el meta tag Open Graph para la imagen (estandar en
    Shopify/Amazon/Walmart); si no existe, cae al primer <img> grande de la
    galeria del producto. El precio sale del meta tag de precio de producto
    de Shopify/Open Graph. Ninguno de los dos es obligatorio: lo que no se
    encuentra queda en None sin tronar el registro del producto.
    """
    resultado = {"image_url": None, "precio_mxn": None}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)

                og_image = await page.get_attribute("meta[property='og:image']", "content")
                if og_image:
                    resultado["image_url"] = og_image
                else:
                    try:
                        primera_img = await page.locator("img").first.get_attribute("src", timeout=5000)
                        if primera_img and primera_img.startswith("http"):
                            resultado["image_url"] = primera_img
                    except Exception:
                        pass

                for meta_selector in ("meta[property='product:price:amount']",
                                       "meta[property='og:price:amount']"):
                    try:
                        precio_raw = await page.get_attribute(meta_selector, "content")
                    except Exception:
                        precio_raw = None
                    if precio_raw:
                        try:
                            resultado["precio_mxn"] = float(precio_raw.replace(",", ""))
                            break
                        except ValueError:
                            pass
            finally:
                await browser.close()
    except Exception:
        pass
    return resultado


async def test_humo(url):
    """
    Visita la pagina SIN comprar y confirma que el selector del boton de
    compra siga existiendo en el DOM — para detectar un selector roto de la
    tienda con horas de anticipacion, no a la hora del drop real. No revisa
    si esta agotado: un boton deshabilitado por "Sold Out" sigue siendo un
    selector sano, lo que se busca aqui es que la tienda no haya cambiado su
    HTML por debajo del bot.
    """
    selector = get_selector(url)
    if selector is None:
        return False, "tienda no soportada"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                boton = await page.query_selector(selector["buy_button"])
                if boton is None:
                    return False, "el selector del boton de compra no encontro nada en la pagina"
                return True, "ok"
            finally:
                await browser.close()
    except Exception as e:
        return False, f"error al visitar la pagina: {e}"

# Captchas / desafios anti-bot mas comunes (reCAPTCHA, hCaptcha, Cloudflare).
SELECTOR_CAPTCHA = (
    "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[title*='captcha' i], "
    "iframe[src*='challenges.cloudflare.com'], #challenge-form, [id*='cf-challenge'], "
    ".g-recaptcha, .h-captcha"
)


async def hay_captcha(page):
    """True si la pagina muestra un captcha VISIBLE. El distintivo invisible de
    reCAPTCHA v3 (.grecaptcha-badge) o un iframe oculto NO cuentan: en Shopify
    estan en casi todas las paginas y no piden nada al usuario."""
    try:
        for el in await page.query_selector_all(SELECTOR_CAPTCHA):
            try:
                if not await el.is_visible():
                    continue
                if await el.evaluate("e => !!e.closest('.grecaptcha-badge')"):
                    continue
                caja = await el.bounding_box()
                if caja and caja["height"] >= 60 and caja["width"] >= 150:
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


async def esperar_captcha(page, url, headless, avisar=True, espera_max=180, intervalo=2):
    """Si aparece un captcha: avisa por notify() y, con ventana visible, espera
    a que TU lo resuelvas (hasta espera_max segundos). Devuelve None si no hay
    captcha o ya se resolvio; un texto de fallo si sigue ahi.

    No intenta resolverlo solo (eso requeriria un servicio de pago tipo
    2Captcha; ver CLAUDE.md): el bot solo detecta y pide ayuda.
    """
    if not await hay_captcha(page):
        return None
    if headless:
        return f"🧩 Captcha detectado (sin ventana visible no se puede resolver): {url}"
    if avisar:
        try:
            notify(f"🧩 Captcha detectado comprando {url}. Resuélvelo en la ventana del navegador "
                   f"(tienes {espera_max // 60} min); el bot sigue solo cuando desaparezca.")
        except Exception:
            pass
    esperado = 0
    while esperado < espera_max:
        await page.wait_for_timeout(intervalo * 1000)
        esperado += intervalo
        if not await hay_captcha(page):
            return None
    return f"🧩 Captcha sin resolver a tiempo ({espera_max}s): {url}"


async def comprar_producto(url, proxy=None, cantidad=None, dry_run=None,
                           permitir_pausa=True, notificar=True, headless=False):
    """Compra (o intenta) UNA URL.

    cantidad/dry_run/permitir_pausa permiten compras puntuales (boton
    "Comprar" del panel) sin tocar las variables de entorno del proceso — el
    cron sigue usando los defaults de siempre cuando no se pasan.
    permitir_pausa=False garantiza que nunca se quede esperando a que alguien
    cierre la ventana a mano (para corridas sin nadie viendo).
    notificar=False (2026-09-16) existe para la ventana de reintentos del
    evento puntual (ver scheduled_run en dashboard_bot.py): reintentar cada
    15s durante varios minutos con notify() prendido spamearia un aviso por
    cada intento fallido intermedio; quien reintenta se hace cargo de avisar
    UNA vez al final con el desenlace real.
    headless=True (prueba diaria del checkout) corre sin ventana; las compras
    normales usan ventana visible para poder resolver captchas a mano.
    """
    selector = get_selector(url)
    if selector is None:
        return f"❌ Tienda no soportada: {url}"

    dry = dry_run if dry_run is not None else os.environ.get("HOTWHEELS_DRY_RUN") == "1"
    pausa = permitir_pausa and os.environ.get("HOTWHEELS_DRY_RUN_KEEP_OPEN") == "1"
    qty_objetivo = MAX_QUANTITY if cantidad is None else cantidad

    page = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context(proxy=proxy)
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await dismiss_overlays(page, selector)
                fallo_captcha = await esperar_captcha(page, url, headless, avisar=(notificar and not dry))
                if fallo_captcha:
                    await guardar_captura_error(page, url, "captcha")
                    return fallo_captcha

                try:
                    sold_out = await page.query_selector(selector["sold_out"])
                    if sold_out:
                        return f"❌ Producto agotado: {url}"

                    add_to_cart_button = await page.wait_for_selector(
                        selector["buy_button"], state="attached", timeout=10000
                    )
                    if await add_to_cart_button.is_disabled():
                        return f"❌ Producto agotado (botón deshabilitado): {url}"
                    try:
                        await add_to_cart_button.wait_for_element_state("visible", timeout=10000)
                    except Exception:
                        # Igual que con el click: un pop-up con retraso puede tapar
                        # el botón justo aquí. Se cierra y se reintenta una vez.
                        await dismiss_overlays(page, selector)
                        await add_to_cart_button.wait_for_element_state("visible", timeout=10000)

                    qty = await set_quantity(page, selector, qty_objetivo)

                    try:
                        await add_to_cart_button.click(timeout=5000)
                    except Exception:
                        # Un pop-up (p.ej. el de suscripción de Klaviyo en Mattel) puede
                        # aparecer con retraso y tapar el botón — reintenta tras cerrarlo.
                        await dismiss_overlays(page, selector)
                        await add_to_cart_button.click(timeout=10000)
                    resultado = f"✅ Producto agregado al carrito (cantidad: {qty}): {url}"
                    if not dry and notificar:
                        notify(resultado)

                    # El clic en "Add to Bag" dispara una llamada AJAX de Shopify;
                    # si se navega de inmediato al carrito esa llamada puede no
                    # haber terminado y el carrito llega vacío (detectado
                    # 2026-09-28). Se confirma esperando a que el contador del
                    # carrito en el header deje de marcar 0 antes de seguir.
                    contador_carrito = selector.get("cart_count")
                    if contador_carrito:
                        try:
                            await page.wait_for_function(
                                "(sel) => { const el = document.querySelector(sel); "
                                "const t = el && el.textContent.trim(); return t && t !== '0'; }",
                                arg=contador_carrito,
                                timeout=8000,
                            )
                        except Exception:
                            pass  # best-effort: si no se puede confirmar, se sigue igual
                except Exception as e:
                    await guardar_captura_error(page, url, "boton")
                    resultado = f"❌ No se encontró el botón en: {url} | Error: {e}"
                    if not dry and notificar:
                        notify(resultado)
                    return resultado

                # El flujo de checkout automático solo está implementado para Mattel Creations.
                if selector["store"] != "mattel":
                    return resultado

                try:
                    # Ir directo a /checkout redirige al home desde que Mattel
                    # cambió su flujo de carrito (detectado 2026-09-28): hay que
                    # pasar por /cart (respetando el idioma de la URL del
                    # producto) y usar el botón real "Checkout" del carrito, que
                    # sí arrastra el token de sesión al checkout de invitado.
                    prefijo_idioma = url.split("/products/")[0].split("creations.mattel.com")[-1]
                    await page.goto(f"https://creations.mattel.com{prefijo_idioma}/cart")
                    fallo_captcha = await esperar_captcha(page, url, headless, avisar=(notificar and not dry))
                    if fallo_captcha:
                        await guardar_captura_error(page, url, "captcha")
                        return f"⚠️ Producto en carrito pero el checkout pidio captcha: {fallo_captcha}"

                    await dismiss_overlays(page, selector)
                    boton_checkout = await page.wait_for_selector(
                        selector["cart_checkout"], state="visible", timeout=10000
                    )
                    await boton_checkout.click(timeout=10000)
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)

                    fallo_captcha = await esperar_captcha(page, url, headless, avisar=(notificar and not dry))
                    if fallo_captcha:
                        await guardar_captura_error(page, url, "captcha")
                        return f"⚠️ Producto en carrito pero el checkout pidio captcha: {fallo_captcha}"

                    await page.fill("#email", USER_EMAIL)
                    await dismiss_shop_modal(page)

                    try:
                        await page.select_option("select[name='countryCode']", label="Mexico", timeout=5000)
                    except Exception:
                        pass

                    not_autofill = ":not([id*='autofill'])"
                    await page.fill(f"input[name='firstName']{not_autofill}", SHIP_FIRST_NAME)
                    await page.fill(f"input[name='lastName']{not_autofill}", SHIP_LAST_NAME)
                    await page.fill(f"input[name='address1']{not_autofill}", SHIP_ADDRESS1)
                    if SHIP_ADDRESS2:
                        await page.fill(f"input[name='address2']{not_autofill}", SHIP_ADDRESS2)
                    await page.fill(f"input[name='city']{not_autofill}", SHIP_CITY)
                    await page.fill(f"input[name='postalCode']{not_autofill}", SHIP_POSTAL_CODE)
                    await page.fill(f"input[name='phone']{not_autofill}", SHIP_PHONE)

                    for candidate in (SHIP_STATE, "Ciudad de Mexico", "Ciudad de México"):
                        try:
                            await page.select_option("select[name='zone']", label=candidate, timeout=5000)
                            break
                        except Exception:
                            continue

                    if RFC:
                        try:
                            await page.fill("input[name*='rfc' i]", RFC, timeout=5000)
                        except Exception:
                            pass

                    await dismiss_shop_modal(page)
                    await page.check("#basic-creditCards")
                    await page.wait_for_timeout(2000)

                    def find_frame(marker):
                        return next(f for f in page.frames if marker in f.url)

                    await find_frame("number-ltr").fill("input[name='number']", CARD_NUMBER)
                    await find_frame("expiry-ltr").fill("input[name='expiry']", CARD_EXPIRY)
                    await find_frame("verification_value-ltr").fill("input[name='verification_value']", CARD_CVV)
                    await find_frame("name-ltr").fill("input[name='name']", CARD_NAME)

                    if dry:
                        resultado = f"🧪 DRY RUN: checkout llenado, sin pagar: {url}"
                        if pausa:
                            print(resultado)
                            print("🧪 Ventana abierta para inspección — ciérrala manualmente para continuar.")
                            await page.wait_for_event("close", timeout=0)
                        return resultado

                    await dismiss_shop_modal(page)
                    await page.click("#checkout-pay-button")
                    resultado = f"🎉 Pedido realizado para: {url}"
                    if notificar:
                        notify(resultado)
                except Exception as e:
                    resultado = f"⚠️ Producto en carrito pero falló el checkout automático: {url} | Error: {e}"
                    await guardar_captura_error(page, url, "checkout")
                    if not dry and notificar:
                        notify(resultado)
                    if pausa:
                        print(resultado)
                        print(f"🧪 URL actual al fallar: {page.url}")
                        print("🧪 Ventana abierta para inspección — ciérrala manualmente para continuar.")
                        await page.wait_for_event("close", timeout=0)

                return resultado
            finally:
                await browser.close()
    except Exception as e:
        await guardar_captura_error(page, url, "general")
        resultado = f"❌ Error inesperado con {url} | Error: {e}"
        if not dry and notificar:
            notify(resultado)
        return resultado
