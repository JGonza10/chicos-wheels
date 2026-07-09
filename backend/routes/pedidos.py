"""
Checkout con Mercado Pago.

Dos flujos:
1. checkout()        -> el cliente paga desde su carrito en la tienda online.
2. cobro_directo()    -> el administrador/vendedor cobra en el momento leyendo
                          el código de barras, el QR o la clave hablada del
                          producto (usado en /api/productos/buscar-codigo),
                          sin que el cliente tenga que pasar por el carrito.

Requiere la variable de entorno MP_ACCESS_TOKEN (token de Mercado Pago).
"""
import os
import mercadopago
from flask import Blueprint, request, jsonify, session

from models import db, CarritoItem, Producto, Pedido, DetallePedido
from auth import requiere_rol

pedidos_bp = Blueprint("pedidos", __name__, url_prefix="/api/pedidos")

_sdk = None


def _mp_sdk():
    global _sdk
    if _sdk is None:
        _sdk = mercadopago.SDK(os.environ["MP_ACCESS_TOKEN"])
    return _sdk


def _crear_preferencia(items_mp, referencia_externa, url_base):
    preference_data = {
        "items": items_mp,
        "external_reference": referencia_externa,
        "back_urls": {
            "success": f"{url_base}/pago-exitoso",
            "failure": f"{url_base}/pago-fallido",
            "pending": f"{url_base}/pago-pendiente",
        },
        "auto_return": "approved",
        "notification_url": f"{os.environ.get('BACKEND_URL', '')}/api/pedidos/webhook",
    }
    return _mp_sdk().preference().create(preference_data)["response"]


@pedidos_bp.route("/checkout", methods=["POST"])
def checkout():
    """El cliente confirma su carrito y se genera el link de pago de Mercado Pago."""
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return jsonify({"error": "No autenticado"}), 401

    items_carrito = CarritoItem.query.filter_by(usuario_id=usuario_id).all()
    if not items_carrito:
        return jsonify({"error": "El carrito está vacío"}), 400

    pedido = Pedido(usuario_id=usuario_id, estado="pendiente", metodo_pago="mercado_pago", total=0)
    db.session.add(pedido)
    db.session.flush()  # para obtener pedido.id antes del commit

    items_mp = []
    total = 0
    for item in items_carrito:
        producto = Producto.query.get(item.producto_id)
        if not producto or producto.stock < item.cantidad:
            db.session.rollback()
            nombre = producto.nombre if producto else "producto"
            return jsonify({"error": f"Stock insuficiente de {nombre}"}), 400

        detalle = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio,
        )
        db.session.add(detalle)
        subtotal = float(producto.precio) * item.cantidad
        total += subtotal

        items_mp.append({
            "title": producto.nombre,
            "quantity": item.cantidad,
            "unit_price": float(producto.precio),
            "currency_id": "MXN",
        })

    pedido.total = round(total, 2)
    db.session.commit()

    respuesta_mp = _crear_preferencia(
        items_mp,
        referencia_externa=f"pedido-{pedido.id}",
        url_base=os.environ.get("FRONTEND_URL", ""),
    )

    return jsonify({
        "pedido_id": pedido.id,
        "total": pedido.total,
        "link_pago": respuesta_mp["init_point"],
    }), 201


@pedidos_bp.route("/cobro-directo", methods=["POST"])
@requiere_rol("administrador", "vendedor")
def cobro_directo():
    """
    Cobro en el momento desde el panel: se arma con productos identificados
    por código de barras, QR o clave de voz (ya resueltos por el frontend
    contra /api/productos/buscar-codigo).

    Body esperado: { "items": [{"producto_id": 12, "cantidad": 1}, ...] }
    """
    data = request.get_json() or {}
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "No se recibieron productos para cobrar"}), 400

    pedido = Pedido(
        usuario_id=session.get("usuario_id"),
        estado="pendiente",
        metodo_pago="mercado_pago",
        total=0,
    )
    db.session.add(pedido)
    db.session.flush()

    items_mp = []
    total = 0
    for entrada in items:
        producto = Producto.query.get(entrada["producto_id"])
        cantidad = int(entrada.get("cantidad", 1))
        if not producto or producto.stock < cantidad:
            db.session.rollback()
            return jsonify({"error": "Stock insuficiente para uno de los productos escaneados"}), 400

        db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=producto.id,
            cantidad=cantidad, precio_unitario=producto.precio,
        ))
        total += float(producto.precio) * cantidad
        items_mp.append({
            "title": producto.nombre, "quantity": cantidad,
            "unit_price": float(producto.precio), "currency_id": "MXN",
        })

    pedido.total = round(total, 2)
    db.session.commit()

    respuesta_mp = _crear_preferencia(
        items_mp, referencia_externa=f"pedido-{pedido.id}",
        url_base=os.environ.get("FRONTEND_URL", ""),
    )

    return jsonify({
        "pedido_id": pedido.id,
        "total": pedido.total,
        "link_pago": respuesta_mp["init_point"],
    }), 201


@pedidos_bp.route("/webhook", methods=["POST"])
def webhook_mercado_pago():
    """Mercado Pago notifica aquí cuando cambia el estado de un pago."""
    data = request.get_json() or {}
    if data.get("type") != "payment":
        return jsonify({"ok": True})

    pago_id = data["data"]["id"]
    pago = _mp_sdk().payment().get(pago_id)["response"]

    referencia = pago.get("external_reference", "")
    if not referencia.startswith("pedido-"):
        return jsonify({"ok": True})

    pedido_id = int(referencia.replace("pedido-", ""))
    pedido = Pedido.query.get(pedido_id)
    if not pedido:
        return jsonify({"ok": True})

    if pago["status"] == "approved" and pedido.estado != "pagado":
        pedido.estado = "pagado"
        pedido.referencia_pago = str(pago_id)
        for detalle in pedido.detalles:
            producto = Producto.query.get(detalle.producto_id)
            if producto:
                producto.stock = max(0, producto.stock - detalle.cantidad)
        # limpiar el carrito del cliente si el pedido vino de la tienda online
        CarritoItem.query.filter_by(usuario_id=pedido.usuario_id).delete()
        db.session.commit()
    elif pago["status"] in ("rejected", "cancelled"):
        pedido.estado = "cancelado"
        db.session.commit()

    return jsonify({"ok": True})
