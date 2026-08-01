#!/usr/bin/env python3
"""
Respaldo en caliente de la base de datos.

SQLite no se debe copiar con `cp` mientras hay escrituras: se usa la API de
respaldo del motor, que produce un archivo consistente aunque la app esté en uso.

    python scripts/backup.py
    python scripts/backup.py /ruta/donde/guardar
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from collecthub.db import RUTA_BD  # noqa: E402


def main():
    if not RUTA_BD.exists():
        print(f"No encuentro la base en {RUTA_BD}. ¿Ya arrancaste la app al menos una vez?")
        return 1

    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "respaldos"
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"collecthub-{datetime.now():%Y-%m-%dT%H-%M-%S}.db"

    origen = sqlite3.connect(RUTA_BD)
    copia = sqlite3.connect(archivo)
    with copia:
        origen.backup(copia)
    copia.close()
    origen.close()

    mb = archivo.stat().st_size / 1048576
    print(f"Respaldo listo: {archivo} ({mb:.2f} MB)")
    print(f"Origen: {RUTA_BD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
