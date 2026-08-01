#!/usr/bin/env python3
"""
Punto de entrada. Para uso local:

    python app.py

En producción usa un servidor WSGI, por ejemplo:

    gunicorn "collecthub:crear_app()" -b 0.0.0.0:3000
"""
import os
from pathlib import Path

# Carga las variables de .env si el archivo existe. Sin dependencias extra.
_env = Path(__file__).resolve().parent / ".env"
if _env.is_file():
    for linea in _env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, _, valor = linea.partition("=")
            os.environ.setdefault(clave.strip(), valor.strip())

from collecthub import crear_app  # noqa: E402  (después de cargar .env)
from collecthub.db import RUTA_BD  # noqa: E402

app = crear_app()

if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 3000))
    print(f"\n  CollectHub corriendo en http://localhost:{puerto}")
    print(f"  Base de datos: {RUTA_BD}\n")
    app.run(host="0.0.0.0", port=puerto, debug=os.environ.get("FLASK_ENV") == "development")
