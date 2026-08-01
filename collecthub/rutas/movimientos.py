"""Ventas, lotes, apartados con anticipo e intercambios."""
from flask import Blueprint, g, jsonify, request

from ..db import bd, todos, transaccion, uno
from ..util import ErrorApp, entero, fecha, hoy, num, texto, uid

bp = Blueprint("movimientos", __name__)

COLS_VENTA = ("id", "usuario_id", "articulo_id", "comprador_id", "plataforma_id", "lote_id",
              "nombre_snap", "tipo_snap", "plataforma_snap", "cantidad", "precio", "envio",
              "otros", "costo_unit", "com_pct", "com_fija", "ret_pct", "anticipo_aplicado",
              "fecha", "fecha_adq_snap", "guia", "estatus_envio")

SQL_VENTA = (f"INSERT INTO ventas ({','.join(COLS_VENTA)}) "
             f"VALUES ({','.join(':' + c for c in COLS_VENTA)})")


def _articulo(id_art):
    return uno("SELECT * FROM v_articulos WHERE id=? AND usuario_id=?", (id_art, g.usuario_id))


def _plataforma(id_plat):
    return uno("SELECT * FROM plataformas WHERE id=? AND usuario_id=?", (id_plat, g.usuario_id))


def _fila_venta(a, p, b, **extra) -> dict:
    """Arma la fila de venta congelando los costos vigentes hoy."""
    return {
        "id": uid("V"),
        "usuario_id": g.usuario_id,
        "articulo_id": a["id"],
        "comprador_id": texto(b.get("comprador_id"), 40) or None,
        "plataforma_id": p["id"],
        "lote_id": extra.get("lote_id"),
        "nombre_snap": a["nombre"],
        "tipo_snap": a["tipo"],
        "plataforma_snap": p["nombre"],
        "cantidad": extra.get("cantidad", max(1, entero(b.get("cantidad"), 1))),
        "precio": extra.get("precio", max(0.0, num(b.get("precio")))),
        "envio": extra.get("envio", max(0.0, num(b.get("envio")))),
        "otros": max(0.0, num(b.get("otros"))),
        "costo_unit": num(a["precio_compra"]),                       # congelado
        "com_pct": num(p["com_pct"]),                                # congelado
        "com_fija": extra.get("com_fija", num(p["com_fija"])),
        "ret_pct": num(p["ret_pct"]),                                # congelado
        "anticipo_aplicado": extra.get("anticipo_aplicado", 0),
        "fecha": fecha(b.get("fecha")),
        "fecha_adq_snap": a["fecha_adq"] or "",
        "guia": texto(b.get("guia"), 60),
        "estatus_envio": "Pendiente" if num(b.get("envio")) > 0 else "Sin envío",
    }


# ==================== VENTAS ====================

@bp.get("/ventas")
def listar_ventas():
    return jsonify(todos(
        "SELECT * FROM ventas WHERE usuario_id=? ORDER BY fecha DESC, creado_en DESC",
        (g.usuario_id,)))


@bp.post("/ventas")
def vender():
    """
    Registrar la venta y descontar el stock ocurre dentro de una transacción:
    si algo falla, ni se descuenta ni se registra.
    """
    b = request.get_json(silent=True) or {}
    a = _articulo(b.get("articulo_id"))
    if not a:
        raise ErrorApp("Esa pieza no existe en tu inventario", 404)
    p = _plataforma(b.get("plataforma_id"))
    if not p:
        raise ErrorApp("Elige un canal de venta válido")

    cantidad = max(1, entero(b.get("cantidad"), 1))
    apartado = None
    if b.get("apartado_id"):
        apartado = uno("SELECT * FROM apartados WHERE id=? AND usuario_id=? "
                       "AND estatus IN ('Vigente','Vencido')",
                       (b["apartado_id"], g.usuario_id))
        if not apartado:
            raise ErrorApp("Ese apartado ya no está activo", 409)

    # Un apartado ya reservó su stock; una venta normal solo toma lo libre.
    tope = apartado["cantidad"] if apartado else a["disponible"]
    if cantidad > tope:
        raise ErrorApp(
            "No puedes liquidar más piezas de las que se apartaron" if apartado
            else f"Solo tienes {a['disponible']} pieza(s) libres. El resto está apartado.", 409)
    if num(b.get("precio")) <= 0:
        raise ErrorApp("Falta el precio cobrado")

    fila = _fila_venta(a, p, b, cantidad=cantidad,
                       anticipo_aplicado=num(apartado["anticipo"]) if apartado else 0)
    with transaccion() as con:
        con.execute(SQL_VENTA, fila)
        con.execute("UPDATE articulos SET cantidad=cantidad-?, actualizado_en=datetime('now') "
                    "WHERE id=?", (cantidad, a["id"]))
        if apartado:
            con.execute("UPDATE apartados SET estatus='Liquidado' WHERE id=?", (apartado["id"],))

    return jsonify(uno("SELECT * FROM ventas WHERE id=?", (fila["id"],))), 201


@bp.post("/ventas/lote")
def vender_lote():
    """
    El precio se reparte entre las piezas en proporción a su valor de mercado.
    La cuota fija y el envío se cobran una sola vez, no por pieza.
    """
    b = request.get_json(silent=True) or {}
    ids = b.get("articulo_ids") or []
    if not isinstance(ids, list) or len(ids) < 2:
        raise ErrorApp("Un lote necesita al menos dos piezas")
    p = _plataforma(b.get("plataforma_id"))
    if not p:
        raise ErrorApp("Elige un canal de venta válido")
    precio = num(b.get("precio"))
    if precio <= 0:
        raise ErrorApp("Falta el precio del lote")

    piezas = []
    for id_art in ids:
        a = _articulo(id_art)
        if not a:
            raise ErrorApp("Una de las piezas del lote ya no existe", 404)
        if a["disponible"] < 1:
            raise ErrorApp(f'"{a["nombre"]}" no está disponible: revisa si está apartada', 409)
        piezas.append(a)

    base = sum(num(a["valor_estimado"]) for a in piezas) or len(piezas)
    id_lote = uid("L")

    with transaccion() as con:
        con.execute("INSERT INTO lotes (id,usuario_id,fecha,precio,piezas) VALUES (?,?,?,?,?)",
                    (id_lote, g.usuario_id, fecha(b.get("fecha")), precio, len(piezas)))
        for i, a in enumerate(piezas):
            parte = precio * ((num(a["valor_estimado"]) or 1) / base)
            con.execute(SQL_VENTA, _fila_venta(
                a, p, b, lote_id=id_lote, cantidad=1, precio=parte,
                envio=max(0.0, num(b.get("envio"))) if i == 0 else 0,   # el envío es del paquete
                com_fija=num(p["com_fija"]) if i == 0 else 0))          # la cuota, una sola vez
            con.execute("UPDATE articulos SET cantidad=cantidad-1 WHERE id=?", (a["id"],))

    return jsonify(
        lote=uno("SELECT * FROM lotes WHERE id=?", (id_lote,)),
        ventas=todos("SELECT * FROM ventas WHERE lote_id=?", (id_lote,)),
    ), 201


@bp.patch("/ventas/<id_venta>")
def actualizar_venta(id_venta):
    v = uno("SELECT * FROM ventas WHERE id=? AND usuario_id=?", (id_venta, g.usuario_id))
    if not v:
        raise ErrorApp("Venta no encontrada", 404)
    b = request.get_json(silent=True) or {}
    if b.get("estatus_envio") not in ("Sin envío", "Pendiente", "Enviado", "Entregado"):
        raise ErrorApp("Estatus de envío no válido")
    guia = texto(b["guia"], 60) if b.get("guia") is not None else v["guia"]
    bd().execute("UPDATE ventas SET estatus_envio=?, guia=? WHERE id=?",
                 (b["estatus_envio"], guia, id_venta))
    bd().commit()
    return jsonify(uno("SELECT * FROM ventas WHERE id=?", (id_venta,)))


@bp.delete("/ventas/<id_venta>")
def cancelar_venta(id_venta):
    """Cancelar una venta devuelve el stock: si no, el inventario miente."""
    v = uno("SELECT * FROM ventas WHERE id=? AND usuario_id=?", (id_venta, g.usuario_id))
    if not v:
        raise ErrorApp("Venta no encontrada", 404)
    with transaccion() as con:
        if v["articulo_id"]:
            con.execute("UPDATE articulos SET cantidad=cantidad+? WHERE id=?",
                        (v["cantidad"], v["articulo_id"]))
        con.execute("DELETE FROM ventas WHERE id=?", (id_venta,))
    return jsonify(ok=True, stock_devuelto=v["cantidad"])


# ==================== APARTADOS ====================

@bp.get("/apartados")
def listar_apartados():
    return jsonify(todos("SELECT * FROM apartados WHERE usuario_id=? ORDER BY fecha_limite",
                         (g.usuario_id,)))


@bp.post("/apartados")
def apartar():
    b = request.get_json(silent=True) or {}
    a = _articulo(b.get("articulo_id"))
    if not a:
        raise ErrorApp("Esa pieza no existe en tu inventario", 404)
    cantidad = max(1, entero(b.get("cantidad"), 1))
    if cantidad > a["disponible"]:
        raise ErrorApp(f"Solo quedan {a['disponible']} pieza(s) libres para apartar", 409)
    precio, anticipo = num(b.get("precio_acordado")), num(b.get("anticipo"))
    if precio <= 0:
        raise ErrorApp("Falta el precio acordado")
    if anticipo > precio:
        raise ErrorApp("El anticipo no puede ser mayor al precio acordado")

    id_ap = uid("AP")
    bd().execute(
        "INSERT INTO apartados (id,usuario_id,articulo_id,comprador_id,nombre_snap,cantidad,"
        "precio_acordado,anticipo,fecha,fecha_limite,notas) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (id_ap, g.usuario_id, a["id"], texto(b.get("comprador_id"), 40) or None, a["nombre"],
         cantidad, precio, anticipo, hoy(),
         fecha(b["fecha_limite"]) if b.get("fecha_limite") else "", texto(b.get("notas"), 300)))
    bd().commit()
    return jsonify(uno("SELECT * FROM apartados WHERE id=?", (id_ap,))), 201


@bp.post("/apartados/<id_ap>/cancelar")
def cancelar_apartado(id_ap):
    cur = bd().execute("UPDATE apartados SET estatus='Cancelado' WHERE id=? AND usuario_id=? "
                       "AND estatus IN ('Vigente','Vencido')", (id_ap, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Ese apartado ya no se puede cancelar", 409)
    return jsonify(ok=True)


# ==================== INTERCAMBIOS ====================

@bp.get("/intercambios")
def listar_intercambios():
    lista = todos("SELECT * FROM intercambios WHERE usuario_id=? ORDER BY fecha DESC",
                  (g.usuario_id,))
    for t in lista:
        items = todos("SELECT * FROM intercambio_items WHERE intercambio_id=?", (t["id"],))
        t["entregados"] = [i for i in items if i["direccion"] == "entrega"]
        t["recibidos"] = [i for i in items if i["direccion"] == "recibe"]
    return jsonify(lista)


@bp.post("/intercambios")
def intercambiar():
    """
    Un intercambio son dos movimientos simultáneos sin dinero: las piezas que
    entregas salen del inventario y las que recibes entran con costo cero.
    """
    b = request.get_json(silent=True) or {}
    entrega = b.get("entrega_ids") or []
    recibe = b.get("recibidos") or []
    if not entrega and not recibe:
        raise ErrorApp("Agrega al menos una pieza al intercambio")

    salen = []
    for id_art in entrega:
        a = _articulo(id_art)
        if not a:
            raise ErrorApp("Una de las piezas que entregas ya no existe", 404)
        if a["disponible"] < 1:
            raise ErrorApp(f'"{a["nombre"]}" no está disponible para intercambio', 409)
        salen.append(a)

    v_sale = sum(num(a["valor_estimado"]) for a in salen)
    v_entra = sum(num(r.get("valor")) for r in recibe)
    f = fecha(b.get("fecha"))
    id_t = uid("T")
    contraparte = texto(b.get("contraparte"), 100)

    with transaccion() as con:
        con.execute("INSERT INTO intercambios (id,usuario_id,fecha,contraparte,notas,diferencia) "
                    "VALUES (?,?,?,?,?,?)",
                    (id_t, g.usuario_id, f, contraparte, texto(b.get("notas"), 300),
                     v_entra - v_sale))
        sql_item = ("INSERT INTO intercambio_items "
                    "(id,intercambio_id,direccion,articulo_id,nombre,tipo,valor) "
                    "VALUES (?,?,?,?,?,?,?)")
        for a in salen:
            con.execute(sql_item, (uid("TI"), id_t, "entrega", a["id"], a["nombre"], a["tipo"],
                                   num(a["valor_estimado"])))
            con.execute("UPDATE articulos SET cantidad=cantidad-1 WHERE id=?", (a["id"],))
        for r in recibe:
            tipo = r.get("tipo") if r.get("tipo") in ("Hot Wheels", "Pokémon") else "Hot Wheels"
            nombre = texto(r.get("nombre"), 160)
            if not nombre:
                raise ErrorApp("Cada pieza que recibes necesita nombre")
            nuevo = uid("PKM" if tipo == "Pokémon" else "HW")
            con.execute(
                "INSERT INTO articulos (id,usuario_id,tipo,nombre,cantidad,cant_inicial,"
                "precio_compra,valor_estimado,fecha_adq,fuente,estado,notas) "
                "VALUES (?,?,?,?,1,1,0,?,?,'Intercambio',?,?)",
                (nuevo, g.usuario_id, tipo, nombre, num(r.get("valor")), f,
                 "Near Mint" if tipo == "Pokémon" else "Excelente",
                 f"Recibida en intercambio con {contraparte or '—'}"))
            con.execute("INSERT INTO valuaciones (id,articulo_id,fecha,valor,fuente) "
                        "VALUES (?,?,?,?,?)",
                        (uid("VAL"), nuevo, f, num(r.get("valor")), "Intercambio"))
            con.execute(sql_item, (uid("TI"), id_t, "recibe", nuevo, nombre, tipo,
                                   num(r.get("valor"))))

    return jsonify(uno("SELECT * FROM intercambios WHERE id=?", (id_t,))), 201


@bp.delete("/intercambios/<id_t>")
def borrar_intercambio(id_t):
    cur = bd().execute("DELETE FROM intercambios WHERE id=? AND usuario_id=?", (id_t, g.usuario_id))
    bd().commit()
    if not cur.rowcount:
        raise ErrorApp("Intercambio no encontrado", 404)
    return jsonify(ok=True)
