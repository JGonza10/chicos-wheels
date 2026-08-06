"""Sesiones con JWT y el decorador que protege las rutas."""
import os
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, request

from .util import ErrorApp

SECRETO = os.environ.get("JWT_SECRET", "")
DIAS_VIGENCIA = int(os.environ.get("JWT_DIAS", "30"))

# Obligatoria siempre, no solo cuando FLASK_ENV=="production": ese valor
# depende de que quien despliegue lo haya puesto correctamente, y si se le
# olvida (o cambia la forma de arrancar la app) la app seguía funcionando en
# silencio con una llave que cualquiera puede leer en este mismo archivo del
# repositorio público — quien la conozca puede firmar un token válido para
# cualquier usuario. Sin la variable, la app se niega a arrancar.
if not SECRETO:
    print("\n  ⚠  Falta JWT_SECRET. Es obligatoria: defínela y reinicia.\n"
          "     Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\"\n",
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
