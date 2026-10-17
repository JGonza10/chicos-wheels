# -*- coding: utf-8 -*-
"""
Topes de gasto como GUARDIA DE CONFIRMACION (no como compra automatica).

Cuando el usuario pulsa Comprar y el costo pasa el tope por pieza o el tope
del mes, el panel (o Telegram) le avisa y pide una confirmacion mas fuerte;
nunca bloquea del todo -- la decision sigue siendo suya.
"""

import sqlite3

import hallazgos as H

TOPE_PIEZA_POR_DEFECTO = 1500.0
TOPE_MES_POR_DEFECTO = 6000.0


def _conn(db=None):
    conn = sqlite3.connect(db or H.DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db=None):
    conn = _conn(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS limites (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        tope_pieza_mxn REAL NOT NULL,
                        tope_mensual_mxn REAL NOT NULL
                    )""")
    if conn.execute("SELECT COUNT(*) FROM limites").fetchone()[0] == 0:
        conn.execute("INSERT INTO limites (id, tope_pieza_mxn, tope_mensual_mxn) VALUES (1, ?, ?)",
                     (TOPE_PIEZA_POR_DEFECTO, TOPE_MES_POR_DEFECTO))
    conn.commit()
    conn.close()


def obtener(db=None):
    init_db(db)
    conn = _conn(db)
    f = conn.execute("SELECT tope_pieza_mxn, tope_mensual_mxn FROM limites WHERE id=1").fetchone()
    conn.close()
    return {"tope_pieza_mxn": f["tope_pieza_mxn"], "tope_mensual_mxn": f["tope_mensual_mxn"],
            "gastado_mes_mxn": H.gastado_mes(db)}


def guardar(tope_pieza_mxn, tope_mensual_mxn, db=None):
    """Valida y guarda. Devuelve (ok, mensaje)."""
    try:
        p, m = float(tope_pieza_mxn), float(tope_mensual_mxn)
    except (TypeError, ValueError):
        return False, "los topes deben ser numeros"
    if p <= 0 or m <= 0:
        return False, "los topes deben ser mayores que cero"
    if p > m:
        return False, "el tope por pieza no puede ser mayor que el del mes"
    init_db(db)
    conn = _conn(db)
    conn.execute("UPDATE limites SET tope_pieza_mxn=?, tope_mensual_mxn=? WHERE id=1", (p, m))
    conn.commit()
    conn.close()
    return True, "guardado"


def evaluar(precio_mxn, cantidad=1, db=None):
    """(excede, mensaje). Sin precio conocido no se puede evaluar: no excede."""
    if not precio_mxn:
        return False, ""
    lim = obtener(db)
    costo = float(precio_mxn) * max(1, int(cantidad or 1))
    avisos = []
    if costo > lim["tope_pieza_mxn"]:
        avisos.append("esta compra ($%s) pasa tu tope por pieza ($%s)"
                      % (format(costo, ",.0f"), format(lim["tope_pieza_mxn"], ",.0f")))
    if lim["gastado_mes_mxn"] + costo > lim["tope_mensual_mxn"]:
        avisos.append("con esto llevarías $%s este mes y tu tope mensual es $%s"
                      % (format(lim["gastado_mes_mxn"] + costo, ",.0f"),
                         format(lim["tope_mensual_mxn"], ",.0f")))
    return bool(avisos), "; ".join(avisos)
