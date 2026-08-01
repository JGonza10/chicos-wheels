"""Sesiones con JWT y el decorador que protege las rutas."""
import os
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, request

from .util import ErrorApp

SECRETO = os.environ.get("JWT_SECRET", "cambia-esta-llave-en-produccion")
DIAS_VIGENCIA = int(os.environ.get("JWT_DIAS", "30"))

if os.environ.get("FLASK_ENV") == "production" and not os.environ.get("JWT_SECRET"):
    print("\n  ⚠  Falta JWT_SECRET. En producción es obligatorio: defínelo y reinicia.\n",
          file=sys.stderr)
    sys.exit(1)


def firmar(usuario: dict) -> str:
    carga = {
        "uid": usuario["id"],
        "email": usuario["email"],
        "exp": datetime.now(timezone.utc) + timedelta(days=DIAS_VIGENCIA),
    }
    token = jwt.encode(carga, SECRETO, algorithm="HS256")
    return token.decode() if isinstance(token, bytes) else token  # PyJWT 1.x devolvía bytes


def requiere_sesion(fn):
    """Exige un token válido y deja g.usuario_id listo para la vista."""
    @wraps(fn)
    def envoltura(*args, **kwargs):
        cabecera = request.headers.get("Authorization", "")
        token = cabecera[7:] if cabecera.startswith("Bearer ") else None
        if not token:
            raise ErrorApp("Inicia sesión para continuar", 401)
        try:
            g.usuario_id = jwt.decode(token, SECRETO, algorithms=["HS256"])["uid"]
        except jwt.PyJWTError:
            raise ErrorApp("Tu sesión expiró, vuelve a entrar", 401)
        return fn(*args, **kwargs)
    return envoltura
