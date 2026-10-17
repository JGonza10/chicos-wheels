# -*- coding: utf-8 -*-
"""
"Ya tienes esta": cruza una pieza encontrada contra tu coleccion de
Chicos Wheels (02 chicos-wheels) para avisar de duplicados y mostrar cuanto
vale lo que ya tienes.

Solo LEE (GET /api/articulos) con el mismo login que usa collecthub_bridge.
Todo es tolerante a fallos: si Chicos Wheels esta apagado o sin credenciales
el panel funciona igual y solo dice por que no pudo comparar.
"""

import difflib
import re
import time
import unicodedata

import collecthub_bridge as CH

_CACHE = {"t": 0.0, "datos": None, "motivo": None}
SEGUNDOS_CACHE = 600

# Palabras que aparecen en casi todos los titulos y no distinguen un modelo.
_COMUNES = {
    "hot", "wheels", "mattel", "creations", "premium", "collectors", "collector", "the", "de",
    "car", "culture", "edition", "series", "serie", "set", "pack", "case", "and", "y", "with",
    "x", "vs", "los", "las", "el", "la", "un", "una", "of", "for", "by", "new", "nuevo",
}


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _tokens(texto):
    return {w for w in normalizar(texto).split() if w not in _COMUNES and len(w) > 1}


def son_parecidas(a, b):
    """True si dos titulos parecen ser el mismo modelo."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    comunes = ta & tb
    if len(comunes) >= 2 and len(comunes) / float(min(len(ta), len(tb))) >= 0.75:
        return True
    # Solo las palabras que distinguen el modelo: comparar el titulo completo
    # daria falsos positivos ("Hot Wheels Premium Nissan Skyline" vs "...Silvia").
    return difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() >= 0.85


def similares(titulo, articulos, maximo=3):
    """Articulos de la coleccion que parecen ser `titulo` (lista de dicts)."""
    if not titulo or not articulos:
        return []
    salida = []
    for art in articulos:
        if son_parecidas(titulo, art.get("nombre") or ""):
            salida.append({"nombre": art.get("nombre"), "estatus": art.get("estatus"),
                           "cantidad": art.get("cantidad") or 1})
            if len(salida) >= maximo:
                break
    return salida


def _pedir_articulos():
    """(lista | None, motivo)."""
    if not CH.configurado():
        return None, "falta COLLECTHUB_EMAIL/COLLECTHUB_PASSWORD en .env"
    try:
        r = CH.pedir("GET", "/api/articulos", timeout=8)
        r.raise_for_status()
        datos = r.json()
        return (datos if isinstance(datos, list) else []), None
    except Exception as e:
        return None, "Chicos Wheels no responde (%s)" % type(e).__name__


def articulos(forzar=False):
    """(lista | None, motivo), con cache de 10 minutos (tambien de los fallos,
    para no golpear un Chicos Wheels apagado en cada refresco del panel)."""
    ahora = time.time()
    if not forzar and ahora - _CACHE["t"] < SEGUNDOS_CACHE:
        return _CACHE["datos"], _CACHE["motivo"]
    datos, motivo = _pedir_articulos()
    _CACHE.update({"t": ahora if datos is not None else ahora - SEGUNDOS_CACHE + 60,
                   "datos": datos, "motivo": motivo})
    return datos, motivo


def resumen():
    """Cifras de la coleccion para el panel."""
    datos, motivo = articulos()
    if datos is None:
        return {"configurado": False, "motivo": motivo}
    hw = [a for a in datos if (a.get("tipo") or "").lower() == "hot wheels"] or datos
    return {"configurado": True, "motivo": None,
            "piezas": int(sum((a.get("cantidad") or 1) for a in hw)),
            "valor_estimado_mxn": float(sum((a.get("valor_estimado") or 0) * (a.get("cantidad") or 1) for a in hw))}


def marcar(piezas):
    """Agrega a cada pieza (dict de hallazgos) la clave `ya_tienes`:
    None = no se pudo comparar; [] = no la tienes; [..] = coincidencias.
    Tambien cuenta como "ya la tienes" una compra ya anotada por este sistema."""
    datos, _ = articulos()
    for p in piezas:
        p["ya_tienes"] = None if datos is None else similares(p.get("titulo"), datos)
    return piezas
