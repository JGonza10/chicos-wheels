# -*- coding: utf-8 -*-
"""
Token de Mercado Libre que se renueva solo (2026-11-10).

El access token de Mercado Libre dura 6 horas; el refresh token, meses, pero
se usa UNA vez (cada renovacion entrega uno nuevo). Por eso no basta con
pegar un token en config.env.

Configuracion (una vez):
  1. App gratuita en developers.mercadolibre.com.mx con permisos read y
     offline_access, y URI de redirect https://kestrel-ia.up.railway.app/
  2. En hotwheels/config.env:  ML_CLIENT_ID=...  y  ML_CLIENT_SECRET=...
  3. python ml_auth.py            -> imprime el link para autorizar
     python ml_auth.py --code TG-...   -> guarda los tokens en ml_token.json

Desde ahi token() entrega siempre uno vigente. ml_token.json y config.env
viven fuera de git. Si no hay app configurada, token() devuelve el
MERCADOLIBRE_ACCESS_TOKEN de siempre (o "").
"""

import json
import os
import sys
import threading
import time

DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(DIR, "ml_token.json")
CONFIG = os.path.join(DIR, "config.env")
REDIRECT = "https://kestrel-ia.up.railway.app/"
URL_TOKEN = "https://api.mercadolibre.com/oauth/token"
MARGEN_SEG = 10 * 60
_LOCK = threading.Lock()


def _config():
    datos = {}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    datos[k.strip()] = v.strip()
    except OSError:
        pass
    return datos


def configurado():
    c = _config()
    return bool(c.get("ML_CLIENT_ID") and c.get("ML_CLIENT_SECRET"))


def link_autorizar():
    c = _config()
    return ("https://auth.mercadolibre.com.mx/authorization?response_type=code&client_id=%s&redirect_uri=%s"
            % (c.get("ML_CLIENT_ID", ""), REDIRECT))


def _leer():
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _guardar(datos):
    tmp = ARCHIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    os.replace(tmp, ARCHIVO)


def _pedir(campos, post=None):
    import requests
    post = post or requests.post
    c = _config()
    r = post(URL_TOKEN, data=dict(campos, client_id=c.get("ML_CLIENT_ID", ""),
                                  client_secret=c.get("ML_CLIENT_SECRET", "")),
             headers={"accept": "application/json"}, timeout=20)
    datos = r.json()
    if r.status_code >= 400 or "access_token" not in datos:
        raise RuntimeError("Mercado Libre no entregó el token: %s" % (datos.get("message") or datos.get("error")
                                                                     or r.status_code))
    datos["vence"] = time.time() + int(datos.get("expires_in", 21600))
    return datos


def canjear_codigo(code, post=None):
    """Primer paso: el ?code=TG-... de la redireccion -> tokens guardados."""
    datos = _pedir({"grant_type": "authorization_code", "code": code.strip(), "redirect_uri": REDIRECT}, post)
    with _LOCK:
        _guardar(datos)
    return datos


def token(post=None, ahora=None):
    """Un access token vigente (renueva si le quedan menos de 10 min), o el
    MERCADOLIBRE_ACCESS_TOKEN fijo de config.env, o ""."""
    ahora = ahora or time.time()
    with _LOCK:
        datos = _leer()
        if datos.get("access_token") and datos.get("vence", 0) - ahora > MARGEN_SEG:
            return datos["access_token"]
        if datos.get("refresh_token") and configurado():
            try:
                nuevo = _pedir({"grant_type": "refresh_token", "refresh_token": datos["refresh_token"]}, post)
                _guardar(nuevo)
                return nuevo["access_token"]
            except Exception as e:
                print("  [ML] no se pudo renovar el token: %s" % e)
                if datos.get("vence", 0) > ahora:
                    return datos["access_token"]
    return (_config().get("MERCADOLIBRE_ACCESS_TOKEN") or "").strip()


if __name__ == "__main__":
    if not configurado():
        print("❌ Falta ML_CLIENT_ID y ML_CLIENT_SECRET en hotwheels/config.env")
        sys.exit(1)
    if "--code" in sys.argv:
        codigo = sys.argv[sys.argv.index("--code") + 1]
        if "code=" in codigo:
            codigo = codigo.split("code=", 1)[1].split("&")[0]
        canjear_codigo(codigo)
        print("✅ Token de Mercado Libre guardado; se renueva solo.")
    else:
        print("Abre este link, acepta, y copia la dirección a la que te manda:")
        print(link_autorizar())
        print("Luego: python ml_auth.py --code <esa dirección o el código TG-...>")
