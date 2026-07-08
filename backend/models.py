"""
Modelos de base de datos para Chicos Wheels.
Patrón: Flask + SQLAlchemy + PostgreSQL (Railway), igual a Sistema GONZA.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ---------------------------------------------------------------------------
# Roles disponibles en el sistema
# ---------------------------------------------------------------------------
ROLES = ("administrador", "vendedor", "cliente")


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="cliente")  # administrador | vendedor | cliente
    telefono = db.Column(db.String(20))
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    pedidos = db.relationship("Pedido", backref="cliente", lazy=True)
    resenas = db.relationship("Resena", backref="autor", lazy=True)


class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)          # Hot Wheels, Pokémon TCG, Accesorios...
    slug = db.Column(db.String(80), unique=True, nullable=False)
    icono = db.Column(db.String(50))                            # nombre de icono (ej. "ti-car")

    productos = db.relationship("Producto", backref="categoria", lazy=True)


class Producto(db.Model):
    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=False)

    precio = db.Column(db.Numeric(10, 2), nullable=False)
    precio_anterior = db.Column(db.Numeric(10, 2))              # para mostrar anclaje de precio (tachado)
    stock = db.Column(db.Integer, nullable=False, default=0)

    edicion_limitada = db.Column(db.Boolean, default=False)
    destacado = db.Column(db.Boolean, default=False)            # aparece en "destacados con descuento"
    imagen_url = db.Column(db.String(255))

    codigo_barras = db.Column(db.String(50), unique=True, index=True)   # EAN/UPC físico del producto
    clave_producto = db.Column(db.String(30), unique=True, index=True)  # clave corta legible por voz, ej. "HW-1024"

    activo = db.Column(db.Boolean, default=True)
    creado_por = db.Column(db.Integer, db.ForeignKey("usuarios.id"))  # administrador o vendedor que lo cargó
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    resenas = db.relationship("Resena", backref="producto", lazy=True)

    @property
    def porcentaje_descuento(self):
        if self.precio_anterior and self.precio_anterior > self.precio:
            return round((1 - float(self.precio) / float(self.precio_anterior)) * 100)
        return 0


class Oferta(db.Model):
    """Ofertas por tiempo limitado (para el banner de urgencia/escasez)."""
    __tablename__ = "ofertas"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.String(255))
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"))
    fecha_inicio = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_fin = db.Column(db.DateTime, nullable=False)
    activa = db.Column(db.Boolean, default=True)


class Pedido(db.Model):
    __tablename__ = "pedidos"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default="pendiente")   # pendiente | pagado | enviado | entregado | cancelado
    metodo_pago = db.Column(db.String(30))                    # mercado_pago | stripe
    referencia_pago = db.Column(db.String(120))               # id de transacción de la pasarela
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    detalles = db.relationship("DetallePedido", backref="pedido", lazy=True, cascade="all, delete-orphan")


class DetallePedido(db.Model):
    __tablename__ = "detalle_pedidos"

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedidos.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)  # precio al momento de la compra

    producto = db.relationship("Producto")


class Resena(db.Model):
    __tablename__ = "resenas"

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    calificacion = db.Column(db.Integer, nullable=False)  # 1-5
    comentario = db.Column(db.Text)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)


class CarritoItem(db.Model):
    """Carrito persistente por usuario (para poder mandar recordatorios de carrito abandonado)."""
    __tablename__ = "carrito_items"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    fecha_agregado = db.Column(db.DateTime, default=datetime.utcnow)
