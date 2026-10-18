# -*- coding: utf-8 -*-
"""
Piezas encontradas por el monitor, registradas en la base del bot (bot.db).

Flujo del proyecto fusionado: el monitor (monitor.py) busca en Mattel; cuando
aparece algo comprable avisa por Telegram Y lo registra aqui. El usuario ve la
lista en el panel (o en los botones de Telegram) y decide: Comprar (lo hace el
bot), Ignorar o "Ya la compre". Nada se compra solo.

Lo llama monitor.py (proceso aparte) y dashboard_bot.py (Flask): SQLite en
modo WAL con timeout para que puedan escribir a la vez sin estorbarse.
Nunca lanza excepcion hacia el monitor: registrar() devuelve None si falla.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

# Estados: pendiente -> (en_cola) -> comprando -> comprado | carrito | fallo ;
# o ignorado. "en_cola" = el usuario pidio comprarla pero el bot esta ocupado
# con otra; el hilo de la cola (dashboard_bot) la toma en orden.
ESTADOS = ("pendiente", "en_cola", "comprando", "comprado", "carrito", "fallo", "ignorado")
# Una pieza ya cerrada (ignorada/fallida/en carrito) que el monitor vuelve a
# ver disponible tras este tiempo se considera una oportunidad nueva.
MINUTOS_REAPERTURA = 30

# Columnas que se agregaron despues de la primera version (migracion suave).
_COLUMNAS_EXTRA = (
    ("reventa_mxn", "REAL"),      # precio de reventa estimado (eBay/ML), en pesos
    ("ganancia_mxn", "REAL"),     # ganancia neta estimada por pieza
    ("margen_pct", "REAL"),
    ("agota_min", "REAL"),        # minutos que suele durar disponible (historial)
    ("cantidad", "INTEGER"),      # cantidad pedida al comprar
    ("comprado_at", "TEXT"),      # ISO UTC del momento en que quedo comprada
    ("cola_orden", "INTEGER"),    # orden en la cola de compras
)


def _conn(db=None):
    conn = sqlite3.connect(db or DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    return conn


def init_db(db=None):
    conn = _conn(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS hallazgos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL UNIQUE,
                        url_carrito TEXT,
                        titulo TEXT,
                        imagen TEXT,
                        precio_mxn REAL,
                        tipo TEXT,
                        impacto TEXT,
                        deseado INTEGER NOT NULL DEFAULT 0,
                        disponible INTEGER NOT NULL DEFAULT 1,
                        estado TEXT NOT NULL DEFAULT 'pendiente',
                        resultado TEXT,
                        veces_visto INTEGER NOT NULL DEFAULT 1,
                        detectado_at TEXT NOT NULL,
                        ultima_vez TEXT NOT NULL
                    )""")
    existentes = {r[1] for r in conn.execute("PRAGMA table_info(hallazgos)").fetchall()}
    for nombre, tipo in _COLUMNAS_EXTRA:
        if nombre not in existentes:
            conn.execute("ALTER TABLE hallazgos ADD COLUMN %s %s" % (nombre, tipo))
    conn.commit()
    conn.close()


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def registrar(url, titulo=None, url_carrito=None, imagen=None, precio_mxn=None,
              tipo=None, impacto=None, deseado=False, reventa_mxn=None,
              ganancia_mxn=None, margen_pct=None, agota_min=None, db=None):
    """Alta o refresco de una pieza disponible. Devuelve su id (None si falla)."""
    try:
        init_db(db)
        conn = _conn(db)
        ahora = _ahora()
        fila = conn.execute("SELECT * FROM hallazgos WHERE url = ?", (url,)).fetchone()
        if fila is None:
            cur = conn.execute(
                "INSERT INTO hallazgos (url, url_carrito, titulo, imagen, precio_mxn, tipo,"
                " impacto, deseado, disponible, estado, detectado_at, ultima_vez,"
                " reventa_mxn, ganancia_mxn, margen_pct, agota_min)"
                " VALUES (?,?,?,?,?,?,?,?,1,'pendiente',?,?,?,?,?,?)",
                (url, url_carrito, titulo, imagen, precio_mxn, tipo, impacto,
                 1 if deseado else 0, ahora, ahora,
                 reventa_mxn, ganancia_mxn, margen_pct, agota_min))
            nuevo_id = cur.lastrowid
        else:
            nuevo_id = fila["id"]
            estado = fila["estado"]
            try:
                hace = (datetime.now(timezone.utc)
                        - datetime.fromisoformat(fila["ultima_vez"])).total_seconds() / 60.0
            except Exception:
                hace = 0
            # Reaparece tras un rato (o estaba agotada): oportunidad nueva.
            reabre = (estado in ("ignorado", "fallo", "carrito")
                      and (hace >= MINUTOS_REAPERTURA or not fila["disponible"]))
            conn.execute(
                "UPDATE hallazgos SET url_carrito=?, titulo=COALESCE(?,titulo),"
                " imagen=COALESCE(?,imagen), precio_mxn=COALESCE(?,precio_mxn), tipo=?,"
                " impacto=COALESCE(?,impacto), deseado=?, disponible=1,"
                " reventa_mxn=COALESCE(?,reventa_mxn), ganancia_mxn=COALESCE(?,ganancia_mxn),"
                " margen_pct=COALESCE(?,margen_pct), agota_min=COALESCE(?,agota_min),"
                " veces_visto=veces_visto+1, ultima_vez=?,"
                " estado=CASE WHEN ? THEN 'pendiente' ELSE estado END,"
                " detectado_at=CASE WHEN ? THEN ? ELSE detectado_at END WHERE id=?",
                (url_carrito, titulo, imagen, precio_mxn, tipo, impacto,
                 1 if deseado else 0, reventa_mxn, ganancia_mxn, margen_pct, agota_min,
                 ahora, 1 if reabre else 0, 1 if reabre else 0, ahora, nuevo_id))
        conn.commit()
        conn.close()
        return nuevo_id
    except Exception as e:
        print(f"  [hallazgos] no se pudo registrar: {e}")
        return None


def completar(hallazgo_id, impacto=None, reventa_mxn=None, ganancia_mxn=None,
              margen_pct=None, agota_min=None, db=None):
    """Agrega los datos lentos (reventa, ganancia) a una pieza ya registrada
    por el aviso express. No suma veces_visto ni reabre: es la misma vista."""
    if not hallazgo_id:
        return
    try:
        init_db(db)
        conn = _conn(db)
        conn.execute(
            "UPDATE hallazgos SET impacto=COALESCE(?,impacto), reventa_mxn=COALESCE(?,reventa_mxn),"
            " ganancia_mxn=COALESCE(?,ganancia_mxn), margen_pct=COALESCE(?,margen_pct),"
            " agota_min=COALESCE(?,agota_min) WHERE id=?",
            (impacto, reventa_mxn, ganancia_mxn, margen_pct, agota_min, hallazgo_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [hallazgos] no se pudo completar: {e}")


def marcar_agotado(url, db=None):
    """El monitor vio que se agoto: la tarjeta queda como 'Agotada'."""
    try:
        init_db(db)
        conn = _conn(db)
        conn.execute("UPDATE hallazgos SET disponible=0, ultima_vez=? WHERE url=?",
                     (_ahora(), url))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [hallazgos] no se pudo marcar agotado: {e}")


def listar(estados=None, limite=60, db=None):
    init_db(db)
    conn = _conn(db)
    sql = "SELECT * FROM hallazgos"
    params = []
    if estados:
        sql += " WHERE estado IN (%s)" % ",".join("?" * len(estados))
        params = list(estados)
    # Lo disponible y pendiente primero; luego lo mas reciente.
    sql += " ORDER BY (estado='pendiente' AND disponible=1) DESC, detectado_at DESC LIMIT ?"
    params.append(limite)
    filas = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return filas


def obtener(hallazgo_id, db=None):
    init_db(db)
    conn = _conn(db)
    fila = conn.execute("SELECT * FROM hallazgos WHERE id = ?", (hallazgo_id,)).fetchone()
    conn.close()
    return dict(fila) if fila else None


def cambiar_estado(hallazgo_id, estado, resultado=None, db=None):
    if estado not in ESTADOS:
        raise ValueError("estado invalido: %s" % estado)
    init_db(db)
    conn = _conn(db)
    conn.execute(
        "UPDATE hallazgos SET estado=?, resultado=COALESCE(?,resultado),"
        " comprado_at=CASE WHEN ?='comprado' THEN ? ELSE comprado_at END,"
        " cola_orden=CASE WHEN ?='en_cola' THEN cola_orden ELSE NULL END WHERE id=?",
        (estado, resultado, estado, _ahora(), estado, hallazgo_id))
    conn.commit()
    conn.close()


def reservar_compra(hallazgo_id, cantidad=None, db=None):
    """Pasa a 'comprando' solo si NO estaba ya comprando/comprado. Devuelve
    True si este llamado gano la reserva (evita doble clic = doble compra)."""
    init_db(db)
    conn = _conn(db)
    cur = conn.execute(
        "UPDATE hallazgos SET estado='comprando', cola_orden=NULL,"
        " cantidad=COALESCE(?,cantidad) WHERE id=? AND estado NOT IN ('comprando','comprado')",
        (cantidad, hallazgo_id))
    conn.commit()
    ganada = cur.rowcount == 1
    conn.close()
    return ganada


# --- Cola de compras ----------------------------------------------------------

def encolar(hallazgo_id, cantidad=1, db=None):
    """Pone la pieza en la cola (el bot esta ocupado). Devuelve su posicion
    (1 = la siguiente) o None si no se pudo (ya comprando/comprada/no existe)."""
    init_db(db)
    conn = _conn(db)
    fila = conn.execute("SELECT estado FROM hallazgos WHERE id=?", (hallazgo_id,)).fetchone()
    if fila is None or fila["estado"] in ("comprando", "comprado"):
        conn.close()
        return None
    maximo = conn.execute("SELECT COALESCE(MAX(cola_orden),0) FROM hallazgos WHERE estado='en_cola'").fetchone()[0]
    if fila["estado"] != "en_cola":
        conn.execute("UPDATE hallazgos SET estado='en_cola', cola_orden=?, cantidad=? WHERE id=?",
                     (maximo + 1, cantidad, hallazgo_id))
    conn.commit()
    conn.close()
    return posicion_en_cola(hallazgo_id, db=db)


def posicion_en_cola(hallazgo_id, db=None):
    conn = _conn(db)
    fila = conn.execute("SELECT cola_orden FROM hallazgos WHERE id=? AND estado='en_cola'",
                        (hallazgo_id,)).fetchone()
    if fila is None:
        conn.close()
        return None
    n = conn.execute("SELECT COUNT(*) FROM hallazgos WHERE estado='en_cola' AND cola_orden<=?",
                     (fila["cola_orden"],)).fetchone()[0]
    conn.close()
    return n


def siguiente_en_cola(db=None):
    """La pieza que sigue en la cola (dict) o None."""
    init_db(db)
    conn = _conn(db)
    fila = conn.execute("SELECT * FROM hallazgos WHERE estado='en_cola' "
                        "ORDER BY cola_orden ASC, id ASC LIMIT 1").fetchone()
    conn.close()
    return dict(fila) if fila else None


def resumen(dias=30, db=None):
    """Conteo por estado en los ultimos dias (para las cifras del panel)."""
    init_db(db)
    conn = _conn(db)
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    filas = conn.execute(
        "SELECT estado, COUNT(*) n FROM hallazgos WHERE detectado_at >= ? GROUP BY estado",
        (desde,)).fetchall()
    conn.close()
    total = {e: 0 for e in ESTADOS}
    for f in filas:
        total[f["estado"]] = f["n"]
    total["total"] = sum(total[e] for e in ESTADOS)
    return total


# --- Gasto del mes (para los topes de confirmacion) -----------------------------

def gastado_mes(db=None):
    """Suma de lo comprado este mes calendario (hora de Mexico): precio x
    cantidad de cada pieza en estado 'comprado'. Los ensayos nunca llegan a
    'comprado', asi que no cuentan."""
    init_db(db)
    conn = _conn(db)
    ahora = datetime.now(timezone(timedelta(hours=-6)))
    inicio = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    filas = conn.execute(
        "SELECT precio_mxn, COALESCE(cantidad,1) c FROM hallazgos "
        "WHERE estado='comprado' AND comprado_at >= ?", (inicio.isoformat(),)).fetchall()
    conn.close()
    return float(sum((f["precio_mxn"] or 0) * f["c"] for f in filas))
