"""Stock público para la landing page (carpeta `landing page/`, servida en /tienda).

La landing solo muestra lo que hay a la venta. Este módulo arma ese stock al
momento desde la base, con una lista blanca de campos (lo que ve un comprador):
nunca costo, ganancia, fuente, ubicación, notas, código, id interno ni nada de
clientes. Sale lo Disponible con existencias libres; lo que viene en camino
(ubicación "Por recibir") sale también, marcado "Por llegar" con su fecha
aproximada de llegada, para que se pueda apartar antes de que llegue.

Se enciende con LANDING_EMAIL (la cuenta cuyo inventario se muestra). Sin esa
variable, la landing usa las piezas de ejemplo de `landing page/stock.js`.
"""
import hashlib
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from .catalogo import _host_permitido
from .db import RUTA_BD, todos, uno

CARPETA_LANDING = Path(__file__).resolve().parent.parent / "landing page"

CAMPOS = ("tipo", "nombre", "numero", "anio", "serie", "color", "expansion",
          "rareza", "grado", "estado", "grail", "disponible")

SQL_STOCK = ("SELECT * FROM v_articulos WHERE usuario_id=? AND estatus='Disponible' "
             "AND disponible > 0 ORDER BY creado_en DESC")

DIAS_ENVIO = 14   # sin fecha anotada, se estima compra + 14 días (igual que DIAS_ENVIO en app.js)


def por_llegar(a: dict) -> bool:
    return (a.get("ubicacion") or "").strip().lower() == "por recibir"


def llegada(a: dict) -> str:
    """Fecha aproximada de llegada (YYYY-MM-DD): la anotada o compra + DIAS_ENVIO.
    Si ya pasó y sigue sin llegar, se da por hoy (no se publica una fecha vencida)."""
    f = a.get("fecha_llegada") or ""
    if not f:
        base = (a.get("fecha_adq") or a.get("creado_en") or "")[:10]
        try:
            f = (date.fromisoformat(base) + timedelta(days=DIAS_ENVIO)).isoformat()
        except ValueError:
            f = (date.today() + timedelta(days=DIAS_ENVIO)).isoformat()
    return max(f, date.today().isoformat())


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


def publica(a: dict) -> dict:
    """Lo que un comprador puede ver de una pieza (lista blanca de campos)."""
    p = {k: a.get(k) for k in CAMPOS}
    p["id"] = id_publico(a["id"])
    p["grail"] = int(a.get("grail") or 0)
    p["precio"] = a.get("valor_estimado") or 0
    p["fecha"] = (a.get("creado_en") or "")[:10]
    p["por_llegar"] = por_llegar(a)
    p["llega"] = llegada(a) if p["por_llegar"] else ""
    foto = a.get("foto") or ""
    if foto.startswith("http://"):  # piezas guardadas antes de normalizar a https
        foto = "https://" + foto[7:]
    if foto.startswith("local:"):
        p["foto"] = f"foto/{p['id']}.jpg"
    elif _host_permitido(foto):
        p["foto"] = foto
    else:
        p["foto"] = ""
    return p


def stock(usuario_id: str) -> dict:
    piezas = [publica(a) for a in todos(SQL_STOCK, (usuario_id,))]
    # Categorías propias de la cuenta (Barbie, …): la tienda arma sus filtros con
    # ellas en automático y solo muestra las que tienen piezas a la venta.
    categorias = todos("SELECT nombre, emoji FROM categorias WHERE usuario_id=? "
                       "ORDER BY creado_en, nombre", (usuario_id,))
    return {"generado": datetime.now().strftime("%Y-%m-%d %H:%M"), "muestra": False,
            "contacto": contacto(), "categorias": categorias, "piezas": piezas,
            "asistente": True}


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
