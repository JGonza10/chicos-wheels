"""
Acceso a la base de datos.

Cada petición HTTP usa su propia conexión y se cierra al terminar. SQLite no
permite compartir una conexión entre hilos, y el servidor atiende peticiones
en paralelo, así que este es el patrón seguro.
"""
import os
import re
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
        _quitar_check_tipo(con)
        habia_categorias = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='categorias'").fetchone()
        con.executescript(sql)
        if not habia_categorias:
            # Primera vez con categorías: toda cuenta existente recibe las iniciales.
            from .categorias import INICIALES
            for nombre, emoji in INICIALES:
                con.execute("""INSERT OR IGNORE INTO categorias (id,usuario_id,nombre,emoji)
                               SELECT 'CAT-' || lower(hex(randomblob(6))), id, ?, ? FROM usuarios""",
                            (nombre, emoji))
        # Bases creadas antes de existir una columna: CREATE IF NOT EXISTS no la agrega.
        cols = {f["name"] for f in con.execute("PRAGMA table_info(ventas)")}
        if "fecha_entrega" not in cols:
            con.execute("ALTER TABLE ventas ADD COLUMN fecha_entrega TEXT NOT NULL DEFAULT ''")
            con.execute("UPDATE ventas SET fecha_entrega=fecha WHERE estatus_envio='Entregado'")
        cols_ap = {f["name"] for f in con.execute("PRAGMA table_info(apartados)")}
        if "lugar_entrega" not in cols_ap:
            con.execute("ALTER TABLE apartados ADD COLUMN lugar_entrega TEXT NOT NULL DEFAULT 'Balderas'")
        if "cliente_snap" not in cols_ap:
            con.execute("ALTER TABLE apartados ADD COLUMN cliente_snap TEXT NOT NULL DEFAULT ''")
        # El nombre del cliente queda guardado en el apartado aunque luego borren al cliente.
        con.execute("""UPDATE apartados SET cliente_snap=(SELECT c.nombre FROM compradores c
                        WHERE c.id=apartados.comprador_id)
                      WHERE cliente_snap='' AND comprador_id IS NOT NULL""")
        _agregar_columnas(con, {
            "compradores": [("faltas", "INTEGER NOT NULL DEFAULT 0")],
            "encargos": [("origen", "TEXT NOT NULL DEFAULT ''"), ("confirmado", "INTEGER NOT NULL DEFAULT 1")],
            "ajustes": [("ultimo_respaldo", "TEXT NOT NULL DEFAULT ''")],
            "articulos": [("fecha_llegada", "TEXT NOT NULL DEFAULT ''")],
        })
        _apartados_a_pedidos(con)
        # Canal de entrega en persona (Balderas) para cuentas que ya existían.
        con.execute("""INSERT INTO plataformas (id,usuario_id,codigo,nombre,com_pct,com_fija,ret_pct,notas)
            SELECT 'P-TG-' || u.id, u.id, 'TG', 'Balderas', 0, 0, 0,
                   'Entrega en persona en Balderas.'
            FROM usuarios u WHERE NOT EXISTS
              (SELECT 1 FROM plataformas p WHERE p.usuario_id=u.id AND p.codigo='TG')""")
        con.commit()
    finally:
        con.close()


def _agregar_columnas(con, por_tabla: dict):
    for tabla, cols in por_tabla.items():
        hay = {f["name"] for f in con.execute(f"PRAGMA table_info({tabla})")}
        for nombre, tipo in cols:
            if nombre not in hay:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")


def _apartados_a_pedidos(con):
    """Desde 2026-09-25 todo apartado es un Pedido (encargo). Los apartados viejos
    que seguían vigentes pasan a Pedidos con su cliente, precio, anticipo y fecha;
    el apartado queda Cancelado con la nota de a qué pedido pasó (el historial no se borra)."""
    vigentes = con.execute("SELECT ap.*, a.precio_compra FROM apartados ap "
                           "LEFT JOIN articulos a ON a.id = ap.articulo_id WHERE ap.estatus='Vigente'").fetchall()
    if not vigentes:
        return
    from .util import uid
    for ap in vigentes:
        id_enc = uid("E")
        cant = max(1, ap["cantidad"] or 1)
        con.execute("INSERT INTO encargos (id,usuario_id,comprador_id,fecha,fecha_entrega,anticipo,forma_anticipo,notas) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (id_enc, ap["usuario_id"], ap["comprador_id"], ap["fecha"], ap["fecha_limite"] or "",
                     ap["anticipo"] or 0, "Efectivo" if ap["anticipo"] else "",
                     " ".join(x for x in (f"Pasado de Apartados ({ap['id']}).", ap["notas"] or "",
                                          f"Cliente: {ap['cliente_snap']}" if ap["cliente_snap"] and not ap["comprador_id"] else "") if x)))
        con.execute("INSERT INTO encargo_items (id,encargo_id,articulo_id,nombre_snap,cantidad,precio_unit,costo_unit) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (uid("EI"), id_enc, ap["articulo_id"], ap["nombre_snap"], cant,
                     round((ap["precio_acordado"] or 0) / cant, 2), ap["precio_compra"] or 0))
        con.execute("UPDATE apartados SET estatus='Cancelado', notas=? WHERE id=?",
                    (f"[Pasado a Pedidos {id_enc}] {ap['notas'] or ''}".strip(), ap["id"]))


def _quitar_check_tipo(con):
    """Bases anteriores al 2026-09-29 limitaban `articulos.tipo` a Hot Wheels o
    Pokémon con un CHECK. SQLite no permite quitar un CHECK: se reconstruye la
    tabla (mismas columnas y datos) con las llaves foráneas apagadas mientras
    tanto. Antes se deja una copia de la base junto a ella."""
    fila = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='articulos'").fetchone()
    if not fila or "CHECK (tipo IN" not in fila["sql"]:
        return
    respaldo = RUTA_BD.with_name(RUTA_BD.stem + "-antes-categorias.db")
    if not respaldo.exists():
        destino = sqlite3.connect(respaldo)
        con.backup(destino)
        destino.close()
    nuevo = re.sub(r"\s*CHECK \(tipo IN \([^)]*\)\)", "", fila["sql"], count=1)
    nuevo = nuevo.replace("CREATE TABLE articulos", "CREATE TABLE articulos_nueva", 1)
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DROP VIEW IF EXISTS v_articulos")  # schema.sql la vuelve a crear
        con.execute(nuevo)
        con.execute("INSERT INTO articulos_nueva SELECT * FROM articulos")
        con.execute("DROP TABLE articulos")
        con.execute("ALTER TABLE articulos_nueva RENAME TO articulos")
        if con.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("la migración de categorías dejó relaciones rotas")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")


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
