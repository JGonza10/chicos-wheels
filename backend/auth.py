"""
Login y control de acceso por rol para Chicos Wheels.
Mismo patrón que Sistema GONZA: sesión de Flask + werkzeug para hash de contraseñas.
"""
from functools import wraps
from flask import Blueprint, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Usuario, ROLES

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def requiere_rol(*roles_permitidos):
    """Decorador para proteger rutas por rol. Uso: @requiere_rol('administrador', 'vendedor')"""
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            usuario_id = session.get("usuario_id")
            if not usuario_id:
                return jsonify({"error": "No autenticado"}), 401

            usuario = Usuario.query.get(usuario_id)
            if not usuario or not usuario.activo:
                return jsonify({"error": "Usuario no válido"}), 401

            if roles_permitidos and usuario.rol not in roles_permitidos:
                return jsonify({"error": "No tienes permiso para esta acción"}), 403

            return func(*args, **kwargs)
        return wrapper
    return decorador


@auth_bp.route("/registro", methods=["POST"])
def registro():
    data = request.get_json() or {}
    nombre = data.get("nombre")
    email = data.get("email")
    password = data.get("password")

    if not nombre or not email or not password:
        return jsonify({"error": "Nombre, email y contraseña son obligatorios"}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({"error": "Ese correo ya está registrado"}), 409

    nuevo = Usuario(
        nombre=nombre,
        email=email,
        password_hash=generate_password_hash(password),
        rol="cliente",  # el registro público siempre crea clientes; admin/vendedor se asignan desde el panel
    )
    db.session.add(nuevo)
    db.session.commit()

    session["usuario_id"] = nuevo.id
    return jsonify({"id": nuevo.id, "nombre": nuevo.nombre, "rol": nuevo.rol}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario or not check_password_hash(usuario.password_hash, password):
        return jsonify({"error": "Correo o contraseña incorrectos"}), 401

    if not usuario.activo:
        return jsonify({"error": "Cuenta deshabilitada"}), 403

    session["usuario_id"] = usuario.id
    return jsonify({"id": usuario.id, "nombre": usuario.nombre, "rol": usuario.rol})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/sesion", methods=["GET"])
def sesion_actual():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return jsonify({"autenticado": False})

    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({"autenticado": False})

    return jsonify({
        "autenticado": True,
        "id": usuario.id,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
    })
