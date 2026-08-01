"""Registro, inicio de sesión y consulta de la cuenta activa."""
import re

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import firmar, requiere_sesion
from ..db import bd, transaccion, uno
from ..util import ErrorApp, texto, uid

bp = Blueprint("auth", __name__)

CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PLATAFORMAS_INICIALES = [
    ("ML", "Mercado Libre", 0.13, 25, 0, "Verifica tu tarifa real por categoría y precio."),
    ("EB", "eBay", 0.1325, 0, 0, "Incluye la tarifa de pago internacional."),
    ("FB", "Facebook Marketplace", 0, 0, 0, "Venta directa, sin comisión."),
    ("BZ", "Bazar / Convención", 0, 150, 0, "Costo de la mesa prorrateado."),
]


def _crear_cuenta(email: str, hash_pwd: str, nombre: str) -> dict:
    """Toda cuenta nueva arranca con ajustes y canales de venta usables."""
    uid_usuario = uid("U")
    with transaccion() as con:
        con.execute("INSERT INTO usuarios (id,email,password_hash,nombre) VALUES (?,?,?,?)",
                    (uid_usuario, email, hash_pwd, nombre))
        con.execute("INSERT INTO ajustes (usuario_id) VALUES (?)", (uid_usuario,))
        for codigo, nom, pct, fija, ret, nota in PLATAFORMAS_INICIALES:
            con.execute(
                "INSERT INTO plataformas (id,usuario_id,codigo,nombre,com_pct,com_fija,ret_pct,notas) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (uid("P"), uid_usuario, codigo, nom, pct, fija, ret, nota))
    return uno("SELECT id,email,nombre FROM usuarios WHERE id=?", (uid_usuario,))


@bp.post("/registro")
def registro():
    datos = request.get_json(silent=True) or {}
    email = texto(datos.get("email"), 160).lower()
    password = str(datos.get("password") or "")
    nombre = texto(datos.get("nombre"), 80) or email.split("@")[0]

    if not CORREO.fullmatch(email):
        raise ErrorApp("Escribe un correo válido")
    if len(password) < 8:
        raise ErrorApp("La contraseña necesita al menos 8 caracteres")
    if uno("SELECT 1 FROM usuarios WHERE email=?", (email,)):
        raise ErrorApp("Ese correo ya tiene una cuenta. Inicia sesión.", 409)

    usuario = _crear_cuenta(email, generate_password_hash(password), nombre)
    return jsonify(token=firmar(usuario), usuario=usuario), 201


@bp.post("/login")
def login():
    datos = request.get_json(silent=True) or {}
    email = texto(datos.get("email"), 160).lower()
    fila = uno("SELECT * FROM usuarios WHERE email=?", (email,))
    # Mismo mensaje en ambos casos: no revelamos qué correos existen.
    if not fila or not check_password_hash(fila["password_hash"], str(datos.get("password") or "")):
        raise ErrorApp("Correo o contraseña incorrectos", 401)
    usuario = {"id": fila["id"], "email": fila["email"], "nombre": fila["nombre"]}
    return jsonify(token=firmar(usuario), usuario=usuario)


@bp.get("/yo")
@requiere_sesion
def yo():
    usuario = uno("SELECT id,email,nombre,creado_en FROM usuarios WHERE id=?", (g.usuario_id,))
    if not usuario:
        raise ErrorApp("Cuenta no encontrada", 404)
    return jsonify(usuario=usuario)
