"""
Chatbot de Chicos Wheels.

Estrategia de dos capas (rápida y barata primero, IA solo si hace falta):
1. Se compara el mensaje contra un diccionario de preguntas frecuentes
   (envíos, cambios, horarios, métodos de pago). Si hay coincidencia,
   se responde al instante sin gastar la API de Anthropic.
2. Si no coincide con ninguna, se manda a Claude (API de Anthropic) junto
   con el catálogo destacado, para que pueda recomendar productos y
   resolver dudas más abiertas ("¿qué me recomiendas para regalo?").

Requiere la variable de entorno ANTHROPIC_API_KEY.
"""
import os
import re
import anthropic
from flask import Blueprint, request, jsonify

from models import Producto

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/api/chatbot")

_client = None


def _anthropic_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# Capa 1 — Preguntas frecuentes con respuesta fija
# Cada entrada: (patrones que activan la respuesta, respuesta)
# ---------------------------------------------------------------------------
FAQ = [
    (r"env[íi]o|cu[áa]nto tarda|entrega",
     "Los envíos dentro de México tardan de 3 a 5 días hábiles. "
     "Son gratis en compras desde $599 MXN."),
    (r"cambio|devoluci[óo]n|garant[íi]a",
     "Tienes 15 días naturales para cambios o devoluciones, siempre que el "
     "producto esté sellado y sin usar. Escríbenos con tu número de pedido."),
    (r"horario|atenci[óo]n|abierto",
     "Nuestra tienda en línea está abierta 24/7. El equipo de soporte "
     "responde de lunes a sábado, de 10:00 a 20:00 (hora CDMX)."),
    (r"pago|tarjeta|oxxo|spei|mercado pago",
     "Aceptamos tarjeta de crédito/débito, transferencia SPEI y pago en "
     "efectivo en OXXO a través de Mercado Pago."),
    (r"edici[óo]n limitada|se agot[óo]|reservar",
     "Las piezas de edición limitada se marcan en el catálogo con una "
     "etiqueta especial. Cuando el stock llega a 0 ya no se pueden reservar."),
]


def _buscar_respuesta_fija(mensaje: str):
    mensaje_normalizado = mensaje.lower()
    for patron, respuesta in FAQ:
        if re.search(patron, mensaje_normalizado):
            return respuesta
    return None


# ---------------------------------------------------------------------------
# Capa 2 — IA de respaldo (Claude) para preguntas abiertas
# ---------------------------------------------------------------------------
def _contexto_catalogo() -> str:
    destacados = Producto.query.filter_by(activo=True, destacado=True).limit(8).all()
    lineas = [
        f"- {p.nombre} ({p.categoria.nombre if p.categoria else ''}): ${p.precio} MXN, stock {p.stock}"
        for p in destacados
    ]
    return "\n".join(lineas) if lineas else "Sin productos destacados por ahora."


def _responder_con_ia(mensaje: str) -> str:
    prompt_sistema = (
        "Eres el asistente de Chicos Wheels, una tienda mexicana de carros de "
        "colección Hot Wheels y tarjetas Pokémon TCG. Responde en español, de "
        "forma breve y amigable. Recomienda productos del catálogo destacado "
        "cuando aplique. No inventes precios ni stock que no te den.\n\n"
        f"Catálogo destacado actual:\n{_contexto_catalogo()}"
    )

    respuesta = _anthropic_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=prompt_sistema,
        messages=[{"role": "user", "content": mensaje}],
    )
    return "".join(bloque.text for bloque in respuesta.content if bloque.type == "text")


@chatbot_bp.route("/mensaje", methods=["POST"])
def mensaje():
    data = request.get_json() or {}
    texto = (data.get("mensaje") or "").strip()
    if not texto:
        return jsonify({"error": "Falta el mensaje"}), 400

    respuesta_fija = _buscar_respuesta_fija(texto)
    if respuesta_fija:
        return jsonify({"respuesta": respuesta_fija, "fuente": "faq"})

    try:
        respuesta_ia = _responder_con_ia(texto)
        return jsonify({"respuesta": respuesta_ia, "fuente": "ia"})
    except Exception:
        return jsonify({
            "respuesta": "No pude procesar tu pregunta en este momento. "
                         "¿Puedes reformularla o escribirnos por WhatsApp?",
            "fuente": "error",
        }), 200
