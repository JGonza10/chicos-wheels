"""Datos de una pieza a partir de su link de Mattel Creations.

Mattel Creations es una tienda Shopify: cada producto publica su ficha en
`/products/<handle>.js`. Solo se consultan hosts de mattel.com por https (nunca
una URL arbitraria que mande el cliente) y con tope de tamaño y tiempo.
"""
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .util import ErrorApp

HOST_VALIDO = re.compile(r"^([a-z0-9-]+\.)*mattel\.com$")
HANDLE_VALIDO = re.compile(r"^/products/([a-z0-9][a-z0-9_-]{0,200})/?$")
MAX_BYTES = 2 * 1024 * 1024
_UA = {"User-Agent": "Mozilla/5.0 (ChicosWheels)", "Accept": "application/json"}


def _leer(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (host validado antes)
        return r.read(MAX_BYTES)


def tipo_de_cambio() -> float:
    """USD -> MXN en vivo; si falla la red, 20.0 (el mismo valor por defecto del monitor)."""
    try:
        tasa = json.loads(_leer("https://open.er-api.com/v6/latest/USD", 6))["rates"]["MXN"]
        return round(float(tasa), 2) if 10 < float(tasa) < 40 else 20.0
    except Exception:
        return 20.0


def traer_producto(url: str) -> dict:
    p = urlparse((url or "").strip())
    if p.scheme != "https" or not HOST_VALIDO.match((p.hostname or "").lower()):
        raise ErrorApp("Pega un link de Mattel Creations (creations.mattel.com/products/...)")
    m = HANDLE_VALIDO.match(p.path)
    if not m:
        raise ErrorApp("Ese link no es de una pieza (debe verse como .../products/nombre-de-la-pieza)")
    handle = m.group(1)
    try:
        d = json.loads(_leer(f"https://{p.hostname}/products/{handle}.js"))
    except urllib.error.HTTPError as e:
        raise ErrorApp("Mattel no encontró esa pieza" if e.code == 404 else "Mattel no respondió, intenta de nuevo", 502)
    except Exception:
        raise ErrorApp("No se pudo consultar Mattel en este momento", 502)

    usd = round((d.get("price") or 0) / 100, 2)
    tc = tipo_de_cambio()
    imagen = d.get("featured_image") or (d.get("images") or [""])[0] or ""
    if imagen.startswith("//"):
        imagen = "https:" + imagen
    texto = re.sub(r"<[^>]+>", " ", d.get("description") or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    return {
        "nombre": (d.get("title") or "")[:160],
        "precio_usd": usd, "tipo_cambio": tc, "precio_mxn": round(usd * tc, 2),
        "imagen": imagen[:500], "disponible": bool(d.get("available")),
        "linea": (d.get("vendor") or "")[:80], "descripcion": texto[:300],
        "url": f"https://{p.hostname}/products/{handle}",
    }
