"""Asistente de la tienda (/tienda): responde si hay una pieza, la aparta y
anota a quien quiere que le avisen.

Funciona sin IA (búsqueda por palabras sobre el stock real). Con
`ASISTENTE_IA=1` y `ANTHROPIC_API_KEY`, Claude solo *interpreta* lo que escribió
el cliente (qué busca y en qué piezas del stock encaja); la respuesta, el precio
y la disponibilidad siempre salen de la base, así que la IA no puede inventar
una pieza ni un precio. Tope diario de consultas a la IA (`ASISTENTE_IA_TOPE`);
al pasarlo, o si Claude falla, sigue la búsqueda por palabras.

Apartar crea un encargo (Pedidos → "Apartado") sin anticipo, para el próximo
sábado en Balderas. "Avísame" crea un registro en la lista de espera de clientes.
"""
import json
import os
import re
import threading
import traceback
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, timedelta

from . import landing
from .db import todos, transaccion
from .util import ErrorApp, num, texto, uid

MODELO = os.environ.get("ASISTENTE_MODELO", "claude-haiku-4-5")
MAX_PIEZAS = 6
FALTAS_BLOQUEO = 2   # con 2 "no se presentó", apartar ya no es automático
LUGAR = "Balderas"

# Palabras que no ayudan a encontrar una pieza.
VACIAS = set("""
hola buenas buenos dias tardes noches que tal tienes tienen tendras tendran hay habra busco buscando
quiero quisiera queria me interesa interesan necesito ando alguna alguno algun algo un una uno unos unas tiene
el la los las lo le les de del al en con sin por para y o u a mi tu su sus favor porfa gracias
es son esta estan este estos esa ese eso disponible disponibles venta vendes venden precio cuanto
cuesta cuestan vale valen stock pieza piezas modelo modelos coleccion si no ya aun todavia mas
""".split())

_ia_lock = threading.Lock()
_ia_uso = {"dia": "", "n": 0}


def _plano(s) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _raiz(p: str) -> str:
    """Singular aproximado: 'barbies' → 'barbie', 'skylines' → 'skyline'."""
    if len(p) > 4 and p.endswith("es") and p[-3] not in "aeiou":
        return p[:-2]
    if len(p) > 3 and p.endswith("s"):
        return p[:-1]
    return p


def palabras(t: str) -> list:
    return [_raiz(p) for p in re.findall(r"[a-z0-9]+", _plano(t)) if len(p) >= 2 and p not in VACIAS]


def _texto_pieza(a: dict) -> str:
    return _plano(" ".join(str(a.get(k) or "") for k in
                           ("nombre", "serie", "color", "numero", "anio", "tipo", "expansion", "rareza")))


def _coincidencias(filas: list, consulta: list) -> list:
    """Piezas con más palabras de la consulta. Cada palabra cuenta si aparece
    como palabra (o prefijo de palabra) en los datos de la pieza."""
    if not consulta:
        return []
    puntuadas = []
    for a in filas:
        pal = set(_raiz(p) for p in re.findall(r"[a-z0-9]+", _texto_pieza(a)))
        n = sum(1 for q in consulta if q in pal or any(p.startswith(q) for p in pal if len(q) >= 3))
        if n:
            puntuadas.append((n, a))
    if not puntuadas:
        return []
    mejor = max(n for n, _ in puntuadas)
    # Con varias palabras, pide al menos la mitad: "barbie roja" no debe traer todo lo rojo.
    minimo = max(1, (len(consulta) + 1) // 2) if len(consulta) > 1 else 1
    return [a for n, a in puntuadas if n == mejor and n >= minimo]


def proximo_sabado(hoy_: date | None = None) -> str:
    d = hoy_ or date.today()
    return (d + timedelta(days=(5 - d.weekday()) % 7)).isoformat()


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(iso: str) -> str:
    """'2026-10-03' → 'sábado 3 de octubre' (las entregas siempre son en sábado)."""
    d = date.fromisoformat(iso)
    return f"sábado {d.day} de {MESES[d.month - 1]}"


# ---------------------------------------------------------------- IA opcional

def ia_activa() -> bool:
    return os.environ.get("ASISTENTE_IA") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _cupo_ia() -> bool:
    tope = int(os.environ.get("ASISTENTE_IA_TOPE", "300") or 0)
    with _ia_lock:
        hoy_ = date.today().isoformat()
        if _ia_uso["dia"] != hoy_:
            _ia_uso.update(dia=hoy_, n=0)
        if _ia_uso["n"] >= tope:
            return False
        _ia_uso["n"] += 1
        return True


ESQUEMA_IA = {
    "type": "object",
    "properties": {
        "intencion": {"type": "string", "enum": ["buscar", "saludo", "otra"]},
        "busqueda": {"type": "string", "description": "Lo que busca el cliente, en pocas palabras (vacío si no busca nada)."},
        "ids": {"type": "array", "items": {"type": "string"},
                "description": "ids de la lista de stock que encajan con lo que busca; vacío si ninguna encaja."},
    },
    "required": ["intencion", "busqueda", "ids"],
    "additionalProperties": False,
}

PROMPT_IA = """Eres el asistente de una tienda de coleccionables (Hot Wheels, cartas Pokémon, Barbie y más).
Un cliente escribió un mensaje. Tu único trabajo es entender qué busca y elegir de la
lista de STOCK las piezas que encajan (por nombre, serie, personaje, color, año).
No respondas al cliente ni inventes piezas: solo clasifica.

- intencion "buscar": pregunta por una pieza o tipo de pieza.
- intencion "saludo": solo saluda o pregunta qué hay.
- intencion "otra": cualquier otra cosa (entregas, pagos, horarios…).
- busqueda: lo que busca, corto y en español (para avisarle si llega).
- ids: solo ids que aparecen en STOCK y que de verdad encajan. Si nada encaja, lista vacía.

STOCK (id | categoría | nombre | serie | color | año):
{stock}

Mensaje del cliente:
<<<{mensaje}>>>"""


def _interpretar_con_ia(mensaje: str, filas: list) -> dict | None:
    if not ia_activa() or not _cupo_ia():
        return None
    try:
        import anthropic
        stock = "\n".join(f"{landing.id_publico(a['id'])} | {a['tipo']} | {a['nombre']} | {a.get('serie') or a.get('expansion') or ''}"
                          f" | {a.get('color') or ''} | {a.get('anio') or ''}" for a in filas[:400])
        cliente = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).with_options(timeout=20, max_retries=1)
        resp = cliente.messages.create(
            model=MODELO,
            max_tokens=400,
            messages=[{"role": "user", "content": PROMPT_IA.format(stock=stock or "(vacío)", mensaje=mensaje[:500])}],
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA_IA}},
        )
        if resp.stop_reason == "refusal":
            return None
        return json.loads(next(b.text for b in resp.content if b.type == "text"))
    except Exception:
        traceback.print_exc()
        return None  # sigue la búsqueda por palabras


# ------------------------------------------------------------------ respuestas

def _categorias(usuario_id: str) -> list:
    return ["Hot Wheels", "Pokémon"] + [c["nombre"] for c in
                                        todos("SELECT nombre FROM categorias WHERE usuario_id=? ORDER BY creado_en", (usuario_id,))]


def responder(usuario_id: str, mensaje: str) -> dict:
    """{"texto", "piezas": [...públicas], "avisame": bool, "busqueda", "motor"}"""
    mensaje = texto(mensaje, 500)
    if not mensaje:
        raise ErrorApp("Escribe qué pieza buscas")
    filas = todos(landing.SQL_STOCK, (usuario_id,))
    consulta = palabras(mensaje)
    motor = "palabras"
    # Para la lista de espera: solo lo que distingue la pieza ("busco un porsche 911" → "porsche 911").
    utiles = " ".join(w for w in re.findall(r"\w+", mensaje) if _plano(w) not in VACIAS)
    encontradas, busqueda, intencion = [], texto(utiles, 160) or mensaje, None

    ia = _interpretar_con_ia(mensaje, filas)
    if ia:
        motor = "ia"
        intencion = ia.get("intencion")
        busqueda = texto(ia.get("busqueda"), 160) or mensaje
        por_id = {landing.id_publico(a["id"]): a for a in filas}
        encontradas = [por_id[i] for i in ia.get("ids") or [] if i in por_id]
        if intencion == "buscar" and not encontradas:
            # La IA no halló nada: se confirma con la búsqueda por palabras (no se pierde una pieza real).
            encontradas = _coincidencias(filas, palabras(busqueda)) or _coincidencias(filas, consulta)
    else:
        encontradas = _coincidencias(filas, consulta)
        intencion = "buscar" if consulta else "saludo"

    if intencion in ("saludo", "otra") and not encontradas:
        cats = ", ".join(_categorias(usuario_id))
        extra = (f"Las entregas son los sábados en {LUGAR}; apartas aquí mismo. "
                 if intencion == "otra" else "")
        return {"texto": f"¡Hola! {extra}Dime qué pieza buscas ({cats}…) y te digo si la tenemos.",
                "piezas": [], "avisame": False, "busqueda": "", "motor": motor}

    if encontradas:
        encontradas = encontradas[:MAX_PIEZAS]
        n = len(encontradas)
        en_camino = sum(1 for a in encontradas if landing.por_llegar(a))
        if en_camino == n:   # todo lo que coincide viene en camino
            texto_r = ("¡Viene en camino! " if n == 1 else f"¡Vienen {n} piezas en camino que coinciden! ") + \
                      "Toca «Lo quiero» y te la aparto para el primer sábado después de que llegue, en " + LUGAR + "."
        else:
            texto_r = ("¡Sí la tenemos disponible! " if n == 1 else f"¡Sí tenemos {n} piezas que coinciden! ") + \
                      "Toca «Lo quiero» y te la aparto para el sábado en " + LUGAR + "." + \
                      (" Las marcadas «por llegar» se entregan el sábado después de que lleguen." if en_camino else "")
        return {"texto": texto_r, "piezas": [landing.publica(a) for a in encontradas],
                "avisame": False, "busqueda": busqueda, "motor": motor}

    # Nada a la venta: ¿la tuvimos? (solo para elegir las palabras, no se muestra nada de ella)
    todas = todos("SELECT * FROM v_articulos WHERE usuario_id=? AND estatus <> 'Conservar'", (usuario_id,))
    se_agoto = bool(_coincidencias(todas, palabras(busqueda)) or _coincidencias(todas, consulta))
    texto_r = ("Por el momento se agotó 😔" if se_agoto else "Por el momento no la tenemos en stock 😔") + \
              ", pero cada semana llegan piezas nuevas. Si me dejas tu nombre y tu Facebook o Instagram, " \
              "te avisamos en cuanto llegue."
    return {"texto": texto_r, "piezas": [], "avisame": True, "busqueda": busqueda, "motor": motor}


# ------------------------------------------------------------ apartar / avisar

def _contacto(b: dict) -> tuple:
    nombre = texto(b.get("nombre"), 60)
    contacto = texto(b.get("contacto"), 80)
    if len(nombre) < 2:
        raise ErrorApp("Escribe tu nombre")
    if len(contacto) < 3:
        raise ErrorApp("Escribe tu Facebook o Instagram para confirmarte")
    return nombre, contacto


def _comprador(con, usuario_id: str, nombre: str, contacto: str) -> str:
    """Reusa al cliente si ya existe con el mismo nombre y contacto."""
    fila = con.execute("SELECT id FROM compradores WHERE usuario_id=? AND lower(nombre)=lower(?) AND tel=?",
                       (usuario_id, nombre, contacto)).fetchone()
    if fila:
        return fila["id"]
    id_c = uid("C")
    con.execute("INSERT INTO compradores (id,usuario_id,nombre,tel,interes,notas) VALUES (?,?,?,?,?,?)",
                (id_c, usuario_id, nombre, contacto, "Ambas", "Cliente nuevo (desde el asistente de la tienda)"))
    return id_c


def apartar(usuario_id: str, b: dict) -> dict:
    nombre, contacto = _contacto(b)
    pid = str(b.get("pieza") or "")
    fila = next((a for a in todos(landing.SQL_STOCK, (usuario_id,)) if landing.id_publico(a["id"]) == pid), None)
    if not fila:
        raise ErrorApp("Esa pieza ya no está disponible", 409)
    # Lo que viene en camino se entrega el primer sábado después de que llegue.
    llega = landing.llegada(fila) if landing.por_llegar(fila) else ""
    entrega = proximo_sabado(date.fromisoformat(llega)) if llega else proximo_sabado()
    id_enc = uid("E")
    faltas = todos("SELECT MAX(faltas) f FROM compradores WHERE usuario_id=? AND lower(tel)=lower(?)",
                   (usuario_id, contacto))[0]["f"] or 0
    if faltas >= FALTAS_BLOQUEO:
        raise ErrorApp("Para apartar esta pieza escríbenos por Facebook o Instagram 🙂", 403)
    with transaccion() as con:
        # Se revisa otra vez dentro de la transacción: dos clientes pueden pedir la última al mismo tiempo.
        libre = con.execute("SELECT disponible FROM v_articulos WHERE id=?", (fila["id"],)).fetchone()
        if not libre or libre["disponible"] < 1:
            raise ErrorApp("Alguien acaba de apartar la última pieza 😔", 409)
        id_c = _comprador(con, usuario_id, nombre, contacto)
        con.execute("INSERT INTO encargos (id,usuario_id,comprador_id,fecha,fecha_entrega,anticipo,forma_anticipo,notas,"
                    "origen,confirmado) VALUES (?,?,?,?,?,0,'',?,'tienda',0)",
                    (id_enc, usuario_id, id_c, date.today().isoformat(), entrega,
                     f"Apartado desde la tienda (asistente), sin anticipo. Contacto: {contacto}"
                     + (f". Pieza por llegar (aprox. {llega})" if llega else "")))
        con.execute("INSERT INTO encargo_items (id,encargo_id,articulo_id,nombre_snap,cantidad,precio_unit,costo_unit) "
                    "VALUES (?,?,?,?,1,?,?)",
                    (uid("EI"), id_enc, fila["id"], fila["nombre"], num(fila["valor_estimado"]), num(fila["precio_compra"])))
    avisar_dueno(f"🛍 Apartado desde la tienda{' (por llegar)' if llega else ''}\n{fila['nombre']} — ${num(fila['valor_estimado']):,.0f}\n"
                 f"Cliente: {nombre} ({contacto})\nEntrega: {fecha_larga(entrega)} en {LUGAR}")
    return {"ok": True, "entrega": entrega, "pieza": fila["nombre"],
            "texto": f"¡Listo, {nombre}! Te aparté «{fila['nombre']}» para el {fecha_larga(entrega)} en {LUGAR}. "
                     + ("Todavía viene en camino; si se retrasa, te avisamos. " if llega else "")
                     + f"Te escribiremos a {contacto} para confirmar la hora."}


def avisame(usuario_id: str, b: dict) -> dict:
    nombre, contacto = _contacto(b)
    busqueda = texto(b.get("busqueda"), 160)
    if not busqueda:
        raise ErrorApp("Dime qué pieza buscas")
    with transaccion() as con:
        id_c = _comprador(con, usuario_id, nombre, contacto)
        con.execute("INSERT INTO pedidos_cliente (id,usuario_id,comprador_id,descripcion,tope) VALUES (?,?,?,?,0)",
                    (uid("R"), usuario_id, id_c, f"{busqueda} (desde la tienda)"[:200]))
    avisar_dueno(f"🔔 Lista de espera (tienda)\nBusca: {busqueda}\nCliente: {nombre} ({contacto})")
    return {"ok": True, "texto": f"¡Gracias, {nombre}! Te avisamos a {contacto} en cuanto llegue «{busqueda}»."}


def avisar_dueno(mensaje: str) -> None:
    """Aviso por Telegram si hay CW_TELEGRAM_TOKEN y CW_TELEGRAM_CHAT_ID; si no, nada.
    En un hilo aparte y sin lanzar nunca: el cliente no espera por esto."""
    token, chat = os.environ.get("CW_TELEGRAM_TOKEN", ""), os.environ.get("CW_TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    def _enviar():
        try:
            datos = urllib.parse.urlencode({"chat_id": chat, "text": mensaje}).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", datos, timeout=10).read()
        except Exception:
            traceback.print_exc()

    threading.Thread(target=_enviar, daemon=True).start()
