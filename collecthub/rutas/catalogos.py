"""Compradores, canales de venta, faltantes y ajustes de la cuenta."""
import sqlite3

from flask import Blueprint, g, jsonify, request

from ..db import bd, todos, uno
from ..util import ErrorApp, entero, num, texto, uid

bp = Blueprint("catalogos", __name__)


# ---------- Compradores ----------
INTERESES = ("Hot Wheels", "Pokémon", "Ambas")


def _limpiar_comprador(b):
    nombre = texto(b.get("nombre"), 100)
    if not nombre:
        raise ErrorApp("El comprador necesita un nombre o alias")
    return {
        "nombre": nombre,
        "tel": texto(b.get("tel"), 40),
        "interes": b["interes"] if b.get("interes") in INTERESES else "Ambas",
        "notas": texto(b.get("notas"), 400),
    }


@bp.get("/compradores")
def listar_compradores():
    return jsonify(todos("SELECT * FROM compradores WHERE usuario_id=? ORDER BY nombre",
                         (g.usuario_id,)))


@bp.post("/compradores")
def crear_comprador():
    d = _limpiar_comprador(request.get_json(silent=True) or {})
    id_c = uid("C")
    bd().execute("INSERT INTO compradores (id,usuario_id,nombre,tel,interes,notas) "
                 "VALUES (?,?,?,?,?,?)",
                 (id_c, g.usuario_id, d["nombre"], d["tel"], d["interes"], d["notas"]))
    bd().commit()
    return jsonify(uno("SELECT * FROM compradores WHERE id=?", (id_c,))), 201


@bp.patch("/compradores/<id_c>")
def editar_comprador(id_c):
    d = _limpiar_comprador(request.get_json(silent=True) or {})
    cur = bd().execute("UPDATE compradores SET nombre=?,tel=?,interes=?,notas=? "
                       "WHERE id=? AND usuario_id=?",
                       (d["nombre"], d["tel"], d["interes"], d["notas"], id_c, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Comprador no encontrado", 404)
    return jsonify(uno("SELECT * FROM compradores WHERE id=?", (id_c,)))


@bp.delete("/compradores/<id_c>")
def borrar_comprador(id_c):
    cur = bd().execute("DELETE FROM compradores WHERE id=? AND usuario_id=?", (id_c, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Comprador no encontrado", 404)
    return jsonify(ok=True)


# ---------- Plataformas ----------

def _limpiar_plataforma(b):
    nombre = texto(b.get("nombre"), 80)
    if not nombre:
        raise ErrorApp("El canal necesita un nombre")
    pct, ret = num(b.get("com_pct")), num(b.get("ret_pct"))
    if not 0 <= pct < 1:
        raise ErrorApp("La comisión debe estar entre 0 y 99%")
    if not 0 <= ret < 1:
        raise ErrorApp("La retención debe estar entre 0 y 99%")
    return {
        "codigo": (texto(b.get("codigo"), 8) or nombre[:2]).upper(),
        "nombre": nombre,
        "com_pct": pct,
        "com_fija": max(0.0, num(b.get("com_fija"))),
        "ret_pct": ret,
        "notas": texto(b.get("notas"), 200),
    }


@bp.get("/plataformas")
def listar_plataformas():
    return jsonify(todos("SELECT * FROM plataformas WHERE usuario_id=? ORDER BY nombre",
                         (g.usuario_id,)))


@bp.post("/plataformas")
def crear_plataforma():
    d = _limpiar_plataforma(request.get_json(silent=True) or {})
    id_p = uid("P")
    try:
        bd().execute("INSERT INTO plataformas (id,usuario_id,codigo,nombre,com_pct,com_fija,"
                     "ret_pct,notas) VALUES (?,?,?,?,?,?,?,?)",
                     (id_p, g.usuario_id, d["codigo"], d["nombre"], d["com_pct"],
                      d["com_fija"], d["ret_pct"], d["notas"]))
        bd().commit()
    except sqlite3.IntegrityError:
        raise ErrorApp(f"Ya tienes un canal con el código {d['codigo']}", 409)
    return jsonify(uno("SELECT * FROM plataformas WHERE id=?", (id_p,))), 201


@bp.patch("/plataformas/<id_p>")
def editar_plataforma(id_p):
    d = _limpiar_plataforma(request.get_json(silent=True) or {})
    cur = bd().execute("UPDATE plataformas SET codigo=?,nombre=?,com_pct=?,com_fija=?,"
                       "ret_pct=?,notas=? WHERE id=? AND usuario_id=?",
                       (d["codigo"], d["nombre"], d["com_pct"], d["com_fija"],
                        d["ret_pct"], d["notas"], id_p, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Canal no encontrado", 404)
    return jsonify(uno("SELECT * FROM plataformas WHERE id=?", (id_p,)))


@bp.delete("/plataformas/<id_p>")
def borrar_plataforma(id_p):
    # Las ventas guardan su comisión congelada: borrar el canal no altera el historial.
    cur = bd().execute("DELETE FROM plataformas WHERE id=? AND usuario_id=?", (id_p, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Canal no encontrado", 404)
    return jsonify(ok=True)


# ---------- Faltantes ----------

def _limpiar_deseo(b):
    nombre = texto(b.get("nombre"), 160)
    if not nombre:
        raise ErrorApp("Escribe qué pieza estás buscando")
    return {
        "nombre": nombre,
        "tipo": b["tipo"] if b.get("tipo") in ("Hot Wheels", "Pokémon") else "Hot Wheels",
        "tope": max(0.0, num(b.get("tope"))),
        "prioridad": min(5, max(1, entero(b.get("prioridad"), 3))),
        "detalle": texto(b.get("detalle"), 300),
    }


@bp.get("/wishlist")
def listar_wishlist():
    return jsonify(todos("SELECT * FROM wishlist WHERE usuario_id=? ORDER BY prioridad DESC",
                         (g.usuario_id,)))


@bp.post("/wishlist")
def crear_deseo():
    d = _limpiar_deseo(request.get_json(silent=True) or {})
    id_w = uid("W")
    bd().execute("INSERT INTO wishlist (id,usuario_id,nombre,tipo,tope,prioridad,detalle) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (id_w, g.usuario_id, d["nombre"], d["tipo"], d["tope"],
                  d["prioridad"], d["detalle"]))
    bd().commit()
    return jsonify(uno("SELECT * FROM wishlist WHERE id=?", (id_w,))), 201


@bp.delete("/wishlist/<id_w>")
def borrar_deseo(id_w):
    cur = bd().execute("DELETE FROM wishlist WHERE id=? AND usuario_id=?", (id_w, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Faltante no encontrado", 404)
    return jsonify(ok=True)


# ---------- Ajustes ----------
MONEDAS = ("MXN", "USD", "EUR", "COP", "ARS", "CLP", "PEN")


@bp.get("/ajustes")
def ver_ajustes():
    return jsonify(uno("SELECT * FROM ajustes WHERE usuario_id=?", (g.usuario_id,)))


@bp.patch("/ajustes")
def editar_ajustes():
    a = uno("SELECT * FROM ajustes WHERE usuario_id=?", (g.usuario_id,))
    b = request.get_json(silent=True) or {}
    moneda = b["moneda"] if b.get("moneda") in MONEDAS else a["moneda"]
    meta = max(0.0, num(b["meta_mensual"])) if "meta_mensual" in b else a["meta_mensual"]
    dias = max(1, entero(b["dias_estancado"], 120)) if "dias_estancado" in b else a["dias_estancado"]
    bd().execute("UPDATE ajustes SET moneda=?,meta_mensual=?,dias_estancado=? WHERE usuario_id=?",
                 (moneda, meta, dias, g.usuario_id))
    bd().commit()
    return jsonify(uno("SELECT * FROM ajustes WHERE usuario_id=?", (g.usuario_id,)))
