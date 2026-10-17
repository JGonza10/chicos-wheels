# -*- coding: utf-8 -*-
"""
Extras del Monitor de Hot Wheels v5.

Modulo aparte a proposito: monitor.py sigue siendo el motor y aqui viven las
habilidades nuevas. Todo lo de este archivo es OPCIONAL: monitor.py lo importa
dentro de un try/except, asi que si este archivo falta o truena, el monitor
sigue avisando igual que siempre.

Habilidades que viven aqui:
  1. Configuracion en archivo aparte (saca el token de Telegram del codigo).
  2. Lista de deseados: los autos que si te importan de verdad (y su
     contraparte, la lista de BLOQUEADOS: mismas funciones, otro archivo).
  3. Historial en base de datos (SQLite) de todo lo que ha pasado.
  4. Aprender el dia y la hora reales de los drops a partir de ese historial.
  5. Calculo de ganancia neta en pesos (no solo "impacto").
  6. Latido: dejar rastro de que el monitor sigue vivo y viendo.
  7. Puente con el bot de compra (cola rapida, nunca compra sola).
  8. Precio de reventa en Mercado Libre (ademas de eBay).
  9. Historial de precios por producto, para la mini-grafica del tablero.
 10. Que se vigila: colecciones y productos sueltos, editables desde el tablero.
 11. Ajustes editables desde el tablero (lista blanca, sin secretos).
 12. Mercado Libre como segunda tienda vigilada.
"""

import io
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from datetime import datetime, timezone, timedelta

try:
    import requests
except Exception:
    requests = None

ZONA_MX = timezone(timedelta(hours=-6))


# ============================================================
# 1. CONFIGURACION EN ARCHIVO APARTE
# ============================================================

def cargar_config(ruta):
    """Lee un archivo tipo LLAVE=valor y devuelve un diccionario.

    Sirve para que el token del bot de Telegram NO viva dentro de monitor.py.
    Lineas vacias y las que empiezan con # se ignoran. Las comillas alrededor
    del valor se quitan solas.
    """
    datos = {}
    if not ruta or not os.path.exists(ruta):
        return datos
    try:
        with io.open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                llave, valor = linea.split("=", 1)
                valor = valor.strip()
                if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                    valor = valor[1:-1]
                datos[llave.strip()] = valor
    except Exception:
        return datos
    return datos


def config_num(config, llave, por_defecto):
    """Lee un numero de la configuracion sin tronar si viene mal escrito."""
    try:
        valor = config.get(llave)
        if valor is None or valor == "":
            return por_defecto
        return type(por_defecto)(float(valor))
    except Exception:
        return por_defecto


# ============================================================
# 2. LISTA DE DESEADOS
# ============================================================

def _normalizar(texto):
    """Quita acentos, comillas y dobles espacios para poder comparar bien.
    Asi 'Datsun 510' encuentra tambien a "'71 Datsun 510 Wagon"."""
    texto = (texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("'", " ").replace("`", " ").replace('"', " ")
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def cargar_deseados(ruta):
    """Lee deseados.json: lista de {"texto":..., "categoria":..., "agregado":...}.
    Devuelve solo la lista de textos NORMALIZADOS (para es_deseado/coincidencia_deseada,
    que ya esperaban justo ese formato). Para el detalle completo (con mayusculas,
    categoria y fecha) usa listar_deseados_detalle().
    """
    return [e["texto_normalizado"] for e in listar_deseados_detalle(ruta)]


def listar_deseados_detalle(ruta):
    """Igual que cargar_deseados() pero devuelve las entradas completas tal
    como se guardaron (texto original, categoria, cuando se agrego) — lo que
    necesita el tablero para mostrar/editar la lista."""
    if not ruta or not os.path.exists(ruta):
        return []
    try:
        with io.open(ruta, encoding="utf-8") as f:
            entradas = json.load(f)
        if not isinstance(entradas, list):
            return []
        salida = []
        for e in entradas:
            texto = (e.get("texto") or "").strip()
            n = _normalizar(texto)
            if not n:
                continue
            salida.append({"texto": texto, "texto_normalizado": n,
                           "categoria": e.get("categoria"), "agregado": e.get("agregado")})
        return salida
    except Exception:
        return []


def _guardar_deseados(ruta, entradas):
    """Escritura atomica (mismo patron que guardar_estado() de monitor.py):
    a un temporal y luego os.replace, para que un corte a medias nunca deje
    el archivo truncado."""
    dir_ = os.path.dirname(os.path.abspath(ruta)) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".deseados_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entradas, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise


def agregar_deseado(ruta, texto, categoria=None):
    """Agrega un modelo a deseados.json si no esta ya (comparando normalizado,
    igual que hace es_deseado). Devuelve (True, entrada) si lo agrego, o
    (False, None) si ya existia o el texto vino vacio."""
    texto = (texto or "").strip()
    n = _normalizar(texto)
    if not n:
        return False, None
    entradas_crudas = []
    if os.path.exists(ruta):
        try:
            with io.open(ruta, encoding="utf-8") as f:
                entradas_crudas = json.load(f)
            if not isinstance(entradas_crudas, list):
                entradas_crudas = []
        except Exception:
            entradas_crudas = []
    for e in entradas_crudas:
        if _normalizar(e.get("texto") or "") == n:
            return False, None
    entrada = {"texto": texto, "categoria": categoria,
               "agregado": datetime.now(timezone.utc).isoformat()}
    entradas_crudas.append(entrada)
    _guardar_deseados(ruta, entradas_crudas)
    return True, entrada


def quitar_deseado(ruta, texto):
    """Quita la entrada cuyo texto normalizado coincida. Devuelve True si
    de verdad quito algo, False si no existia."""
    n = _normalizar(texto or "")
    if not n or not os.path.exists(ruta):
        return False
    try:
        with io.open(ruta, encoding="utf-8") as f:
            entradas_crudas = json.load(f)
        if not isinstance(entradas_crudas, list):
            return False
    except Exception:
        return False
    restantes = [e for e in entradas_crudas if _normalizar(e.get("texto") or "") != n]
    if len(restantes) == len(entradas_crudas):
        return False
    _guardar_deseados(ruta, restantes)
    return True


def migrar_deseados_legacy(ruta_txt, ruta_json):
    """Convierte el viejo deseados.txt (un modelo por linea, con comentarios
    '# --- Categoria ---' como separadores) al deseados.json nuevo -- una
    sola vez, y solo si deseados.json todavia no existe. No borra el .txt
    viejo (se deja como referencia historica)."""
    if os.path.exists(ruta_json) or not ruta_txt or not os.path.exists(ruta_txt):
        return 0
    entradas = []
    categoria_actual = None
    try:
        with io.open(ruta_txt, encoding="utf-8") as f:
            for linea_cruda in f:
                linea = linea_cruda.strip()
                if not linea:
                    continue
                if linea.startswith("#"):
                    texto_comentario = linea.lstrip("#").strip().strip("-").strip()
                    if texto_comentario:
                        categoria_actual = texto_comentario
                    continue
                modelo = linea.split("#")[0].strip()
                if modelo:
                    entradas.append({"texto": modelo, "categoria": categoria_actual,
                                     "agregado": None})
    except Exception:
        return 0
    if entradas:
        _guardar_deseados(ruta_json, entradas)
    return len(entradas)


def es_deseado(titulo, deseados):
    """True si el titulo del producto contiene alguno de tus deseados."""
    if not deseados:
        return False
    t = _normalizar(titulo)
    return any(d in t for d in deseados)


def coincidencia_deseada(titulo, deseados):
    """Devuelve cual de tus deseados fue el que coincidio (para el mensaje)."""
    t = _normalizar(titulo)
    for d in deseados:
        if d in t:
            return d
    return None


# ============================================================
# 3. HISTORIAL EN BASE DE DATOS
# ============================================================

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc              TEXT    NOT NULL,
    fecha_mx            TEXT    NOT NULL,
    hora_mx             INTEGER NOT NULL,
    dia_semana          INTEGER NOT NULL,
    tipo                TEXT    NOT NULL,
    producto_id         TEXT,
    handle              TEXT,
    titulo              TEXT,
    precio_usd          REAL,
    precio_mxn          REAL,
    impacto             TEXT,
    minutos_agotamiento INTEGER,
    deseado             INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_eventos_tipo  ON eventos(tipo);
CREATE INDEX IF NOT EXISTS idx_eventos_ts    ON eventos(ts_utc);
CREATE INDEX IF NOT EXISTS idx_eventos_prod  ON eventos(producto_id);
"""


def abrir_historial(ruta):
    """Abre (y crea si no existe) la base de datos del historial.

    Es un solo archivo, no hay que instalar nada. Devuelve None si algo falla,
    y en ese caso el monitor simplemente no guarda historial.
    """
    try:
        conn = sqlite3.connect(ruta, timeout=10)
        conn.executescript(_ESQUEMA)
        conn.commit()
        return conn
    except Exception:
        return None


def registrar_evento(conn, tipo, producto=None, precio_usd=None, precio_mxn=None,
                     impacto=None, minutos_agotamiento=None, deseado=False,
                     titulo=None, producto_id=None, handle=None):
    """Guarda una linea del historial. Nunca truena: si falla, no pasa nada."""
    if conn is None:
        return
    try:
        if producto is not None:
            titulo = titulo or producto.get("title")
            producto_id = producto_id or str(producto.get("id", ""))
            handle = handle or producto.get("handle", "")
        ahora_utc = datetime.now(timezone.utc)
        ahora_mx = ahora_utc.astimezone(ZONA_MX)
        conn.execute(
            "INSERT INTO eventos (ts_utc, fecha_mx, hora_mx, dia_semana, tipo, "
            "producto_id, handle, titulo, precio_usd, precio_mxn, impacto, "
            "minutos_agotamiento, deseado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ahora_utc.isoformat(), ahora_mx.strftime("%Y-%m-%d"), ahora_mx.hour,
             ahora_mx.weekday(), tipo, producto_id, handle, titulo,
             precio_usd, precio_mxn, impacto, minutos_agotamiento,
             1 if deseado else 0))
        conn.commit()
    except Exception:
        pass


def resumen_historial(conn, dias=30):
    """Numeros de los ultimos N dias, para el resumen diario y el dashboard."""
    vacio = {"total": 0, "por_tipo": {}, "mas_rapidos": [], "dias": dias}
    if conn is None:
        return vacio
    try:
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        filas = conn.execute(
            "SELECT tipo, COUNT(*) FROM eventos WHERE ts_utc >= ? GROUP BY tipo",
            (desde,)).fetchall()
        por_tipo = {t: n for t, n in filas}
        rapidos = conn.execute(
            "SELECT titulo, minutos_agotamiento FROM eventos "
            "WHERE ts_utc >= ? AND minutos_agotamiento IS NOT NULL "
            "AND minutos_agotamiento > 0 ORDER BY minutos_agotamiento ASC LIMIT 10",
            (desde,)).fetchall()
        return {"total": sum(por_tipo.values()), "por_tipo": por_tipo,
                "mas_rapidos": [{"titulo": t, "minutos": m} for t, m in rapidos],
                "dias": dias}
    except Exception:
        return vacio


# ============================================================
# 4. APRENDER EL CALENDARIO REAL DE DROPS
# ============================================================

DIAS_NOMBRE = {0: "Lun", 1: "Mar", 2: "Mie", 3: "Jue", 4: "Vie", 5: "Sab", 6: "Dom"}
MESES_NOMBRE = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
                7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}


def patron_de_drops(conn, dias=120, minimo_eventos=8):
    """Busca a que dia y hora caen de verdad los drops, segun lo ya visto.

    En vez de suponer "martes 11am", cuenta cuando aparecieron los productos
    nuevos y devuelve el dia y la hora que mas se repiten. Si todavia no hay
    datos suficientes, devuelve None y el monitor usa la suposicion de antes.
    """
    if conn is None:
        return None
    try:
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        filas = conn.execute(
            "SELECT dia_semana, hora_mx, COUNT(*) AS n FROM eventos "
            "WHERE ts_utc >= ? AND tipo IN ('nuevo', 'proximamente') "
            "GROUP BY dia_semana, hora_mx ORDER BY n DESC", (desde,)).fetchall()
        if not filas:
            return None
        total = sum(f[2] for f in filas)
        dia, hora, n = filas[0]
        # Solo se confia si hay suficientes casos Y si de verdad destaca
        # sobre el resto (al menos 1 de cada 5 apariciones cayo ahi).
        if n < minimo_eventos or (n / float(total)) < 0.20:
            return None
        return {"dia_semana": int(dia), "hora": int(hora), "casos": int(n),
                "total": int(total), "confianza": round(n / float(total), 2)}
    except Exception:
        return None


def proximo_drop(patron):
    """Convierte el patron aprendido en la proxima fecha concreta."""
    if not patron:
        return None
    ahora = datetime.now(ZONA_MX)
    dias = (patron["dia_semana"] - ahora.weekday()) % 7
    if dias == 0 and ahora.hour >= patron["hora"]:
        dias = 7
    fecha = (ahora + timedelta(days=dias)).date()
    return (f"{DIAS_NOMBRE[fecha.weekday()]} {fecha.day} {MESES_NOMBRE[fecha.month]}, "
            f"{patron['hora']:02d}:00 CDMX")


# ============================================================
# 5. GANANCIA NETA (no solo "impacto")
# ============================================================

def ganancia_neta(precio_retail_usd, precio_reventa_usd, tipo_cambio,
                  envio_mxn=250.0, impuestos_mxn=25.0, comision_pct=13.0):
    """Cuanto te queda LIMPIO en pesos si lo compras y lo revendes.

    'Impacto alto' no dice si te conviene: un auto de 25 dolares que se
    revende en 40 suena bien hasta que le restas envio y comision. Esto
    responde la pregunta real.

    Devuelve None si faltan datos para calcularlo.
    """
    if not precio_retail_usd or not precio_reventa_usd or not tipo_cambio:
        return None
    try:
        costo = precio_retail_usd * tipo_cambio + envio_mxn + impuestos_mxn
        venta = precio_reventa_usd * tipo_cambio
        neto = venta - (venta * comision_pct / 100.0) - costo
        return {"costo_mxn": round(costo, 2),
                "venta_mxn": round(venta, 2),
                "ganancia_mxn": round(neto, 2),
                "margen_pct": round((neto / costo) * 100.0, 1) if costo else None}
    except Exception:
        return None


def texto_ganancia(g):
    """Una linea corta para meter en el mensaje de Telegram."""
    if not g:
        return ""
    signo = "Ganas" if g["ganancia_mxn"] >= 0 else "Pierdes"
    return (f"\nGanancia estimada: {signo} MXN ${abs(g['ganancia_mxn']):,.0f} "
            f"({g['margen_pct']:.0f}%) — costo puesto en casa MXN ${g['costo_mxn']:,.0f}")


# ============================================================
# 6. LATIDO (para el vigilante)
# ============================================================

def latido(ruta, extra=""):
    """Deja la hora de la ultima revision buena en un archivo chiquito.

    El vigilante (watchdog_hw.py) lee este archivo desde afuera. Si la hora
    ya esta vieja, quiere decir que el monitor esta trabado o ciego, aunque
    el proceso siga 'vivo' para el sistema.
    """
    try:
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat() + "\n" + str(extra))
    except Exception:
        pass


def leer_latido(ruta):
    """Minutos transcurridos desde el ultimo latido. None si no hay archivo."""
    try:
        with io.open(ruta, encoding="utf-8") as f:
            ts = f.readline().strip()
        cuando = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - cuando).total_seconds() / 60.0
    except Exception:
        return None


# (Seccion 7, puente HTTP con el bot: eliminada al fusionar 15+16 -- el monitor
# registra las piezas directo en la base del bot, ver hallazgos.py.)


# ============================================================
# 8. PRECIO DE REVENTA EN MERCADO LIBRE
# ============================================================
# buscar_ebay() (en monitor.py) da el precio en dolares scrapeando HTML.
# Mercado Libre Mexico tiene una API publica de busqueda (sin autenticacion)
# que ya devuelve precios en MXN -- mas confiable que un regex sobre HTML, y
# no hace falta tipo de cambio para usarlo. Se usa como SEGUNDA fuente de
# precio de reventa, ademas de eBay, no en vez de.

_CACHE_MERCADOLIBRE = {}


def limpiar_cache_mercadolibre():
    _CACHE_MERCADOLIBRE.clear()


MOTIVO_ML_PRECIOS = None   # ultimo motivo por el que ML no dio precios


def buscar_mercadolibre(termino, tag_cache=None, token=None):
    """Precio promedio de reventa en Mercado Libre (sitio MLM), ya en MXN.
    Devuelve (precio_promedio_mxn, cuantos). (None, 0) si no hay suficientes
    resultados o algo falla -- nunca lanza excepcion.

    Desde 2026-09-15 la API exige token (ver seccion 12). Cuando no lo hay,
    esto devolvia (None, 0) sin decir nada y parecia "es que no hay datos":
    ahora el motivo queda en MOTIVO_ML_PRECIOS para que el tablero lo muestre.
    """
    global MOTIVO_ML_PRECIOS
    if requests is None:
        return None, 0
    cache_key = (tag_cache or termino).lower().strip()
    if cache_key in _CACHE_MERCADOLIBRE:
        return _CACHE_MERCADOLIBRE[cache_key]
    datos, motivo = _pedir_ml("/sites/MLM/search",
                              {"q": "hot wheels %s" % termino, "limit": 30}, token)
    MOTIVO_ML_PRECIOS = motivo
    if motivo:
        _CACHE_MERCADOLIBRE[cache_key] = (None, 0)
        return None, 0
    try:
        items = (datos or {}).get("results", []) or []
        precios = [float(it["price"]) for it in items
                  if it.get("price") and 30.0 <= float(it["price"]) <= 16000.0]
        if len(precios) >= 3:
            ordenados = sorted(precios)
            recortados = ordenados[1:-1] if len(ordenados) > 4 else ordenados
            resultado = (round(sum(recortados) / len(recortados), 2), len(recortados))
        elif precios:
            resultado = (round(sum(precios) / len(precios), 2), len(precios))
        else:
            resultado = (None, 0)
    except Exception:
        resultado = (None, 0)
    _CACHE_MERCADOLIBRE[cache_key] = resultado
    return resultado


# ============================================================
# 9. HISTORIAL DE PRECIOS POR PRODUCTO (para la mini-grafica del tablero)
# ============================================================

def historial_precios(conn, titulo, dias=90, maximo=40):
    """Serie (fecha, precio_mxn) de UN producto especifico, del mas viejo al
    mas nuevo -- lo que necesita el tablero para dibujar una mini-grafica de
    tendencia junto a cada alerta. Vacio si no hay historial o datos."""
    if conn is None or not titulo:
        return []
    try:
        desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        filas = conn.execute(
            "SELECT ts_utc, precio_mxn FROM eventos WHERE titulo = ? AND ts_utc >= ? "
            "AND precio_mxn IS NOT NULL ORDER BY ts_utc ASC LIMIT ?",
            (titulo, desde, maximo)).fetchall()
        return [{"ts": ts, "precio_mxn": precio} for ts, precio in filas]
    except Exception:
        return []


# ============================================================
# 10. QUE SE VIGILA: COLECCIONES Y PRODUCTOS SUELTOS
# ============================================================
# Hasta 2026-09-15 la lista de colecciones vivia hardcodeada en monitor.py
# (COLECCIONES) y cambiarla obligaba a editar codigo y reiniciar el servicio.
# Ahora vive en colecciones.json y el monitor la recarga sola en su refresco
# periodico, igual que ya hacia con deseados.json.
#
# Dos archivos distintos, a proposito:
#   - colecciones.json: las vitrinas completas que se barren cada 2 min.
#   - vigilar.json: productos SUELTOS por handle, para cuando Gonza quiere
#     seguir uno exacto (ej. un anuncio de "coming soon" que vio en redes)
#     sin barrer una coleccion entera.
#
# El tablero escribe estos archivos; el monitor solo los lee. Nunca al reves:
# estado.json lo sobreescribe el monitor y el tablero no debe tocarlo.

COLECCIONES_POR_DEFECTO = [
    {"handle": "hot-wheels-collectors", "rapida": False},
    {"handle": "hot-wheels-premium", "rapida": False},
    {"handle": "hot-wheels-red-line-club", "rapida": False},
    {"handle": "hot-wheels-elite-64", "rapida": False},
    {"handle": "new-arrivals", "rapida": True},
]


def _handle_limpio(texto):
    """Acepta un handle suelto o una URL completa de Mattel Creations y
    devuelve solo el handle. Gonza normalmente va a pegar la URL del
    navegador, no el handle: pedirselo a mano seria una friccion tonta."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    if "://" in texto or "creations.mattel.com" in texto:
        texto = texto.split("?")[0].split("#")[0].rstrip("/")
        texto = texto.split("/")[-1]
    texto = texto.strip().lower()
    # Los handles de Shopify son minusculas, numeros y guiones.
    texto = re.sub(r"[^a-z0-9\-]+", "-", texto)
    return re.sub(r"-+", "-", texto).strip("-")


def _leer_lista_json(ruta):
    if not ruta or not os.path.exists(ruta):
        return []
    try:
        with io.open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, list) else []
    except Exception:
        return []


def listar_colecciones(ruta):
    """Entradas completas tal como se guardaron (con activa/rapida/fecha)."""
    salida = []
    for e in _leer_lista_json(ruta):
        handle = _handle_limpio(e.get("handle"))
        if not handle:
            continue
        salida.append({
            "handle": handle,
            "nombre": (e.get("nombre") or handle.replace("-", " ").title()),
            "activa": bool(e.get("activa", True)),
            "rapida": bool(e.get("rapida", False)),
            "agregada": e.get("agregada"),
        })
    return salida


def cargar_colecciones(ruta, solo_rapidas=False):
    """Lo que consume el monitor: lista plana de handles ACTIVOS. Con
    solo_rapidas=True devuelve las del ciclo corto de 15 s."""
    return [c["handle"] for c in listar_colecciones(ruta)
            if c["activa"] and (c["rapida"] or not solo_rapidas)]


def sembrar_colecciones(ruta, por_defecto=None):
    """Crea colecciones.json la primera vez con las 5 que estaban en el
    codigo, para que el cambio no altere en nada lo que se vigila hoy.
    Devuelve cuantas sembro (0 si el archivo ya existia)."""
    if not ruta or os.path.exists(ruta):
        return 0
    entradas = []
    for c in (por_defecto or COLECCIONES_POR_DEFECTO):
        entradas.append({
            "handle": c["handle"],
            "nombre": c["handle"].replace("-", " ").title(),
            "activa": True,
            "rapida": bool(c.get("rapida")),
            "agregada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    _guardar_deseados(ruta, entradas)
    return len(entradas)


def agregar_coleccion(ruta, handle, nombre=None, rapida=False):
    """Devuelve (True, entrada) o (False, None) si ya existia o venia vacio."""
    handle = _handle_limpio(handle)
    if not handle:
        return False, None
    entradas = _leer_lista_json(ruta)
    if any(_handle_limpio(e.get("handle")) == handle for e in entradas):
        return False, None
    entrada = {
        "handle": handle,
        "nombre": (nombre or handle.replace("-", " ").title()).strip(),
        "activa": True,
        "rapida": bool(rapida),
        "agregada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entradas.append(entrada)
    _guardar_deseados(ruta, entradas)
    return True, entrada


def quitar_coleccion(ruta, handle):
    handle = _handle_limpio(handle)
    if not handle:
        return False
    entradas = _leer_lista_json(ruta)
    restantes = [e for e in entradas if _handle_limpio(e.get("handle")) != handle]
    if len(restantes) == len(entradas):
        return False
    _guardar_deseados(ruta, restantes)
    return True


def cambiar_coleccion(ruta, handle, activa=None, rapida=None):
    """Prende/apaga una coleccion o la mueve al ciclo rapido, sin borrarla
    (apagar es mejor que borrar: conserva el historial de por que estaba)."""
    handle = _handle_limpio(handle)
    if not handle:
        return False, None
    entradas = _leer_lista_json(ruta)
    cambiada = None
    for e in entradas:
        if _handle_limpio(e.get("handle")) == handle:
            if activa is not None:
                e["activa"] = bool(activa)
            if rapida is not None:
                e["rapida"] = bool(rapida)
            cambiada = e
            break
    if cambiada is None:
        return False, None
    _guardar_deseados(ruta, entradas)
    return True, cambiada


def listar_vigilados(ruta):
    """Productos sueltos que Gonza pidio seguir por handle."""
    salida = []
    for e in _leer_lista_json(ruta):
        handle = _handle_limpio(e.get("handle"))
        if not handle:
            continue
        salida.append({
            "handle": handle,
            "nota": (e.get("nota") or "").strip(),
            "agregado": e.get("agregado"),
        })
    return salida


def agregar_vigilado(ruta, handle, nota=None):
    handle = _handle_limpio(handle)
    if not handle:
        return False, None
    entradas = _leer_lista_json(ruta)
    if any(_handle_limpio(e.get("handle")) == handle for e in entradas):
        return False, None
    entrada = {
        "handle": handle,
        "nota": (nota or "").strip(),
        "agregado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entradas.append(entrada)
    _guardar_deseados(ruta, entradas)
    return True, entrada


def quitar_vigilado(ruta, handle):
    handle = _handle_limpio(handle)
    if not handle:
        return False
    entradas = _leer_lista_json(ruta)
    restantes = [e for e in entradas if _handle_limpio(e.get("handle")) != handle]
    if len(restantes) == len(entradas):
        return False
    _guardar_deseados(ruta, restantes)
    return True


# ============================================================
# 11. AJUSTES EDITABLES DESDE EL TABLERO
# ============================================================
# Solo se deja tocar una lista blanca de claves numericas. Los secretos
# (TELEGRAM_BOT_TOKEN, la llave del puente, la contraseña del panel) NUNCA
# entran aqui: un panel web sin contraseña que pueda reescribir el token de
# Telegram es una puerta abierta, y el tablero corre sin contraseña por
# defecto. Quien quiera cambiarlos, edita config.env a mano.

AJUSTES_PERMITIDOS = {
    "SEGUNDOS_CICLO_RAPIDO": {"etiqueta": "Ciclo rápido (segundos)", "min": 5, "max": 300, "default": 15,
                              "ayuda": "Cada cuánto revisa lo urgente entre barrido y barrido."},
    "MAX_FRANCOTIRADOR": {"etiqueta": "Productos vigilados por ciclo", "min": 1, "max": 30, "default": 6,
                          "ayuda": "Cuántos productos bajo vigilancia consulta en cada ciclo rápido."},
    "ENVIO_MXN_ESTIMADO": {"etiqueta": "Envío estimado (MXN)", "min": 0, "max": 5000, "default": 250,
                           "ayuda": "Se suma al costo para calcular tu ganancia real."},
    "COMISION_REVENTA_PCT": {"etiqueta": "Comisión de reventa (%)", "min": 0, "max": 50, "default": 13,
                             "ayuda": "Lo que te cobra la plataforma donde revendes."},
    "MINUTOS_ALERTA_CIEGO": {"etiqueta": "Avisar si no ve nada (minutos)", "min": 5, "max": 180, "default": 15,
                             "ayuda": "Tras cuántos minutos sin leer la tienda te avisa MONITOR CIEGO."},
    "MINUTOS_MERCADOLIBRE": {"etiqueta": "Revisar Mercado Libre (minutos)", "min": 0, "max": 240, "default": 10,
                             "ayuda": "Cada cuánto busca tus términos en Mercado Libre. 0 lo apaga."},
    "FALLOS_ALERTA_COLECCION": {"etiqueta": "Avisar si una colección falla (veces)", "min": 2, "max": 20, "default": 3,
                                "ayuda": "Cuántos barridos seguidos debe fallar una colección para avisarte."},
}


def leer_ajustes(ruta_config):
    """Valores actuales de la lista blanca, con su metadato para pintarlos."""
    config = cargar_config(ruta_config)
    salida = []
    for clave, meta in AJUSTES_PERMITIDOS.items():
        salida.append({
            "clave": clave,
            "etiqueta": meta["etiqueta"],
            "ayuda": meta["ayuda"],
            "min": meta["min"],
            "max": meta["max"],
            "default": meta["default"],
            "valor": config.get(clave, ""),
        })
    salida.sort(key=lambda a: a["etiqueta"])
    return salida


def guardar_ajustes(ruta_config, cambios):
    """Reescribe config.env respetando comentarios, orden y claves ajenas.

    Devuelve (guardados, rechazados). Rechaza en silencio cualquier clave
    fuera de la lista blanca y cualquier valor fuera de rango: el archivo
    tambien tiene secretos, y una escritura descuidada aqui deja el monitor
    sin arrancar.
    """
    guardados, rechazados = {}, {}
    for clave, valor in (cambios or {}).items():
        meta = AJUSTES_PERMITIDOS.get(clave)
        if meta is None:
            rechazados[clave] = "no se puede cambiar desde el tablero"
            continue
        try:
            numero = float(str(valor).strip())
        except (TypeError, ValueError):
            rechazados[clave] = "no es un número"
            continue
        if numero < meta["min"] or numero > meta["max"]:
            rechazados[clave] = "fuera de rango (%s a %s)" % (meta["min"], meta["max"])
            continue
        guardados[clave] = ("%g" % numero)
    if not guardados:
        return guardados, rechazados

    lineas = []
    if os.path.exists(ruta_config):
        with io.open(ruta_config, encoding="utf-8") as f:
            lineas = f.read().splitlines()
    pendientes = dict(guardados)
    salida = []
    for linea in lineas:
        limpia = linea.strip()
        if limpia and not limpia.startswith("#") and "=" in limpia:
            clave = limpia.split("=", 1)[0].strip()
            if clave in pendientes:
                salida.append("%s=%s" % (clave, pendientes.pop(clave)))
                continue
        salida.append(linea)
    if pendientes:
        salida.append("")
        salida.append("# Agregadas desde el tablero (%s)"
                      % datetime.now(ZONA_MX).strftime("%Y-%m-%d %H:%M"))
        for clave, valor in pendientes.items():
            salida.append("%s=%s" % (clave, valor))

    dir_ = os.path.dirname(os.path.abspath(ruta_config)) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".config_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(salida) + "\n")
        os.replace(tmp, ruta_config)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise
    return guardados, rechazados


# ============================================================
# 12. MERCADO LIBRE COMO SEGUNDA TIENDA VIGILADA
# ============================================================
# Distinto del uso de la seccion 8: alla se consulta ML para saber a cuanto
# se revende algo; aqui se vigila ML como TIENDA, para enterarse de que
# alguien publico algo que quieres (y a como).
#
# Estado real al 2026-09-15 (comprobado, no supuesto):
#   - api.mercadolibre.com ya NO responde sin autenticacion: devuelve 403
#     "PA_UNAUTHORIZED_RESULT_FROM_POLICIES" incluso para /sites/MLM. Antes si
#     respondia: por eso la seccion 8 (precio de reventa) llevaba tiempo
#     devolviendo (None, 0) en silencio sin que nadie lo notara.
#   - listado.mercadolibre.com.mx tampoco sirve para scrapear: contesta con
#     su pared anti-bot ("suspicious-traffic-frontend"), sin resultados.
#   - Amazon y Walmart estan igual o peor: sin API abierta y con defensas
#     anti-bot; su vigilancia NO se implemento en vez de fingir que funciona.
# Solucion: token de una app de desarrollador de Mercado Libre (gratis, sin
# tarjeta) en MERCADOLIBRE_ACCESS_TOKEN dentro de config.env. Sin token, todo
# esto se apaga solo y lo dice en el tablero, en vez de fallar callado.

MOTIVO_SIN_TOKEN = ("Falta MERCADOLIBRE_ACCESS_TOKEN en config.env "
                    "(app gratuita en developers.mercadolibre.com.mx)")


def _pedir_ml(ruta, params, token, timeout=15):
    """Llamada autenticada a la API de Mercado Libre.

    Devuelve (datos, motivo_de_fallo). Nunca lanza excepcion, y nunca
    devuelve un motivo con el token dentro.
    """
    if requests is None:
        return None, "sin la libreria requests"
    token = (token or "").strip()
    if not token:
        return None, MOTIVO_SIN_TOKEN
    try:
        r = requests.get("https://api.mercadolibre.com" + ruta, params=params,
                         headers={"Authorization": "Bearer %s" % token},
                         timeout=timeout)
        if r.status_code in (401, 403):
            return None, "Mercado Libre rechazó el token (%d): ¿caducó?" % r.status_code
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, "no se pudo consultar Mercado Libre (%s)" % type(e).__name__

def listar_busquedas_ml(ruta):
    salida = []
    for e in _leer_lista_json(ruta):
        termino = (e.get("termino") or "").strip()
        if not termino:
            continue
        salida.append({
            "termino": termino,
            "precio_max": e.get("precio_max"),
            "activa": bool(e.get("activa", True)),
            "agregada": e.get("agregada"),
        })
    return salida


def agregar_busqueda_ml(ruta, termino, precio_max=None):
    termino = (termino or "").strip()
    if not termino:
        return False, None
    entradas = _leer_lista_json(ruta)
    if any(_normalizar(e.get("termino") or "") == _normalizar(termino) for e in entradas):
        return False, None
    try:
        precio_max = float(precio_max) if str(precio_max or "").strip() != "" else None
    except (TypeError, ValueError):
        precio_max = None
    entrada = {
        "termino": termino,
        "precio_max": precio_max,
        "activa": True,
        "agregada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entradas.append(entrada)
    _guardar_deseados(ruta, entradas)
    return True, entrada


def quitar_busqueda_ml(ruta, termino):
    n = _normalizar(termino or "")
    if not n:
        return False
    entradas = _leer_lista_json(ruta)
    restantes = [e for e in entradas if _normalizar(e.get("termino") or "") != n]
    if len(restantes) == len(entradas):
        return False
    _guardar_deseados(ruta, restantes)
    return True


def buscar_listados_ml(termino, token=None, limite=25, condicion="new"):
    """Publicaciones reales de Mercado Libre para un termino.

    Devuelve (listados, motivo). `motivo` es None si todo salio bien, o el
    texto a mostrar en el tablero si no se pudo consultar — a diferencia de
    la seccion 8, aqui el fallo NO es silencioso.
    """
    params = {"q": "hot wheels %s" % termino, "limit": max(1, min(int(limite), 50))}
    if condicion:
        params["condition"] = condicion
    data, motivo = _pedir_ml("/sites/MLM/search", params, token)
    if motivo:
        return [], motivo
    items = (data or {}).get("results", []) or []
    salida = []
    for it in items:
        try:
            precio = float(it.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if precio <= 0:
            continue
        salida.append({
            "id": str(it.get("id") or ""),
            "titulo": (it.get("title") or "").strip(),
            "precio_mxn": round(precio, 2),
            "link": it.get("permalink") or "",
            "imagen": (it.get("thumbnail") or "").replace("http://", "https://"),
            "envio_gratis": bool((it.get("shipping") or {}).get("free_shipping")),
            "condicion": it.get("condition") or "",
        })
    return [s for s in salida if s["id"]], None
