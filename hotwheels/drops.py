# -*- coding: utf-8 -*-
"""
Calendario de drops (2026-11-10).

Mattel pone la hora del lanzamiento en la pagina de la pieza ("Launches
November 10, 2026 9:00 am PT" y data-coming-soon-date="November 10 2026,
09:00:30 PST"). Antes el disparo se programaba a mano y el monitor no
siempre sabia que una pieza era "Coming Soon" (el Challenger RLC no traia la
etiqueta). Aqui:

  1. leer_lanzamiento(html): saca la fecha y hora (UTC) de la pagina.
  2. La tabla `drops` (en bot.db) guarda cada lanzamiento detectado:
     propuesto -> programado (Gonza toco "Programar disparo") -> hecho,
     o descartado.
  3. Cada drop programado lleva su agenda: chequeo a -30 min, aviso de CVV a
     -5, navegador listo a -2 y disparo en el minuto exacto (dashboard_bot).

Fechas en UTC en la base; la hora local solo para mostrar y disparar.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

_ZONAS = {"PST": -8, "PDT": -7, "PT": None, "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
          "MST": -7, "MDT": -6, "UTC": 0, "GMT": 0}
_MESES = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def _es_horario_verano_eeuu(fecha):
    """DST de EE.UU.: del segundo domingo de marzo al primer domingo de noviembre."""
    def domingo(n, mes):
        d = datetime(fecha.year, mes, 1)
        primero = d + timedelta(days=(6 - d.weekday()) % 7)
        return primero + timedelta(weeks=n - 1)
    inicio = domingo(2, 3).replace(hour=2)
    fin = domingo(1, 11).replace(hour=2)
    return inicio <= fecha < fin


def _a_utc(anio, mes, dia, hora, minuto, segundo, zona):
    local = datetime(anio, mes, dia, hora, minuto, segundo)
    zona = (zona or "PT").upper()
    offset = _ZONAS.get(zona)
    if offset is None:  # "PT" sin decir si es verano o invierno
        offset = -7 if _es_horario_verano_eeuu(local) else -8
    return (local - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def leer_lanzamiento(html):
    """datetime UTC del lanzamiento que anuncia la pagina, o None."""
    if not html:
        return None
    # 1) El texto visible de la pieza principal: "Launches November 10, 2026 9:00 am PT"
    m = re.search(r"Launches\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([ap]m)\s*([A-Z]{2,3})?",
                  html, re.I)
    if m and _MESES.get(m.group(1).lower()):
        hora = int(m.group(4)) % 12 + (12 if m.group(6).lower() == "pm" else 0)
        try:
            return _a_utc(int(m.group(3)), _MESES[m.group(1).lower()], int(m.group(2)),
                          hora, int(m.group(5)), 0, m.group(7) or "PT")
        except ValueError:
            pass
    # 2) El atributo fijo (puede repetirse en piezas relacionadas: va despues): "November 10 2026, 09:00:30 PST"
    for m in re.finditer(r'data-coming-soon-date="([A-Za-z]+) (\d{1,2}) (\d{4}), '
                         r'(\d{1,2}):(\d{2})(?::(\d{2}))? ([A-Z]{2,3})"', html):
        mes = _MESES.get(m.group(1).lower())
        if mes:
            try:
                return _a_utc(int(m.group(3)), mes, int(m.group(2)), int(m.group(4)),
                              int(m.group(5)), int(m.group(6) or 0), m.group(7))
            except ValueError:
                continue
    return None


def es_coming_soon_pagina(html):
    t = (html or "").lower()
    return "coming soon" in t and ("launches" in t or "data-coming-soon=\"true\"" in t)


# --- tabla -----------------------------------------------------------------
def crear_tabla(db):
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS drops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        titulo TEXT,
        cuando_utc TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'propuesto',
        cantidad INTEGER,
        hechos TEXT NOT NULL DEFAULT '',
        creado TEXT NOT NULL,
        UNIQUE(url, cuando_utc))""")
    conn.commit()
    conn.close()


def _fila(r):
    return {"id": r[0], "url": r[1], "titulo": r[2],
            "cuando": datetime.fromisoformat(r[3]), "estado": r[4], "cantidad": r[5],
            "hechos": set(filter(None, (r[6] or "").split(","))), "creado": r[7]}


_COLS = "id, url, titulo, cuando_utc, estado, cantidad, hechos, creado"


def proponer(db, url, titulo, cuando_utc):
    """Registra un lanzamiento. Devuelve (id, es_nuevo)."""
    conn = sqlite3.connect(db)
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO drops (url, titulo, cuando_utc, creado) VALUES (?, ?, ?, ?)",
            (url, titulo, cuando_utc.astimezone(timezone.utc).isoformat(),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        conn.commit()
        if cur.rowcount:
            return cur.lastrowid, True
        r = conn.execute("SELECT id FROM drops WHERE url = ? AND cuando_utc = ?",
                         (url, cuando_utc.astimezone(timezone.utc).isoformat())).fetchone()
        return (r[0] if r else None), False
    finally:
        conn.close()


def obtener(db, drop_id):
    conn = sqlite3.connect(db)
    r = conn.execute("SELECT %s FROM drops WHERE id = ?" % _COLS, (drop_id,)).fetchone()
    conn.close()
    return _fila(r) if r else None


def cambiar_estado(db, drop_id, estado, cantidad=None):
    conn = sqlite3.connect(db)
    if cantidad is not None:
        conn.execute("UPDATE drops SET estado = ?, cantidad = ? WHERE id = ?", (estado, cantidad, drop_id))
    else:
        conn.execute("UPDATE drops SET estado = ? WHERE id = ?", (estado, drop_id))
    conn.commit()
    conn.close()


def marcar_hecho(db, drop_id, paso):
    """Anota que un paso de la agenda (chequeo, cvv, precalentar) ya corrio."""
    d = obtener(db, drop_id)
    if not d or paso in d["hechos"]:
        return False
    conn = sqlite3.connect(db)
    conn.execute("UPDATE drops SET hechos = ? WHERE id = ?",
                 (",".join(sorted(d["hechos"] | {paso})), drop_id))
    conn.commit()
    conn.close()
    return True


def programados(db):
    conn = sqlite3.connect(db)
    filas = conn.execute("SELECT %s FROM drops WHERE estado = 'programado' ORDER BY cuando_utc"
                         % _COLS).fetchall()
    conn.close()
    return [_fila(r) for r in filas]


def proximos(db, limite=20):
    conn = sqlite3.connect(db)
    ahora = datetime.now(timezone.utc).isoformat()
    filas = conn.execute("SELECT %s FROM drops WHERE cuando_utc >= ? AND estado != 'descartado' "
                         "ORDER BY cuando_utc LIMIT ?" % _COLS, (ahora, limite)).fetchall()
    conn.close()
    return [_fila(r) for r in filas]


# --- agenda de un drop programado -------------------------------------------
AGENDA = (("chequeo", 30 * 60), ("cvv", 5 * 60), ("precalentar", 2 * 60 + 30))


def pasos_pendientes(drop, ahora_utc=None):
    """Pasos de la agenda que ya tocan (y no han corrido) y si toca disparar."""
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    faltan = (drop["cuando"] - ahora_utc).total_seconds()
    pasos = [p for p, antes in AGENDA if 0 < faltan <= antes and p not in drop["hechos"]]
    # Se dispara en el minuto del lanzamiento (el evento reintenta 5 min).
    disparar = faltan <= 30 and faltan > -10 * 60
    return pasos, disparar


def hora_local(cuando_utc):
    return cuando_utc.astimezone().strftime("%d/%m %H:%M")
