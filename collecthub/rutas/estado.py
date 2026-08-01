"""Estado completo para el frontend, métricas calculadas en SQL y respaldo."""
import json
from datetime import datetime

from flask import Blueprint, Response, g, jsonify, request

from ..db import bd, todos, transaccion, uno, vencer_apartados
from ..seed import sembrar
from ..util import ErrorApp, precio_objetivo

bp = Blueprint("estado", __name__)

TABLAS_USUARIO = ("ventas", "apartados", "intercambios", "lotes", "wishlist",
                  "articulos", "compradores")


def estado_completo(usuario_id: str) -> dict:
    """Todo lo que el frontend necesita para pintarse, en una sola llamada."""
    vencer_apartados()
    articulos = todos("SELECT * FROM v_articulos WHERE usuario_id=? ORDER BY creado_en DESC",
                      (usuario_id,))
    for a in articulos:
        a["checks"] = json.loads(a["checks"] or "[]")
        a["grail"] = bool(a["grail"])
        a["valuaciones"] = todos(
            "SELECT * FROM valuaciones WHERE articulo_id=? ORDER BY fecha", (a["id"],))

    intercambios = todos("SELECT * FROM intercambios WHERE usuario_id=? ORDER BY fecha DESC",
                         (usuario_id,))
    for t in intercambios:
        items = todos("SELECT * FROM intercambio_items WHERE intercambio_id=?", (t["id"],))
        t["entregados"] = [i for i in items if i["direccion"] == "entrega"]
        t["recibidos"] = [i for i in items if i["direccion"] == "recibe"]

    return {
        "ajustes": uno("SELECT * FROM ajustes WHERE usuario_id=?", (usuario_id,)),
        "plataformas": todos("SELECT * FROM plataformas WHERE usuario_id=? ORDER BY nombre",
                             (usuario_id,)),
        "compradores": todos("SELECT * FROM compradores WHERE usuario_id=? ORDER BY nombre",
                             (usuario_id,)),
        "articulos": articulos,
        "ventas": todos("SELECT * FROM ventas WHERE usuario_id=? "
                        "ORDER BY fecha DESC, creado_en DESC", (usuario_id,)),
        "apartados": todos("SELECT * FROM apartados WHERE usuario_id=? ORDER BY fecha_limite",
                           (usuario_id,)),
        "intercambios": intercambios,
        "lotes": todos("SELECT * FROM lotes WHERE usuario_id=? ORDER BY fecha DESC", (usuario_id,)),
        "wishlist": todos("SELECT * FROM wishlist WHERE usuario_id=? ORDER BY prioridad DESC",
                          (usuario_id,)),
    }


@bp.get("/estado")
def ver_estado():
    return jsonify(estado_completo(g.usuario_id))


@bp.get("/stats")
def stats():
    """Métricas calculadas en SQL: una sola verdad, sin recorrer listas en el cliente."""
    vencer_apartados()
    u = g.usuario_id

    inv = uno("""SELECT
        COALESCE(SUM(precio_compra*cantidad),0)  AS capital,
        COALESCE(SUM(valor_estimado*cantidad),0) AS mercado,
        COALESCE(SUM(cantidad),0)                AS piezas,
        COUNT(*)                                 AS skus
      FROM articulos WHERE usuario_id=? AND cantidad>0""", (u,))

    ven = uno("""SELECT COALESCE(SUM(precio),0) AS ingresos,
        COALESCE(SUM(ganancia_neta),0) AS ganancia, COUNT(*) AS n
      FROM ventas WHERE usuario_id=?""", (u,))

    mes = uno("""SELECT COALESCE(SUM(ganancia_neta),0) AS saldo FROM ventas
      WHERE usuario_id=? AND substr(fecha,1,7)=strftime('%Y-%m','now')""", (u,))

    rot = uno("""SELECT AVG(julianday(fecha)-julianday(fecha_adq_snap)) AS d
      FROM ventas WHERE usuario_id=? AND fecha_adq_snap<>''""", (u,))

    dias = uno("SELECT dias_estancado FROM ajustes WHERE usuario_id=?", (u,))["dias_estancado"]
    estancados = uno("""SELECT COUNT(*) n FROM articulos
      WHERE usuario_id=? AND cantidad>0 AND estatus='Disponible' AND fecha_adq<>''
        AND julianday('now')-julianday(fecha_adq) > ?""", (u, dias))["n"]

    ap = uno("""SELECT
        COALESCE(SUM(CASE WHEN estatus='Vigente' THEN 1 ELSE 0 END),0)        AS vigentes,
        COALESCE(SUM(CASE WHEN estatus='Vigente' THEN anticipo ELSE 0 END),0) AS anticipos,
        COALESCE(SUM(CASE WHEN estatus='Vencido' THEN 1 ELSE 0 END),0)        AS vencidos
      FROM apartados WHERE usuario_id=?""", (u,))

    return jsonify({
        **inv,
        "plusvalia": inv["mercado"] - inv["capital"],
        "ingresos": ven["ingresos"], "ganancia": ven["ganancia"], "ventas": ven["n"],
        "margen": (ven["ganancia"] / ven["ingresos"]) if ven["ingresos"] else 0,
        "ticket": (ven["ingresos"] / ven["n"]) if ven["n"] else 0,
        "rotacion": round(rot["d"]) if rot["d"] else None,
        "saldo_mes": mes["saldo"], "estancados": estancados,
        "apartados": ap["vigentes"], "anticipos": ap["anticipos"], "vencidos": ap["vencidos"],
        "sin_valor": uno("SELECT COUNT(*) n FROM articulos WHERE usuario_id=? "
                         "AND cantidad>0 AND valor_estimado=0", (u,))["n"],
        "agotados": uno("SELECT COUNT(*) n FROM articulos WHERE usuario_id=? AND cantidad=0",
                        (u,))["n"],
        "por_canal": todos("SELECT plataforma_snap AS canal, SUM(ganancia_neta) AS neto, "
                           "COUNT(*) AS n FROM ventas WHERE usuario_id=? "
                           "GROUP BY plataforma_snap ORDER BY neto DESC", (u,)),
        "por_tipo": todos("SELECT tipo, SUM(cantidad) AS piezas, "
                          "SUM(valor_estimado*cantidad) AS valor FROM articulos "
                          "WHERE usuario_id=? AND cantidad>0 GROUP BY tipo", (u,)),
    })


@bp.post("/calculadora/precio-objetivo")
def calcular_precio():
    """¿A cuánto publico para ganar X limpio? El servidor tiene la única fórmula."""
    b = request.get_json(silent=True) or {}
    p = uno("SELECT * FROM plataformas WHERE id=? AND usuario_id=?",
            (b.get("plataforma_id"), g.usuario_id))
    if not p:
        raise ErrorApp("Elige un canal válido")
    return jsonify(
        precio=precio_objetivo(b.get("deseado"), b.get("costo_total"), p,
                               b.get("envio"), b.get("otros")),
        plataforma=p["nombre"])


@bp.get("/exportar")
def exportar():
    datos = {"version": 2, "exportado_en": datetime.now().isoformat(),
             **estado_completo(g.usuario_id)}
    nombre = f"collecthub-{datetime.now():%Y-%m-%d}.json"
    return Response(json.dumps(datos, ensure_ascii=False, indent=2),
                    mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _borrar_todo(usuario_id):
    with transaccion() as con:
        for tabla in TABLAS_USUARIO:
            con.execute(f"DELETE FROM {tabla} WHERE usuario_id=?", (usuario_id,))


@bp.delete("/estado")
def borrar_estado():
    _borrar_todo(g.usuario_id)
    return jsonify(ok=True)


@bp.post("/seed")
def cargar_ejemplo():
    _borrar_todo(g.usuario_id)
    sembrar(g.usuario_id)
    return jsonify(estado_completo(g.usuario_id))
