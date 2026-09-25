"""Respaldo automático diario de la base de datos.

Usa la API de respaldo de SQLite (consistente aunque la app esté en uso). Guarda un
archivo por día en datos/respaldos y conserva los últimos 14. Un hilo revisa cada
hora si ya existe el de hoy. Se apaga con COLLECTHUB_SIN_RESPALDO=1.
"""
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .db import RUTA_BD

CONSERVAR = 14
_iniciado = False


def carpeta() -> Path:
    return RUTA_BD.parent / "respaldos"


def hacer_respaldo(forzar: bool = False):
    """Crea el respaldo de hoy si no existe. Devuelve la ruta creada o None."""
    if not RUTA_BD.exists():
        return None
    destino = carpeta()
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"collecthub-{datetime.now():%Y-%m-%d}.db"
    if archivo.exists() and not forzar:
        return None
    origen = sqlite3.connect(RUTA_BD)
    copia = sqlite3.connect(archivo)
    try:
        with copia:
            origen.backup(copia)
    finally:
        copia.close()
        origen.close()
    for viejo in sorted(destino.glob("collecthub-*.db"))[:-CONSERVAR]:
        viejo.unlink(missing_ok=True)
    return archivo


def _bucle():
    import time
    while True:
        try:
            hacer_respaldo()
        except Exception as e:  # nunca tumbar la app por un respaldo
            print(f"⚠️ Respaldo automático falló: {e}")
        time.sleep(3600)


def iniciar():
    global _iniciado
    if _iniciado or os.environ.get("COLLECTHUB_SIN_RESPALDO") == "1":
        return
    _iniciado = True
    threading.Thread(target=_bucle, name="respaldo-diario", daemon=True).start()
