"""
CRUD de catálogo: categorías, productos y ofertas.
Lectura pública (para la tienda). Escritura solo administrador/vendedor.
"""
from flask import Blueprint, request, jsonify
from models import db, Producto, Categoria, Oferta
from auth import requiere_rol

catalogo_bp = Blueprint("catalogo", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------------
@catalogo_bp.route("/categorias", methods=["GET"])
def listar_categorias():
    categorias = Categoria.query.all()
    return jsonify([
        {"id": c.id, "nombre": c.nombre, "slug": c.slug, "icono": c.icono}
        for c in categorias
    ])


@catalogo_bp.route("/categorias", methods=["POST"])
@requiere_rol("administrador")
def crear_categoria():
    data = request.get_json() or {}
    categoria = Categoria(nombre=data["nombre"], slug=data["slug"], icono=data.get("icono"))
    db.session.add(categoria)
    db.session.commit()
    return jsonify({"id": categoria.id}), 201


# ---------------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------------
@catalogo_bp.route("/productos", methods=["GET"])
def listar_productos():
    categoria_slug = request.args.get("categoria")
    destacados = request.args.get("destacados")

    query = Producto.query.filter_by(activo=True)
    if categoria_slug:
        query = query.join(Categoria).filter(Categoria.slug == categoria_slug)
    if destacados == "true":
        query = query.filter_by(destacado=True)

    productos = query.all()
    return jsonify([_producto_a_dict(p) for p in productos])


@catalogo_bp.route("/productos/<int:producto_id>", methods=["GET"])
def obtener_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    return jsonify(_producto_a_dict(producto))


@catalogo_bp.route("/productos", methods=["POST"])
@requiere_rol("administrador", "vendedor")
def crear_producto():
    data = request.get_json() or {}
    producto = Producto(
        nombre=data["nombre"],
        descripcion=data.get("descripcion"),
        categoria_id=data["categoria_id"],
        precio=data["precio"],
        precio_anterior=data.get("precio_anterior"),
        stock=data.get("stock", 0),
        edicion_limitada=data.get("edicion_limitada", False),
        destacado=data.get("destacado", False),
        imagen_url=data.get("imagen_url"),
    )
    db.session.add(producto)
    db.session.commit()
    return jsonify({"id": producto.id}), 201


@catalogo_bp.route("/productos/<int:producto_id>", methods=["PUT"])
@requiere_rol("administrador", "vendedor")
def actualizar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    data = request.get_json() or {}
    for campo in ("nombre", "descripcion", "precio", "precio_anterior", "stock",
                  "edicion_limitada", "destacado", "imagen_url", "activo"):
        if campo in data:
            setattr(producto, campo, data[campo])
    db.session.commit()
    return jsonify({"ok": True})


@catalogo_bp.route("/productos/<int:producto_id>", methods=["DELETE"])
@requiere_rol("administrador")
def eliminar_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    producto.activo = False  # baja lógica, nunca borrado físico
    db.session.commit()
    return jsonify({"ok": True})


def _producto_a_dict(p: Producto) -> dict:
    return {
        "id": p.id,
        "nombre": p.nombre,
        "descripcion": p.descripcion,
        "categoria": p.categoria.nombre if p.categoria else None,
        "precio": float(p.precio),
        "precio_anterior": float(p.precio_anterior) if p.precio_anterior else None,
        "descuento": p.porcentaje_descuento,
        "stock": p.stock,
        "edicion_limitada": p.edicion_limitada,
        "destacado": p.destacado,
        "imagen_url": p.imagen_url,
    }
