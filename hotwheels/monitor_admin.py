# -*- coding: utf-8 -*-
"""
API del panel para administrar al monitor (proyecto fusionado).

Antes vivia en el tablero del monitor (puerto 5057, dashboard.py). Ahora es un
Blueprint del panel unico (/bot dentro de Chicos Wheels). Igual que antes: solo escribe los
archivos JSON / config.env que el monitor relee solo (sin reiniciarlo) y LEE
estado.json / historial.db / latido.txt -- nunca toca estado.json.
"""

import io
import json
import os
import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

import hw_extras as EX

DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_ESTADO = os.path.join(DIR, "estado.json")
ARCHIVO_HISTORIAL = os.path.join(DIR, "historial.db")
ARCHIVO_LATIDO = os.path.join(DIR, "latido.txt")
ARCHIVO_DESEADOS = os.path.join(DIR, "deseados.json")
ARCHIVO_BLOQUEADOS = os.path.join(DIR, "no_deseados.json")
ARCHIVO_COLECCIONES = os.path.join(DIR, "colecciones.json")
ARCHIVO_VIGILAR = os.path.join(DIR, "vigilar.json")
ARCHIVO_BUSQUEDAS_ML = os.path.join(DIR, "busquedas_ml.json")
ARCHIVO_CONFIG = os.path.join(DIR, "config.env")

# Minutos sin latido antes de pintar el semaforo en ambar / en rojo.
MIN_TARDE = 6
MIN_CIEGO = 15

EX.migrar_deseados_legacy(os.path.join(DIR, "deseados.txt"), ARCHIVO_DESEADOS)
EX.sembrar_colecciones(ARCHIVO_COLECCIONES)

bp = Blueprint("monitor_admin", __name__, url_prefix="/api/monitor")

_LISTAS = {"deseados": ARCHIVO_DESEADOS, "bloqueados": ARCHIVO_BLOQUEADOS}


def _leer_estado():
    try:
        with io.open(ARCHIVO_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _semaforo(minutos):
    if minutos is None:
        return "sin_datos"
    if minutos >= MIN_CIEGO:
        return "ciego"
    if minutos >= MIN_TARDE:
        return "tarde"
    return "bien"


def estado_monitor():
    """Resumen corto de si el monitor esta vivo y que vio hoy."""
    estado = _leer_estado()
    min_lat = EX.leer_latido(ARCHIVO_LATIDO)
    hoy = estado.get("stats_hoy") or {}
    return {
        "minutos_latido": round(min_lat, 1) if min_lat is not None else None,
        "semaforo": _semaforo(min_lat),
        "revisiones": estado.get("revisiones", 0),
        "tipo_cambio": estado.get("tipo_cambio"),
        "productos_vistos": len(estado.get("productos") or {}),
        "proximo_drop": proximo_drop_info(),
        "hoy": {k: hoy.get(k, 0) for k in
                ("nuevos", "restocks", "pocas_unidades", "agotados", "cambios_precio")},
    }


BASE_URL_TIENDA = "https://creations.mattel.com"


def proximo_drop_info():
    """Cuenta regresiva: el dia/hora en que suelen caer los drops, aprendido del
    historial (hw_extras.patron_de_drops). Sin datos suficientes se asume el
    martes 11:00 CDMX, igual que hace el monitor, y se marca como `supuesto`."""
    patron = None
    if os.path.exists(ARCHIVO_HISTORIAL):
        try:
            conn = sqlite3.connect(ARCHIVO_HISTORIAL, timeout=5)
            patron = EX.patron_de_drops(conn)
            conn.close()
        except Exception:
            patron = None
    supuesto = patron is None
    if supuesto:
        patron = {"dia_semana": 1, "hora": 11, "casos": 0, "total": 0, "confianza": None}
    ahora = datetime.now(EX.ZONA_MX)
    dias = (patron["dia_semana"] - ahora.weekday()) % 7
    if dias == 0 and ahora.hour >= patron["hora"]:
        dias = 7
    cuando = (ahora + timedelta(days=dias)).replace(hour=patron["hora"], minute=0,
                                                     second=0, microsecond=0)
    return {"texto": EX.proximo_drop(patron), "iso": cuando.isoformat(),
            "confianza": patron.get("confianza"), "casos": patron.get("casos"),
            "supuesto": supuesto}


def producto_disponible_para_prueba():
    """URL de un producto que HOY este disponible en Mattel (el mas barato), para
    la prueba diaria del checkout. None si el ultimo barrido no vio ninguno."""
    mejor = None
    for pid, p in (_leer_estado().get("productos") or {}).items():
        if not p.get("disponible") or p.get("coming_soon") or not p.get("handle"):
            continue
        precio = p.get("precio") or 1e9
        if mejor is None or precio < mejor[0]:
            mejor = (precio, p["handle"])
    return "%s/products/%s" % (BASE_URL_TIENDA, mejor[1]) if mejor else None


@bp.route("/estado")
def api_estado():
    return jsonify(estado_monitor())


def _datos_json(): return request.get_json(silent=True) or {}


# --- Deseados / bloqueados ---------------------------------------------------

@bp.route("/lista/<lista>")
def api_lista(lista):
    ruta = _LISTAS.get(lista)
    if ruta is None:
        return jsonify({"ok": False, "error": "lista desconocida"}), 404
    return jsonify({"ok": True, "entradas": EX.listar_deseados_detalle(ruta)})


@bp.route("/lista/<lista>/agregar", methods=["POST"])
def api_lista_agregar(lista):
    ruta = _LISTAS.get(lista)
    if ruta is None:
        return jsonify({"ok": False, "error": "lista desconocida"}), 404
    data = _datos_json()
    texto = (data.get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "error": "falta texto"}), 400
    agregado, entrada = EX.agregar_deseado(ruta, texto, categoria=data.get("categoria"))
    if not agregado:
        return jsonify({"ok": False, "error": "ya estaba en la lista (o vacio)"}), 409
    return jsonify({"ok": True, "entrada": entrada})


@bp.route("/lista/<lista>/quitar", methods=["POST"])
def api_lista_quitar(lista):
    ruta = _LISTAS.get(lista)
    if ruta is None:
        return jsonify({"ok": False, "error": "lista desconocida"}), 404
    quitado = EX.quitar_deseado(ruta, (_datos_json().get("texto") or "").strip())
    return jsonify({"ok": True, "quitado": quitado})


# --- Colecciones que se vigilan ---------------------------------------------

@bp.route("/colecciones")
def api_colecciones():
    return jsonify({"ok": True, "entradas": EX.listar_colecciones(ARCHIVO_COLECCIONES)})


@bp.route("/colecciones/agregar", methods=["POST"])
def api_colecciones_agregar():
    data = _datos_json()
    agregada, entrada = EX.agregar_coleccion(
        ARCHIVO_COLECCIONES, data.get("handle"),
        nombre=data.get("nombre"), rapida=bool(data.get("rapida")))
    if not agregada:
        return jsonify({"ok": False, "error": "ya estaba en la lista (o handle vacio)"}), 409
    return jsonify({"ok": True, "entrada": entrada})


@bp.route("/colecciones/quitar", methods=["POST"])
def api_colecciones_quitar():
    return jsonify({"ok": True, "quitada": EX.quitar_coleccion(
        ARCHIVO_COLECCIONES, _datos_json().get("handle"))})


@bp.route("/colecciones/cambiar", methods=["POST"])
def api_colecciones_cambiar():
    data = _datos_json()
    cambiada, entrada = EX.cambiar_coleccion(
        ARCHIVO_COLECCIONES, data.get("handle"),
        activa=data.get("activa"), rapida=data.get("rapida"))
    if not cambiada:
        return jsonify({"ok": False, "error": "no existe esa coleccion"}), 404
    return jsonify({"ok": True, "entrada": entrada})


# --- Productos sueltos bajo vigilancia (handle de Mattel) --------------------

@bp.route("/vigilar")
def api_vigilar():
    return jsonify({"ok": True, "entradas": EX.listar_vigilados(ARCHIVO_VIGILAR)})


@bp.route("/vigilar/agregar", methods=["POST"])
def api_vigilar_agregar():
    data = _datos_json()
    agregado, entrada = EX.agregar_vigilado(ARCHIVO_VIGILAR, data.get("handle"),
                                            nota=data.get("nota"))
    if not agregado:
        return jsonify({"ok": False, "error": "ya estaba vigilado (o handle vacio)"}), 409
    return jsonify({"ok": True, "entrada": entrada})


@bp.route("/vigilar/quitar", methods=["POST"])
def api_vigilar_quitar():
    return jsonify({"ok": True, "quitado": EX.quitar_vigilado(
        ARCHIVO_VIGILAR, _datos_json().get("handle"))})


# --- Ajustes (lista blanca, sin secretos) ------------------------------------

@bp.route("/ajustes")
def api_ajustes():
    return jsonify({"ok": True, "ajustes": EX.leer_ajustes(ARCHIVO_CONFIG)})


@bp.route("/ajustes/guardar", methods=["POST"])
def api_ajustes_guardar():
    guardados, rechazados = EX.guardar_ajustes(ARCHIVO_CONFIG, _datos_json().get("cambios") or {})
    return jsonify({"ok": bool(guardados), "guardados": guardados, "rechazados": rechazados})


# --- Rastro de precio de una pieza (mini-grafica) ----------------------------

@bp.route("/precios")
def api_precios():
    titulo = (request.args.get("titulo") or "").strip()
    if not titulo or not os.path.exists(ARCHIVO_HISTORIAL):
        return jsonify({"ok": True, "precios": []})
    try:
        conn = sqlite3.connect(ARCHIVO_HISTORIAL, timeout=5)
        precios = EX.historial_precios(conn, titulo)
        conn.close()
    except Exception:
        precios = []
    return jsonify({"ok": True, "precios": precios})
