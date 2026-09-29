"""Categorías de piezas: Hot Wheels y Pokémon (fijas, con formulario propio)
más las que agrega cada cuenta (Barbie, etc.) en la tabla `categorias`."""
from .db import todos

TIPOS_BASE = ("Hot Wheels", "Pokémon")
# Toda cuenta arranca con estas (se pueden borrar si no tienen piezas).
INICIALES = (("Barbie", "💖"),)


def tipos_de(usuario_id: str, con=None) -> tuple:
    """Categorías válidas para esa cuenta, en el orden en que se muestran."""
    sql = "SELECT nombre FROM categorias WHERE usuario_id=? ORDER BY creado_en, nombre"
    filas = con.execute(sql, (usuario_id,)).fetchall() if con is not None else todos(sql, (usuario_id,))
    return TIPOS_BASE + tuple(f["nombre"] for f in filas)


def prefijo_id(tipo: str) -> str:
    return {"Pokémon": "PKM", "Hot Wheels": "HW"}.get(tipo, "CO")
