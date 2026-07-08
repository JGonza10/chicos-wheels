"""
CRUD de catálogo: categorías, productos y ofertas.
Lectura pública (para la tienda). Escritura solo administrador/vendedor.
"""
from flask import Blueprint, request, jsonify
from models import db, Producto, Categoria, Oferta
from auth import requiere_rol
from social_publicar import publicar_oferta

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


@catalogo_bp.route("/productos/buscar-codigo", methods=["GET"])
def buscar_por_codigo():
    """
    Búsqueda para cobro rápido en el panel de administrador/vendedor.
    Un solo endpoint sirve a los 3 métodos de entrada:
      - Escáner de código de barras -> manda el EAN/UPC leído en ?codigo=
      - Escáner de QR -> el QR del producto codifica su clave_producto, se manda igual en ?codigo=
      - Voz -> el frontend convierte el audio a texto (Web Speech API) y normaliza
        la clave leída (ej. "H W guión mil veinticuatro" -> "HW-1024") antes de mandarla aquí.
    """
    codigo = (request.args.get("codigo") or "").strip().upper()
    if not codigo:
        return jsonify({"error": "Falta el parámetro codigo"}), 400

    producto = Producto.query.filter(
        (Producto.codigo_barras == codigo) | (Producto.clave_producto == codigo)
    ).filter_by(activo=True).first()

    if not producto:
        return jsonify({"error": "No se encontró ningún producto con ese código"}), 404

    return jsonify(_producto_a_dict(producto))


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


# ---------------------------------------------------------------------------
# Ofertas (publican automáticamente en Facebook/Instagram al crearse)
# ---------------------------------------------------------------------------
@catalogo_bp.route("/ofertas", methods=["GET"])
def listar_ofertas():
    ofertas = Oferta.query.filter_by(activa=True).all()
    return jsonify([
        {
            "id": o.id, "titulo": o.titulo, "descripcion": o.descripcion,
            "producto_id": o.producto_id, "fecha_fin": o.fecha_fin.isoformat(),
        }
        for o in ofertas
    ])


@catalogo_bp.route("/ofertas", methods=["POST"])
@requiere_rol("administrador")
def crear_oferta():
    data = request.get_json() or {}
    oferta = Oferta(
        titulo=data["titulo"],
        descripcion=data.get("descripcion"),
        producto_id=data.get("producto_id"),
        fecha_fin=data["fecha_fin"],
    )
    db.session.add(oferta)
    db.session.commit()

    resultado_publicacion = None
    if oferta.producto_id:
        producto = Producto.query.get(oferta.producto_id)
        if producto and producto.imagen_url:
            resultado_publicacion = publicar_oferta(
                titulo=oferta.titulo,
                descripcion=oferta.descripcion or "",
                imagen_url=producto.imagen_url,
                link_producto=f"{request.host_url}producto/{producto.id}",
            )

    return jsonify({"id": oferta.id, "redes_sociales": resultado_publicacion}), 201


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
        "codigo_barras": p.codigo_barras,
        "clave_producto": p.clave_producto,
    }
