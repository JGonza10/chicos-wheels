"""
Acceso a la base de datos.

Cada petición HTTP usa su propia conexión y se cierra al terminar. SQLite no
permite compartir una conexión entre hilos, y el servidor atiende peticiones
en paralelo, así que este es el patrón seguro.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import g

RUTA_BD = Path(os.environ.get("DB_FILE", Path(__file__).resolve().parent.parent / "datos" / "collecthub.db"))


def conectar() -> sqlite3.Connection:
    """Abre una conexión con las opciones que este proyecto necesita."""
    RUTA_BD.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA_BD, timeout=5.0)
    con.row_factory = sqlite3.Row          # las filas se leen como diccionarios
    con.execute("PRAGMA journal_mode = WAL")   # leer no bloquea escribir
    con.execute("PRAGMA foreign_keys = ON")    # las relaciones se respetan de verdad
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def bd() -> sqlite3.Connection:
    """La conexión de esta petición; se crea la primera vez que se pide."""
    if "bd" not in g:
        g.bd = conectar()
    return g.bd


def cerrar_bd(_error=None):
    con = g.pop("bd", None)
    if con is not None:
        con.close()


def crear_esquema():
    """Aplica schema.sql. Es idempotente: se puede correr en cada arranque."""
    sql = (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")
    con = conectar()
    try:
        con.executescript(sql)
        con.commit()
    finally:
        con.close()


@contextmanager
def transaccion():
    """
    Agrupa varias escrituras: o pasan todas, o no pasa ninguna.

        with transaccion() as con:
            con.execute(...)
            con.execute(...)

    Si algo falla a mitad, se deshace lo anterior. Es lo que evita que una
    venta descuente el stock sin quedar registrada.
    """
    con = bd()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise


def uno(sql, params=()):
    fila = bd().execute(sql, params).fetchone()
    return dict(fila) if fila else None


def todos(sql, params=()):
    return [dict(f) for f in bd().execute(sql, params).fetchall()]


def vencer_apartados() -> int:
    """Marca como Vencido todo apartado cuya fecha límite ya pasó."""
    cur = bd().execute(
        "UPDATE apartados SET estatus = 'Vencido' "
        "WHERE estatus = 'Vigente' AND fecha_limite <> '' AND fecha_limite < date('now')"
    )
    bd().commit()
    return cur.rowcount
