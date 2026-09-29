"""Lista de espera de clientes (`pedidos_cliente`): quién espera una pieza.

Dos clases de registro:
- una pieza concreta ("Skyline R32") → coincide si la pieza tiene al menos
  la mitad (máx. 2) de sus palabras;
- "Novedades: <categoría>" (de la tienda) → coincide con cualquier pieza de esa
  categoría ("Todas" = cualquiera).

La misma regla vive en `pedidosPara()` de static/app.js; si cambias una, cambia la otra.
"""
import re

from .asistente import _plano, _raiz, avisar_dueno, palabras
from .db import todos

PREFIJO_NOVEDADES = "novedades"
IGNORAR = {"desde", "tienda"}


def _categoria_novedades(desc: str) -> str | None:
    """'Novedades: Barbie (desde la tienda)' → 'barbie'; None si no es de novedades."""
    d = _plano(desc).strip()
    if not d.startswith(PREFIJO_NOVEDADES):
        return None
    resto = re.sub(r"\(.*?\)", "", d[len(PREFIJO_NOVEDADES):]).strip(" :-")
    return "" if resto in ("", "todas", "todo", "cualquiera") else resto


def coincide(desc: str, a: dict) -> bool:
    cat = _categoria_novedades(desc)
    if cat is not None:
        return cat == "" or cat == _plano(a.get("tipo"))
    consulta = [p for p in palabras(desc) if p not in IGNORAR]
    if not consulta:
        return False
    texto = " ".join(str(a.get(k) or "") for k in ("nombre", "numero", "serie", "color", "expansion", "tipo"))
    pal = {_raiz(p) for p in re.findall(r"[a-z0-9]+", _plano(texto))}
    n = sum(1 for q in consulta if q in pal or (len(q) >= 3 and any(p.startswith(q) for p in pal)))
    return n >= min(2, len(consulta))


def esperan(usuario_id: str, a: dict) -> list:
    """Registros abiertos de la lista de espera que coinciden con la pieza."""
    filas = todos("SELECT p.*, c.nombre AS cliente, c.tel AS contacto FROM pedidos_cliente p "
                  "LEFT JOIN compradores c ON c.id = p.comprador_id "
                  "WHERE p.usuario_id=? AND p.atendido=0 ORDER BY p.creado_en", (usuario_id,))
    return [f for f in filas if coincide(f["descripcion"], a)]


def avisar_si_esperan(usuario_id: str, a: dict) -> None:
    """Al registrar una pieza (a mano, desde Mattel o desde el bot): aviso por Telegram
    si alguien la esperaba. Nunca falla: el alta no depende de esto."""
    try:
        l = esperan(usuario_id, a)
        if l:
            quienes = ", ".join(sorted({f["cliente"] or "un cliente" for f in l}))
            avisar_dueno(f"🔔 Llegó algo que esperan {len(l)} cliente(s)\n{a.get('nombre')}\nAvisa a: {quienes}")
    except Exception:
        pass
