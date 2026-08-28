"""Identificación de piezas por foto (Claude, visión) y precio de mercado
para cartas Pokémon (API pública pokemontcg.io).

Ninguna función de este módulo toca la base de datos: reciben bytes y
devuelven un dict de sugerencia; quien las llama decide qué hacer con eso.
"""
import base64
import io
import json
import os
import traceback
import urllib.parse
import urllib.request

import anthropic
from PIL import Image

from .util import ErrorApp

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODELO = os.environ.get("IDENTIFICAR_MODELO", "claude-sonnet-5")
POKEMONTCG_API_KEY = os.environ.get("POKEMONTCG_API_KEY", "")

LADO_MAXIMO = 1280  # px, ya reescalada — de sobra para que la IA lea texto/serigrafía

ESQUEMA_IDENTIFICACION = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["Hot Wheels", "Pokémon", "desconocido"]},
        "confianza": {"type": "number", "description": "0 a 1: qué tan seguro estás de la identificación."},
        "nombre": {"type": "string"},
        "numero": {"type": "string"},
        "serie": {"type": "string", "description": "Solo Hot Wheels: serie o línea (ej. Treasure Hunt, Mainline)."},
        "color": {"type": "string", "description": "Solo Hot Wheels."},
        "expansion": {"type": "string", "description": "Solo Pokémon: nombre del set/expansión."},
        "rareza": {"type": "string", "description": "Solo Pokémon."},
        "grado": {"type": "string", "description": "Solo si se ve una funda/slab certificada (ej. PSA 9)."},
        "cert": {"type": "string", "description": "Número de certificado, solo si es visible en un slab."},
        "notas": {"type": "string", "description": "Una o dos frases en español de lo que ves en la foto."},
    },
    "required": ["tipo", "confianza", "nombre", "numero", "serie", "color",
                 "expansion", "rareza", "grado", "cert", "notas"],
    "additionalProperties": False,
}

PROMPT = """Eres un experto tasador de coleccionables Hot Wheels y cartas Pokémon.

Analiza la foto y decide primero si es un auto Hot Wheels (suelto o en su
blíster original) o una carta Pokémon (suelta o en funda/slab certificado).
Si no logras identificar ninguno de los dos con algo de certeza, usa
tipo:"desconocido".

Completa TODOS los campos del esquema. Los que no apliquen al tipo que
identificaste (por ejemplo "expansion" en un Hot Wheels) o que no puedas
leer en la foto, déjalos como cadena vacía "" — nunca inventes un dato que
no puedas sustentar con lo que ves.

Si la foto muestra el blíster/empaque original o una funda con texto
impreso, léelo literalmente (nombre, número, set) en vez de adivinar por
apariencia — es mucho más confiable. Si es una pieza suelta sin texto
legible, da tu mejor estimación visual pero baja "confianza" en
proporción a qué tan seguro estás.

"confianza" mide certeza de identificación, no calidad de la foto."""


def _cliente():
    if not ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY).with_options(timeout=30)


def procesar_imagen(datos: bytes) -> bytes:
    """Valida que sea una imagen real, descarta metadatos (EXIF/GPS) y la
    deja en un JPEG chico y predecible antes de mandarla a la IA o guardarla.
    Nunca confía en la extensión ni el Content-Type que mandó el navegador."""
    try:
        con_verificacion = Image.open(io.BytesIO(datos))
        con_verificacion.verify()  # invalida el objeto para más usos, por eso se reabre abajo
        img = Image.open(io.BytesIO(datos)).convert("RGB")
    except Exception:
        raise ErrorApp("Ese archivo no es una imagen válida")

    ancho, alto = img.size
    if max(ancho, alto) > LADO_MAXIMO:
        escala = LADO_MAXIMO / max(ancho, alto)
        img = img.resize((max(1, round(ancho * escala)), max(1, round(alto * escala))), Image.LANCZOS)

    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=85)  # sin exif=... a propósito: no se copian metadatos
    return salida.getvalue()


def identificar_foto(jpeg_bytes: bytes) -> dict:
    """Llama a Claude con la foto ya procesada y regresa el dict de
    sugerencia crudo (sin tocar la base de datos). 503 si no hay API key
    configurada; 502 si Claude no respondió."""
    cliente = _cliente()
    if cliente is None:
        raise ErrorApp("La identificación por foto no está configurada en este servidor "
                        "(falta ANTHROPIC_API_KEY). Llena el formulario a mano por ahora.", 503)

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    try:
        resp = cliente.messages.create(
            model=MODELO,
            max_tokens=700,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA_IDENTIFICACION}},
        )
        texto_resp = next(b.text for b in resp.content if b.type == "text")
        return json.loads(texto_resp)
    except Exception:
        traceback.print_exc()
        raise ErrorApp("No se pudo identificar la foto ahora mismo. Intenta de nuevo o "
                        "llena el formulario a mano.", 502)


def _sin_comillas(v: str) -> str:
    return (v or "").replace('"', "").strip()


def buscar_precio_pokemon(nombre: str, expansion: str = "", numero: str = "") -> dict | None:
    """Cruza la sugerencia de Claude contra pokemontcg.io para traer datos
    canónicos (set/rareza/número) y precio de mercado real. Solo devuelve
    algo cuando hay una coincidencia sin ambigüedad — con 0 o varios
    resultados, no adivina: regresa None y se queda lo que dijo Claude."""
    nombre = _sin_comillas(nombre)
    if not nombre:
        return None

    partes = [f'name:"{nombre}"']
    expansion = _sin_comillas(expansion)
    numero = _sin_comillas(numero)
    if expansion:
        partes.append(f'set.name:"{expansion}"')
    if numero:
        partes.append(f'number:"{numero}"')

    url = "https://api.pokemontcg.io/v2/cards?" + urllib.parse.urlencode(
        {"q": " ".join(partes), "pageSize": "5"})
    cabeceras = {"X-Api-Key": POKEMONTCG_API_KEY} if POKEMONTCG_API_KEY else {}
    try:
        peticion = urllib.request.Request(url, headers=cabeceras)
        with urllib.request.urlopen(peticion, timeout=8) as r:
            datos = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

    cartas = datos.get("data") or []
    if len(cartas) != 1:
        return None

    carta = cartas[0]
    precios = ((carta.get("tcgplayer") or {}).get("prices") or {})
    valor_estimado = None
    for variante in precios.values():
        if isinstance(variante, dict) and variante.get("market"):
            valor_estimado = round(float(variante["market"]), 2)
            break

    return {
        "expansion": (carta.get("set") or {}).get("name") or expansion,
        "numero": carta.get("number") or numero,
        "rareza": carta.get("rarity") or "",
        "valor_estimado": valor_estimado,
    }
