"""Validaciones, fórmulas de negocio y el error que se traduce a HTTP 4xx."""
import re
import secrets
import time
from datetime import date


class ErrorApp(Exception):
    """Error esperado, con mensaje pensado para que lo lea una persona."""

    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def uid(prefijo: str) -> str:
    """Identificador legible y estable: HW-K3F9A2C"""
    base36 = ""
    n = int(time.time() * 1000)
    while n:
        n, r = divmod(n, 36)
        base36 = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + base36
    return f"{prefijo}-{base36[-5:]}{secrets.token_hex(2)[:3]}".upper()


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
