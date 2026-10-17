# collecthub_bridge.py
"""Puente hacia Chicos Wheels (CollectHub): registra ahi cada compra
confirmada de Mattel Creations, para no tener que volver a teclearla a mano.

Chicos Wheels solo tiene JWT de cuenta real (no existe API key de servicio),
asi que este modulo se loguea como una cuenta real (COLLECTHUB_EMAIL /
COLLECTHUB_PASSWORD en .env) y cachea el token en memoria; si una llamada
regresa 401 (token vencido), reloguea una vez y reintenta.

Idempotencia: antes de crear un articulo nuevo revisa la tabla local
registros_collecthub por la misma URL -- si ya quedo registrada con exito
("ok"), no vuelve a crear nada. Cubre tanto el boton "Marcar comprado" del
monitor pulsado dos veces como el caso de que el modo armado y una
confirmacion manual coincidan en el mismo producto.

Nunca lanza una excepcion hacia quien lo llama: si Chicos Wheels no esta
corriendo o falla el login, se guarda el error en registros_collecthub y el
resto del flujo de compra sigue intacto -- mismo patron defensivo que
notify() en bot_logic.py.
"""

import os
import sqlite3
from datetime import date, timedelta

import requests

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

COLLECTHUB_URL = os.environ.get("COLLECTHUB_URL", "http://localhost:3000").rstrip("/")
COLLECTHUB_EMAIL = os.environ.get("COLLECTHUB_EMAIL", "")
COLLECTHUB_PASSWORD = os.environ.get("COLLECTHUB_PASSWORD", "")

_token_cache = {"token": None}

# Desde 2026-10-17 el bot corre dentro de Chicos Wheels (un solo proceso): el 02
# instala aqui una funcion (metodo, ruta, json) -> respuesta que atiende la
# peticion en memoria, sin HTTP ni contraseña. Sin ella (pruebas, o el bot
# suelto) se usa HTTP con login como antes.
EN_PROCESO = None


def configurado():
    return EN_PROCESO is not None or bool(COLLECTHUB_EMAIL and COLLECTHUB_PASSWORD)


def pedir(metodo, ruta, json=None, timeout=10):
    """Llama a la API de Chicos Wheels (en el mismo proceso o por HTTP). Por HTTP,
    si el token vencio reloguea una vez y reintenta."""
    if EN_PROCESO is not None:
        return EN_PROCESO(metodo, ruta, json)
    token = _token()
    if not token:
        raise RuntimeError("no se pudo obtener token de sesión de Chicos Wheels")
    r = requests.request(metodo, COLLECTHUB_URL + ruta, json=json,
                         headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    if r.status_code == 401:
        _token_cache["token"] = None
        token = _login()
        if not token:
            raise RuntimeError("el token venció y no se pudo renovar (revisa la contraseña)")
        r = requests.request(metodo, COLLECTHUB_URL + ruta, json=json,
                             headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    return r


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS registros_collecthub (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    titulo TEXT,
                    precio_mxn REAL,
                    origen TEXT,
                    articulo_id_remoto TEXT,
                    resultado TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )""")
    # Columnas agregadas después (cantidad y resultado del bot, para reintentar y anotar).
    cols = {r[1] for r in c.execute("PRAGMA table_info(registros_collecthub)")}
    for col, tipo in (("cantidad", "INTEGER DEFAULT 1"), ("pedido", "TEXT"), ("intentos", "INTEGER DEFAULT 0")):
        if col not in cols:
            c.execute(f"ALTER TABLE registros_collecthub ADD COLUMN {col} {tipo}")
    conn.commit()
    conn.close()


def _datos_hallazgo(url):
    """Foto, precio de reventa y ganancia que el monitor ya guardó de esta pieza."""
    try:
        conn = sqlite3.connect(DB)
        fila = conn.execute("SELECT imagen, reventa_mxn, ganancia_mxn FROM hallazgos WHERE url = ?",
                            (url,)).fetchone()
        conn.close()
        return {"imagen": fila[0], "reventa": fila[1], "ganancia": fila[2]} if fila else {}
    except sqlite3.Error:
        return {}


def _ya_registrado(url):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT resultado FROM registros_collecthub WHERE url = ?", (url,))
    fila = c.fetchone()
    conn.close()
    return bool(fila and fila[0] == "ok")


def _guardar(url, titulo, precio_mxn, origen, articulo_id_remoto, resultado, cantidad=1, pedido=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""INSERT INTO registros_collecthub
                 (url, titulo, precio_mxn, origen, articulo_id_remoto, resultado, cantidad, pedido, intentos)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                 ON CONFLICT(url) DO UPDATE SET
                   titulo=excluded.titulo, precio_mxn=excluded.precio_mxn,
                   origen=excluded.origen, articulo_id_remoto=excluded.articulo_id_remoto,
                   resultado=excluded.resultado, cantidad=excluded.cantidad,
                   pedido=COALESCE(excluded.pedido, pedido),
                   intentos=COALESCE(intentos,0)+1, created_at=datetime('now','localtime')""",
              (url, titulo, precio_mxn, origen, articulo_id_remoto, resultado, cantidad, pedido))
    conn.commit()
    conn.close()


def ultimos(n=10):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""SELECT url, titulo, precio_mxn, origen, resultado, created_at
                 FROM registros_collecthub ORDER BY id DESC LIMIT ?""", (n,))
    filas = [{"url": r[0], "titulo": r[1], "precio_mxn": r[2], "origen": r[3],
              "resultado": r[4], "created_at": r[5]} for r in c.fetchall()]
    conn.close()
    return filas


def _login():
    if not COLLECTHUB_EMAIL or not COLLECTHUB_PASSWORD:
        return None
    r = requests.post(f"{COLLECTHUB_URL}/api/auth/login",
                       json={"email": COLLECTHUB_EMAIL, "password": COLLECTHUB_PASSWORD},
                       timeout=10)
    r.raise_for_status()
    token = r.json().get("token")
    _token_cache["token"] = token
    return token


def _token():
    return _token_cache["token"] or _login()


def _datos_mattel(url):
    """Nombre, precio en MXN y foto desde el link (lo resuelve Chicos Wheels con
    su lector de Mattel, que ya entiende /en-mx/). {} si algo falla."""
    try:
        r = pedir("POST", "/api/articulos/desde-mattel", {"url": url}, timeout=15)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def registrar_compra(url, titulo=None, precio_mxn=None, imagen=None, origen="manual",
                     cantidad=1, pedido=None):
    """Da de alta la pieza comprada en Chicos Wheels. Devuelve (ok, mensaje);
    nunca lanza excepcion."""
    url = (url or "").strip()
    if not url:
        return False, "falta la url del producto"
    if _ya_registrado(url):
        return True, "ya estaba registrado en Chicos Wheels"

    try:
        precio = float(precio_mxn) if precio_mxn is not None else 0.0
    except (TypeError, ValueError):
        precio = 0.0

    try:
        cantidad = max(1, int(cantidad or 1))
    except (TypeError, ValueError):
        cantidad = 1
    extra = _datos_hallazgo(url)
    imagen = imagen or extra.get("imagen")
    reventa = extra.get("reventa") or 0
    if not configurado():
        mensaje = "falta configurar COLLECTHUB_EMAIL/COLLECTHUB_PASSWORD en .env"
        _guardar(url, titulo, precio, origen, None, mensaje, cantidad, pedido)
        return False, mensaje

    # "Mis links" no guarda nombre ni precio: se completan desde Mattel.
    m = {}
    if (not titulo or not precio) and "mattel.com" in url:
        m = _datos_mattel(url)
        titulo = titulo or m.get("nombre")
        precio = precio or float(m.get("precio_mxn") or 0)
        imagen = imagen or m.get("imagen")

    fuente = "Mattel Creations"  # el origen (panel/manual) queda en las notas
    body = {
        # Categoría propia de Chicos Wheels (existe desde 2026-09-29); si la
        # cuenta la borró, el alta se reintenta como Hot Wheels.
        "tipo": "Barbie" if "barbie" in f"{titulo or ''} {m.get('linea', '')}".lower() else "Hot Wheels",
        "nombre": (titulo or "Hot Wheels sin título")[:160],
        "precio_compra": precio,
        # Valor de mercado: la reventa que estimó el monitor; si no hay, lo pagado.
        "valor_estimado": reventa if reventa > 0 else precio,
        "cantidad": cantidad,
        "ubicacion": "Por recibir",
        "fecha_adq": date.today().isoformat(),
        # Llega aprox. en 14 días (envío de Mattel); se corrige en "Por llegar".
        "fecha_llegada": (date.today() + timedelta(days=14)).isoformat(),
        "fuente": fuente[:60],
        "notas": "\n".join(x for x in (f"Link original: {url}",
                                        f"Resultado del bot: {pedido}" if pedido else "",
                                        "Llega por paquetería: cambia la ubicación al recibirla.") if x)[:1000],
        "foto": (imagen or "")[:500],
        "estatus": "Disponible",
    }

    try:
        resp = pedir("POST", "/api/articulos", body)
        if resp.status_code == 400 and body["tipo"] != "Hot Wheels":
            body["tipo"] = "Hot Wheels"
            resp = pedir("POST", "/api/articulos", body)
        resp.raise_for_status()
        articulo = resp.json()
        _guardar(url, titulo, precio, origen, articulo.get("id"), "ok", cantidad, pedido)
        return True, f"registrado en Chicos Wheels (id {articulo.get('id')})"
    except Exception as e:
        mensaje = f"no se pudo registrar en Chicos Wheels: {e}"
        _guardar(url, titulo, precio, origen, None, mensaje, cantidad, pedido)
        return False, mensaje


def reintentar_pendientes(maximo=20):
    """Cola de reintentos: los registros que fallaron (Chicos Wheels apagado, token, red)
    se vuelven a intentar. Devuelve cuántos quedaron registrados."""
    if not configurado():
        return 0
    conn = sqlite3.connect(DB)
    filas = conn.execute("""SELECT url, titulo, precio_mxn, origen, COALESCE(cantidad,1), pedido
                            FROM registros_collecthub WHERE resultado != 'ok'
                            ORDER BY id LIMIT ?""", (maximo,)).fetchall()
    conn.close()
    logrados = 0
    for url, titulo, precio, origen, cant, pedido in filas:
        ok, msg = registrar_compra(url, titulo, precio, None, origen, cant, pedido)
        if ok:
            logrados += 1
        elif "onnect" in msg:
            break  # Chicos Wheels sigue apagado: no insistir con el resto
    return logrados


def reporte_semanal_pdf(dias=7):
    """PDF de Chicos Wheels (resumen + ventas de la última semana) o None si no se pudo."""
    from datetime import timedelta
    try:
        if not configurado():
            return None
        cfg = {"titulo": "Reporte semanal", "secciones": ["resumen", "ventas", "apartados"],
               "desde": (date.today() - timedelta(days=dias)).isoformat(), "orientacion": "vertical"}
        r = pedir("POST", "/api/reporte-pdf", cfg, timeout=30)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"⚠️ No se pudo pedir el reporte semanal a Chicos Wheels: {e}")
        return None


def apartados_por_vencer(dias=1):
    """Apartados vigentes de Chicos Wheels cuyo límite es hoy, mañana (o ya pasó).
    Devuelve una lista de textos listos para avisar, o [] (también si la app está apagada)."""
    from datetime import timedelta
    try:
        if not configurado():
            return []
        r = pedir("GET", "/api/estado", timeout=15)
        r.raise_for_status()
        datos = r.json()
    except Exception as e:
        print(f"⚠️ No se pudieron revisar los apartados de Chicos Wheels: {e}")
        return []
    limite = (date.today() + timedelta(days=dias)).isoformat()
    clientes = {c["id"]: c for c in datos.get("compradores", [])}
    avisos = []
    for x in datos.get("apartados", []):
        if x.get("estatus") != "Vigente" or not x.get("fecha_limite") or x["fecha_limite"] > limite:
            continue
        c = clientes.get(x.get("comprador_id")) or {}
        resta = (x.get("precio_acordado") or 0) - (x.get("anticipo") or 0)
        cuando = "HOY" if x["fecha_limite"] == date.today().isoformat() else (
            "vencido" if x["fecha_limite"] < date.today().isoformat() else "mañana")
        avisos.append(f"⏳ {x['nombre_snap']} — {c.get('nombre', 'cliente')}"
                      f"{' (' + c['tel'] + ')' if c.get('tel') else ''}: vence {cuando}, "
                      f"resta ${resta:,.2f}")
    return avisos
