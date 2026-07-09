"""
Carrito de compras persistente por usuario.
Se guarda en base de datos (no en sesión) para poder mandar recordatorios
de carrito abandonado por correo, como se hace en Sistema GONZA con Resend.
"""
from flask import Blueprint, request, jsonify, session
from models import db, CarritoItem, Producto

carrito_bp = Blueprint("carrito", __name__, url_prefix="/api/carrito")


def _usuario_actual_id():
    return session.get("usuario_id")


@carrito_bp.route("", methods=["GET"])
def ver_carrito():
    usuario_id = _usuario_actual_id()
    if not usuario_id:
        return jsonify({"error": "No autenticado"}), 401

    items = CarritoItem.query.filter_by(usuario_id=usuario_id).all()
    resultado = []
    total = 0
    for item in items:
        producto = Producto.query.get(item.producto_id)
        if not producto:
            continue
        subtotal = float(producto.precio) * item.cantidad
        total += subtotal
        resultado.append({
            "item_id": item.id,
            "producto_id": producto.id,
            "nombre": producto.nombre,
            "precio": float(producto.precio),
            "cantidad": item.cantidad,
            "subtotal": subtotal,
            "imagen_url": producto.imagen_url,
        })

    return jsonify({"items": resultado, "total": round(total, 2)})


@carrito_bp.route("/agregar", methods=["POST"])
def agregar_al_carrito():
    usuario_id = _usuario_actual_id()
    if not usuario_id:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json() or {}
    producto_id = data.get("producto_id")
    cantidad = int(data.get("cantidad", 1))

    producto = Producto.query.get_or_404(producto_id)
    if producto.stock < cantidad:
        return jsonify({"error": f"Solo quedan {producto.stock} unidades disponibles"}), 400

    item = CarritoItem.query.filter_by(usuario_id=usuario_id, producto_id=producto_id).first()
    if item:
        item.cantidad += cantidad
    else:
        item = CarritoItem(usuario_id=usuario_id, producto_id=producto_id, cantidad=cantidad)
        db.session.add(item)

    db.session.commit()
    return jsonify({"ok": True})


@carrito_bp.route("/item/<int:item_id>", methods=["PUT"])
def actualizar_cantidad(item_id):
    usuario_id = _usuario_actual_id()
    item = CarritoItem.query.get_or_404(item_id)
    if item.usuario_id != usuario_id:
        return jsonify({"error": "No autorizado"}), 403

    data = request.get_json() or {}
    nueva_cantidad = int(data.get("cantidad", item.cantidad))
    if nueva_cantidad <= 0:
        db.session.delete(item)
    else:
        item.cantidad = nueva_cantidad
    db.session.commit()
    return jsonify({"ok": True})


@carrito_bp.route("/item/<int:item_id>", methods=["DELETE"])
def eliminar_item(item_id):
    usuario_id = _usuario_actual_id()
    item = CarritoItem.query.get_or_404(item_id)
    if item.usuario_id != usuario_id:
        return jsonify({"error": "No autorizado"}), 403

    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})
