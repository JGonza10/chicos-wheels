# salud.py
"""Test de humo diario: visita cada producto activo SIN comprar y confirma
que el selector del boton de compra siga existiendo en el DOM.

Objetivo: enterarse de un selector roto de la tienda (Mattel cambia su HTML
sin avisar) con horas de anticipacion, en vez de descubrirlo justo a la hora
de un drop real. No revisa agotado/disponible, solo que el selector exista
-- un producto agotado con el boton en el DOM sigue siendo "selector sano".
Vive en la misma bot.db.
"""

import os
import sqlite3

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")


def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS smoke_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    detalle TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
    conn.commit()
    conn.close()


def registrar(url, ok, detalle):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO smoke_tests (url, ok, detalle) VALUES (?, ?, ?)",
              (url, int(bool(ok)), detalle))
    conn.commit()
    conn.close()


def ultimo_por_url():
    """El test de humo mas reciente de cada URL que se haya probado alguna vez."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""SELECT url, ok, detalle, created_at FROM smoke_tests
                 WHERE id IN (SELECT MAX(id) FROM smoke_tests GROUP BY url)""")
    filas = {r[0]: {"ok": bool(r[1]), "detalle": r[2], "created_at": r[3]}
             for r in c.fetchall()}
    conn.close()
    return filas


# --- Prueba diaria del checkout completo (ensayo, sin pagar) -------------------
# Distinta del test de humo de arriba (que solo mira que el boton exista): esta
# recorre TODO el proceso -- carrito, checkout, datos de envio, campos de
# tarjeta -- con un producto disponible real y se detiene justo antes de pagar.

def init_checkout():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS checkout_tests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        estado TEXT NOT NULL,      -- ok | roto | sin_producto | captcha
                        detalle TEXT,
                        url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""")
    conn.commit()
    conn.close()


def registrar_checkout(estado, detalle, url=None):
    init_checkout()
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO checkout_tests (estado, detalle, url) VALUES (?, ?, ?)",
                 (estado, detalle, url))
    conn.commit()
    conn.close()


def ultimos_checkout(n=5):
    init_checkout()
    conn = sqlite3.connect(DB)
    filas = conn.execute("SELECT estado, detalle, url, created_at FROM checkout_tests "
                         "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    conn.close()
    return [{"estado": f[0], "detalle": f[1], "url": f[2], "created_at": f[3]} for f in filas]


def checkout_roto_seguido():
    """True si las dos ultimas pruebas con producto real fallaron (asi un tropiezo
    aislado -- internet, una pagina lenta -- no dispara la alarma)."""
    reales = [f for f in ultimos_checkout(10) if f["estado"] in ("ok", "roto")][:2]
    return len(reales) == 2 and all(f["estado"] == "roto" for f in reales)
