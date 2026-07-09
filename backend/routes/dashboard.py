"""
Dashboard de ventas. Todo se agrega en el backend (no en el cliente),
igual que en Sistema GONZA, para no exponer todos los pedidos crudos.
"""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from sqlalchemy import func

from models import db, Pedido, DetallePedido, Producto
from auth import requiere_rol

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("/resumen", methods=["GET"])
@requiere_rol("administrador", "vendedor")
def resumen():
    ventas_pagadas = Pedido.query.filter_by(estado="pagado")

    total_ventas = db.session.query(func.coalesce(func.sum(Pedido.total), 0)) \
        .filter(Pedido.estado == "pagado").scalar()
    total_pedidos = ventas_pagadas.count()

    por_estado = dict(
        db.session.query(Pedido.estado, func.count(Pedido.id)).group_by(Pedido.estado).all()
    )

    hace_7_dias = datetime.utcnow() - timedelta(days=7)
    ventas_por_dia = db.session.query(
        func.date(Pedido.fecha), func.coalesce(func.sum(Pedido.total), 0)
    ).filter(Pedido.estado == "pagado", Pedido.fecha >= hace_7_dias) \
     .group_by(func.date(Pedido.fecha)).order_by(func.date(Pedido.fecha)).all()

    mas_vendidos = db.session.query(
        Producto.nombre, func.coalesce(func.sum(DetallePedido.cantidad), 0).label("unidades")
    ).join(DetallePedido, DetallePedido.producto_id == Producto.id) \
     .join(Pedido, Pedido.id == DetallePedido.pedido_id) \
     .filter(Pedido.estado == "pagado") \
     .group_by(Producto.nombre).order_by(func.sum(DetallePedido.cantidad).desc()).limit(5).all()

    return jsonify({
        "total_ventas": float(total_ventas),
        "total_pedidos": total_pedidos,
        "por_estado": por_estado,
        "ventas_por_dia": [{"fecha": str(f), "total": float(t)} for f, t in ventas_por_dia],
        "mas_vendidos": [{"nombre": n, "unidades": int(u)} for n, u in mas_vendidos],
    })
