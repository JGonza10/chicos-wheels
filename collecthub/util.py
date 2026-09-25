"""Validaciones, fórmulas de negocio y el error que se traduce a HTTP 4xx."""
import re
import secrets
import threading
import time
from datetime import date


class ErrorApp(Exception):
    """Error esperado, con mensaje pensado para que lo lea una persona."""

    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


_ALFA36 = "0123456789abcdefghijklmnopqrstuvwxyz"
_contador = 0
_candado = threading.Lock()


def _base36(n: int, ancho: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _ALFA36[r] + out
    return out[-ancho:].rjust(ancho, "0")


def uid(prefijo: str) -> str:
    """Identificador legible: HW-K3F9A00C7B.

    Marca de tiempo + contador del proceso + azar. El contador garantiza que dos
    ids creados en el mismo milisegundo (una importación de cientos de filas, los
    datos de ejemplo) nunca choquen; el azar cubre a varios procesos con la misma base.
    """
    global _contador
    with _candado:
        _contador = (_contador + 1) % (36 ** 3)
        c = _contador
    return f"{prefijo}-{_base36(int(time.time() * 1000), 5)}{_base36(c, 3)}{secrets.token_hex(2)[:3]}".upper()


def num(v, defecto: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else defecto  # descarta NaN e infinito
    except (TypeError, ValueError):
        return defecto


def entero(v, defecto: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return defecto


def texto(v, largo: int = 500) -> str:
    return "" if v is None else str(v)[:largo].strip()


def hoy() -> str:
    return date.today().isoformat()


def fecha(v) -> str:
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v or "")) else hoy()


def precio_objetivo(deseado, costo_total, plataforma, envio=0, otros=0) -> float:
    """¿A cuánto publico para que me queden X limpios?"""
    divisor = 1 - num(plataforma["com_pct"]) - num(plataforma["ret_pct"])
    if divisor <= 0:
        return 0.0
    return (num(deseado) + num(costo_total) + num(plataforma["com_fija"])
            + num(envio) + num(otros)) / divisor
