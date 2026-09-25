"""Hoja de entrega para Balderas (PDF para imprimir).

Cruza las piezas que se llevan (con costo y precio por pieza y total) contra el
dinero que hay que cobrar, cliente por cliente. Usa las mismas piezas de dibujo
que el reporte general (`reporte.py`).
"""
from datetime import date

from .db import todos, uno
from .reporte import AZUL, GRIS, _fecha_ok, _Pdf, _t
from .util import ErrorApp


ETIQUETA = {"Pendiente": "Apartado", "Empacado": "En proceso"}


def generar_hoja_entrega(usuario_id: str, config: dict) -> bytes:
    from .rutas.movimientos import ACTIVOS, encargos_de

    fecha_f = _fecha_ok(config.get("fecha"))
    incluir_costos = config.get("incluir_costos", True) is not False
    encargos = [e for e in encargos_de(usuario_id) if e["estatus"] in ACTIVOS
                and (not fecha_f or e["fecha_entrega"] == fecha_f)]
    if not encargos:
        raise ErrorApp("No hay encargos pendientes" + (f" para el {fecha_f}" if fecha_f else "") + " que imprimir")
    clientes = {c["id"]: c for c in todos("SELECT id,nombre,tel FROM compradores WHERE usuario_id=?", (usuario_id,))}
    arts = {a["id"]: a for a in todos("SELECT id,ubicacion,numero FROM articulos WHERE usuario_id=?", (usuario_id,))}
    usuario = uno("SELECT nombre, email FROM usuarios WHERE id=?", (usuario_id,)) or {}
    encargos.sort(key=lambda e: (e["fecha_entrega"] or "9999",
                                 (clientes.get(e["comprador_id"]) or {}).get("nombre", "").lower()))

    def m(x):
        return f"${(x or 0):,.2f}"

    pdf = _Pdf("Hoja de entrega - Balderas", "P")
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 10, "Hoja de entrega - Balderas", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 5, _t(f"Entrega: {fecha_f or 'todos los encargos pendientes'}  |  Impreso {date.today().isoformat()}  |  "
                      f"{usuario.get('nombre') or usuario.get('email', '')}"), new_x="LMARGIN", new_y="NEXT")

    piezas = sum(e["piezas"] for e in encargos)
    total = sum(e["total"] for e in encargos)
    costo = sum(e["costo"] for e in encargos)
    anticipos = sum(e["anticipo"] for e in encargos)
    por_cobrar = sum(e["resta"] for e in encargos)
    por_forma = {}
    for e in encargos:
        if e["anticipo"]:
            k = e["forma_anticipo"] or "Sin especificar"
            por_forma[k] = por_forma.get(k, 0) + e["anticipo"]

    pdf.titulo_seccion("Resumen del dia")
    filas = [["Clientes a atender", str(len({e["comprador_id"] for e in encargos}))],
             ["Piezas a llevar", str(piezas)]]
    if incluir_costos:
        filas.append(["Costo total de las piezas", m(costo)])
    filas.append(["Precio total (lo que vas a vender)", m(total)])
    if incluir_costos:
        filas.append(["Ganancia esperada", m(total - costo)])
    detalle_forma = "  (" + ", ".join(f"{k} {m(v)}" for k, v in por_forma.items()) + ")" if por_forma else ""
    filas.append(["Ya cobrado por adelantado", m(anticipos) + detalle_forma])
    filas.append(["POR COBRAR EN BALDERAS", m(por_cobrar)])
    pdf.tabla([("Concepto", 3, "L"), ("Monto", 3, "R")], filas)

    # ---- lista para empacar (todas las piezas juntas, ordenadas por ubicación)
    consol = {}
    for e in encargos:
        for it in e["items"]:
            base = arts.get(it["articulo_id"]) or {}
            c = consol.setdefault(it["articulo_id"] or it["nombre_snap"], {
                "nombre": it["nombre_snap"], "cant": 0, "ubic": base.get("ubicacion") or "-",
                "num": base.get("numero") or ""})
            c["cant"] += it["cantidad"]
    pdf.titulo_seccion("Lista para empacar (todas las piezas juntas)")
    pdf.tabla([("OK", 1, "C"), ("Pieza", 6, "L"), ("Num.", 2, "L"), ("Ubicacion", 3, "L"), ("Cant", 1.2, "R")],
              [["[  ]", c["nombre"], c["num"], c["ubic"], str(c["cant"])]
               for c in sorted(consol.values(), key=lambda c: (c["ubic"], c["nombre"]))],
              pie=["", "Total de piezas", "", "", str(piezas)])

    # ---- detalle por cliente
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 9, "Detalle por cliente", new_x="LMARGIN", new_y="NEXT")
    for e in encargos:
        c = clientes.get(e["comprador_id"]) or {}
        if pdf.get_y() + 30 + 6 * (len(e["items"]) + 3) > pdf.h - 20:
            pdf.add_page()
        pdf.ln(2)
        pdf.set_fill_color(225, 230, 240)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 7, _t(f"{c.get('nombre', 'Cliente')}{'  -  ' + c['tel'] if c.get('tel') else ''}"
                          f"   |   Entrega: {e['fecha_entrega'] or 'sin fecha'}   |   {ETIQUETA.get(e['estatus'], e['estatus'])}"),
                 fill=True, new_x="LMARGIN", new_y="NEXT")
        cols = [("OK", 1, "C"), ("Pieza", 6, "L"), ("Cant", 1.1, "R")]
        if incluir_costos:
            cols += [("Costo u.", 2, "R"), ("Costo tot.", 2.2, "R")]
        cols += [("Precio u.", 2, "R"), ("Precio tot.", 2.2, "R")]
        filas = []
        for it in e["items"]:
            f = ["[  ]", it["nombre_snap"], str(it["cantidad"])]
            if incluir_costos:
                f += [m(it["costo_unit"]), m(it["cantidad"] * it["costo_unit"])]
            f += [m(it["precio_unit"]), m(it["cantidad"] * it["precio_unit"])]
            filas.append(f)
        pie = ["", f"Subtotal ({e['piezas']} pzs)", str(e["piezas"])]
        if incluir_costos:
            pie += ["", m(e["costo"])]
        pie += ["", m(e["total"])]
        pdf.tabla(cols, filas, pie=pie)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 36, 51)
        ant = f"Anticipo recibido: {m(e['anticipo'])}" + (f" ({e['forma_anticipo']})" if e["forma_anticipo"] else "")
        pdf.cell(0, 6, _t(f"{ant}     Resta por cobrar: {m(e['resta'])}"
                          + (f"     Ganancia: {m(e['ganancia'])}" if incluir_costos else "")),
                 new_x="LMARGIN", new_y="NEXT")
        if e["notas"]:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*GRIS)
            pdf.cell(0, 5, _t("Nota: " + e["notas"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(30, 36, 51)
        pdf.cell(0, 6, "Cobrado:  Efectivo $__________   Deposito $__________   Firma: ____________________",
                 new_x="LMARGIN", new_y="NEXT")

    # ---- cruce final: piezas contra dinero
    if pdf.get_y() + 40 + 6 * len(encargos) > pdf.h - 20:
        pdf.add_page()
    pdf.titulo_seccion("Cruce final: piezas entregadas contra dinero")
    cols = [("Cliente", 4, "L"), ("Pzs", 1, "R"), ("Total", 2, "R"), ("Anticipo", 2, "R"), ("Por cobrar", 2, "R"),
            ("Efectivo", 2.2, "R"), ("Deposito", 2.2, "R"), ("Dif.", 1.6, "R")]
    filas = [[(clientes.get(e["comprador_id"]) or {}).get("nombre", "Cliente"), str(e["piezas"]), m(e["total"]),
              m(e["anticipo"]), m(e["resta"]), "", "", ""] for e in encargos]
    pdf.tabla(cols, filas, pie=["TOTAL", str(piezas), m(total), m(anticipos), m(por_cobrar), "", "", ""])
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 36, 51)
    pdf.multi_cell(0, 5.5, _t(
        f"Debes regresar con {m(por_cobrar)} entre efectivo y deposito ({m(total)} en piezas menos {m(anticipos)} ya cobrados). "
        "Anota lo cobrado en cada renglon; la columna Dif. es lo cobrado menos lo que debia cobrarse (debe ser $0)."
        + (f" Al terminar, tu ganancia bruta esperada es {m(total - costo)}." if incluir_costos else "")),
        new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
