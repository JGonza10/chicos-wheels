# -*- coding: utf-8 -*-
"""
Lo que pasa DESPUES de pagar en Mattel Creations (Shopify):

1. Confirmacion: al pagar, Shopify abre la pagina de "gracias" con el numero
   de pedido y el total cobrado. El bot la lee para que el inventario guarde
   lo que de verdad pagaste (no el estimado del monitor) y la liga de esa
   pagina, que es la del estado del pedido.
2. Envio: esa misma pagina, dias despues, muestra la guia de rastreo y cuando
   llega. seguimiento_envios() (dashboard_bot, cada 6 h) la vuelve a abrir y
   actualiza "Por llegar" en el inventario.

Los lectores de texto (leer_confirmacion, leer_envio) son puros: reciben el
texto visible de la pagina y no tocan red, para poder probarlos sin Mattel.
Son tolerantes a ingles y español porque /en-mx/ y /es-mx/ cambian el idioma.
"""

import re
from datetime import date, datetime, timedelta

MESES = {"jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dec": 12, "dic": 12}

_RE_PEDIDO = re.compile(
    r"(?:order|pedido|orden|confirmation|confirmaci[oó]n)\s*(?:number|n[uú]mero|no\.?|#)?\s*[:#]?\s*#?\s*"
    r"([A-Z]{0,5}-?\d{3,12})\b", re.I)
_RE_PEDIDO_SUELTO = re.compile(r"#\s?([A-Z]{0,5}\d{3,12})\b")
_RE_TOTAL = re.compile(
    r"(?<![A-Za-z])total\b[^\n$]{0,30}?(MXN|USD)?\s*\$\s*([\d,]+\.\d{2})\s*(MXN|USD)?", re.I)
_RE_GUIA = re.compile(
    r"(?:tracking(?:\s*number)?|n[uú]mero\s+de\s+(?:rastreo|gu[ií]a)|gu[ií]a|rastreo)\s*[:#]?\s*"
    r"([A-Z0-9]{8,30})\b", re.I)
PAQUETERIAS = ("DHL", "FedEx", "Estafeta", "UPS", "Redpack", "99 Minutos", "Paquetexpress",
               "Correos de México", "USPS", "J&T", "iMile")
_RE_FECHA_LLEGA = re.compile(
    r"(?:estimated\s+delivery|arriving|delivery\s+date|llega(?:r[aá])?|entrega\s+estimada|"
    r"fecha\s+(?:estimada\s+)?de\s+entrega)[^\n]{0,25}?"
    r"(?:(\d{1,2})\s+(?:de\s+)?([A-Za-zé]{3,10})\.?|([A-Za-z]{3,10})\.?\s+(\d{1,2}))", re.I)
_RE_ENTREGADO = re.compile(r"\b(delivered|entregado|entregada)\b", re.I)


def leer_confirmacion(texto):
    """{"pedido", "total", "moneda"} de la pagina de gracias. Lo que no se
    encuentre queda en None: nunca se inventa un numero."""
    texto = texto or ""
    m = _RE_PEDIDO.search(texto) or _RE_PEDIDO_SUELTO.search(texto)
    pedido = m.group(1).upper() if m else None
    total = moneda = None
    totales = list(_RE_TOTAL.finditer(texto))
    if totales:
        t = totales[-1]          # el ultimo "Total" es el que va despues de envio e impuestos
        total = float(t.group(2).replace(",", ""))
        moneda = (t.group(1) or t.group(3) or "").upper() or None
    if total is not None and not moneda:
        moneda = "MXN" if "MXN" in texto else ("USD" if "USD" in texto else None)
    return {"pedido": pedido, "total": total, "moneda": moneda}


def texto_confirmacion(conf, url_estado=None):
    """Pedazo estable que se agrega al resultado de la compra. El inventario lo
    vuelve a leer con datos_del_resultado(): no cambiar el formato a la ligera."""
    partes = []
    if conf.get("pedido"):
        partes.append(f"Pedido #{conf['pedido']}")
    if conf.get("total") is not None:
        partes.append(f"Cobrado {conf.get('moneda') or 'MXN'} ${conf['total']:,.2f}")
    if url_estado:
        partes.append(f"Estado: {url_estado}")
    return " | ".join(partes)


def datos_del_resultado(resultado):
    """Inverso de texto_confirmacion: {"pedido", "total", "moneda", "url_estado"}."""
    r = resultado or ""
    pedido = re.search(r"Pedido #([A-Z0-9-]+)", r)
    cobrado = re.search(r"Cobrado (MXN|USD) \$([\d,]+\.\d{2})", r)
    estado = re.search(r"Estado: (https://\S+)", r)
    return {"pedido": pedido.group(1) if pedido else None,
            "total": float(cobrado.group(2).replace(",", "")) if cobrado else None,
            "moneda": cobrado.group(1) if cobrado else None,
            "url_estado": estado.group(1) if estado else None}


def _fecha_mes(dia, mes, hoy):
    n = MESES.get((mes or "")[:3].lower())
    if not n:
        return None
    try:
        f = date(hoy.year, n, int(dia))
    except ValueError:
        return None
    if f < hoy - timedelta(days=60):       # "Jan 5" leido en diciembre = el año que entra
        f = date(hoy.year + 1, n, int(dia))
    return f


def leer_envio(texto, hoy=None):
    """{"guia", "paqueteria", "llega" (YYYY-MM-DD), "entregado"} de la pagina
    de estado del pedido. Lo que no aparezca queda en None/False."""
    texto = texto or ""
    hoy = hoy or date.today()
    m = _RE_GUIA.search(texto)
    guia = m.group(1).upper() if m and any(ch.isdigit() for ch in m.group(1)) else None
    paq = next((p for p in PAQUETERIAS if re.search(r"\b" + re.escape(p) + r"\b", texto, re.I)), None)
    llega = None
    f = _RE_FECHA_LLEGA.search(texto)
    if f:
        dia, mes = (f.group(1), f.group(2)) if f.group(1) else (f.group(4), f.group(3))
        fecha = _fecha_mes(dia, mes, hoy)
        llega = fecha.isoformat() if fecha else None
    return {"guia": guia, "paqueteria": paq, "llega": llega,
            "entregado": bool(_RE_ENTREGADO.search(texto))}


async def esperar_confirmacion(page, timeout_ms=45000):
    """Tras dar "Pagar": espera la pagina de gracias de Shopify y la lee.
    Devuelve (conf, url_estado). Si no llega a tiempo, conf viene vacia: el
    pedido pudo haberse hecho igual, por eso nunca se marca como fallo aqui."""
    try:
        await page.wait_for_url(re.compile(r"thank[_-]?you|/orders/|/order-status", re.I),
                                timeout=timeout_ms)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        texto = await page.inner_text("body")
        return leer_confirmacion(texto), page.url
    except Exception:
        return {"pedido": None, "total": None, "moneda": None}, None


def fecha_iso(valor):
    try:
        return datetime.fromisoformat(str(valor)[:10]).date()
    except (TypeError, ValueError):
        return None
