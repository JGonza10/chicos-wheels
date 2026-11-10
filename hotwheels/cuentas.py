# -*- coding: utf-8 -*-
"""
Cuentas de Mattel para comprar en paralelo (2026-11-10).

Cada cuenta es una persona con su propia membresia, sesion, tarjeta y
direccion:

  - "principal": la de Gonza. Datos en hotwheels/.env y sesion en
    hotwheels/perfil_mattel/ (lo de siempre, no cambia nada).
  - las demas: una carpeta por cuenta en hotwheels/cuentas/<nombre>/ con su
    .env (mismas variables HOTWHEELS_* que el principal) y su perfil_mattel/.
    Se dan de alta con:  python iniciar_sesion_mattel.py --cuenta <nombre>

Todo vive fuera de git (ver .gitignore). Los datos se leen del .env en el
momento en que se necesitan, sin reiniciar: el CVV dinamico se pone minutos
antes del drop.

Mattel limita las piezas POR CLIENTE: cada cuenta debe tener su propia
membresia RLC, su tarjeta y de preferencia su direccion, o Mattel puede
cancelar los pedidos.
"""

import json
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))
DIR_CUENTAS = os.path.join(DIR, "cuentas")
PRINCIPAL = "principal"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
_NOMBRE_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")


def nombre_valido(nombre):
    return bool(_NOMBRE_VALIDO.match((nombre or "").strip().lower()))


class Cuenta:
    def __init__(self, nombre, carpeta, es_principal=False):
        self.nombre = nombre
        self.carpeta = carpeta
        self.es_principal = es_principal
        self.env = os.path.join(carpeta, ".env")
        self.perfil = os.path.join(carpeta, "perfil_mattel")
        self.cookies = os.path.join(self.perfil, "cookies_sesion.json")

    def __repr__(self):
        return "Cuenta(%s)" % self.nombre

    # --- datos (se leen al momento) ----------------------------------------
    def _valores(self):
        from dotenv import dotenv_values
        try:
            archivo = dotenv_values(self.env) if os.path.exists(self.env) else {}
        except Exception:
            archivo = {}

        def valor(clave):
            v = (archivo.get(clave) or "").strip()
            # Solo la principal hereda las variables del proceso (y las pruebas).
            if not v and self.es_principal:
                v = os.environ.get(clave, "").strip()
            return v
        return valor

    def datos(self):
        """Todo lo que el checkout necesita de esta cuenta."""
        valor = self._valores()
        nombre_tarjeta = valor("HOTWHEELS_CARD_NAME")
        tarjetas = []
        for n in range(1, 11):
            pre = "HOTWHEELS_CARD_" if n == 1 else "HOTWHEELS_CARD%d_" % n
            t = {k: valor(pre + k.upper()) for k in ("number", "expiry", "cvv", "name")}
            if t["number"] and t["expiry"] and t["cvv"]:
                t["name"] = t["name"] or nombre_tarjeta
                t["n"] = n
                tarjetas.append(t)
        return {
            "cuenta": self.nombre,
            "email": valor("HOTWHEELS_USER_EMAIL"),
            "tarjetas": tarjetas,
            "tarjeta1": {k: valor("HOTWHEELS_CARD_" + k.upper())
                         for k in ("number", "expiry", "cvv", "name")},
            "nombre_tarjeta": nombre_tarjeta,
            "first_name": valor("HOTWHEELS_SHIP_FIRST_NAME"),
            "last_name": valor("HOTWHEELS_SHIP_LAST_NAME"),
            "address1": valor("HOTWHEELS_SHIP_ADDRESS1"),
            "address2": valor("HOTWHEELS_SHIP_ADDRESS2"),
            "city": valor("HOTWHEELS_SHIP_CITY"),
            "postal_code": valor("HOTWHEELS_SHIP_POSTAL_CODE"),
            "state": valor("HOTWHEELS_SHIP_STATE"),
            "phone": valor("HOTWHEELS_SHIP_PHONE"),
            "rfc": valor("HOTWHEELS_RFC"),
            "activa": valor("HOTWHEELS_CUENTA_ACTIVA") != "0",
        }

    # --- CVV dinamico -------------------------------------------------------
    def borrar_cvv(self):
        """Vacia los HOTWHEELS_CARD*_CVV del .env despues de pagar: el CVV
        dinamico ya no sirve y no debe quedarse guardado. Devuelve cuantos
        vacio."""
        if not os.path.exists(self.env):
            return 0
        with open(self.env, encoding="utf-8") as f:
            lineas = f.readlines()
        n = 0
        salida = []
        for linea in lineas:
            m = re.match(r"^(\s*HOTWHEELS_CARD\d*_CVV\s*=)(.*)$", linea.rstrip("\r\n"))
            if m and m.group(2).strip():
                salida.append(m.group(1) + "\n")
                n += 1
            else:
                salida.append(linea)
        if n:
            tmp = self.env + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(salida)
            os.replace(tmp, self.env)
        return n

    # --- sesion de Mattel sin abrir ventana --------------------------------
    def _sesion_http(self):
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = UA
        if os.path.exists(self.cookies):
            with open(self.cookies, encoding="utf-8") as f:
                for c in json.load(f):
                    s.cookies.set(c["name"], c["value"], domain=c.get("domain"),
                                  path=c.get("path", "/"))
        return s

    def revisar_sesion(self, timeout=20):
        """(True/False/None, detalle). True = Mattel reconoce la cuenta;
        False = sesion vencida o sin iniciar; None = no se pudo saber (red,
        Cloudflare). Usa las cookies guardadas, sin abrir navegador."""
        if not os.path.exists(self.cookies):
            return False, "nunca se inició sesión (corre iniciar_sesion_mattel.py%s)" % (
                "" if self.es_principal else " --cuenta " + self.nombre)
        try:
            s = self._sesion_http()
            r = s.get("https://creations.mattel.com/en-mx/account",
                      allow_redirects=False, timeout=timeout)
        except Exception as e:
            return None, "no se pudo consultar Mattel (%s)" % type(e).__name__
        # Sin sesion, /account redirige a /account/login (302).
        if r.status_code == 200:
            return True, "sesión activa"
        if r.status_code in (301, 302, 303) and "login" in (r.headers.get("location") or ""):
            return False, "la sesión de Mattel venció"
        if r.status_code in (403, 429, 503):
            return None, "Mattel no respondió (%d)" % r.status_code
        return False, "Mattel no reconoce la sesión (%d)" % r.status_code

    def piezas_en_carrito(self, timeout=20):
        try:
            r = self._sesion_http().get("https://creations.mattel.com/en-mx/cart.js", timeout=timeout)
            return int(r.json().get("item_count", 0))
        except Exception:
            return None


def principal():
    return Cuenta(PRINCIPAL, DIR, es_principal=True)


def obtener(nombre=None):
    """La cuenta por nombre (None o "principal" = la de Gonza)."""
    if not nombre or nombre == PRINCIPAL:
        return principal()
    nombre = nombre.strip().lower()
    if not nombre_valido(nombre):
        raise ValueError("nombre de cuenta no válido: %r" % nombre)
    return Cuenta(nombre, os.path.join(DIR_CUENTAS, nombre))


def listar(solo_activas=True):
    """La principal primero y luego las de cuentas/ que tengan .env."""
    salida = [principal()]
    if os.path.isdir(DIR_CUENTAS):
        for nombre in sorted(os.listdir(DIR_CUENTAS)):
            if not nombre_valido(nombre):
                continue
            c = obtener(nombre)
            if os.path.exists(c.env):
                salida.append(c)
    if solo_activas:
        salida = [c for c in salida if c.datos()["activa"]]
    return salida


def crear(nombre):
    """Crea la carpeta de una cuenta nueva con un .env de plantilla (sin
    datos). Devuelve la Cuenta. No pisa un .env que ya exista."""
    c = obtener(nombre)
    if c.es_principal:
        return c
    os.makedirs(c.perfil, exist_ok=True)
    if not os.path.exists(c.env):
        with open(c.env, "w", encoding="utf-8") as f:
            f.write(PLANTILLA_ENV.format(nombre=c.nombre))
    return c


def chequeo(cuenta, revisar_red=True):
    """Lista de (ok, texto) para el semaforo antes de un drop. ok es True,
    False (rojo) o None (no se pudo saber)."""
    d = cuenta.datos()
    t = d["tarjeta1"]
    digitos = re.sub(r"\D", "", t["number"])
    puntos = []
    puntos.append((bool(digitos) and len(digitos) >= 15 and bool(t["expiry"]),
                   "tarjeta •••• %s con vencimiento" % (digitos[-4:] or "????")
                   if digitos else "falta la tarjeta (HOTWHEELS_CARD_NUMBER)"))
    puntos.append((None if not t["cvv"] else True,
                   "CVV puesto" if t["cvv"] else "CVV pendiente (ponlo antes del drop)"))
    rfc = d["rfc"].upper()
    puntos.append((bool(re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", rfc)),
                   "RFC válido" if rfc else "falta el RFC (HOTWHEELS_RFC)"))
    tel = re.sub(r"\D", "", d["phone"])
    puntos.append((len(tel) >= 10, "teléfono •••• %s" % tel[-4:] if tel
                   else "falta el teléfono (HOTWHEELS_SHIP_PHONE)"))
    if revisar_red:
        ok, detalle = cuenta.revisar_sesion()
        puntos.append((ok, "sesión de Mattel: " + detalle))
        n = cuenta.piezas_en_carrito()
        if n is not None:
            puntos.append((n == 0 or None, "carrito vacío" if n == 0
                           else "el carrito tiene %d pieza(s): el bot lo vacía antes de comprar" % n))
    return puntos


def texto_chequeo(cuenta, puntos):
    icono = {True: "🟢", False: "🔴", None: "🟡"}
    return "\n".join(["👤 " + cuenta.nombre] + ["  %s %s" % (icono[ok], txt) for ok, txt in puntos])


PLANTILLA_ENV = """# Cuenta de Mattel "{nombre}" para el Bot Hot Wheels (fuera de git).
# Mismas variables que hotwheels/.env. Cada cuenta necesita SU membresia
# Red Line Club, SU tarjeta y de preferencia SU direccion.
# Despues de llenar esto: python iniciar_sesion_mattel.py --cuenta {nombre}
HOTWHEELS_CUENTA_ACTIVA=1
HOTWHEELS_USER_EMAIL=
HOTWHEELS_CARD_NUMBER=
HOTWHEELS_CARD_EXPIRY=MM/AA
# CVV dinamico: ponlo minutos antes del drop; el bot lo borra al pagar.
HOTWHEELS_CARD_CVV=
HOTWHEELS_CARD_NAME=
HOTWHEELS_SHIP_FIRST_NAME=
HOTWHEELS_SHIP_LAST_NAME=
HOTWHEELS_SHIP_ADDRESS1=
HOTWHEELS_SHIP_ADDRESS2=
HOTWHEELS_SHIP_CITY=Ciudad de Mexico
HOTWHEELS_SHIP_POSTAL_CODE=
HOTWHEELS_SHIP_STATE=Ciudad de Mexico
HOTWHEELS_SHIP_PHONE=
HOTWHEELS_RFC=
"""
