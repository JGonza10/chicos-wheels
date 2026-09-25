"""Reporte en PDF configurable (secciones, filtros, orientación).

Se arma en el servidor con fpdf2 y siempre con los datos del usuario en sesión.
Las fuentes base de fpdf2 solo cubren latin-1, así que el texto se sanea antes.
"""
from datetime import date, datetime

from fpdf import FPDF

from .db import todos, uno, vencer_apartados
from .util import ErrorApp

SECCIONES = ("resumen", "inventario", "ventas", "apartados")
ESTATUS_INV = ("todos", "disponible", "apartado", "conservar", "agotado", "estancado")
TIPOS = ("todos", "Hot Wheels", "Pokémon")
ORDENES = ("nombre", "valor", "reciente", "antiguedad")

AZUL = (10, 31, 68)
GRIS = (90, 100, 115)
ZEBRA = (244, 246, 250)


def _t(s) -> str:
    """Texto seguro para las fuentes base (latin-1)."""
    s = "" if s is None else str(s)
    for a, b in (("–", "-"), ("—", "-"), ("·", "-"), ("’", "'"), ("“", '"'), ("”", '"'),
                 ("…", "..."), ("✕", "x"), ("€", "EUR")):
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def _fecha_ok(s) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ErrorApp("Las fechas del reporte deben ser AAAA-MM-DD")


def normalizar_config(b: dict) -> dict:
    secciones = [s for s in (b.get("secciones") or []) if s in SECCIONES]
    if not secciones:
        raise ErrorApp("Elige al menos una sección para el reporte")
    tipo = b.get("tipo", "todos")
    estatus = b.get("estatus", "todos")
    orden = b.get("orden", "nombre")
    if tipo not in TIPOS or estatus not in ESTATUS_INV or orden not in ORDENES:
        raise ErrorApp("Configuración de reporte no válida")
    return {
        "titulo": _t((b.get("titulo") or "Reporte de inventario").strip())[:80] or "Reporte",
        "secciones": secciones, "tipo": tipo, "estatus": estatus, "orden": orden,
        "orientacion": "L" if b.get("orientacion") == "horizontal" else "P",
        "desde": _fecha_ok(b.get("desde")), "hasta": _fecha_ok(b.get("hasta")),
        "solo_con_valor": bool(b.get("solo_con_valor")),
    }


def _articulos(u: str, c: dict, dias_estancado: int) -> list[dict]:
    rows = todos("SELECT * FROM v_articulos WHERE usuario_id=?", (u,))
    hoy = date.today()
    out = []
    for a in rows:
        if c["tipo"] != "todos" and a["tipo"] != c["tipo"]:
            continue
        cant = a["cantidad"] or 0
        e = c["estatus"]
        if e == "disponible" and (a["estatus"] == "Conservar" or (cant - (a.get("apartadas") or 0)) <= 0):
            continue
        if e == "apartado" and not a.get("apartadas"):
            continue
        if e == "conservar" and a["estatus"] != "Conservar":
            continue
        if e == "agotado" and cant:
            continue
        if e == "estancado":
            try:
                viejo = (hoy - datetime.strptime(a["fecha_adq"][:10], "%Y-%m-%d").date()).days
            except ValueError:
                viejo = -1
            if not (a["estatus"] == "Disponible" and cant and viejo > dias_estancado):
                continue
        if c["solo_con_valor"] and not a["valor_estimado"]:
            continue
        out.append(a)
    if c["orden"] == "nombre":
        out.sort(key=lambda a: a["nombre"].lower())
    elif c["orden"] == "valor":
        out.sort(key=lambda a: -(a["valor_estimado"] or 0))
    elif c["orden"] == "reciente":
        out.sort(key=lambda a: a["creado_en"] or "", reverse=True)
    else:
        out.sort(key=lambda a: a["fecha_adq"] or "9999")
    return out


class _Pdf(FPDF):
    def __init__(self, titulo, orient):
        super().__init__(orientation=orient, unit="mm", format="A4")
        self.titulo = titulo
        self.set_auto_page_break(True, margin=14)
        self.set_margins(12, 14, 12)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _t(f"{self.titulo}  |  Pagina {self.page_no()}/{{nb}}"), align="C")

    def titulo_seccion(self, txt):
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*AZUL)
        self.cell(0, 7, _t(txt), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*AZUL)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def vacio(self, txt):
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*GRIS)
        self.cell(0, 6, _t(txt), new_x="LMARGIN", new_y="NEXT")

    def tabla(self, cols, filas, pie=None):
        """cols: [(titulo, peso, alineacion)]; filas: listas de texto."""
        ancho = self.w - self.l_margin - self.r_margin
        tot = sum(p for _, p, _ in cols)
        w = [ancho * p / tot for _, p, _ in cols]

        def cab():
            self.set_font("Helvetica", "B", 8)
            self.set_fill_color(*AZUL)
            self.set_text_color(255, 255, 255)
            for (t, _, al), wi in zip(cols, w):
                self.cell(wi, 6, _t(t), fill=True, align=al)
            self.ln()
            self.set_text_color(30, 36, 51)

        cab()
        for i, f in enumerate(filas):
            if self.get_y() > self.h - 22:
                self.add_page()
                cab()
            self.set_font("Helvetica", "", 8)
            self.set_fill_color(*ZEBRA)
            for (_, _, al), wi, v in zip(cols, w, f):
                txt = _t(v)
                while txt and self.get_string_width(txt) > wi - 2:
                    txt = txt[:-1]
                self.cell(wi, 5.5, txt, fill=i % 2 == 1, align=al)
            self.ln()
        if pie:
            self.set_font("Helvetica", "B", 8)
            self.set_fill_color(225, 230, 240)
            for (_, _, al), wi, v in zip(cols, w, pie):
                self.cell(wi, 6, _t(v), fill=True, align=al)
            self.ln()


def generar_pdf(usuario_id: str, config: dict) -> bytes:
    c = normalizar_config(config)
    vencer_apartados()
    aj = uno("SELECT * FROM ajustes WHERE usuario_id=?", (usuario_id,)) or {}
    moneda = aj.get("moneda", "MXN")
    dias = aj.get("dias_estancado", 120)

    def m(v):
        return f"${(v or 0):,.2f}"

    arts = _articulos(usuario_id, c, dias)

    q, par = "SELECT * FROM ventas WHERE usuario_id=?", [usuario_id]
    if c["desde"]:
        q += " AND fecha>=?"
        par.append(c["desde"])
    if c["hasta"]:
        q += " AND fecha<=?"
        par.append(c["hasta"])
    ventas = todos(q + " ORDER BY fecha DESC", tuple(par))
    if c["tipo"] != "todos":
        ventas = [v for v in ventas if v["tipo_snap"] == c["tipo"]]

    # Los apartados traen su propio estatus (Vigente/Vencido/...), no el del inventario.
    ap = todos("SELECT * FROM apartados WHERE usuario_id=? ORDER BY fecha_limite", (usuario_id,))

    pdf = _Pdf(c["titulo"], c["orientacion"])
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 10, _t(c["titulo"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GRIS)
    filtros = [f"Categoria: {c['tipo'] if c['tipo'] != 'todos' else 'todas'}",
               f"Estatus: {c['estatus']}"]
    if c["desde"] or c["hasta"]:
        filtros.append(f"Ventas: {c['desde'] or 'inicio'} a {c['hasta'] or 'hoy'}")
    pdf.cell(0, 5, _t(f"Generado el {date.today().isoformat()}  |  Moneda: {moneda}  |  " + "  |  ".join(filtros)),
             new_x="LMARGIN", new_y="NEXT")

    if "resumen" in c["secciones"]:
        pdf.titulo_seccion("Resumen")
        piezas = sum(a["cantidad"] or 0 for a in arts)
        capital = sum((a["precio_compra"] or 0) * (a["cantidad"] or 0) for a in arts)
        mercado = sum((a["valor_estimado"] or 0) * (a["cantidad"] or 0) for a in arts)
        ing = sum(v["precio"] for v in ventas)
        gan = sum(v["ganancia_neta"] or 0 for v in ventas)
        est = {}
        for a in arts:
            k = "Agotada" if not a["cantidad"] else a["estatus"]
            est[k] = est.get(k, 0) + 1
        pdf.tabla([("Concepto", 3, "L"), ("Valor", 2, "R")], [
            ["Modelos en el reporte", str(len(arts))], ["Piezas fisicas", str(piezas)],
            ["Capital invertido", m(capital)], ["Valor de mercado", m(mercado)],
            ["Plusvalia", m(mercado - capital)],
            ["Ventas (periodo)", str(len(ventas))], ["Ingresos brutos", m(ing)],
            ["Ganancia neta", m(gan)], ["Margen", f"{(gan / ing * 100) if ing else 0:.1f}%"],
            ["Modelos por estatus", ", ".join(f"{k}: {n}" for k, n in sorted(est.items())) or "-"],
        ])

    if "inventario" in c["secciones"]:
        pdf.titulo_seccion(f"Inventario ({len(arts)} modelos)")
        if arts:
            filas = []
            for a in arts:
                det = a["serie"] if a["tipo"] == "Hot Wheels" else a["expansion"]
                dif = (a["valor_estimado"] or 0) - (a["precio_compra"] or 0)
                filas.append([a["nombre"], a["tipo"], a["numero"], det, str(a["cantidad"]),
                              "Agotada" if not a["cantidad"] else a["estatus"],
                              a["ubicacion"] or "-", m(a["precio_compra"]), m(a["valor_estimado"]), m(dif)])
            capital = sum((a["precio_compra"] or 0) * (a["cantidad"] or 0) for a in arts)
            mercado = sum((a["valor_estimado"] or 0) * (a["cantidad"] or 0) for a in arts)
            pdf.tabla([("Pieza", 5, "L"), ("Tipo", 2.2, "L"), ("Num.", 1.6, "L"), ("Serie/Expansion", 3, "L"),
                       ("Cant", 1, "R"), ("Estatus", 2.2, "L"), ("Ubicacion", 2.4, "L"),
                       ("Compra", 2, "R"), ("Valor", 2, "R"), ("Dif.", 2, "R")], filas,
                      pie=["Total (x cantidad)", "", "", "", "", "", "", m(capital), m(mercado), m(mercado - capital)])
        else:
            pdf.vacio("Ninguna pieza coincide con los filtros.")

    if "ventas" in c["secciones"]:
        pdf.titulo_seccion(f"Ventas ({len(ventas)})")
        if ventas:
            filas = [[v["fecha"], v["nombre_snap"], v["plataforma_snap"], str(v["cantidad"]),
                      m(v["precio"]), m(v["ganancia_neta"]), v["estatus_envio"]] for v in ventas]
            pdf.tabla([("Fecha", 2, "L"), ("Pieza", 5, "L"), ("Canal", 2.6, "L"), ("Cant", 1, "R"),
                       ("Cobrado", 2.2, "R"), ("Neto", 2.2, "R"), ("Envio", 2, "L")], filas,
                      pie=["Total", "", "", "", m(sum(v["precio"] for v in ventas)),
                           m(sum(v["ganancia_neta"] or 0 for v in ventas)), ""])
        else:
            pdf.vacio("Sin ventas en el periodo.")

    if "apartados" in c["secciones"]:
        pdf.titulo_seccion(f"Apartados ({len(ap)})")
        if ap:
            filas = [[x["fecha"], x["nombre_snap"], x["estatus"], x["fecha_limite"] or "-",
                      m(x["precio_acordado"]), m(x["anticipo"]),
                      m(x["precio_acordado"] - x["anticipo"])] for x in ap]
            pdf.tabla([("Fecha", 2, "L"), ("Pieza", 5, "L"), ("Estatus", 2, "L"), ("Limite", 2, "L"),
                       ("Acordado", 2.2, "R"), ("Anticipo", 2.2, "R"), ("Pendiente", 2.2, "R")], filas)
        else:
            pdf.vacio("No hay apartados.")

    return bytes(pdf.output())


LUGAR_ENTREGA = "Balderas"


def generar_recibo(usuario_id: str, id_venta: str) -> bytes:
    """Recibo de una venta (media hoja A5): lo que se entrega, a quién y dónde."""
    v = uno("SELECT * FROM ventas WHERE id=? AND usuario_id=?", (id_venta, usuario_id))
    if not v:
        raise ErrorApp("Venta no encontrada", 404)
    comp = (uno("SELECT nombre, tel FROM compradores WHERE id=? AND usuario_id=?",
                (v["comprador_id"], usuario_id)) if v["comprador_id"] else None) or {}
    usuario = uno("SELECT nombre, email FROM usuarios WHERE id=?", (usuario_id,)) or {}

    def m(x):
        return f"${(x or 0):,.2f}"

    pdf = FPDF(orientation="P", unit="mm", format="A5")
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 9, "Recibo de venta", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 5, _t(f"Folio {v['id']}  |  Fecha {v['fecha']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, _t(f"Vendedor: {usuario.get('nombre') or usuario.get('email', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_draw_color(*AZUL)
    pdf.line(14, pdf.get_y(), pdf.w - 14, pdf.get_y())
    pdf.ln(3)

    def fila(k, val, negrita=False):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*GRIS)
        pdf.cell(38, 6, _t(k))
        pdf.set_font("Helvetica", "B" if negrita else "", 10)
        pdf.set_text_color(30, 36, 51)
        pdf.multi_cell(0, 6, _t(val), new_x="LMARGIN", new_y="NEXT")

    fila("Pieza", v["nombre_snap"], True)
    fila("Cantidad", str(v["cantidad"]))
    fila("Categoria", v["tipo_snap"] or "-")
    fila("Comprador", comp.get("nombre") or "-")
    if comp.get("tel"):
        fila("Telefono", comp["tel"])
    fila("Canal", v["plataforma_snap"] or "-")
    fila("Entrega", LUGAR_ENTREGA if not v["guia"] else f"Envio - guia {v['guia']}")
    fila("Estatus", v["estatus_envio"] + (f" ({v['fecha_entrega']})" if v["fecha_entrega"] else ""))
    pdf.ln(3)
    pdf.line(14, pdf.get_y(), pdf.w - 14, pdf.get_y())
    pdf.ln(3)
    fila("Total cobrado", m(v["precio"]), True)
    if v["anticipo_aplicado"]:
        fila("Anticipo aplicado", m(v["anticipo_aplicado"]))
    pdf.ln(16)
    y = pdf.get_y()
    mitad = (pdf.w - 28) / 2
    pdf.line(14, y, 14 + mitad - 6, y)
    pdf.line(14 + mitad + 6, y, pdf.w - 14, y)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GRIS)
    pdf.cell(mitad, 5, "Firma del vendedor", align="C")
    pdf.cell(mitad, 5, "Recibi de conformidad", align="C")
    return bytes(pdf.output())
