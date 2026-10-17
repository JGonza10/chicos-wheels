# precios.py
"""Historial de precios por producto.

Se registra cada vez que se obtienen los datos del producto (al agregar una
URL, al refrescar su imagen, o en el test de humo diario de salud.py), para
poder comparar el precio de un drop contra el promedio historico y saber si
es un buen precio o no. Vive en la misma bot.db.
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS precios_historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    precio_mxn REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
    conn.commit()
    conn.close()


def registrar(url, precio_mxn):
    if precio_mxn is None:
        return
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO precios_historial (url, precio_mxn) VALUES (?, ?)",
              (url, precio_mxn))
    conn.commit()
    conn.close()


def historial(url, n=30):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""SELECT precio_mxn, created_at FROM precios_historial
                 WHERE url = ? ORDER BY id DESC LIMIT ?""", (url, n))
    filas = [{"precio_mxn": r[0], "created_at": r[1]} for r in c.fetchall()]
    conn.close()
    return filas


def resumen(url):
    """Promedio/minimo/maximo historico, o None si no hay muestras todavia."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""SELECT AVG(precio_mxn), MIN(precio_mxn), MAX(precio_mxn), COUNT(*)
                 FROM precios_historial WHERE url = ?""", (url,))
    row = c.fetchone()
    conn.close()
    if not row or not row[3]:
        return None
    return {"promedio": row[0], "minimo": row[1], "maximo": row[2], "muestras": row[3]}
