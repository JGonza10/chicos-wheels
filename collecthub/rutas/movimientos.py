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


@bp.get("/ventas/<id_venta>/recibo")
def recibo_venta(id_venta):
    from flask import Response
    from ..reporte import generar_recibo
    return Response(generar_recibo(g.usuario_id, id_venta), mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="recibo-{id_venta}.pdf"', "Cache-Control": "no-store"})


@bp.patch("/ventas/<id_venta>")
def actualizar_venta(id_venta):
    v = uno("SELECT * FROM ventas WHERE id=? AND usuario_id=?", (id_venta, g.usuario_id))
    if not v:
        raise ErrorApp("Venta no encontrada", 404)
    b = request.get_json(silent=True) or {}
    if b.get("estatus_envio") not in ("Sin envío", "Pendiente", "Enviado", "Entregado"):
        raise ErrorApp("Estatus de envío no válido")
    guia = texto(b["guia"], 60) if b.get("guia") is not None else v["guia"]
    # La fecha real de entrega solo existe mientras la venta esté Entregada.
    if b["estatus_envio"] == "Entregado":
        f_ent = fecha(b["fecha_entrega"]) if b.get("fecha_entrega") else (v["fecha_entrega"] or hoy())
    else:
        f_ent = ""
    bd().execute("UPDATE ventas SET estatus_envio=?, guia=?, fecha_entrega=? WHERE id=?",
                 (b["estatus_envio"], guia, f_ent, id_venta))
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

    # Todo apartado lleva el nombre de quien aparta: un cliente registrado o uno nuevo.
    comprador = texto(b.get("comprador_id"), 40) or None
    nombre_cliente = ""
    if comprador:
        c = uno("SELECT nombre FROM compradores WHERE id=? AND usuario_id=?", (comprador, g.usuario_id))
        if not c:
            raise ErrorApp("Cliente no encontrado", 404)
        nombre_cliente = c["nombre"]
    else:
        nombre_cliente = texto(b.get("cliente_nuevo"), 100)
        if not nombre_cliente:
            raise ErrorApp("Falta el nombre del cliente que aparta")

    id_ap = uid("AP")
    with transaccion() as con:
        if not comprador:
            comprador = uid("C")
            con.execute("INSERT INTO compradores (id,usuario_id,nombre,tel,interes,notas) VALUES (?,?,?,?,?,?)",
                        (comprador, g.usuario_id, nombre_cliente, texto(b.get("tel_nuevo"), 40), "Ambas",
                         "Cliente nuevo (alta desde un apartado)"))
        con.execute(
            "INSERT INTO apartados (id,usuario_id,articulo_id,comprador_id,nombre_snap,cantidad,"
            "precio_acordado,anticipo,fecha,fecha_limite,notas,lugar_entrega,cliente_snap) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (id_ap, g.usuario_id, a["id"], comprador, a["nombre"],
             cantidad, precio, anticipo, hoy(),
             fecha(b["fecha_limite"]) if b.get("fecha_limite") else "", texto(b.get("notas"), 300),
             texto(b.get("lugar_entrega"), 80) or "Balderas", nombre_cliente))
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


# ==================== ENCARGOS ====================
FORMAS_PAGO = ("Efectivo", "Depósito", "Transferencia")
ACTIVOS = ("Pendiente", "Empacado")


def encargos_de(usuario_id, id_enc=None):
    """Encargos del usuario con sus piezas, costos y saldos ya calculados."""
    filtro, par = ("AND id=?", (usuario_id, id_enc)) if id_enc else ("", (usuario_id,))
    lista = todos(f"SELECT * FROM encargos WHERE usuario_id=? {filtro} "
                  "ORDER BY CASE estatus WHEN 'Pendiente' THEN 0 WHEN 'Empacado' THEN 0 ELSE 1 END, "
                  "fecha_entrega, creado_en", par)
    for e in lista:
        e["items"] = todos("SELECT * FROM encargo_items WHERE encargo_id=? ORDER BY rowid", (e["id"],))
        e["piezas"] = sum(i["cantidad"] for i in e["items"])
        e["total"] = round(sum(i["cantidad"] * i["precio_unit"] for i in e["items"]), 2)
        e["costo"] = round(sum(i["cantidad"] * i["costo_unit"] for i in e["items"]), 2)
        e["ganancia"] = round((e["total_final"] if e["estatus"] == "Entregado" and e["total_final"] is not None
                               else e["total"]) - e["costo"], 2)
        e["resta"] = round(max(0.0, e["total"] - e["anticipo"]), 2)
        e["pagos"] = todos("SELECT * FROM encargo_pagos WHERE encargo_id=? ORDER BY fecha, rowid", (e["id"],))
        if e["estatus"] == "Entregado":
            final = e["total_final"] if e["total_final"] is not None else e["total"]
            e["debe"] = round(max(0.0, final - e["anticipo"] - e["cobrado_entrega"] - sum(p["monto"] for p in e["pagos"])), 2)
        else:
            e["debe"] = 0.0
    return lista


def _limpiar_encargo(b, id_actual=None):
    """Valida cliente, piezas y stock. Devuelve (campos, items, comprador_nuevo)."""
    comprador = texto(b.get("comprador_id"), 40) or None
    if comprador and not uno("SELECT 1 FROM compradores WHERE id=? AND usuario_id=?",
                             (comprador, g.usuario_id)):
        raise ErrorApp("Cliente no encontrado", 404)
    nuevo = texto(b.get("cliente_nuevo"), 100) if not comprador else ""
    if not comprador and not nuevo:
        raise ErrorApp("Elige un cliente o escribe el nombre del cliente nuevo")

    crudos = b.get("items")
    if not isinstance(crudos, list) or not crudos:
        raise ErrorApp("Agrega al menos una pieza al encargo")
    if len(crudos) > 200:
        raise ErrorApp("Demasiadas piezas en un solo encargo")

    pedido = {}
    items = []
    for it in crudos:
        a = _articulo(it.get("articulo_id"))
        if not a:
            raise ErrorApp("Una de las piezas ya no existe en tu inventario", 404)
        cant = max(1, entero(it.get("cantidad"), 1))
        pedido[a["id"]] = pedido.get(a["id"], 0) + cant
        precio = it.get("precio_unit")
        items.append({"articulo": a, "cantidad": cant,
                      "precio_unit": max(0.0, num(precio) if precio not in (None, "") else num(a["valor_estimado"]))})
    for id_art, cant in pedido.items():
        a = _articulo(id_art)
        propio = 0
        if id_actual:   # lo que este mismo encargo ya tiene reservado se puede volver a pedir
            propio = (uno("SELECT COALESCE(SUM(cantidad),0) n FROM encargo_items WHERE encargo_id=? "
                          "AND articulo_id=?", (id_actual, id_art)) or {"n": 0})["n"]
        if cant > a["disponible"] + propio:
            raise ErrorApp(f'De "{a["nombre"]}" solo tienes {a["disponible"] + propio} libre(s); '
                           f"pediste {cant}. El resto está apartado o en otro encargo.", 409)

    anticipo = max(0.0, num(b.get("anticipo")))
    total = sum(i["cantidad"] * i["precio_unit"] for i in items)
    if anticipo > total + 0.005:
        raise ErrorApp("El anticipo no puede ser mayor al total del encargo")
    forma = b.get("forma_anticipo") if b.get("forma_anticipo") in FORMAS_PAGO else ""
    campos = {
        "comprador_id": comprador, "fecha_entrega": fecha(b.get("fecha_entrega")) if b.get("fecha_entrega") else "",
        "anticipo": anticipo, "forma_anticipo": forma if anticipo else "",
        "notas": texto(b.get("notas"), 400),
    }
    return campos, items, nuevo


def _guardar_items(con, id_enc, items):
    con.execute("DELETE FROM encargo_items WHERE encargo_id=?", (id_enc,))
    for i in items:
        con.execute("INSERT INTO encargo_items (id,encargo_id,articulo_id,nombre_snap,cantidad,precio_unit,costo_unit) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (uid("EI"), id_enc, i["articulo"]["id"], i["articulo"]["nombre"], i["cantidad"],
                     i["precio_unit"], num(i["articulo"]["precio_compra"])))


@bp.get("/encargos")
def listar_encargos():
    return jsonify(encargos_de(g.usuario_id))


@bp.post("/encargos")
def crear_encargo():
    b = request.get_json(silent=True) or {}
    campos, items, nuevo = _limpiar_encargo(b)
    id_enc = uid("E")
    with transaccion() as con:
        if nuevo:
            campos["comprador_id"] = uid("C")
            con.execute("INSERT INTO compradores (id,usuario_id,nombre,tel,interes,notas) VALUES (?,?,?,?,?,?)",
                        (campos["comprador_id"], g.usuario_id, nuevo, texto(b.get("tel_nuevo"), 40), "Ambas",
                         "Cliente nuevo (alta desde un encargo)"))
        con.execute("INSERT INTO encargos (id,usuario_id,comprador_id,fecha,fecha_entrega,anticipo,forma_anticipo,notas) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (id_enc, g.usuario_id, campos["comprador_id"], hoy(), campos["fecha_entrega"],
                     campos["anticipo"], campos["forma_anticipo"], campos["notas"]))
        _guardar_items(con, id_enc, items)
    return jsonify(encargos_de(g.usuario_id, id_enc)[0]), 201


def _encargo_activo(id_enc):
    e = uno("SELECT * FROM encargos WHERE id=? AND usuario_id=?", (id_enc, g.usuario_id))
    if not e:
        raise ErrorApp("Encargo no encontrado", 404)
    if e["estatus"] not in ACTIVOS:
        raise ErrorApp(f"Este encargo ya está {e['estatus'].lower()}", 409)
    return e


@bp.post("/encargos/hoja-entrega")
def hoja_entrega():
    """PDF para imprimir: piezas por empacar, detalle por cliente y cruce contra dinero."""
    from flask import Response
    from ..hoja_entrega import generar_hoja_entrega
    pdf = generar_hoja_entrega(g.usuario_id, request.get_json(silent=True) or {})
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="hoja-entrega-{hoy()}.pdf"', "Cache-Control": "no-store"})


@bp.post("/encargos/hoja-entrega-excel")
def hoja_entrega_excel():
    """La misma hoja de entrega como lista de hoja de cálculo (.xlsx)."""
    from flask import Response
    from ..hoja_excel import generar_hoja_excel
    datos = generar_hoja_excel(g.usuario_id, request.get_json(silent=True) or {})
    return Response(datos, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": f'attachment; filename="pedidos-{hoy()}.xlsx"', "Cache-Control": "no-store"})


@bp.put("/encargos/<id_enc>")
def reemplazar_encargo(id_enc):
    _encargo_activo(id_enc)
    b = request.get_json(silent=True) or {}
    campos, items, nuevo = _limpiar_encargo(b, id_actual=id_enc)
    with transaccion() as con:
        if nuevo:
            campos["comprador_id"] = uid("C")
            con.execute("INSERT INTO compradores (id,usuario_id,nombre,tel,interes,notas) VALUES (?,?,?,?,?,?)",
                        (campos["comprador_id"], g.usuario_id, nuevo, texto(b.get("tel_nuevo"), 40), "Ambas",
                         "Cliente nuevo (alta desde un encargo)"))
        con.execute("UPDATE encargos SET comprador_id=?, fecha_entrega=?, anticipo=?, forma_anticipo=?, notas=? "
                    "WHERE id=?", (campos["comprador_id"], campos["fecha_entrega"], campos["anticipo"],
                                   campos["forma_anticipo"], campos["notas"], id_enc))
        _guardar_items(con, id_enc, items)
    return jsonify(encargos_de(g.usuario_id, id_enc)[0])


@bp.patch("/encargos/<id_enc>")
def estatus_encargo(id_enc):
    """Empacar / desempacar / cancelar. Cancelar libera el stock reservado."""
    _encargo_activo(id_enc)
    nuevo = (request.get_json(silent=True) or {}).get("estatus")
    if nuevo not in ("Pendiente", "Empacado", "Cancelado"):
        raise ErrorApp("Estatus no válido")
    bd().execute("UPDATE encargos SET estatus=? WHERE id=?", (nuevo, id_enc))
    bd().commit()
    return jsonify(encargos_de(g.usuario_id, id_enc)[0])


@bp.delete("/encargos/<id_enc>")
def borrar_encargo(id_enc):
    e = uno("SELECT estatus FROM encargos WHERE id=? AND usuario_id=?", (id_enc, g.usuario_id))
    if not e:
        raise ErrorApp("Encargo no encontrado", 404)
    if e["estatus"] == "Entregado":
        raise ErrorApp("Un encargo entregado ya es parte de tus ventas; no se borra", 409)
    bd().execute("DELETE FROM encargos WHERE id=?", (id_enc,))
    bd().commit()
    return jsonify(ok=True)


@bp.post("/encargos/<id_enc>/entregar")
def entregar_encargo(id_enc):
    """Entrega en persona: cada pieza se vuelve una venta (con su costo congelado),
    se descuenta el stock y se anota lo que se cobró. Todo en una transacción."""
    e = _encargo_activo(id_enc)
    b = request.get_json(silent=True) or {}
    enc = encargos_de(g.usuario_id, id_enc)[0]
    if not enc["items"]:
        raise ErrorApp("El encargo no tiene piezas")
    p = (uno("SELECT * FROM plataformas WHERE usuario_id=? AND codigo='TG'", (g.usuario_id,))
         or uno("SELECT * FROM plataformas WHERE usuario_id=? AND codigo='FB'", (g.usuario_id,))
         or uno("SELECT * FROM plataformas WHERE usuario_id=? ORDER BY nombre LIMIT 1", (g.usuario_id,)))
    if not p:
        raise ErrorApp("No tienes un canal de venta configurado")

    total = enc["total"]
    final = max(0.0, num(b.get("total_final"))) if b.get("total_final") not in (None, "") else total
    factor = (final / total) if total > 0 else 1.0
    cobrado = max(0.0, num(b.get("cobrado"))) if b.get("cobrado") not in (None, "") else max(0.0, final - e["anticipo"])
    forma = b.get("forma") if b.get("forma") in FORMAS_PAGO else ""

    with transaccion() as con:
        for n, it in enumerate(enc["items"]):
            a = _articulo(it["articulo_id"]) if it["articulo_id"] else None
            if not a:
                raise ErrorApp(f'La pieza "{it["nombre_snap"]}" ya no existe en tu inventario', 409)
            if a["cantidad"] < it["cantidad"]:
                raise ErrorApp(f'De "{a["nombre"]}" ya solo quedan {a["cantidad"]}; no alcanza para el encargo', 409)
            linea = it["cantidad"] * it["precio_unit"]
            fila = _fila_venta(a, p, {"comprador_id": e["comprador_id"], "fecha": hoy(), "envio": 0, "otros": 0},
                               cantidad=it["cantidad"], precio=round(linea * factor, 2),
                               anticipo_aplicado=round(e["anticipo"] * (linea / total), 2) if total > 0 else 0,
                               com_fija=num(p["com_fija"]) if n == 0 else 0)
            con.execute(SQL_VENTA, fila)
            con.execute("UPDATE articulos SET cantidad=cantidad-?, actualizado_en=datetime('now') WHERE id=?",
                        (it["cantidad"], a["id"]))
        con.execute("UPDATE encargos SET estatus='Entregado', entregado_en=?, total_final=?, cobrado_entrega=?, "
                    "forma_entrega=? WHERE id=?", (hoy(), final, cobrado, forma, id_enc))
    return jsonify(encargos_de(g.usuario_id, id_enc)[0])


@bp.post("/encargos/<id_enc>/pago")
def pago_encargo(id_enc):
    """Abono de un cliente que se llevó la pieza y quedó debiendo."""
    e = uno("SELECT estatus FROM encargos WHERE id=? AND usuario_id=?", (id_enc, g.usuario_id))
    if not e:
        raise ErrorApp("Pedido no encontrado", 404)
    if e["estatus"] != "Entregado":
        raise ErrorApp("Solo se registran abonos de pedidos ya entregados", 409)
    b = request.get_json(silent=True) or {}
    monto = num(b.get("monto"))
    if monto <= 0:
        raise ErrorApp("Escribe cuánto pagó")
    actual = encargos_de(g.usuario_id, id_enc)[0]
    if actual["debe"] <= 0.004:
        raise ErrorApp("Este pedido ya está liquidado", 409)
    if monto > actual["debe"] + 0.005:
        raise ErrorApp(f"Solo debe {actual['debe']:.2f}; el abono no puede ser mayor", 409)
    forma = b.get("forma") if b.get("forma") in FORMAS_PAGO else ""
    with transaccion() as con:
        con.execute("INSERT INTO encargo_pagos (id,encargo_id,fecha,monto,forma) VALUES (?,?,?,?,?)",
                    (uid("PG"), id_enc, hoy(), monto, forma))
    return jsonify(encargos_de(g.usuario_id, id_enc)[0]), 201
