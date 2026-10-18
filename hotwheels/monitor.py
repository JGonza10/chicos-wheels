"""
Monitor de Hot Wheels Collectors - Mattel Creations v5
Multi-coleccion, ciclo rapido + francotirador, carrito precargado,
lista de deseados, historial, ganancia neta y vigilante.
"""

import html
import json
import os
import random
import re
import sys
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import requests

# ------------------------------------------------------------
# Forzar salida UTF-8 sin importar el locale del sistema/servicio.
# Evita que un print() de un titulo con comilla curva (') o acento
# (e) reviente con: "'latin-1' codec can't encode character ...".
# Ese crash detenia el ciclo ANTES de guardar el estado.
# ------------------------------------------------------------
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================
# HABILIDADES EXTRA (opcionales)
# ============================================================
# hw_extras.py trae: lista de deseados, historial en base de datos,
# ganancia neta y latido. Si ese archivo no esta o truena, EX queda en
# None y el monitor sigue funcionando exactamente igual que antes.
try:
    import hw_extras as EX
except Exception as _e:
    EX = None
    print(f"  [aviso] hw_extras.py no disponible ({_e}). Extras desactivados.")

# hallazgos.py (proyecto fusionado): cada pieza comprable que el monitor
# encuentra queda registrada en la base del bot, donde el usuario decide.
try:
    import hallazgos as HALLAZGOS
except Exception as _e:
    HALLAZGOS = None
    print(f"  [aviso] hallazgos.py no disponible ({_e}). Las piezas solo se avisaran por Telegram.")

_DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
# Donde viven los datos (estado, historial, listas, config.env). En la PC es la
# carpeta del script, como siempre. En Railway HOTWHEELS_DATOS apunta al
# volumen (/app/datos/hotwheels) para que sobrevivan a cada redespliegue.
_DIR_DATOS = os.environ.get("HOTWHEELS_DATOS") or _DIR_SCRIPT
os.makedirs(_DIR_DATOS, exist_ok=True)

# Claves que tambien pueden llegar como variables de entorno (Railway no tiene
# config.env). Si el archivo trae la clave, gana el archivo: en la PC nada cambia.
_CLAVES_ENTORNO = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_CANAL_ID",
                   "MERCADOLIBRE_ACCESS_TOKEN", "URL_PANEL")


def _cargar_config():
    datos = EX.cargar_config(os.path.join(_DIR_DATOS, "config.env")) if EX else {}
    claves = _CLAVES_ENTORNO + tuple(getattr(EX, "AJUSTES_PERMITIDOS", {}) or ())
    for clave in claves:
        if not datos.get(clave) and os.environ.get(clave):
            datos[clave] = os.environ[clave]
    return datos


# config.env vive junto a monitor.py y NO se comparte con nadie: ahi va el
# token del bot. Si el archivo no existe, se usan los valores de abajo.
CONFIG = _cargar_config()


# ============================================================
# CONFIGURACION
# ============================================================

TELEGRAM_BOT_TOKEN = CONFIG.get("TELEGRAM_BOT_TOKEN") or "PEGA_AQUI_TU_TOKEN"
TELEGRAM_CHAT_ID = CONFIG.get("TELEGRAM_CHAT_ID") or "PEGA_AQUI_TU_CHAT_ID"
TELEGRAM_CANAL_ID = CONFIG.get("TELEGRAM_CANAL_ID") or ""

INTERVALO_MINUTOS = 2
PALABRAS_CLAVE = []

# Colecciones a vigilar (se deduplican automaticamente).
# Desde 2026-09-15 la lista real vive en colecciones.json y se administra
# desde el tablero; esta de aqui es solo la semilla de la primera vez y el
# respaldo si hw_extras no esta disponible. COLECCIONES/COLECCIONES_RAPIDAS
# se recargan solas en el refresco periodico (ver main()).
COLECCIONES = [
    "hot-wheels-collectors",
    "hot-wheels-premium",
    "hot-wheels-red-line-club",
    "hot-wheels-elite-64",
    "new-arrivals",
]

# ============================================================
# CONSTANTES
# ============================================================

BASE_URL = "https://creations.mattel.com"
# Panel unico, dentro de Chicos Wheels desde 2026-10-17: ahi se decide que comprar.
URL_PANEL = CONFIG.get("URL_PANEL", "http://127.0.0.1:3000/bot/")
# Ruta ABSOLUTA anclada a la carpeta del script. Asi el monitor y el
# dashboard siempre usan el MISMO estado.json sin importar desde donde
# se ejecute (terminal, cron, systemd con otro WorkingDirectory, etc.).
ARCHIVO_ESTADO = os.path.join(_DIR_DATOS, "estado.json")
ARCHIVO_HISTORIAL = os.path.join(_DIR_DATOS, "historial.db")
ARCHIVO_DESEADOS = os.path.join(_DIR_DATOS, "deseados.json")
ARCHIVO_DESEADOS_LEGACY = os.path.join(_DIR_DATOS, "deseados.txt")
# Misma idea que deseados.json pero al reves: modelos que NUNCA quieres que
# te avisen, sin importar el impacto (ej. una linea que no coleccionas).
# Usa exactamente las mismas funciones de hw_extras.py -- es el mismo tipo
# de archivo, solo que este apaga en vez de marcar.
ARCHIVO_BLOQUEADOS = os.path.join(_DIR_DATOS, "no_deseados.json")
ARCHIVO_LATIDO = os.path.join(_DIR_DATOS, "latido.txt")
# Que se vigila, administrable desde el tablero (ver hw_extras seccion 10).
ARCHIVO_COLECCIONES = os.path.join(_DIR_DATOS, "colecciones.json")
ARCHIVO_VIGILAR = os.path.join(_DIR_DATOS, "vigilar.json")
ARCHIVO_BUSQUEDAS_ML = os.path.join(_DIR_DATOS, "busquedas_ml.json")
ARCHIVO_CONFIG = os.path.join(_DIR_DATOS, "config.env")
TIPO_CAMBIO = 20.0
CACHE_EBAY = {}
REVISIONES_CALENTAMIENTO = 3
MAX_ALERTAS_GUARDADAS = 50
AJUSTE_IMPUESTOS_MXN = 25
HORA_RESUMEN_DIARIO = 22  # 10pm hora Mexico

# ------------------------------------------------------------
# CICLO RAPIDO
# El barrido completo de las 5 colecciones sigue igual cada 2 minutos.
# Encima corre un ciclo corto cada pocos segundos que solo mira
# new-arrivals y los productos bajo vigilancia (francotirador).
# ------------------------------------------------------------
SEGUNDOS_CICLO_RAPIDO = int(EX.config_num(CONFIG, "SEGUNDOS_CICLO_RAPIDO", 15)) if EX else 15
COLECCIONES_RAPIDAS = ["new-arrivals"]
MAX_FRANCOTIRADOR = int(EX.config_num(CONFIG, "MAX_FRANCOTIRADOR", 6)) if EX else 6
# Modo drop: en la ventana del dia y hora aprendidos (o martes 11am) el ciclo
# rapido acelera. El barrido completo sigue igual: las RLC y Elite salen en su
# propia coleccion, no en new-arrivals, y no se deben ver tarde.
SEGUNDOS_CICLO_DROP = int(EX.config_num(CONFIG, "SEGUNDOS_CICLO_DROP", 5)) if EX else 5
MINUTOS_ANTES_DROP = int(EX.config_num(CONFIG, "MINUTOS_ANTES_DROP", 10)) if EX else 10
MINUTOS_DESPUES_DROP = int(EX.config_num(CONFIG, "MINUTOS_DESPUES_DROP", 45)) if EX else 45
SEGUNDOS_PAUSA_429 = 60          # si Mattel dice "mas despacio", se le hace caso
_PAUSA_HASTA = 0.0               # time.monotonic() hasta donde no se consulta Mattel
HORAS_VIGILANCIA = 72            # cuanto tiempo se sigue vigilando un producto
SEGUNDOS_REFRESCO_DATOS = 7200   # tipo de cambio + cache de eBay cada 2 h
SEGUNDOS_REFRESCO_LISTAS = 60    # deseados/bloqueados/colecciones/vigilar: solo disco

# --- Segunda tienda: Mercado Libre (ver hw_extras seccion 12) ---
# Necesita MERCADOLIBRE_ACCESS_TOKEN en config.env: desde 2026 su API no
# responde sin autenticacion. Sin token, este ciclo ni se intenta.
ML_TOKEN = (CONFIG.get("MERCADOLIBRE_ACCESS_TOKEN") or "").strip() if CONFIG else ""
MINUTOS_MERCADOLIBRE = int(EX.config_num(CONFIG, "MINUTOS_MERCADOLIBRE", 10)) if EX else 10
MAX_IDS_ML_RECORDADOS = 400      # por termino, para que estado.json no crezca sin fin
FALLOS_ALERTA_COLECCION = int(EX.config_num(CONFIG, "FALLOS_ALERTA_COLECCION", 3)) if EX else 3
_TS_ALERTA_COLECCION = {}        # handle -> ultima vez que se aviso (una por hora)

# ------------------------------------------------------------
# GANANCIA NETA (todo editable desde config.env)
# ------------------------------------------------------------
ENVIO_MXN_ESTIMADO = EX.config_num(CONFIG, "ENVIO_MXN_ESTIMADO", 250.0) if EX else 250.0
COMISION_REVENTA_PCT = EX.config_num(CONFIG, "COMISION_REVENTA_PCT", 13.0) if EX else 13.0

# ------------------------------------------------------------
# VIGILANTE: si pasan estos minutos sin un barrido bueno, te avisa que
# el monitor esta ciego (corriendo, pero sin ver nada).
# ------------------------------------------------------------
MINUTOS_ALERTA_CIEGO = int(EX.config_num(CONFIG, "MINUTOS_ALERTA_CIEGO", 15)) if EX else 15

# ------------------------------------------------------------
# RELEVO PC <-> RAILWAY
# En Railway el monitor corre siempre, pero callado mientras la PC le mande
# su latido (cada barrido bueno). Si la PC deja de mandarlo MINUTOS_RELEVO
# minutos, Railway toma el relevo y avisa el; cuando la PC vuelve, se calla.
# Asi no hay avisos dobles y el bot de compra (que solo vive en la PC) sigue
# siendo el unico con botones Comprar/Ignorar.
# ------------------------------------------------------------
MODO_RELEVO = False      # True solo en Railway (activar_relevo, desde collecthub/bot.py)
MINUTOS_RELEVO = 5
_PC_LATIDO = None        # time.monotonic() del ultimo latido con el monitor de la PC sano
_PC_APP = None           # time.monotonic() del ultimo latido (aunque su monitor este ciego)
ESTADO_RELEVO = {}       # En la PC: como respondio Railway al ultimo latido (para el panel)
_RELEVO_ACTIVO = False   # True mientras Railway avisa porque la PC callo
AL_BARRIDO_OK = None     # En la PC: funcion(monitor_ok) que manda el latido a Railway
AL_URGENTE = None        # En la PC: funcion(url) que precalienta el navegador de compra

# Objetos que se llenan al arrancar (ver main)
HISTORIAL = None       # conexion a la base del historial
DESEADOS = []          # tu lista de autos deseados
BLOQUEADOS = []        # lo que nunca quieres que te avise
PATRON_DROPS = None    # dia y hora de drop aprendidos del historial
_TS_ULTIMO_BARRIDO_OK = 0.0
_REVISIONES_HECHAS = 0
_ULTIMO_BARRIDO_FUE_OK = False  # el ultimo barrido completo si vio la tienda
_TS_ULTIMA_ALERTA_CIEGO = None   # None = nunca se ha avisado (ver registrar_salud_coleccion)

# Varios navegadores reales en vez de uno fijo: reduce la huella repetitiva
# de las peticiones (antecedente de bloqueo de Cloudflare/Forter documentado
# en el bot de compra). Se elige uno al azar por proceso, no por peticion --
# cambiar de identidad a media sesion es mas sospechoso que ser consistente.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

HEADERS = {
    "User-Agent": random.choice(_USER_AGENTS),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Una sola sesion por proceso: reutiliza la conexion TCP/TLS (keep-alive) en
# vez de abrir una nueva en cada consulta, que cuesta 100-300 ms por saludo.
# En el ciclo rapido son 7+ consultas cada 15 s; en un drop eso es la ventaja.
SESION = requests.Session()
SESION.headers.update(HEADERS)
SESION_TG = requests.Session()   # Telegram aparte: otro servidor, sin la huella del navegador

TAGS_POCAS_UNIDADES = [
    "only a few left", "low stock", "almost gone", "limited quantity",
    "few left", "selling fast", "act fast", "last chance",
]

TAGS_REBAJA = [
    "sale", "clearance", "% off", "percent off", "discounted", "markdown",
]

# Dedup temporal (15 min)
NOTIFICACIONES_ENVIADAS = {}
HORAS_BLOQUEO_DUPLICADOS = 0.25


def rearmar_aviso(*keys):
    """Borra el candado de duplicados de estos avisos. Se usa cuando la pieza
    cambio de verdad (se agoto o volvio): en un drop los carritos que vencen
    regresan stock a los pocos minutos y ese segundo restock SI importa."""
    for k in keys:
        NOTIFICACIONES_ENVIADAS.pop(k, None)


def activar_relevo():
    """Modo Railway: sin panel ni compras aqui, asi que las piezas no se
    registran (HALLAZGOS). Los botones de compra solo salen si la app de la PC
    esta viva para atenderlos (ver guardar_pieza_relevo).
    Arranca suponiendo que la PC vigila: le da MINUTOS_RELEVO para mandar su
    primer latido antes de hablar (si no, cada redespliegue duplicaria avisos)."""
    global MODO_RELEVO, _PC_LATIDO, _PC_APP, HALLAZGOS
    MODO_RELEVO = True
    HALLAZGOS = None
    _PC_LATIDO = _PC_APP = time.monotonic()


def registrar_latido_pc(monitor_ok=True, listas=None):
    """Latido de la PC, tras cada barrido completo.

    monitor_ok=False: la app de la PC vive pero su monitor no ve la tienda.
    Railway toma el relevo, y como la PC SI puede comprar, sus avisos llevan
    el boton "Comprar con el bot (PC)". `listas` trae deseados, bloqueados,
    colecciones y vigilados de la PC cuando cambiaron (ver aplicar_listas_pc).
    Devuelve como esta Railway, para el panel de la PC."""
    global _PC_LATIDO, _PC_APP
    _PC_APP = time.monotonic()
    if monitor_ok:
        _PC_LATIDO = _PC_APP
    respuesta = {"relevo": _RELEVO_ACTIVO,
                 "minutos_sin_ver": round((time.monotonic() - _TS_ULTIMO_BARRIDO_OK) / 60.0, 1),
                 "revisiones": _REVISIONES_HECHAS,
                 "listas_hash": _LISTAS_HASH}
    if listas is not None:
        respuesta["listas_hash"] = aplicar_listas_pc(listas)
    return respuesta


def pc_vigilando():
    """True si este monitor es el de Railway y la PC esta vigilando: callarse."""
    if not MODO_RELEVO or _PC_LATIDO is None:
        return False
    return (time.monotonic() - _PC_LATIDO) < MINUTOS_RELEVO * 60


def pc_app_viva():
    """True si la app de la PC sigue mandando latido (aunque su monitor este
    ciego): hay quien atienda el boton de compra."""
    return bool(MODO_RELEVO and _PC_APP is not None
                and (time.monotonic() - _PC_APP) < MINUTOS_RELEVO * 60)


# --- Listas de la PC -> Railway ---
# Mismas listas que se editan en el panel de la PC. Viajan con el latido solo
# cuando cambian (la PC compara el hash que Railway le devuelve).
ARCHIVOS_LISTAS = {"deseados": "ARCHIVO_DESEADOS", "bloqueados": "ARCHIVO_BLOQUEADOS",
                   "colecciones": "ARCHIVO_COLECCIONES", "vigilar": "ARCHIVO_VIGILAR"}
MAX_ENTRADAS_LISTA = 2000
MAX_BYTES_LISTA = 256 * 1024
_LISTAS_HASH = None


def _hash_listas(listas):
    import hashlib
    texto = json.dumps(listas, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def listas_para_relevo():
    """PC: el contenido de las listas, tal como estan en disco. La que no
    existe no viaja: mandarla vacia borraria la de Railway sin razon."""
    listas = {}
    for nombre, var in ARCHIVOS_LISTAS.items():
        if not os.path.exists(globals()[var]):
            continue
        try:
            with open(globals()[var], encoding="utf-8") as f:
                datos = json.load(f)
            listas[nombre] = datos if isinstance(datos, list) else []
        except Exception:
            listas[nombre] = []
    return listas, _hash_listas(listas)


def _lista_valida(datos):
    """Lista de objetos planos (texto, numero, booleano o nulo), con tope de
    tamaño. Lo que no cumpla se rechaza entero: nunca se escribe a medias."""
    if not isinstance(datos, list) or len(datos) > MAX_ENTRADAS_LISTA:
        return False
    for e in datos:
        if not isinstance(e, dict) or len(e) > 20:
            return False
        for k, v in e.items():
            if not isinstance(k, str) or not (v is None or isinstance(v, (str, int, float, bool))):
                return False
            if isinstance(v, str) and len(v) > 500:
                return False
    return len(json.dumps(datos, ensure_ascii=False).encode("utf-8")) <= MAX_BYTES_LISTA


def aplicar_listas_pc(listas):
    """Railway: guarda las listas que mando la PC (escritura atomica). El
    monitor las toma solo en su siguiente recarga (cada 60 s). Devuelve el
    hash de lo que quedo guardado; si algo no es valido no toca nada."""
    global _LISTAS_HASH
    if not isinstance(listas, dict) or set(listas) - set(ARCHIVOS_LISTAS):
        raise ValueError("listas desconocidas")
    if not all(_lista_valida(v) for v in listas.values()):
        raise ValueError("lista con formato invalido")
    for nombre, datos in listas.items():
        ruta = globals()[ARCHIVOS_LISTAS[nombre]]
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ruta), prefix=".lista_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            os.replace(tmp, ruta)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    _LISTAS_HASH = _hash_listas(listas)
    print(f"  [relevo] listas de la PC guardadas ({', '.join(sorted(listas))})")
    return _LISTAS_HASH


# --- Piezas que Railway encontro y la PC puede comprar ---
PIEZAS_RELEVO = {}          # id -> datos de la pieza (en memoria, se pierden al reiniciar)
MAX_PIEZAS_RELEVO = 200
_ID_PIEZA_RELEVO = 0


def guardar_pieza_relevo(url, titulo=None, url_carrito=None, imagen=None,
                         precio_mxn=None, tipo=None):
    """Railway: anota una pieza comprable y devuelve su id para el boton
    "Comprar con el bot (PC)" (callback rc:<id>). Al tocarlo, la PC la pide
    con GET /api/bot/pieza-relevo/<id> y sigue su flujo normal de compra."""
    global _ID_PIEZA_RELEVO
    for pid, d in PIEZAS_RELEVO.items():
        if d["url"] == url:
            d.update(url_carrito=url_carrito, precio_mxn=precio_mxn, tipo=tipo)
            return pid
    _ID_PIEZA_RELEVO += 1
    PIEZAS_RELEVO[_ID_PIEZA_RELEVO] = {
        "url": url, "titulo": titulo, "url_carrito": url_carrito, "imagen": imagen,
        "precio_mxn": precio_mxn, "tipo": tipo,
        "cuando": datetime.now(timezone.utc).isoformat()}
    while len(PIEZAS_RELEVO) > MAX_PIEZAS_RELEVO:
        PIEZAS_RELEVO.pop(min(PIEZAS_RELEVO))
    return _ID_PIEZA_RELEVO


def fila_decision(hallazgo_id=None, relevo_id=None):
    """Botones de decidir (solo chat personal): los del panel local o, en
    Railway, el que le pide a la PC que compre."""
    if hallazgo_id:
        return [{"text": "🛒 Comprar con el bot", "callback_data": f"c:{hallazgo_id}"},
                {"text": "🙈 Ignorar", "callback_data": f"i:{hallazgo_id}"}]
    if relevo_id:
        return [{"text": "🛒 Comprar con el bot (PC)", "callback_data": f"rc:{relevo_id}"}]
    return None


def revisar_relevo():
    """Avisa (una vez) cuando Railway toma el relevo y cuando lo suelta."""
    global _RELEVO_ACTIVO
    if not MODO_RELEVO:
        return
    vigila = pc_vigilando()
    if not vigila and not _RELEVO_ACTIVO:
        _RELEVO_ACTIVO = True
        minutos = int((time.monotonic() - _PC_LATIDO) / 60) if _PC_LATIDO else 0
        print(f"  [relevo] la PC lleva {minutos} min sin vigilar: Railway avisa")
        if pc_app_viva():
            como = ("La app de la PC sigue prendida pero su monitor no ve la tienda.\n"
                    "Te aviso desde Railway, y el botón <i>Comprar con el bot (PC)</i> "
                    "hace que la PC compre como siempre.")
        else:
            como = ("La PC está apagada, sin internet o con la app cerrada.\n"
                    "Te aviso desde Railway con la liga del carrito. Sin la PC no hay "
                    "botón <i>Comprar con el bot</i>: el bot de compra vive ahí.")
        enviar_telegram_texto(
            "☁️ <b>RAILWAY TOMA EL RELEVO</b>\n\n"
            f"La PC lleva {minutos} min sin vigilar. {como}", forzar=True)
    elif vigila and _RELEVO_ACTIVO:
        _RELEVO_ACTIVO = False
        print("  [relevo] la PC volvio: Railway se calla")
        enviar_telegram_texto("🖥️ <b>La PC volvió a vigilar.</b> Railway se queda en silencio.",
                              forzar=True)


def ya_notificado(key):
    ahora = datetime.now(timezone.utc)
    if key in NOTIFICACIONES_ENVIADAS:
        ts = NOTIFICACIONES_ENVIADAS[key]
        if (ahora - ts) < timedelta(hours=HORAS_BLOQUEO_DUPLICADOS):
            return True
    NOTIFICACIONES_ENVIADAS[key] = ahora
    viejas = [k for k, v in NOTIFICACIONES_ENVIADAS.items()
              if (ahora - v) > timedelta(hours=HORAS_BLOQUEO_DUPLICADOS)]
    for k in viejas:
        del NOTIFICACIONES_ENVIADAS[k]
    return False


# ============================================================
# TIPO DE CAMBIO
# ============================================================

def obtener_tipo_cambio():
    global TIPO_CAMBIO
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        r.raise_for_status()
        tasa = r.json().get("rates", {}).get("MXN")
        if tasa:
            TIPO_CAMBIO = round(tasa, 2)
            print(f"  Tipo de cambio: 1 USD = ${TIPO_CAMBIO} MXN")
    except Exception:
        print(f"  Tipo de cambio por defecto: ${TIPO_CAMBIO}")


def usd_a_mxn(precio_usd):
    if precio_usd is None:
        return None
    return round(precio_usd * TIPO_CAMBIO, 2)


def usd_a_mxn_ajustado(precio_usd):
    if precio_usd is None:
        return None
    return round(precio_usd * TIPO_CAMBIO + AJUSTE_IMPUESTOS_MXN, 2)


# ============================================================
# ESTADO
# ============================================================

def cargar_estado():
    if os.path.exists(ARCHIVO_ESTADO):
        with open(ARCHIVO_ESTADO, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"productos": {}, "revisiones": 0, "alertas": [], "pocas_unidades": [],
            "ultima_revision": None, "tipo_cambio": TIPO_CAMBIO,
            "stats_hoy": {}, "ultimo_resumen": None}


def guardar_estado(estado):
    estado["tipo_cambio"] = TIPO_CAMBIO
    # Guardado ATOMICO: se escribe primero a un archivo temporal, se fuerza
    # a disco (fsync) y se renombra de golpe con os.replace. Si el proceso
    # muere a medias, estado.json nunca queda corrupto/truncado: o esta el
    # contenido viejo completo, o el nuevo completo. Nunca algo a medias.
    dir_ = os.path.dirname(os.path.abspath(ARCHIVO_ESTADO)) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".estado_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ARCHIVO_ESTADO)  # operacion atomica del sistema
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise


def agregar_alerta(estado, producto, tipo, precio_anterior=None, veces_agotado=0):
    titulo = producto.get("title", "")
    alertas = estado.get("alertas", [])
    ahora = datetime.now(timezone.utc)
    for a in alertas[:20]:
        if a.get("titulo") == titulo and a.get("tipo") == tipo:
            try:
                ts = datetime.fromisoformat(a.get("timestamp", "").replace("Z", "+00:00"))
                if (ahora - ts) < timedelta(minutes=15):
                    return
            except Exception:
                pass

    precio = precio_minimo(producto)
    alerta = {
        "titulo": titulo,
        "tipo": tipo,
        "precio_usd": precio,
        "precio_mxn": usd_a_mxn_ajustado(precio) if precio else None,
        "precio_anterior_usd": precio_anterior,
        "precio_anterior_mxn": usd_a_mxn_ajustado(precio_anterior) if precio_anterior else None,
        "imagen": imagen_thumbnail(producto),
        "url": f"{BASE_URL}/products/{producto.get('handle', '')}",
        "url_carrito": link_carrito(producto) if hay_disponibilidad(producto) else None,
        "deseado": bool(EX and EX.es_deseado(titulo, DESEADOS)),
        "impacto": evaluar_impacto(producto, veces_agotado),
        "timestamp": ahora.isoformat(),
    }
    alertas.insert(0, alerta)
    estado["alertas"] = alertas[:MAX_ALERTAS_GUARDADAS]

    # Contar stats del dia
    zona_mx = timezone(timedelta(hours=-6))
    hoy = datetime.now(zona_mx).strftime("%Y-%m-%d")
    if "stats_hoy" not in estado:
        estado["stats_hoy"] = {}
    if estado["stats_hoy"].get("fecha") != hoy:
        estado["stats_hoy"] = {"fecha": hoy, "nuevos": 0, "restocks": 0,
                                "proximamente": 0, "agotados": 0,
                                "cambios_precio": 0, "pocas_unidades": 0,
                                "rebajas": 0, "agotamientos_rapidos": []}
    stats = estado["stats_hoy"]
    # Mapear tipo de alerta al nombre del contador
    mapa = {"nuevo": "nuevos", "restock": "restocks", "proximamente": "proximamente",
            "agotado": "agotados", "cambio_precio": "cambios_precio",
            "pocas_unidades": "pocas_unidades", "rebaja": "rebajas"}
    clave = mapa.get(tipo, tipo)
    if clave in stats:
        stats[clave] = stats.get(clave, 0) + 1


# ============================================================
# HTTP
# ============================================================

def hacer_request(url, params=None, intentos=3, fresco=False):
    """GET a Mattel con reintentos. `fresco=True` (ciclo rapido) agrega un
    parametro que cambia en cada consulta: la CDN de Shopify guarda
    products.json unos segundos y sin esto un restock se puede ver tarde."""
    global _PAUSA_HASTA
    if time.monotonic() < _PAUSA_HASTA:
        return None     # en pausa por un 429: ni el resto del barrido consulta
    if fresco:
        params = dict(params or {}, _=int(time.time() * 1000))
    for intento in range(1, intentos + 1):
        try:
            r = SESION.get(url, params=params, timeout=10 if fresco else 25)
            if r.status_code == 429:
                # Reintentar en caliente solo empeora el castigo: se pausa todo.
                try:
                    espera = min(int(r.headers.get("Retry-After", "")), 300)
                except ValueError:
                    espera = SEGUNDOS_PAUSA_429
                _PAUSA_HASTA = time.monotonic() + max(espera, 5)
                print(f"    429 - Mattel pide bajar el ritmo; pausa de {max(espera, 5)}s")
                return None
            if r.status_code == 503:
                if intento >= intentos:
                    return None
                espera = intento * 8
                print(f"    503 - reintentando en {espera}s ({intento}/{intentos})")
                time.sleep(espera)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if intento < intentos:
                time.sleep(intento * 5)
                continue
            print(f"    Error: {e}")
            return None
    return None


def obtener_productos_coleccion(coleccion):
    """Devuelve (productos, respondio).

    `respondio` separa dos cosas que antes se veian igual (lista vacia):
    una coleccion que existe y no tiene autos, y una coleccion que dejo de
    responder porque cambio de nombre, la borraron o la tienda esta caida.
    Sin esa diferencia no se puede avisar de lo segundo.
    """
    url = f"{BASE_URL}/collections/{coleccion}/products.json"
    productos = []
    respondio = False
    for page in range(1, 15):
        data = hacer_request(url, params={"limit": 250, "page": page})
        if data is None:
            break
        respondio = True
        items = data.get("products", [])
        if not items:
            break
        productos.extend(items)
        if len(items) < 250:
            break
        time.sleep(2)
    return productos, respondio


def registrar_salud_coleccion(estado, coleccion, respondio, cuantos):
    """Lleva la cuenta de fallos seguidos por coleccion y avisa cuando una
    se cae, sin esperar a que se caiga el monitor entero: perfectamente
    puede seguir 'vigilando' 4 de 5 colecciones y nadie enterarse."""
    salud = estado.setdefault("salud_colecciones", {})
    d = salud.setdefault(coleccion, {"fallos": 0, "ultimo_ok": None, "productos": 0})
    if respondio:
        d["fallos"] = 0
        d["ultimo_ok"] = datetime.now(timezone.utc).isoformat()
        d["productos"] = cuantos
        return
    d["fallos"] = d.get("fallos", 0) + 1
    if d["fallos"] < FALLOS_ALERTA_COLECCION:
        return
    # Ojo: time.monotonic() cuenta desde que prendio la PC. Con 0.0 como
    # "nunca", la primera hora despues de prender la PC no avisaba nada.
    ultima = _TS_ALERTA_COLECCION.get(coleccion)
    if ultima is not None and (time.monotonic() - ultima) < 3600:
        return          # maximo un aviso por hora y por coleccion
    _TS_ALERTA_COLECCION[coleccion] = time.monotonic()
    print(f"  [ALERTA] la coleccion {coleccion} no responde ({d['fallos']} veces)")
    enviar_telegram_texto(
        "<b>COLECCION SIN RESPUESTA</b>\n\n"
        f"<code>{coleccion}</code> lleva {d['fallos']} barridos seguidos sin contestar.\n"
        "El resto del monitor sigue trabajando. Puede que la coleccion haya "
        "cambiado de nombre o ya no exista: revisala en la pestaña "
        "<b>Administrar</b> del tablero.")


COLECCIONES_EN_PARALELO = 3   # pocas a la vez: rapido sin parecer ataque


def obtener_todos_los_productos(estado=None):
    """Consulta todas las colecciones y combina sin duplicados.

    Van de COLECCIONES_EN_PARALELO en paralelo: antes iban una por una con
    pausas y el barrido tardaba lo suficiente para frenar al ciclo rapido.
    Los resultados se juntan en el orden de COLECCIONES, como siempre.
    Devuelve (productos, colecciones_que_fallaron)."""
    colecciones = list(COLECCIONES)
    print(f"    Consultando {len(colecciones)} colecciones...")
    with ThreadPoolExecutor(max_workers=COLECCIONES_EN_PARALELO) as pool:
        resultados = list(pool.map(obtener_productos_coleccion, colecciones))
    productos_por_id = {}
    fallaron = []
    for coleccion, (items, respondio) in zip(colecciones, resultados):
        for p in items:
            pid = str(p["id"])
            if pid not in productos_por_id:
                productos_por_id[pid] = p
        if not respondio:
            fallaron.append(coleccion)
        if estado is not None:
            registrar_salud_coleccion(estado, coleccion, respondio, len(items))
    return list(productos_por_id.values()), fallaron


# ============================================================
# UTILIDADES
# ============================================================

def es_coming_soon(producto):
    tags = producto.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip().lower() for t in tags.split(",")]
    else:
        tags = [t.lower() for t in tags]
    titulo = (producto.get("title") or "").lower()
    indicadores = ["coming soon", "coming-soon", "comingsoon", "pre-order", "preorder", "presale"]
    texto = " ".join(tags) + " " + titulo
    return any(ind in texto for ind in indicadores)


def es_pocas_unidades(producto):
    tags = producto.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip().lower() for t in tags.split(",")]
    else:
        tags = [t.lower() for t in tags]
    texto = " ".join(tags).lower()
    body_html = (producto.get("body_html") or "").lower()
    return any(ind in texto or ind in body_html for ind in TAGS_POCAS_UNIDADES)


def es_en_rebaja(producto):
    """True si el producto trae tag/descripcion de rebaja/liquidacion.
    Distinto de un cambio de precio detectado por diferencia numerica: esto
    es la ETIQUETA que pone Mattel, se nota antes de que compares numeros."""
    tags = producto.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip().lower() for t in tags.split(",")]
    else:
        tags = [t.lower() for t in tags]
    texto = " ".join(tags).lower()
    body_html = (producto.get("body_html") or "").lower()
    return any(ind in texto or ind in body_html for ind in TAGS_REBAJA)


def hay_disponibilidad(producto):
    if es_coming_soon(producto):
        return False
    return any(v.get("available") for v in producto.get("variants", []))


def cumple_filtro(producto):
    if not PALABRAS_CLAVE:
        return True
    titulo = producto.get("title", "").lower()
    return any(p.lower() in titulo for p in PALABRAS_CLAVE)


def precio_minimo(producto):
    precios = [float(v["price"]) for v in producto.get("variants", []) if v.get("price")]
    return min(precios) if precios else None


def imagen_principal(producto):
    imgs = producto.get("images") or []
    if not imgs:
        return None
    src = imgs[0].get("src", "")
    src = re.sub(r'_\d+x(\d+)?\.', '.', src)
    return src if src else None


def imagen_thumbnail(producto):
    imgs = producto.get("images") or []
    if not imgs:
        return None
    src = imgs[0].get("src", "")
    src = re.sub(r'_\d+x(\d+)?\.', '_200x.', src)
    return src if src else None


# ============================================================
# COMPRA DIRECTA (carrito precargado)
# ============================================================

def id_variante_comprable(producto):
    """Id de la variante que se puede comprar (la disponible; si ninguna lo
    esta, la primera, para tener la liga lista de todas formas)."""
    variantes = producto.get("variants") or []
    for v in variantes:
        if v.get("available"):
            return str(v.get("id"))
    if variantes and variantes[0].get("id"):
        return str(variantes[0]["id"])
    return None


def link_carrito(producto):
    """Liga que mete el auto DIRECTO al carrito de Mattel Creations.

    Mattel Creations corre sobre Shopify, y Shopify acepta la ruta
    /cart/<id_variante>:<cantidad>. Al abrirla, el auto ya esta en el carrito
    y solo falta pagar: se brinca elegir variante y agregar a mano, que es
    justo donde se van los segundos en un drop.
    """
    vid = id_variante_comprable(producto)
    if not vid:
        return None
    return f"{BASE_URL}/cart/{vid}:1"


def texto_ganancia_neta(producto):
    """Linea con la ganancia limpia en pesos.

    Reusa el precio de reventa (eBay + Mercado Libre) que ya se consulto
    para el impacto -- ambos vienen de cache, no cuesta una consulta extra.
    """
    if not EX:
        return ""
    try:
        titulo = producto.get("title", "")
        precio_reventa, ventas = precio_reventa_estimado(titulo)
        if not precio_reventa or ventas < 3:
            return ""
        g = EX.ganancia_neta(precio_minimo(producto), precio_reventa, TIPO_CAMBIO,
                             envio_mxn=ENVIO_MXN_ESTIMADO,
                             impuestos_mxn=AJUSTE_IMPUESTOS_MXN,
                             comision_pct=COMISION_REVENTA_PCT)
        return EX.texto_ganancia(g)
    except Exception:
        return ""


# ============================================================
# VIGILANCIA (modo francotirador)
# ============================================================
# Un producto entra a vigilancia cuando vale la pena mirarlo de a uno,
# mucho mas seguido que el barrido completo:
#   - "coming soon": ya existe en la tienda con la venta apagada; puede
#     prender en cualquier momento.
#   - agotado que ya se resurtio antes: candidato claro a restock.
# Se guarda dentro de estado.json para que sobreviva a un reinicio.

_IDX_FRANCOTIRADOR = {}   # grupo -> por donde va el turno

def marcar_vigilancia(estado, producto, motivo):
    handle = producto.get("handle", "")
    if not handle:
        return
    v = estado.setdefault("vigilancia", {})
    if handle not in v:
        v[handle] = {"motivo": motivo,
                     "desde": datetime.now(timezone.utc).isoformat()}


def quitar_vigilancia(estado, producto):
    handle = producto.get("handle", "")
    if handle:
        estado.get("vigilancia", {}).pop(handle, None)


def limpiar_vigilancia(estado):
    """Saca de la lista lo que ya lleva demasiado tiempo sin moverse.

    Los vigilados a mano (motivo 'manual', puestos desde el tablero) NO
    vencen: si Gonza dijo "sigue este", se sigue hasta que lo quite el."""
    v = estado.get("vigilancia", {})
    ahora = datetime.now(timezone.utc)
    for h in list(v.keys()):
        if (v[h] or {}).get("motivo") == "manual":
            continue
        try:
            desde = datetime.fromisoformat(v[h]["desde"].replace("Z", "+00:00"))
            if (ahora - desde) > timedelta(hours=HORAS_VIGILANCIA):
                del v[h]
        except Exception:
            del v[h]


def revisar_mercadolibre(estado):
    """Segunda tienda: busca en Mercado Libre los terminos que Gonza puso en
    el tablero y avisa de publicaciones NUEVAS (y de bajadas de precio en las
    que ya conocia), respetando el precio maximo de cada busqueda.

    La primera pasada de cada termino es de calentamiento: se memoriza lo que
    ya estaba publicado sin avisar de nada. Sin eso, el primer arranque
    mandaria 25 mensajes de autos que llevan meses en venta.

    Devuelve cuantos avisos mando.
    """
    if not EX or not ML_TOKEN:
        return 0
    busquedas = [b for b in EX.listar_busquedas_ml(ARCHIVO_BUSQUEDAS_ML) if b["activa"]]
    if not busquedas:
        return 0
    vistos_todos = estado.setdefault("ml_vistos", {})
    avisos = 0
    for b in busquedas:
        termino = b["termino"]
        listados, motivo = EX.buscar_listados_ml(termino, token=ML_TOKEN)
        estado.setdefault("ml_estado", {})[termino] = {
            "cuando": datetime.now(timezone.utc).isoformat(),
            "resultados": len(listados),
            "motivo": motivo,
        }
        if motivo:
            print(f"  [ML] {termino}: {motivo}")
            continue
        conocidos = vistos_todos.get(termino)
        primera_vez = conocidos is None
        conocidos = dict(conocidos or {})
        for it in listados:
            tope = b.get("precio_max")
            precio = it["precio_mxn"]
            previo = conocidos.get(it["id"])
            conocidos[it["id"]] = precio
            if primera_vez:
                continue
            interesa = (tope is None) or (precio <= float(tope))
            if not interesa:
                continue
            if previo is None:
                titulo_aviso = "NUEVO EN MERCADO LIBRE"
            elif precio < float(previo):
                titulo_aviso = "BAJO DE PRECIO EN MERCADO LIBRE"
            else:
                continue
            if ya_notificado(f"ml:{it['id']}:{int(precio)}"):
                continue
            envio = " · envío gratis" if it["envio_gratis"] else ""
            cuerpo = (f"<b>{titulo_aviso}</b>\n\n"
                      f"{html.escape(it['titulo'])}\n"
                      f"<b>MXN ${precio:,.0f}</b>{envio}\n"
                      f"Búsqueda: <i>{html.escape(termino)}</i>")
            if previo is not None:
                cuerpo += f"\nAntes: MXN ${float(previo):,.0f}"
            enviar_telegram(cuerpo, it["imagen"], it["link"], None)
            agregar_alerta_ml(estado, it, termino, titulo_aviso, previo)
            if EX and HISTORIAL is not None:
                EX.registrar_evento(HISTORIAL, "mercadolibre", None,
                                    precio_mxn=precio, titulo=it["titulo"],
                                    producto_id=it["id"], handle=termino,
                                    impacto="Mercado Libre")
            avisos += 1
        # Recorta lo memorizado para que estado.json no crezca sin fin.
        if len(conocidos) > MAX_IDS_ML_RECORDADOS:
            conocidos = dict(list(conocidos.items())[-MAX_IDS_ML_RECORDADOS:])
        vistos_todos[termino] = conocidos
        time.sleep(1)
    return avisos


def agregar_alerta_ml(estado, item, termino, tipo, precio_anterior=None):
    """Mete una publicacion de Mercado Libre en la misma lista de alertas del
    tablero, marcada con fuente 'mercadolibre' para poder distinguirla de las
    de Mattel (que traen handle, variante y boton de carrito)."""
    alertas = estado.setdefault("alertas", [])
    alertas.insert(0, {
        "titulo": item["titulo"],
        "tipo": "mercadolibre",
        "fuente": "mercadolibre",
        "etiqueta": tipo,
        "precio_mxn": item["precio_mxn"],
        "precio_anterior_mxn": float(precio_anterior) if precio_anterior else None,
        "imagen": item["imagen"],
        "link": item["link"],
        "termino": termino,
        "envio_gratis": item["envio_gratis"],
        "cuando": datetime.now(timezone.utc).isoformat(),
    })
    del alertas[MAX_ALERTAS_GUARDADAS:]


def recargar_ajustes():
    """Relee config.env para tomar lo que se haya cambiado en la pestaña
    Administrar. Solo toca los valores de la lista blanca (hw_extras seccion
    11); el token de Telegram y los del puente NO se recargan en caliente a
    proposito -- cambiarlos exige reiniciar, que es justo lo que se quiere
    para algo tan delicado."""
    global CONFIG, SEGUNDOS_CICLO_RAPIDO, MAX_FRANCOTIRADOR, MINUTOS_ALERTA_CIEGO
    global ENVIO_MXN_ESTIMADO, COMISION_REVENTA_PCT
    global MINUTOS_MERCADOLIBRE, FALLOS_ALERTA_COLECCION
    global SEGUNDOS_CICLO_DROP, MINUTOS_ANTES_DROP, MINUTOS_DESPUES_DROP
    if not EX:
        return
    CONFIG = _cargar_config()
    SEGUNDOS_CICLO_RAPIDO = int(EX.config_num(CONFIG, "SEGUNDOS_CICLO_RAPIDO", SEGUNDOS_CICLO_RAPIDO))
    MAX_FRANCOTIRADOR = int(EX.config_num(CONFIG, "MAX_FRANCOTIRADOR", MAX_FRANCOTIRADOR))
    MINUTOS_ALERTA_CIEGO = int(EX.config_num(CONFIG, "MINUTOS_ALERTA_CIEGO", MINUTOS_ALERTA_CIEGO))
    ENVIO_MXN_ESTIMADO = EX.config_num(CONFIG, "ENVIO_MXN_ESTIMADO", ENVIO_MXN_ESTIMADO)
    COMISION_REVENTA_PCT = EX.config_num(CONFIG, "COMISION_REVENTA_PCT", COMISION_REVENTA_PCT)
    MINUTOS_MERCADOLIBRE = int(EX.config_num(CONFIG, "MINUTOS_MERCADOLIBRE", MINUTOS_MERCADOLIBRE))
    FALLOS_ALERTA_COLECCION = int(EX.config_num(CONFIG, "FALLOS_ALERTA_COLECCION", FALLOS_ALERTA_COLECCION))
    SEGUNDOS_CICLO_DROP = int(EX.config_num(CONFIG, "SEGUNDOS_CICLO_DROP", SEGUNDOS_CICLO_DROP))
    MINUTOS_ANTES_DROP = int(EX.config_num(CONFIG, "MINUTOS_ANTES_DROP", MINUTOS_ANTES_DROP))
    MINUTOS_DESPUES_DROP = int(EX.config_num(CONFIG, "MINUTOS_DESPUES_DROP", MINUTOS_DESPUES_DROP))


def recargar_listas(estado):
    """Relee de disco TODO lo que se administra desde el tablero: lista de
    deseados, bloqueados, colecciones vigiladas y productos sueltos.

    Se llama seguido (cada SEGUNDOS_REFRESCO_LISTAS) porque son archivos
    chicos en disco, sin red: es lo que hace que un cambio hecho en la web
    se sienta inmediato en vez de tardar hasta dos horas."""
    global COLECCIONES, COLECCIONES_RAPIDAS, DESEADOS, BLOQUEADOS
    if not EX:
        return
    DESEADOS = EX.cargar_deseados(ARCHIVO_DESEADOS)
    BLOQUEADOS = EX.cargar_deseados(ARCHIVO_BLOQUEADOS)
    activas = EX.cargar_colecciones(ARCHIVO_COLECCIONES)
    if activas:
        # Si quedara vacio (todo apagado desde el tablero) se conserva lo
        # anterior: un monitor que no mira nada es un monitor roto, y eso
        # casi siempre seria un error de dedo, no una intencion.
        COLECCIONES = activas
        rapidas = EX.cargar_colecciones(ARCHIVO_COLECCIONES, solo_rapidas=True)
        if rapidas:
            COLECCIONES_RAPIDAS = rapidas
    recargar_ajustes()
    if estado is not None:
        sincronizar_vigilados_manuales(estado)


def sincronizar_vigilados_manuales(estado):
    """Refleja vigilar.json (que escribe el tablero) dentro de la vigilancia
    del monitor: agrega los nuevos y quita los que Gonza ya borro. Solo toca
    las entradas con motivo 'manual' — no interfiere con el francotirador
    automatico, que sigue marcando 'coming_soon'/'agotado' por su cuenta."""
    if not EX:
        return 0
    deseados_manual = {c["handle"] for c in EX.listar_vigilados(ARCHIVO_VIGILAR)}
    v = estado.setdefault("vigilancia", {})
    for h in list(v.keys()):
        if (v[h] or {}).get("motivo") == "manual" and h not in deseados_manual:
            del v[h]
    agregados = 0
    for h in deseados_manual:
        if h not in v:
            v[h] = {"motivo": "manual",
                    "desde": datetime.now(timezone.utc).isoformat()}
            agregados += 1
    return agregados


def _turno(grupo, nombre, cupo):
    """Hasta `cupo` elementos de `grupo`, turnandose entre ciclos."""
    if cupo <= 0 or not grupo:
        return []
    if len(grupo) <= cupo:
        return list(grupo)
    i = _IDX_FRANCOTIRADOR.get(nombre, 0) % len(grupo)
    _IDX_FRANCOTIRADOR[nombre] = (i + cupo) % len(grupo)
    return [grupo[(i + k) % len(grupo)] for k in range(cupo)]


def _siguientes_francotirador(estado):
    """A cuales vigilar en este ciclo, por prioridad:
      1. lo que Gonza quiere: vigilados a mano y autos de su lista de deseados
      2. los "coming soon" (pueden prender en cualquier momento)
      3. el resto (agotados candidatos a restock)
    Cada grupo se turna por su lado, asi un deseado nunca espera detras de
    30 agotados cualquiera."""
    v = estado.get("vigilancia", {})
    if not v:
        return []
    titulos = {d.get("handle"): d.get("titulo") or ""
               for d in estado.get("productos", {}).values() if d.get("handle")}

    def es_de_gonza(h, d):
        if (d or {}).get("motivo") == "manual":
            return True
        titulo = titulos.get(h) or h.replace("-", " ")
        return bool(EX and DESEADOS and EX.es_deseado(titulo, DESEADOS))

    top = sorted(h for h, d in v.items() if es_de_gonza(h, d))
    ya = set(top)
    resto = [h for h in v if h not in ya]
    coming = sorted(h for h in resto if (v[h] or {}).get("motivo") == "coming_soon")
    otros = sorted(h for h in resto if (v[h] or {}).get("motivo") != "coming_soon")
    seleccion = []
    for nombre, grupo in (("top", top), ("coming", coming), ("otros", otros)):
        seleccion += _turno(grupo, nombre, MAX_FRANCOTIRADOR - len(seleccion))
    return seleccion


def obtener_producto_individual(handle):
    """Consulta UN solo producto. Es una peticion chica, por eso se puede
    repetir cada pocos segundos sin castigar al servidor."""
    data = hacer_request(f"{BASE_URL}/products/{handle}.json", intentos=1, fresco=True)
    if isinstance(data, dict):
        return data.get("product")
    return None


def obtener_productos_rapidos(estado):
    """Tanda chica del ciclo rapido: new-arrivals + los vigilados."""
    productos_por_id = {}
    for coleccion in COLECCIONES_RAPIDAS:
        data = hacer_request(f"{BASE_URL}/collections/{coleccion}/products.json",
                             params={"limit": 250}, intentos=1, fresco=True)
        if not data:
            continue
        for p in data.get("products", []):
            productos_por_id[str(p["id"])] = p
    for handle in _siguientes_francotirador(estado):
        p = obtener_producto_individual(handle)
        if p and p.get("id"):
            productos_por_id[str(p["id"])] = p
    return list(productos_por_id.values())


# ============================================================
# EBAY + EVALUACION DE IMPACTO
# ============================================================

_RE_PRECIO_USD = re.compile(r'\$(\d{1,3}(?:,\d{3})+|\d{1,5})\.(\d{2})')


def extraer_precios_ebay(texto):
    """Precios en dolares de la pagina de vendidos de eBay. Acepta "$1,250.00"
    (antes solo leia hasta $9999 sin coma, y con el tope de 800 las piezas
    caras salian con reventa baja y se silenciaban como "Bajo interes")."""
    precios = []
    for entero, centavos in _RE_PRECIO_USD.findall(texto):
        valor = float(entero.replace(",", "") + "." + centavos)
        if 3.0 <= valor <= 5000.0:
            precios.append(valor)
    return precios


def buscar_ebay(termino, tag_cache=None):
    cache_key = (tag_cache or termino).lower().strip()
    if cache_key in CACHE_EBAY:
        return CACHE_EBAY[cache_key]
    try:
        r = requests.get("https://www.ebay.com/sch/i.html",
            params={"_nkw": f"hot wheels {termino}", "LH_Complete": "1", "LH_Sold": "1",
                    "_sop": "12", "rt": "nc", "_ipg": "60"},
            headers={"User-Agent": HEADERS["User-Agent"], "Accept-Language": "en-US,en;q=0.9"},
            timeout=15)
        r.raise_for_status()
        precios = extraer_precios_ebay(r.text)
        if len(precios) >= 3:
            ordenados = sorted(precios)
            recortados = ordenados[1:-1] if len(ordenados) > 4 else ordenados
            resultado = (round(sum(recortados) / len(recortados), 2), len(recortados))
        elif precios:
            resultado = (round(sum(precios) / len(precios), 2), len(precios))
        else:
            resultado = (None, 0)
        CACHE_EBAY[cache_key] = resultado
        return resultado
    except Exception:
        resultado = (None, 0)
        CACHE_EBAY[cache_key] = resultado
        return resultado


def precio_reventa_estimado(titulo):
    """Precio de reventa combinando eBay (USD) y Mercado Libre (MXN,
    convertido a USD con el tipo de cambio del dia). Si ambas fuentes tienen
    datos suficientes se promedian -- mas robusto que confiar en una sola
    plataforma; si solo una tiene datos, se usa esa. Devuelve
    (precio_usd, cuantos_resultados_en_total)."""
    busqueda = titulo.replace("Hot Wheels ", "").replace("'", "").replace('"', '')
    tag = f"exacto:{titulo}"
    precio_ebay, ventas_ebay = buscar_ebay(busqueda, tag_cache=tag)
    precio_ml_mxn, resultados_ml = (
        EX.buscar_mercadolibre(busqueda, tag_cache=tag, token=ML_TOKEN)
        if EX else (None, 0))
    precio_ml_usd = (precio_ml_mxn / TIPO_CAMBIO) if (precio_ml_mxn and TIPO_CAMBIO) else None

    candidatos = []
    if precio_ebay and ventas_ebay >= 3:
        candidatos.append(precio_ebay)
    if precio_ml_usd and resultados_ml >= 3:
        candidatos.append(precio_ml_usd)
    if not candidatos:
        return None, 0
    return round(sum(candidatos) / len(candidatos), 2), ventas_ebay + resultados_ml


VARIANTES_PREMIUM = {
    "chase": 25, "spectraflame": 20, "super treasure hunt": 22,
    "treasure hunt": 15, "convention": 20, "rlc exclusive": 18,
    "selections": 15, "limited edition": 12, "gold": 8, "chrome": 8, "zamac": 10,
}
MODELOS_ALTA_DEMANDA = {
    "porsche 911": 30, "porsche 993": 30, "porsche 964": 30, "porsche 930": 30,
    "datsun 510": 28, "datsun 240z": 28, "datsun 280z": 25,
    "skyline": 28, "gt-r": 28, "gtr": 28, "r34": 30, "r32": 27,
    "toyota supra": 27, "ae86": 25, "toyota 2000gt": 28,
    "rx-7": 26, "rx7": 26, "nsx": 25, "honda s2000": 22,
    "lamborghini countach": 28, "lamborghini miura": 30, "aventador": 22,
    "ferrari 250": 30, "ferrari f40": 28, "ferrari 288": 27,
    "mclaren f1": 28, "mclaren p1": 25, "pagani": 25, "bugatti": 22,
    "camaro": 22, "corvette": 22, "'69 camaro": 25, "'67 camaro": 25,
    "mustang": 22, "'67 mustang": 25, "shelby gt500": 25,
    "challenger": 20, "charger": 20, "'70 charger": 23,
    "chevelle": 22, "gto": 20, "nova": 20,
    "volkswagen": 18, "golf": 18, "beetle": 18, "bmw": 20, "mercedes": 18,
}
LINEAS_PRODUCTO = {
    "rlc exclusive": 35, "rlc": 30, "elite 64": 30,
    "hwc special": 25, "special edition": 22,
    "car culture": 20, "premium": 18, "boulevard": 18, "team transport": 20,
    "fast & furious": 17, "fast and furious": 17, "pop culture": 15, "character car": 8,
}


def _reventa_en_cache(titulo):
    """Precio de reventa SOLO si ya esta en memoria (sin red, al instante).
    Mismo calculo que precio_reventa_estimado, sin consultar eBay ni ML."""
    tag = f"exacto:{titulo}".lower().strip()
    candidatos, total = [], 0
    precio_ebay, ventas_ebay = CACHE_EBAY.get(tag, (None, 0))
    if precio_ebay and ventas_ebay >= 3:
        candidatos.append(precio_ebay)
        total += ventas_ebay
    cache_ml = getattr(EX, "_CACHE_MERCADOLIBRE", {}) if EX else {}
    precio_ml_mxn, resultados_ml = cache_ml.get(tag, (None, 0))
    if precio_ml_mxn and resultados_ml >= 3 and TIPO_CAMBIO:
        candidatos.append(precio_ml_mxn / TIPO_CAMBIO)
        total += resultados_ml
    if not candidatos:
        return None, 0
    return round(sum(candidatos) / len(candidatos), 2), total


def impacto_rapido(producto, veces_agotado=0):
    """Impacto sin tocar la red: decide si un aviso sale como express."""
    return _calificar(producto, veces_agotado,
                      _reventa_en_cache(producto.get("title", "")))


def evaluar_impacto(producto, veces_agotado=0):
    return _calificar(producto, veces_agotado,
                      precio_reventa_estimado(producto.get("title", "")))


def _calificar(producto, veces_agotado, reventa):
    titulo = producto.get("title", "")
    precio_retail = precio_minimo(producto)
    t = titulo.lower()

    precio_reventa, ventas = reventa

    if precio_reventa and precio_retail and precio_retail > 0 and ventas >= 3:
        margen = ((precio_reventa - precio_retail) / precio_retail) * 100
        if veces_agotado >= 3: margen += 40
        elif veces_agotado >= 2: margen += 20
        if margen >= 80: return "Alto impacto"
        elif margen >= 30: return "Impacto medio"
        elif margen >= 0: return "Impacto bajo"
        else: return "Bajo interes"

    pts_linea = 12
    for linea, pts in LINEAS_PRODUCTO.items():
        if linea in t: pts_linea = max(pts_linea, pts)
    if any(x in t for x in ["t-shirt", "shirt", "hat", "hoodie", "pin", "mug", "poster"]):
        pts_linea = 3
    pts_modelo = 10
    for modelo, pts in MODELOS_ALTA_DEMANDA.items():
        if modelo in t: pts_modelo = max(pts_modelo, pts)
    pts_variante = 0
    for clave, peso in VARIANTES_PREMIUM.items():
        if clave in t: pts_variante += peso
    pts_demanda = 0
    if veces_agotado >= 4: pts_demanda = 30
    elif veces_agotado >= 3: pts_demanda = 25
    elif veces_agotado >= 2: pts_demanda = 15
    elif veces_agotado >= 1: pts_demanda = 8
    total = min(pts_linea + pts_modelo + pts_variante + pts_demanda, 100)

    if total >= 75: return "Alto impacto"
    elif total >= 55: return "Impacto medio"
    elif total >= 35: return "Impacto bajo"
    else: return "Bajo interes"


# ============================================================
# TELEGRAM
# ============================================================

def _enviar_a_chat(api, chat_id, texto, foto_url=None, boton=None):
    enviado = False
    if foto_url:
        try:
            payload = {"chat_id": chat_id, "photo": foto_url,
                       "caption": texto[:1024], "parse_mode": "HTML"}
            if boton: payload["reply_markup"] = boton
            r = SESION_TG.post(f"{api}/sendPhoto", data=payload, timeout=15)
            enviado = r.status_code == 200
        except Exception:
            pass
    if not enviado and foto_url:
        try:
            img = requests.get(foto_url, headers=HEADERS, timeout=15)
            if img.status_code == 200:
                files = {"photo": ("producto.jpg", img.content, "image/jpeg")}
                payload = {"chat_id": chat_id, "caption": texto[:1024], "parse_mode": "HTML"}
                if boton: payload["reply_markup"] = boton
                r = SESION_TG.post(f"{api}/sendPhoto", data=payload, files=files, timeout=20)
                enviado = r.status_code == 200
        except Exception:
            pass
    if not enviado:
        try:
            payload = {"chat_id": chat_id, "text": texto,
                       "parse_mode": "HTML", "disable_web_page_preview": False}
            if boton: payload["reply_markup"] = boton
            r = SESION_TG.post(f"{api}/sendMessage", data=payload, timeout=15)
            enviado = r.status_code == 200
        except Exception:
            pass
    if not enviado:
        # Ultimo recurso: texto plano. Si Telegram rechazo el HTML (un "<" o
        # "&" raro en un titulo), sin esto el aviso se perdia por completo.
        try:
            plano = html.unescape(re.sub(r"<[^>]+>", "", texto))
            payload = {"chat_id": chat_id, "text": plano[:4096]}
            if boton: payload["reply_markup"] = boton
            r = SESION_TG.post(f"{api}/sendMessage", data=payload, timeout=15)
            enviado = r.status_code == 200
        except Exception:
            pass
    return enviado


def enviar_telegram(texto, foto_url=None, link=None, link_compra=None, hallazgo_id=None,
                    relevo_id=None):
    """Aviso con foto y botones. Con `hallazgo_id` (pieza registrada en el
    panel) suma los botones Comprar / Ignorar: al pulsarlos, telegram_control.py
    (dentro del panel) pide confirmacion y ejecuta. Esos botones van SOLO al
    chat personal, nunca al canal (en un canal los podria pulsar cualquiera)."""
    if pc_vigilando():
        print("    -> [relevo] la PC vigila: aviso omitido en Railway")
        return
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    filas = []
    # El carrito va arriba a proposito: es el boton que se aprieta con prisa.
    if link_compra:
        filas.append([{"text": "COMPRAR AHORA - carrito listo", "url": link_compra}])
    if link:
        filas.append([{"text": "Ver producto", "url": link}])
    boton_canal = json.dumps({"inline_keyboard": filas}) if filas else None
    filas_chat = list(filas)
    decision = fila_decision(hallazgo_id, relevo_id)
    if decision:
        filas_chat.insert(0, decision)
    boton_chat = json.dumps({"inline_keyboard": filas_chat}) if filas_chat else None
    ok = _enviar_a_chat(api, TELEGRAM_CHAT_ID, texto, foto_url, boton_chat)
    print(f"    -> {'Enviado' if ok else 'ERROR'} a Telegram")
    if TELEGRAM_CANAL_ID:
        ok2 = _enviar_a_chat(api, TELEGRAM_CANAL_ID, texto, foto_url, boton_canal)
        print(f"    -> {'Enviado' if ok2 else 'ERROR'} al canal")


def enviar_express(producto, tipo, link, link_compra, hallazgo_id=None, motivo="",
                   relevo_id=None):
    """Aviso corto, solo texto, solo al chat personal, ANTES de calcular nada.

    sendMessage sin foto ni vista previa llega en ~1 s; la tarjeta completa
    (foto, impacto, ganancia con eBay y Mercado Libre) puede tardar 30 s o
    mas y sale despues. Para lo que de verdad quieres, esos segundos son la
    diferencia entre alcanzarla o no."""
    if pc_vigilando():
        return False
    etiqueta = {"nuevo": "NUEVO", "restock": "RESTOCK",
                "pocas_unidades": "POCAS UNIDADES"}.get(tipo, tipo.upper())
    texto = (f"⚡ <b>{etiqueta} — CORRE</b>{(' · ' + html.escape(motivo)) if motivo else ''}\n\n"
             f"{html.escape(producto.get('title', ''))}\n"
             f"🟢 {formato_precio(precio_minimo(producto))}")
    filas = []
    decision = fila_decision(hallazgo_id, relevo_id)
    if decision:
        filas.append(decision)
    if link_compra:
        filas.append([{"text": "COMPRAR AHORA - carrito listo", "url": link_compra}])
    if link:
        filas.append([{"text": "Ver producto", "url": link}])
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if filas:
        payload["reply_markup"] = json.dumps({"inline_keyboard": filas})
    try:
        r = SESION_TG.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                           data=payload, timeout=8)
        ok = r.status_code == 200
    except Exception:
        ok = False
    print(f"    -> express {'enviado' if ok else 'ERROR'}")
    return ok


def es_urgente(estado, producto, tipo, deseado, bloqueado, veces_agotado=0):
    """Que avisos salen como express: piezas comprables que sabemos que
    quieres (deseados, vigilados a mano) o que ya son "Alto impacto" sin
    consultar la red. Devuelve el motivo (texto) o "" si no es urgente."""
    if tipo not in ("nuevo", "restock", "pocas_unidades") or not hay_disponibilidad(producto):
        return ""
    if deseado:
        return "de tu lista"
    if bloqueado:
        return ""
    vig = (estado.get("vigilancia", {}).get(producto.get("handle", "")) or {})
    if vig.get("motivo") == "manual":
        return "la vigilas"
    if impacto_rapido(producto, veces_agotado) == "Alto impacto":
        return "alto impacto"
    return ""


def enviar_telegram_texto(texto, forzar=False):
    """Envia solo texto sin foto ni boton (para resumen diario). En Railway
    se calla mientras la PC vigila, salvo `forzar` (avisos del relevo)."""
    if not forzar and pc_vigilando():
        return True
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        r = SESION_TG.post(f"{api}/sendMessage", data={
            "chat_id": TELEGRAM_CHAT_ID, "text": texto,
            "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False


# ============================================================
# FORMATO DE MENSAJES
# ============================================================

def predecir_fecha_drop():
    # Si el historial ya aprendio a que dia y hora caen de verdad los drops,
    # se usa eso. Mientras no haya datos suficientes, se sigue usando el
    # supuesto de siempre: martes 11:00 CDMX.
    if EX and PATRON_DROPS:
        aprendida = EX.proximo_drop(PATRON_DROPS)
        if aprendida:
            return aprendida
    zona_mx = timezone(timedelta(hours=-6))
    ahora = datetime.now(zona_mx)
    dias_hasta_martes = (1 - ahora.weekday()) % 7
    if dias_hasta_martes == 0 and ahora.hour >= 11:
        dias_hasta_martes = 7
    if dias_hasta_martes == 0:
        proximo = ahora.date()
    else:
        proximo = (ahora + timedelta(days=dias_hasta_martes)).date()
    meses = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
    dias_semana = {0: "Lun", 1: "Mar", 2: "Mie", 3: "Jue", 4: "Vie", 5: "Sab", 6: "Dom"}
    dia_sem = dias_semana[proximo.weekday()]
    mes = meses[proximo.month]
    return f"{dia_sem} {proximo.day} {mes}, 11:00am CDMX"


def en_ventana_drop(ahora=None):
    """True de MINUTOS_ANTES_DROP antes a MINUTOS_DESPUES_DROP despues de la
    hora del drop: la aprendida del historial o, sin datos, martes 11am CDMX."""
    zona_mx = timezone(timedelta(hours=-6))
    ahora = ahora or datetime.now(zona_mx)
    if PATRON_DROPS:
        dia, hora = PATRON_DROPS["dia_semana"], PATRON_DROPS["hora"]
    else:
        dia, hora = 1, 11
    for delta in (-1, 0, 1):            # por si la ventana cruza la medianoche
        d = (ahora + timedelta(days=delta)).date()
        if d.weekday() != dia:
            continue
        inicio = datetime(d.year, d.month, d.day, hora, tzinfo=zona_mx)
        if (inicio - timedelta(minutes=MINUTOS_ANTES_DROP) <= ahora
                <= inicio + timedelta(minutes=MINUTOS_DESPUES_DROP)):
            return True
    return False


def formato_precio(precio_usd):
    if precio_usd is None: return "Precio N/D"
    return f"MXN ${usd_a_mxn_ajustado(precio_usd):,.2f}"


def formato_velocidad(previo):
    """Genera texto de velocidad de agotamiento si hay historial."""
    va = previo.get("veces_agotado", 0) if previo else 0
    prom = previo.get("promedio_agotamiento_min") if previo else None
    if va >= 1 and prom:
        return f"\nHistorial: se agota en promedio {int(prom)} min (agotado {va} veces)"
    elif va >= 1:
        return f"\nAgotado {va} veces anteriormente"
    return ""


def formato_mensaje(producto, tipo, precio_anterior=None, veces_agotado=0, previo=None):
    # Escapado: Telegram rechaza el mensaje entero si un titulo trae "&" o "<"
    # sueltos (ej. "Fast & Furious") con parse_mode=HTML.
    titulo = html.escape(producto.get("title", "Sin titulo"))
    precio = precio_minimo(producto)
    precio_txt = formato_precio(precio)
    handle = producto.get("handle", "")
    url = f"{BASE_URL}/products/{handle}"

    impacto = ""
    if tipo in ("nuevo", "proximamente", "restock", "pocas_unidades", "rebaja"):
        impacto = "\n\n📊 " + evaluar_impacto(producto, veces_agotado)
        impacto += texto_ganancia_neta(producto)

    velocidad = ""
    if tipo in ("restock", "agotado") and previo:
        velocidad = formato_velocidad(previo)

    if tipo == "nuevo":
        etiqueta = "PRODUCTO NUEVO DISPONIBLE"
        cuerpo = f"{titulo}\n\n🟢 {precio_txt}{impacto}"
    elif tipo == "proximamente":
        etiqueta = "PROXIMAMENTE (Coming Soon)"
        fecha_drop = predecir_fecha_drop()
        cuerpo = (f"{titulo}\n\n🟢 {precio_txt}\n\n"
                  f"Producto detectado antes del anuncio oficial.\n"
                  f"📅 Drop probable: {fecha_drop}{impacto}")
    elif tipo == "restock":
        etiqueta = "RESTOCK DISPONIBLE"
        if precio_anterior is not None and precio is not None and precio_anterior != precio:
            dif = usd_a_mxn(abs(precio - precio_anterior))
            cambio = f"📈 Subio MXN ${dif:,.2f}" if precio > precio_anterior else f"📉 Bajo MXN ${dif:,.2f}"
            cuerpo = (f"{titulo}\n\n🔴 Antes: <s>{formato_precio(precio_anterior)}</s>\n"
                      f"🟢 Ahora: {precio_txt}\n{cambio}{velocidad}{impacto}")
        else:
            cuerpo = f"{titulo}\n\n🟢 {precio_txt}{velocidad}{impacto}"
    elif tipo == "pocas_unidades":
        etiqueta = "POCAS UNIDADES — COMPRA RAPIDO"
        cuerpo = f"{titulo}\n\n🟢 {precio_txt}\n\nEl inventario esta por agotarse.{impacto}"
    elif tipo == "agotado":
        etiqueta = "AGOTADO"
        tiempo_txt = ""
        if previo and previo.get("timestamp_disponible"):
            try:
                ts_disp = datetime.fromisoformat(previo["timestamp_disponible"].replace("Z", "+00:00"))
                minutos = int((datetime.now(timezone.utc) - ts_disp).total_seconds() / 60)
                if minutos > 0:
                    tiempo_txt = f"\nSe agoto en {minutos} minutos"
            except Exception:
                pass
        cuerpo = f"{titulo}\n\n🔴 {precio_txt}\n\nEste producto se ha agotado.{tiempo_txt}{velocidad}"
    elif tipo == "cambio_precio":
        etiqueta = "CAMBIO DE PRECIO"
        dif = usd_a_mxn(abs(precio - precio_anterior))
        cambio = f"📈 Subio MXN ${dif:,.2f}" if precio > precio_anterior else f"📉 Bajo MXN ${dif:,.2f}"
        cuerpo = (f"{titulo}\n\n🔴 Antes: <s>{formato_precio(precio_anterior)}</s>\n"
                  f"🟢 Ahora: {precio_txt}\n{cambio}")
    elif tipo == "rebaja":
        etiqueta = "EN REBAJA / LIQUIDACION"
        if precio_anterior is not None and precio is not None and precio_anterior != precio:
            dif = usd_a_mxn(abs(precio - precio_anterior))
            cuerpo = (f"{titulo}\n\n🔴 Antes: <s>{formato_precio(precio_anterior)}</s>\n"
                      f"🟢 Ahora: {precio_txt}\n📉 Bajo MXN ${dif:,.2f}{impacto}")
        else:
            cuerpo = f"{titulo}\n\n🟢 {precio_txt}\n\nMattel lo marco en rebaja.{impacto}"
    else:
        etiqueta = tipo.upper()
        cuerpo = f"{titulo}\n\n🟢 {precio_txt}"

    # Si el auto esta en tu lista de deseados, el mensaje lo grita.
    titulo_crudo = producto.get("title", "")
    if EX and DESEADOS and EX.es_deseado(titulo_crudo, DESEADOS):
        cual = EX.coincidencia_deseada(titulo_crudo, DESEADOS)
        etiqueta = f"DE TU LISTA ({html.escape(str(cual))}) — " + etiqueta

    return f"<b>{etiqueta}</b>\n\n{cuerpo}\n\n{url}"


# ============================================================
# RESUMEN DIARIO
# ============================================================

def enviar_resumen_diario(estado):
    """Envia resumen del dia a las 10pm CDMX."""
    zona_mx = timezone(timedelta(hours=-6))
    ahora = datetime.now(zona_mx)
    hoy = ahora.strftime("%Y-%m-%d")

    # Solo enviar si es la hora del resumen y no se ha enviado hoy
    if ahora.hour != HORA_RESUMEN_DIARIO:
        return
    if estado.get("ultimo_resumen") == hoy:
        return

    stats = estado.get("stats_hoy", {})
    if stats.get("fecha") != hoy:
        # No hay datos de hoy, crear stats vacios para enviar resumen de todas formas
        stats = {"fecha": hoy, "nuevos": 0, "restocks": 0,
                 "proximamente": 0, "agotados": 0,
                 "cambios_precio": 0, "pocas_unidades": 0,
                 "rebajas": 0, "agotamientos_rapidos": []}
        estado["stats_hoy"] = stats

    productos = estado.get("productos", {})
    total = len(productos)
    disponibles = sum(1 for p in productos.values() if p.get("disponible"))
    agotados_total = sum(1 for p in productos.values() if not p.get("disponible"))

    # Agotamientos mas rapidos del dia
    rapidos = stats.get("agotamientos_rapidos", [])
    rapidos_txt = ""
    if rapidos:
        rapidos_sorted = sorted(rapidos, key=lambda x: x.get("minutos", 999))[:5]
        lineas = [f"  {r['titulo'][:40]} — {r['minutos']} min" for r in rapidos_sorted]
        rapidos_txt = "\n\nAgotamientos mas rapidos hoy:\n" + "\n".join(lineas)

    # Pocas unidades
    pocas = estado.get("pocas_unidades", [])
    pocas_txt = ""
    if pocas:
        lineas = [f"  {p['titulo'][:40]}" for p in pocas[:5]]
        pocas_txt = "\n\nProductos con pocas unidades:\n" + "\n".join(lineas)

    mensaje = (
        f"<b>RESUMEN DEL DIA — {ahora.strftime('%d %b %Y')}</b>\n\n"
        f"Productos monitoreados: {total}\n"
        f"Disponibles: {disponibles}\n"
        f"Agotados: {agotados_total}\n"
        f"Colecciones vigiladas: {len(COLECCIONES)}\n\n"
        f"Cambios hoy:\n"
        f"  {stats.get('nuevos', 0)} nuevos\n"
        f"  {stats.get('restocks', 0)} restocks\n"
        f"  {stats.get('proximamente', 0)} proximamente\n"
        f"  {stats.get('agotados', 0)} agotados\n"
        f"  {stats.get('cambios_precio', 0)} cambios de precio\n"
        f"  {stats.get('rebajas', 0)} rebajas/liquidaciones\n"
        f"  {stats.get('pocas_unidades', 0)} pocas unidades"
        f"{rapidos_txt}"
        f"{pocas_txt}"
        f"\n\nHot Wheels Monitor v4 — {ahora.strftime('%H:%M')} CDMX"
    )

    ok = enviar_telegram_texto(mensaje)
    if ok:
        estado["ultimo_resumen"] = hoy
        print("  Resumen diario enviado")


# ============================================================
# LOGICA PRINCIPAL
# ============================================================

def _ganancia_y_urgencia(producto, previo):
    """Datos extra de la tarjeta del panel: reventa estimada, ganancia neta y
    cuanto suele durar disponible. Todo opcional: si falta un dato (o falla la
    red) la tarjeta simplemente no lo muestra -- nunca frena el aviso."""
    extra = {}
    try:
        prom = previo.get("promedio_agotamiento_min") if previo else None
        if prom:
            extra["agota_min"] = float(prom)
        if EX:
            precio_reventa, ventas = precio_reventa_estimado(producto.get("title", ""))
            if precio_reventa and ventas >= 3:
                g = EX.ganancia_neta(precio_minimo(producto), precio_reventa, TIPO_CAMBIO,
                                     envio_mxn=ENVIO_MXN_ESTIMADO,
                                     impuestos_mxn=AJUSTE_IMPUESTOS_MXN,
                                     comision_pct=COMISION_REVENTA_PCT)
                if g:
                    extra.update(reventa_mxn=g["venta_mxn"], ganancia_mxn=g["ganancia_mxn"],
                                 margen_pct=g["margen_pct"])
    except Exception:
        pass
    return extra


def notificar(estado, producto, tipo, precio_anterior=None, previo=None):
    va = previo.get("veces_agotado", 0) if previo else 0
    titulo = producto.get("title", "")
    disponible_ahora = hay_disponibilidad(producto)

    deseado = bool(EX and EX.es_deseado(titulo, DESEADOS))
    bloqueado = bool(EX and BLOQUEADOS and EX.es_deseado(titulo, BLOQUEADOS))
    link = f"{BASE_URL}/products/{producto.get('handle','')}"
    # El boton de comprar solo aparece si de verdad hay algo que comprar.
    compra = link_carrito(producto) if disponible_ahora else None

    # AVISO EXPRESS: lo urgente sale ya, antes de consultar eBay/ML (que
    # puede tardar 30 s). La pieza se registra en el panel en ese momento
    # para que los botones Comprar/Ignorar funcionen desde el primer aviso.
    hallazgo_id = None
    # Railway con la app de la PC viva: la pieza se anota para que el boton
    # "Comprar con el bot (PC)" funcione (la PC la pide al tocarlo).
    relevo_id = None
    if (MODO_RELEVO and disponible_ahora and tipo in ("nuevo", "restock", "pocas_unidades")
            and pc_app_viva() and not pc_vigilando()):
        precio = precio_minimo(producto)
        relevo_id = guardar_pieza_relevo(
            link, titulo=titulo, url_carrito=compra, imagen=imagen_thumbnail(producto),
            precio_mxn=usd_a_mxn_ajustado(precio) if precio else None, tipo=tipo)
    extra_relevo = {"relevo_id": relevo_id} if relevo_id else {}
    urgente = es_urgente(estado, producto, tipo, deseado, bloqueado, va)
    if urgente:
        if HALLAZGOS is not None:
            precio = precio_minimo(producto)
            hallazgo_id = HALLAZGOS.registrar(
                link, titulo=titulo, url_carrito=compra,
                imagen=imagen_thumbnail(producto),
                precio_mxn=usd_a_mxn_ajustado(precio) if precio else None,
                tipo=tipo, deseado=deseado)
        enviar_express(producto, tipo, link, compra, hallazgo_id, motivo=urgente, **extra_relevo)
        # Mientras lees el aviso, el navegador de compra ya abre la pieza.
        if AL_URGENTE and compra and not MODO_RELEVO:
            try:
                AL_URGENTE(link)
            except Exception as e:
                print(f"    -> no se pudo precalentar: {e}")

    impacto_actual = evaluar_impacto(producto, va) if tipo != "agotado" else None

    # Candado de ruido: "agotado" nunca se silencia (es corto e informativo)
    # y nada de tu lista de deseados se silencia jamas. Lo bloqueado a
    # proposito no se manda pase lo que pase; lo de "Bajo interes" (sobre
    # todo mercancia: playeras, gorras, tazas) tampoco, salvo que lo quieras.
    if tipo != "agotado" and not deseado and not urgente:
        if bloqueado:
            print(f"  [bloqueado] {tipo.upper()}: {titulo}")
            return
        if impacto_actual == "Bajo interes":
            print(f"  [silenciado, bajo interes] {tipo.upper()}: {titulo}")
            return

    print(f"  {tipo.upper()}: {titulo}")
    mensaje = formato_mensaje(producto, tipo, precio_anterior, va, previo)
    if compra and tipo != "agotado" and not MODO_RELEVO:
        mensaje += "\n\n<i>Decide en el panel o con los botones: " + URL_PANEL + "</i>"

    # Registro en el bot (proyecto fusionado): la pieza queda en la lista
    # "Piezas encontradas" del panel para que el usuario decida si comprarla.
    # El monitor NUNCA compra ni dispara compras: solo informa y registra.
    if HALLAZGOS is not None:
        if tipo == "agotado":
            HALLAZGOS.marcar_agotado(link)
        elif hallazgo_id:
            # Ya la registro el express: solo se completan los datos lentos.
            HALLAZGOS.completar(hallazgo_id, impacto=impacto_actual,
                                **_ganancia_y_urgencia(producto, previo))
        elif disponible_ahora and tipo in ("nuevo", "restock", "pocas_unidades"):
            precio = precio_minimo(producto)
            extra = _ganancia_y_urgencia(producto, previo)
            hallazgo_id = HALLAZGOS.registrar(
                link, titulo=titulo, url_carrito=compra,
                imagen=imagen_thumbnail(producto),
                precio_mxn=usd_a_mxn_ajustado(precio) if precio else None,
                tipo=tipo, impacto=impacto_actual, deseado=deseado, **extra)

    enviar_telegram(mensaje, imagen_principal(producto), link, compra, hallazgo_id=hallazgo_id,
                    **extra_relevo)
    agregar_alerta(estado, producto, tipo, precio_anterior, va)

    # Historial: cada aviso queda guardado para poder analizarlo despues.
    if EX and HISTORIAL is not None:
        precio = precio_minimo(producto)
        EX.registrar_evento(
            HISTORIAL, tipo, producto,
            precio_usd=precio,
            precio_mxn=usd_a_mxn_ajustado(precio) if precio else None,
            impacto=impacto_actual,
            deseado=deseado)


def _procesar_producto(estado, p, productos_previos, nuevo_catalogo,
                       pocas_unidades_lista, stats, en_calentamiento):
    """Procesa UN producto: actualiza el catalogo y notifica si corresponde.

    Mutar en sitio: nuevo_catalogo, pocas_unidades_lista, stats y estado son
    objetos compartidos que esta funcion modifica directamente. Se extrajo del
    bucle para poder aislarlo con try/except sin reindentar todo el codigo.
    """
    pid = str(p["id"])
    disponible = hay_disponibilidad(p)
    coming_soon = es_coming_soon(p)
    pocas = es_pocas_unidades(p)
    en_rebaja_ahora = es_en_rebaja(p)
    precio_actual = precio_minimo(p)
    previo = productos_previos.get(pid)

    # IMPORTANTE: el producto se registra en el catalogo ANTES de notificar.
    # Asi, aunque la notificacion fallara, el producto ya quedo "visto" y no
    # se vuelve a anunciar en el siguiente ciclo.
    nuevo_catalogo[pid] = {
        "titulo": p.get("title"),
        "disponible": disponible,
        "coming_soon": coming_soon,
        "pocas_unidades": pocas,
        "en_rebaja": en_rebaja_ahora,
        "precio": precio_actual,
        "imagen": imagen_thumbnail(p),
        "handle": p.get("handle", ""),
        "veces_agotado": (previo.get("veces_agotado", 0) if previo else 0),
        "promedio_agotamiento_min": (previo.get("promedio_agotamiento_min") if previo else None),
        "timestamp_disponible": (previo.get("timestamp_disponible") if previo else None),
    }

    # Vigilancia: lo que puede prender en cualquier momento se sigue de cerca
    # en el ciclo rapido. En cuanto ya esta disponible, sale de la lista.
    if coming_soon:
        marcar_vigilancia(estado, p, "coming_soon")
    elif not disponible and previo and previo.get("veces_agotado", 0) >= 1:
        marcar_vigilancia(estado, p, "restock")
    elif disponible:
        quitar_vigilancia(estado, p)

    # Marcar timestamp cuando se vuelve disponible
    if disponible and (not previo or not previo.get("disponible")):
        nuevo_catalogo[pid]["timestamp_disponible"] = datetime.now(timezone.utc).isoformat()

    # En el ciclo rapido llega None: no se rearma la lista con datos parciales
    # y de paso no se consulta eBay cada 15 segundos.
    if disponible and pocas and pocas_unidades_lista is not None:
        pocas_unidades_lista.append({
            "titulo": p.get("title"),
            "precio_usd": precio_actual,
            "precio_mxn": usd_a_mxn_ajustado(precio_actual) if precio_actual else None,
            "imagen": imagen_thumbnail(p),
            "url": f"{BASE_URL}/products/{p.get('handle', '')}",
            "impacto": evaluar_impacto(p, previo.get("veces_agotado", 0) if previo else 0),
        })

    # Calentamiento: notificar productos recientes
    if en_calentamiento:
        if previo is None:
            fecha_pub = p.get("published_at") or p.get("created_at") or ""
            try:
                fecha = datetime.fromisoformat(fecha_pub.replace("Z", "+00:00"))
                es_nuevo = (datetime.now(timezone.utc) - fecha) < timedelta(hours=48)
            except Exception:
                es_nuevo = False
            if es_nuevo:
                # Antes esto mandaba directo por Telegram, sin pasar por
                # notificar(): se saltaba el candado de ruido, el historial
                # y el aviso al bot de compra. Ahora es el mismo camino que
                # el resto de avisos, solo que marcado "(calentamiento)".
                notificar(estado, p, "nuevo" if disponible else "proximamente")
        return

    if not cumple_filtro(p):
        return

    precio_anterior = previo.get("precio") if previo else None
    notif_key = f"{pid}:{p.get('title','')}"

    # --- Pocas unidades ---
    if previo and disponible and pocas and not previo.get("pocas_unidades"):
        if not ya_notificado(f"pocas:{notif_key}"):
            notificar(estado, p, "pocas_unidades", previo=previo)
            stats["pocas_unidades"] += 1

    # --- Agotado ---
    elif previo and previo.get("disponible") and not disponible and not coming_soon:
        if not ya_notificado(f"agotado:{notif_key}"):
            # Se agoto de verdad: el siguiente restock se avisa aunque no
            # hayan pasado los 15 minutos del candado.
            rearmar_aviso(f"restock:{notif_key}", f"disponible:{notif_key}",
                          f"pocas:{notif_key}")
            va_nuevo = previo.get("veces_agotado", 0) + 1
            nuevo_catalogo[pid]["veces_agotado"] = va_nuevo

            # Calcular velocidad de agotamiento
            minutos_agotamiento = None
            if previo.get("timestamp_disponible"):
                try:
                    ts_disp = datetime.fromisoformat(previo["timestamp_disponible"].replace("Z", "+00:00"))
                    minutos_agotamiento = int((datetime.now(timezone.utc) - ts_disp).total_seconds() / 60)
                    if minutos_agotamiento > 0:
                        # Actualizar promedio
                        prom_ant = previo.get("promedio_agotamiento_min")
                        va_ant = previo.get("veces_agotado", 0)
                        if prom_ant and va_ant > 0:
                            nuevo_prom = ((prom_ant * va_ant) + minutos_agotamiento) / (va_ant + 1)
                        else:
                            nuevo_prom = minutos_agotamiento
                        nuevo_catalogo[pid]["promedio_agotamiento_min"] = round(nuevo_prom, 1)

                        # Guardar en stats del dia
                        if "stats_hoy" in estado:
                            rapidos = estado["stats_hoy"].get("agotamientos_rapidos", [])
                            rapidos.append({"titulo": p.get("title", "")[:50], "minutos": minutos_agotamiento})
                            estado["stats_hoy"]["agotamientos_rapidos"] = rapidos

                        # Al historial: cuanto duro disponible este auto.
                        if EX and HISTORIAL is not None:
                            EX.registrar_evento(
                                HISTORIAL, "velocidad_agotamiento", p,
                                minutos_agotamiento=minutos_agotamiento,
                                deseado=EX.es_deseado(p.get("title", ""), DESEADOS))
                except Exception:
                    pass

            notificar(estado, p, "agotado", previo=previo)
            stats["agotados"] += 1

    # --- Producto nunca visto ---
    elif previo is None:
        if disponible:
            if not ya_notificado(f"nuevo:{notif_key}"):
                notificar(estado, p, "nuevo")
                stats["nuevos"] += 1
        else:
            if not ya_notificado(f"proximamente:{notif_key}"):
                notificar(estado, p, "proximamente")
                stats["proximamente"] += 1

    # --- Restock ---
    elif not previo.get("disponible") and disponible:
        if not ya_notificado(f"restock:{notif_key}"):
            rearmar_aviso(f"agotado:{notif_key}")   # y el siguiente agotado tambien
            notificar(estado, p, "restock", precio_anterior, previo)
            stats["restocks"] += 1

    # --- Coming Soon -> Disponible ---
    elif previo.get("coming_soon") and not coming_soon and disponible:
        if not ya_notificado(f"disponible:{notif_key}"):
            notificar(estado, p, "nuevo", previo=previo)
            stats["nuevos"] += 1

    # --- Rebaja / liquidacion (la etiqueta que pone Mattel, no un calculo) ---
    elif previo.get("disponible") and disponible and en_rebaja_ahora and not previo.get("en_rebaja"):
        if not ya_notificado(f"rebaja:{notif_key}"):
            notificar(estado, p, "rebaja", precio_anterior, previo)
            stats["rebajas"] += 1

    # --- Cambio de precio ---
    elif previo.get("disponible") and disponible:
        if (precio_anterior is not None and precio_actual is not None
                and precio_anterior != precio_actual):
            notificar(estado, p, "cambio_precio", precio_anterior, previo)
            stats["cambios_precio"] += 1


def revisar(estado, productos=None, parcial=False):
    """Procesa una tanda de productos y avisa lo que cambio.

    parcial=False -> barrido completo de todas las colecciones (cada 2 min).
                     Recalcula totales, pocas unidades y estadisticas.
    parcial=True  -> ciclo rapido: solo llegan unos cuantos productos
                     (new-arrivals + los vigilados). NO se tocan los totales
                     ni la lista de pocas unidades, porque con datos parciales
                     saldrian mal. Los avisos si se mandan igual.

    Devuelve (estado, numero_de_cambios).
    """
    global _TS_ULTIMO_BARRIDO_OK, _REVISIONES_HECHAS, _ULTIMO_BARRIDO_FUE_OK
    hora = datetime.now().strftime('%H:%M:%S')
    if not parcial:
        _ULTIMO_BARRIDO_FUE_OK = False
    revisiones = estado.get("revisiones", 0)
    en_calentamiento = revisiones < REVISIONES_CALENTAMIENTO

    if not parcial:
        if en_calentamiento:
            print(f"\n[{hora}] Calentamiento ({revisiones + 1}/{REVISIONES_CALENTAMIENTO})...")
        else:
            print(f"\n[{hora}] Revisando {len(COLECCIONES)} colecciones...")

    productos_previos = estado.get("productos", {})
    fallaron = []
    if productos is None:
        productos, fallaron = obtener_todos_los_productos(estado)
        print(f"  Total productos unicos: {len(productos)}")

    if not productos:
        if not parcial:
            print("  Sin productos. Reintentando despues.")
        return estado, 0

    # Barrido incompleto (alguna coleccion no contesto o trajo muy poco).
    # Ya calentado, se procesa lo que SI llego: lo que falto conserva su
    # estado anterior, asi que no se inventan agotados ni nuevos, y un
    # restock en otra coleccion no se pierde. En el calentamiento se salta
    # como antes: si no, lo que faltara se anunciaria luego como "nuevo".
    incompleto = (not parcial and (bool(fallaron) or (
        productos_previos and len(productos) < len(productos_previos) * 0.5)))
    if incompleto and en_calentamiento:
        print(f"  Respuesta parcial en calentamiento ({len(productos)} vs "
              f"{len(productos_previos)} esperados). Saltando.")
        return estado, 0
    if incompleto:
        print(f"  Barrido incompleto ({', '.join(fallaron) or 'respuesta corta'}): "
              "se procesa lo que si respondio")

    nuevo_catalogo = dict(productos_previos)
    pocas_unidades_lista = None if parcial else []
    stats = {"nuevos": 0, "restocks": 0, "proximamente": 0,
             "cambios_precio": 0, "pocas_unidades": 0, "agotados": 0,
             "rebajas": 0}

    for p in productos:
        # Cada producto se procesa de forma AISLADA. Si uno falla (titulo raro,
        # dato faltante, etc.), se registra y se sigue con el resto, en lugar de
        # tumbar toda la revision y saltarse el guardado. Antes, un solo error
        # aqui detenia el ciclo entero y dejaba el estado sin persistir.
        try:
            _procesar_producto(estado, p, productos_previos, nuevo_catalogo,
                               pocas_unidades_lista, stats, en_calentamiento)
        except Exception as ex:
            try:
                titulo_err = p.get("title") or p.get("id") or "?"
            except Exception:
                titulo_err = "?"
            print(f"  [producto omitido por error] {titulo_err}: {ex}")
            continue

    estado["productos"] = nuevo_catalogo
    estado["ultima_revision"] = datetime.now(timezone.utc).isoformat()
    limpiar_vigilancia(estado)
    cambios = sum(stats.values())

    if parcial:
        if cambios:
            print(f"  [rapido {hora}] {cambios} cambio(s): "
                  f"{stats['nuevos']} nuevos, {stats['restocks']} restocks, "
                  f"{stats['proximamente']} proximamente, "
                  f"{stats['pocas_unidades']} pocas unidades, "
                  f"{stats['rebajas']} rebajas, "
                  f"{stats['agotados']} agotados")
        return estado, cambios

    # Solo un barrido COMPLETO cuenta como "el monitor esta viendo bien".
    _TS_ULTIMO_BARRIDO_OK = time.monotonic()
    _REVISIONES_HECHAS += 1
    _ULTIMO_BARRIDO_FUE_OK = True

    estado["revisiones"] = revisiones + 1
    if incompleto:
        # Totales y "pocas unidades" saldrian mal con datos parciales.
        return estado, sum(stats.values())
    estado["pocas_unidades"] = pocas_unidades_lista

    total = len(nuevo_catalogo)
    disponibles = sum(1 for p in nuevo_catalogo.values() if p.get("disponible"))
    coming = sum(1 for p in nuevo_catalogo.values() if p.get("coming_soon"))
    estado["stats"] = {
        "total": total, "disponibles": disponibles, "coming_soon": coming,
        "pocas_unidades": len(pocas_unidades_lista),
        "agotados": sum(1 for p in nuevo_catalogo.values()
                        if not p.get("disponible") and not p.get("coming_soon")),
    }

    if en_calentamiento:
        print(f"  Snapshot guardado ({total} productos)")
    else:
        s = stats
        print(f"  Resumen: {s['nuevos']} nuevos, {s['restocks']} restocks, "
              f"{s['proximamente']} proximamente, {s['cambios_precio']} precio, "
              f"{s['rebajas']} rebajas, "
              f"{s['pocas_unidades']} pocas unidades, {s['agotados']} agotados")
        print(f"  Bajo vigilancia: {len(estado.get('vigilancia', {}))} productos")

    return estado, cambios


_ARCHIVO_INSTANCIA = os.path.join(_DIR_DATOS, "monitor.lock")
_INSTANCIA = None   # se guarda el archivo abierto: el candado vive mientras viva el proceso


def _tomar_instancia_unica():
    """Candado de sistema operativo (se libera solo si el proceso muere, sin
    archivos "colgados"): evita dos monitores a la vez -- por ejemplo uno
    lanzado desde Nexus y otro por el supervisor -- que mandarian cada aviso
    duplicado. Devuelve False si ya hay otro monitor corriendo."""
    global _INSTANCIA
    try:
        f = open(_ARCHIVO_INSTANCIA, "a+")
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _INSTANCIA = f
        return True
    except (OSError, IOError):
        return False


def main():
    if not _tomar_instancia_unica():
        print("Ya hay otro monitor corriendo en esta carpeta; este se cierra para no duplicar avisos.")
        return
    print("=" * 60)
    print("  Monitor de Hot Wheels Collectors v5")
    print("  Mattel Creations")
    print("=" * 60)

    if TELEGRAM_BOT_TOKEN == "PEGA_AQUI_TU_TOKEN" or TELEGRAM_CHAT_ID == "PEGA_AQUI_TU_CHAT_ID":
        print("\nERROR: Falta configurar TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return

    global HISTORIAL, DESEADOS, BLOQUEADOS, PATRON_DROPS
    global _TS_ULTIMO_BARRIDO_OK, _TS_ULTIMA_ALERTA_CIEGO
    global COLECCIONES, COLECCIONES_RAPIDAS

    obtener_tipo_cambio()

    # --- Extras: historial, lista de deseados/bloqueados y patron de drops ---
    if EX:
        HISTORIAL = EX.abrir_historial(ARCHIVO_HISTORIAL)
        migrados = EX.migrar_deseados_legacy(ARCHIVO_DESEADOS_LEGACY, ARCHIVO_DESEADOS)
        if migrados:
            print(f"  Lista de deseados migrada de deseados.txt a deseados.json ({migrados} modelos)")
        DESEADOS = EX.cargar_deseados(ARCHIVO_DESEADOS)
        BLOQUEADOS = EX.cargar_deseados(ARCHIVO_BLOQUEADOS)
        PATRON_DROPS = EX.patron_de_drops(HISTORIAL)

        # Que se vigila: la primera vez se siembra con las mismas 5
        # colecciones que estaban en el codigo, para no cambiar nada de lo
        # que ya hacia; de ahi en adelante manda colecciones.json.
        sembradas = EX.sembrar_colecciones(ARCHIVO_COLECCIONES)
        if sembradas:
            print(f"  colecciones.json creado con las {sembradas} colecciones de siempre")
        activas = EX.cargar_colecciones(ARCHIVO_COLECCIONES)
        if activas:
            COLECCIONES = activas
            COLECCIONES_RAPIDAS = (EX.cargar_colecciones(ARCHIVO_COLECCIONES, solo_rapidas=True)
                                   or COLECCIONES_RAPIDAS)
        print(f"  Historial: {'activo' if HISTORIAL else 'no disponible'}")
        print(f"  Lista de deseados: {len(DESEADOS)} modelos")
        print(f"  Lista de bloqueados: {len(BLOQUEADOS)} modelos")
        if PATRON_DROPS:
            print(f"  Drop aprendido: {EX.proximo_drop(PATRON_DROPS)} "
                  f"(confianza {PATRON_DROPS['confianza']:.0%})")
        else:
            print("  Drop aprendido: aun sin datos suficientes (se usa martes 11am)")

    print(f"  Barrido completo cada {INTERVALO_MINUTOS} min ({len(COLECCIONES)} colecciones)")
    for c in COLECCIONES:
        print(f"    - {c}")
    print(f"  Ciclo rapido cada {SEGUNDOS_CICLO_RAPIDO} s: {', '.join(COLECCIONES_RAPIDAS)}")
    print(f"  Francotirador: hasta {MAX_FRANCOTIRADOR} productos vigilados por ciclo (deseados primero)")
    print(f"  Modo drop: ciclo rapido cada {SEGUNDOS_CICLO_DROP} s de {MINUTOS_ANTES_DROP} min antes "
          f"a {MINUTOS_DESPUES_DROP} min despues del drop")
    print(f"  Resumen diario: {HORA_RESUMEN_DIARIO}:00 CDMX")
    if not MODO_RELEVO:
        print(f"  Panel (donde decides que comprar): {URL_PANEL}")
    if MODO_RELEVO:
        print(f"  Modo relevo (Railway): callado mientras la PC mande latido; "
              f"avisa si calla {MINUTOS_RELEVO} min")
    print("  Para detener: Ctrl + C")
    print("=" * 60)

    estado = cargar_estado()
    manuales = sincronizar_vigilados_manuales(estado)
    print(f"  Vigilancia recuperada: {len(estado.get('vigilancia', {}))} productos"
          + (f" ({manuales} agregados a mano desde el tablero)" if manuales else ""))

    # Reloj propio en vez de dormir 2 minutos de golpe: asi el ciclo rapido
    # puede correr muchas veces entre un barrido completo y el siguiente.
    ahora = time.monotonic()
    proximo_completo = ahora            # el primero, de inmediato
    proximo_rapido = ahora + SEGUNDOS_CICLO_RAPIDO
    proximo_refresco = ahora + SEGUNDOS_REFRESCO_DATOS
    proximo_listas = ahora + SEGUNDOS_REFRESCO_LISTAS
    proximo_ml = ahora + 30          # la primera pasada de ML es de calentamiento
    _TS_ULTIMO_BARRIDO_OK = ahora
    _TS_ULTIMA_ALERTA_CIEGO = None
    modo_drop = False

    while True:
        try:
            ahora = time.monotonic()

            # --- Modo drop: en la ventana del drop se acelera el ciclo rapido ---
            drop_ahora = en_ventana_drop()
            if drop_ahora != modo_drop:
                modo_drop = drop_ahora
                print(f"  [drop] {'ENTRA a modo drop: ciclo rapido cada ' + str(SEGUNDOS_CICLO_DROP) + ' s' if modo_drop else 'sale de modo drop'}")
                if modo_drop:
                    proximo_rapido = min(proximo_rapido, ahora)
            seg_rapido = SEGUNDOS_CICLO_DROP if modo_drop else SEGUNDOS_CICLO_RAPIDO

            # --- Refresco periodico de tipo de cambio, eBay, patron y deseados ---
            if ahora >= proximo_refresco:
                obtener_tipo_cambio()
                CACHE_EBAY.clear()
                if EX:
                    EX.limpiar_cache_mercadolibre()
                if EX and HISTORIAL is not None:
                    PATRON_DROPS = EX.patron_de_drops(HISTORIAL)
                proximo_refresco = time.monotonic() + SEGUNDOS_REFRESCO_DATOS

            # --- Recarga de lo que se administra desde el tablero ---
            # Aparte y mucho mas seguido que el refresco de arriba: son 4
            # archivos JSON chicos en disco, sin red. Antes esto vivia en el
            # ciclo de 2 h, lo que hacia inservible un panel de administracion
            # (agregabas una coleccion y no pasaba nada hasta dos horas despues).
            if ahora >= proximo_listas:
                recargar_listas(estado)
                proximo_listas = time.monotonic() + SEGUNDOS_REFRESCO_LISTAS

            # --- Segunda tienda: Mercado Libre ---
            # Va en su propio reloj y no estorba al ciclo rapido de Mattel:
            # un drop de Mattel se gana en segundos, una publicacion de ML no.
            if MINUTOS_MERCADOLIBRE > 0 and ahora >= proximo_ml:
                proximo_ml = time.monotonic() + MINUTOS_MERCADOLIBRE * 60
                try:
                    avisos_ml = revisar_mercadolibre(estado)
                    if avisos_ml:
                        print(f"  [ML] {avisos_ml} aviso(s) de Mercado Libre")
                        guardar_estado(estado)
                except Exception as e:
                    print(f"  Error revisando Mercado Libre: {e}")

            # --- Relevo (solo Railway): tomar o soltar los avisos ---
            revisar_relevo()

            # --- VIGILANTE: el monitor corre pero no ve nada ---
            sin_ver = (time.monotonic() - _TS_ULTIMO_BARRIDO_OK) / 60.0
            if sin_ver > MINUTOS_ALERTA_CIEGO:
                # Se avisa una vez por hora, para no volverse otra molestia.
                if (_TS_ULTIMA_ALERTA_CIEGO is None
                        or (time.monotonic() - _TS_ULTIMA_ALERTA_CIEGO) > 3600):
                    _TS_ULTIMA_ALERTA_CIEGO = time.monotonic()
                    print(f"  [ALERTA] {int(sin_ver)} min sin un barrido bueno")
                    enviar_telegram_texto(
                        "<b>MONITOR CIEGO</b>\n\n"
                        f"Llevo {int(sin_ver)} minutos sin poder leer la tienda.\n"
                        "El servicio sigue corriendo, pero no esta viendo nada. "
                        "Puede ser internet, un bloqueo del sitio o un cambio en la pagina.")

            # Mattel respondio 429: no se le consulta hasta que pase la pausa.
            if time.monotonic() < _PAUSA_HASTA:
                time.sleep(1)
                continue

            # ---------- BARRIDO COMPLETO ----------
            if ahora >= proximo_completo:
                estado, _ = revisar(estado)
                proximo_completo = time.monotonic() + INTERVALO_MINUTOS * 60

                # El resumen diario se aisla: si fallara, NO debe impedir el guardado.
                try:
                    enviar_resumen_diario(estado)
                except Exception as e:
                    print(f"  Error en resumen diario: {e}")

                guardar_estado(estado)
                if EX:
                    EX.latido(ARCHIVO_LATIDO,
                              f"{len(estado.get('productos', {}))} productos")
                # PC: latido a Railway tras cada barrido. monitor_ok dice si
                # de verdad vio la tienda: si no, Railway avisa por ella, pero
                # con el boton de compra que atiende esta PC.
                if AL_BARRIDO_OK:
                    try:
                        AL_BARRIDO_OK(_ULTIMO_BARRIDO_FUE_OK)
                    except Exception as e:
                        print(f"  [relevo] no se pudo mandar el latido: {e}")

            # ---------- CICLO RAPIDO ----------
            elif ahora >= proximo_rapido:
                proximo_rapido = time.monotonic() + seg_rapido
                # Durante el calentamiento no corre: primero hay que tener la
                # foto completa de la tienda, si no avisaria de todo.
                if estado.get("revisiones", 0) >= REVISIONES_CALENTAMIENTO:
                    productos = obtener_productos_rapidos(estado)
                    estado, cambios = revisar(estado, productos, parcial=True)
                    # Solo se guarda si hubo algo: escribir a disco cada 15 s
                    # desgasta la memoria del Raspberry sin necesidad.
                    if cambios:
                        guardar_estado(estado)

        except Exception as e:
            print(f"Error inesperado: {e}")
            # Intento de rescate: aunque algo arriba haya fallado, tratamos de
            # persistir lo que se haya alcanzado a procesar en memoria.
            try:
                guardar_estado(estado)
            except Exception:
                pass

        time.sleep(1)


if __name__ == "__main__":
    main()
