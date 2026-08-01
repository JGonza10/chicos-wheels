"""Inventario de piezas y su historial de precios."""
import json

from flask import Blueprint, g, jsonify, request

from ..db import bd, todos, transaccion, uno
from ..util import ErrorApp, entero, fecha, hoy, num, texto, uid

bp = Blueprint("articulos", __name__)

TIPOS = ("Hot Wheels", "Pokémon")
ESTATUS = ("Disponible", "En negociación", "Conservar")


def limpiar(b: dict, parcial: bool = False) -> dict:
    """Normaliza lo que llega del cliente. Nunca confiamos en el navegador."""
    o = {}

    def poner(clave, valor):
        if not parcial or clave in b:
            o[clave] = valor

    if "tipo" in b or not parcial:
        if b.get("tipo") not in TIPOS:
            raise ErrorApp("El tipo debe ser Hot Wheels o Pokémon")
        o["tipo"] = b["tipo"]
    if "nombre" in b or not parcial:
        nombre = texto(b.get("nombre"), 160)
        if not nombre:
            raise ErrorApp("La pieza necesita un nombre")
        o["nombre"] = nombre

    poner("numero", texto(b.get("numero"), 40))
    poner("anio", entero(b.get("anio")) if b.get("anio") else None)
    poner("serie", texto(b.get("serie"), 60))
    poner("color", texto(b.get("color"), 60))
    poner("expansion", texto(b.get("expansion"), 80))
    poner("rareza", texto(b.get("rareza"), 60))
    poner("grado", texto(b.get("grado"), 40))
    poner("cert", texto(b.get("cert"), 40))
    poner("sub", texto(b.get("sub"), 60))
    poner("estado", texto(b.get("estado"), 60))
    poner("cantidad", max(0, entero(b.get("cantidad"), 1)))
    poner("estatus", b["estatus"] if b.get("estatus") in ESTATUS else "Disponible")
    poner("precio_compra", max(0.0, num(b.get("precio_compra"))))
    poner("valor_estimado", max(0.0, num(b.get("valor_estimado"))))
    poner("fecha_adq", fecha(b["fecha_adq"]) if b.get("fecha_adq") else "")
    poner("fuente", texto(b.get("fuente"), 60))
    poner("ubicacion", texto(b.get("ubicacion"), 80))
    poner("codigo", texto(b.get("codigo"), 60))
    poner("foto", texto(b.get("foto"), 500))
    poner("notas", texto(b.get("notas"), 1000))
    poner("grail", 1 if b.get("grail") else 0)
    checks = b.get("checks")
    poner("checks", json.dumps([entero(c) for c in checks] if isinstance(checks, list) else []))
    return o


def mio(id_art: str) -> dict:
    a = uno("SELECT * FROM v_articulos WHERE id=? AND usuario_id=?", (id_art, g.usuario_id))
    if not a:
        raise ErrorApp("Esa pieza no existe en tu inventario", 404)
    return a


@bp.get("")
def listar():
    return jsonify(todos(
        "SELECT * FROM v_articulos WHERE usuario_id=? ORDER BY creado_en DESC", (g.usuario_id,)))


@bp.get("/<id_art>")
def detalle(id_art):
    a = mio(id_art)
    a["valuaciones"] = todos(
        "SELECT * FROM valuaciones WHERE articulo_id=? ORDER BY fecha", (id_art,))
    return jsonify(a)


@bp.post("")
def crear():
    datos = limpiar(request.get_json(silent=True) or {})
    nuevo_id = uid("PKM" if datos["tipo"] == "Pokémon" else "HW")
    columnas = list(datos.keys())

    with transaccion() as con:
        con.execute(
            f"INSERT INTO articulos (id,usuario_id,cant_inicial,{','.join(columnas)}) "
            f"VALUES (?,?,?,{','.join('?' * len(columnas))})",
            [nuevo_id, g.usuario_id, datos["cantidad"]] + [datos[c] for c in columnas])
        # La primera valuación es el punto de partida de la gráfica de tendencia.
        if datos["valor_estimado"] > 0:
            con.execute(
                "INSERT INTO valuaciones (id,articulo_id,fecha,valor,fuente) VALUES (?,?,?,?,?)",
                (uid("VAL"), nuevo_id, datos["fecha_adq"] or hoy(),
                 datos["valor_estimado"], "Registro inicial"))

    return jsonify(uno("SELECT * FROM v_articulos WHERE id=?", (nuevo_id,))), 201


@bp.patch("/<id_art>")
def editar(id_art):
    actual = mio(id_art)
    datos = limpiar(request.get_json(silent=True) or {}, parcial=True)
    if not datos:
        return jsonify(actual)
    asigna = ",".join(f"{c}=?" for c in datos)
    bd().execute(
        f"UPDATE articulos SET {asigna}, actualizado_en=datetime('now') "
        f"WHERE id=? AND usuario_id=?",
        list(datos.values()) + [id_art, g.usuario_id])
    bd().commit()
    return jsonify(uno("SELECT * FROM v_articulos WHERE id=?", (id_art,)))


@bp.delete("/<id_art>")
def eliminar(id_art):
    mio(id_art)
    vigentes = uno("SELECT COUNT(*) n FROM apartados WHERE articulo_id=? AND estatus='Vigente'",
                   (id_art,))["n"]
    if vigentes:
        raise ErrorApp("Esta pieza tiene un apartado vigente. Cancélalo primero.", 409)
    bd().execute("DELETE FROM articulos WHERE id=?", (id_art,))
    bd().commit()
    return jsonify(ok=True)


# ---------- Historial de precios ----------

@bp.post("/<id_art>/valuaciones")
def agregar_valuacion(id_art):
    mio(id_art)
    datos = request.get_json(silent=True) or {}
    valor = num(datos.get("valor"))
    if valor <= 0:
        raise ErrorApp("Escribe el valor que observaste en el mercado")

    with transaccion() as con:
        con.execute("INSERT INTO valuaciones (id,articulo_id,fecha,valor,fuente) VALUES (?,?,?,?,?)",
                    (uid("VAL"), id_art, fecha(datos.get("fecha")), valor,
                     texto(datos.get("fuente"), 60)))
        if datos.get("actualizar") is not False:
            con.execute(
                "UPDATE articulos SET valor_estimado=?, actualizado_en=datetime('now') WHERE id=?",
                (valor, id_art))

    return jsonify(
        articulo=uno("SELECT * FROM v_articulos WHERE id=?", (id_art,)),
        valuaciones=todos("SELECT * FROM valuaciones WHERE articulo_id=? ORDER BY fecha", (id_art,)),
    ), 201


@bp.delete("/<id_art>/valuaciones/<id_val>")
def borrar_valuacion(id_art, id_val):
    mio(id_art)
    bd().execute("DELETE FROM valuaciones WHERE id=? AND articulo_id=?", (id_val, id_art))
    bd().commit()
    return jsonify(ok=True)
