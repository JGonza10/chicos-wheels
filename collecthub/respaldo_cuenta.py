"""Respaldo de una cuenta para guardar FUERA del servidor, y su restauración.

El respaldo automático diario (`respaldo.py`) vive en el mismo disco que la base:
si ese disco se pierde, se pierde todo. Este es el que el usuario descarga a su
PC o celular: un .zip con `datos.json` (lo mismo que /api/exportar) y las fotos
subidas (`fotos/`). Solo trae los datos de quien lo descarga, nunca de otras cuentas.

Restaurar reemplaza TODOS los datos de la cuenta por los del respaldo (la interfaz
pide confirmación escrita). Se valida todo antes de borrar nada.
"""
import io
import json
import re
import zipfile
from datetime import date, datetime

from .db import RUTA_BD, transaccion, uno
from .util import ErrorApp

VERSION = 3
NOMBRE_FOTO = re.compile(r"^[0-9a-f]{40}\.jpg$")
MAX_ARCHIVOS = 5000
MAX_DESCOMPRIMIDO = 400 * 1024 * 1024   # contra zips "bomba"

# Orden de inserción (respeta las llaves foráneas).
TABLAS = ("plataformas", "compradores", "categorias", "articulos", "valuaciones", "lotes", "ventas",
          "apartados", "intercambios", "intercambio_items", "wishlist", "pedidos_cliente",
          "encargos", "encargo_items", "encargo_pagos")
# Tablas con usuario_id propio (las hijas se borran en cascada con su padre).
CON_USUARIO = ("ventas", "encargos", "apartados", "intercambios", "lotes", "wishlist", "pedidos_cliente",
               "articulos", "compradores", "categorias", "plataformas")


def carpeta_fotos(usuario_id: str):
    return RUTA_BD.parent / "fotos" / usuario_id


def generar_zip(usuario_id: str) -> bytes:
    from .rutas.estado import estado_completo
    datos = {"version": VERSION, "exportado_en": datetime.now().isoformat(), **estado_completo(usuario_id)}
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("datos.json", json.dumps(datos, ensure_ascii=False, indent=1))
        z.writestr("LEEME.txt", "Respaldo de Chicos Wheels. Guárdalo en tu PC o en tu nube.\n"
                                "Para recuperarlo: menú Datos → Restaurar respaldo.\n")
        carpeta = carpeta_fotos(usuario_id)
        if carpeta.exists():
            for f in carpeta.iterdir():
                if NOMBRE_FOTO.match(f.name):
                    z.write(f, f"fotos/{f.name}", compress_type=zipfile.ZIP_STORED)  # JPEG ya comprimido
    from .db import conectar
    con = conectar()
    try:
        con.execute("UPDATE ajustes SET ultimo_respaldo=? WHERE usuario_id=?", (date.today().isoformat(), usuario_id))
        con.commit()
    finally:
        con.close()
    return salida.getvalue()


def _leer(archivo: bytes) -> tuple:
    """(datos, fotos{nombre: bytes}) de un .zip de respaldo o de un .json de /exportar."""
    if archivo[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(archivo))
        except zipfile.BadZipFile:
            raise ErrorApp("El archivo de respaldo está dañado")
        infos = z.infolist()
        if len(infos) > MAX_ARCHIVOS or sum(i.file_size for i in infos) > MAX_DESCOMPRIMIDO:
            raise ErrorApp("El respaldo es demasiado grande")
        if "datos.json" not in z.namelist():
            raise ErrorApp("Ese .zip no es un respaldo de Chicos Wheels")
        datos = json.loads(z.read("datos.json"))
        fotos = {}
        for i in infos:
            nombre = i.filename.rsplit("/", 1)[-1]
            if i.filename.startswith("fotos/") and NOMBRE_FOTO.match(nombre):
                fotos[nombre] = z.read(i)
        return datos, fotos
    try:
        return json.loads(archivo.decode("utf-8")), {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErrorApp("Ese archivo no es un respaldo de Chicos Wheels")


def _filas(datos: dict) -> dict:
    """Aplana el respaldo en filas por tabla (las hijas vienen anidadas en sus padres)."""
    t = {k: [] for k in TABLAS}
    for k in ("plataformas", "compradores", "categorias", "ventas", "apartados", "lotes", "wishlist"):
        t[k] = list(datos.get(k) or [])
    t["pedidos_cliente"] = list(datos.get("pedidos") or [])
    for a in datos.get("articulos") or []:
        t["articulos"].append(a)
        t["valuaciones"] += a.get("valuaciones") or []
    for x in datos.get("intercambios") or []:
        t["intercambios"].append(x)
        t["intercambio_items"] += (x.get("entregados") or []) + (x.get("recibidos") or [])
    for e in datos.get("encargos") or []:
        t["encargos"].append(e)
        t["encargo_items"] += e.get("items") or []
        t["encargo_pagos"] += e.get("pagos") or []
    return t


def restaurar(usuario_id: str, archivo: bytes) -> dict:
    datos, fotos = _leer(archivo)
    if not isinstance(datos, dict) or not isinstance(datos.get("articulos"), list):
        raise ErrorApp("Ese archivo no es un respaldo de Chicos Wheels")
    filas = _filas(datos)
    with transaccion() as con:
        columnas = {tb: [c["name"] for c in con.execute(f"PRAGMA table_info({tb})")] for tb in TABLAS}
        for tb in CON_USUARIO:
            con.execute(f"DELETE FROM {tb} WHERE usuario_id=?", (usuario_id,))
        for tb in TABLAS:
            cols = columnas[tb]
            for f in filas[tb]:
                if not isinstance(f, dict) or not f.get("id"):
                    continue
                reg = {c: f[c] for c in cols if c in f}
                if "usuario_id" in cols:
                    reg["usuario_id"] = usuario_id   # siempre a la cuenta que restaura
                if tb == "articulos":
                    reg["checks"] = json.dumps(f.get("checks") or [])
                    reg["grail"] = 1 if f.get("grail") else 0
                try:
                    con.execute(f"INSERT INTO {tb} ({','.join(reg)}) VALUES ({','.join('?' * len(reg))})",
                                list(reg.values()))
                except Exception as e:
                    raise ErrorApp(f"No se pudo restaurar ({tb}): {e}. No se cambió nada.", 409)
        aj = datos.get("ajustes") or {}
        con.execute("UPDATE ajustes SET moneda=COALESCE(?,moneda), meta_mensual=COALESCE(?,meta_mensual), "
                    "dias_estancado=COALESCE(?,dias_estancado) WHERE usuario_id=?",
                    (aj.get("moneda"), aj.get("meta_mensual"), aj.get("dias_estancado"), usuario_id))
    carpeta = carpeta_fotos(usuario_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in fotos.items():
        (carpeta / nombre).write_bytes(contenido)
    n = uno("SELECT COUNT(*) n FROM articulos WHERE usuario_id=?", (usuario_id,))["n"]
    return {"ok": True, "articulos": n, "fotos": len(fotos)}
