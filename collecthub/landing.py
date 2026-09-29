"""Stock público para la landing page (carpeta `landing page/`, servida en /tienda).

La landing solo muestra lo que hay a la venta. Este módulo arma ese stock al
momento desde la base, con una lista blanca de campos (lo que ve un comprador):
nunca costo, ganancia, fuente, ubicación, notas, código, id interno ni nada de
clientes. Mismo criterio de venta que el catálogo PDF: Disponible, con
existencias libres y ya recibida.

Se enciende con LANDING_EMAIL (la cuenta cuyo inventario se muestra). Sin esa
variable, la landing usa las piezas de ejemplo de `landing page/stock.js`.
"""
import hashlib
import os
from datetime import datetime
from pathlib import Path

from .catalogo import _host_permitido
from .db import RUTA_BD, todos, uno

CARPETA_LANDING = Path(__file__).resolve().parent.parent / "landing page"

CAMPOS = ("tipo", "nombre", "numero", "anio", "serie", "color", "expansion",
          "rareza", "grado", "estado", "grail", "disponible")

SQL_STOCK = ("SELECT * FROM v_articulos WHERE usuario_id=? AND estatus='Disponible' "
             "AND disponible > 0 AND ubicacion <> 'Por recibir' ORDER BY creado_en DESC")


def id_publico(id_art: str) -> str:
    """Id que se publica: estable, pero sin relación visible con el id interno."""
    return hashlib.sha256(f"cw-landing:{id_art}".encode()).hexdigest()[:16]


def dueno() -> str | None:
    """Usuario cuyo inventario se muestra, según LANDING_EMAIL. None = apagado."""
    email = (os.environ.get("LANDING_EMAIL") or "").strip().lower()
    if not email:
        return None
    fila = uno("SELECT id FROM usuarios WHERE lower(email)=?", (email,))
    return fila["id"] if fila else None


def _usuario_red(valor: str) -> str:
    """Acepta 'chicoswheels', '@chicoswheels' o una URL completa y deja solo el usuario."""
    v = (valor or "").strip().rstrip("/")
    v = v.split("?")[0].rsplit("/", 1)[-1].lstrip("@")
    return "".join(c for c in v if c.isalnum() or c in "._-")


def contacto() -> dict:
    return {"facebook": _usuario_red(os.environ.get("LANDING_FACEBOOK", "")),
            "instagram": _usuario_red(os.environ.get("LANDING_INSTAGRAM", ""))}


def stock(usuario_id: str) -> dict:
    piezas = []
    for a in todos(SQL_STOCK, (usuario_id,)):
        p = {k: a.get(k) for k in CAMPOS}
        p["id"] = id_publico(a["id"])
        p["grail"] = int(a.get("grail") or 0)
        p["precio"] = a.get("valor_estimado") or 0
        p["fecha"] = (a.get("creado_en") or "")[:10]
        foto = a.get("foto") or ""
        if foto.startswith("http://"):  # piezas guardadas antes de normalizar a https
            foto = "https://" + foto[7:]
        if foto.startswith("local:"):
            p["foto"] = f"foto/{p['id']}.jpg"
        elif _host_permitido(foto):
            p["foto"] = foto
        else:
            p["foto"] = ""
        piezas.append(p)
    # Categorías propias de la cuenta (Barbie, …): la tienda arma sus filtros con
    # ellas en automático y solo muestra las que tienen piezas a la venta.
    categorias = todos("SELECT nombre, emoji FROM categorias WHERE usuario_id=? "
                       "ORDER BY creado_en, nombre", (usuario_id,))
    return {"generado": datetime.now().strftime("%Y-%m-%d %H:%M"), "muestra": False,
            "contacto": contacto(), "categorias": categorias, "piezas": piezas}


def archivo_foto(usuario_id: str, pid: str) -> Path | None:
    """Ruta de la foto local de una pieza que está hoy a la venta; None si no aplica."""
    for a in todos(SQL_STOCK, (usuario_id,)):
        if id_publico(a["id"]) == pid:
            foto = a.get("foto") or ""
            if not foto.startswith("local:"):
                return None
            ruta = RUTA_BD.parent / "fotos" / usuario_id / foto[len("local:"):]
            return ruta if ruta.is_file() else None
    return None
