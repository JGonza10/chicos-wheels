"""
Pruebas del Bot Hot Wheels montado en /bot (collecthub/bot.py).

Usan una copia temporal del código de hotwheels/ (sin datos reales ni
secretos) y una base temporal de Chicos Wheels. No arrancan el monitor, el
scheduler ni Telegram: solo el acceso, el montaje y el puente al inventario.

    python -m unittest tests.test_bot -v
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = Path(tempfile.gettempdir()) / f"ch-test-bot-{os.getpid()}.db"
os.environ.setdefault("DB_FILE", str(_TMP))
os.environ.setdefault("JWT_SECRET", "llave-de-prueba")
os.environ["COLLECTHUB_SIN_RESPALDO"] = "1"

from collecthub import bot, crear_app  # noqa: E402

DUENO = "dueno-bot@prueba.mx"
OTRO = "otro-bot@prueba.mx"
HAY_DEPENDENCIAS = all(importlib.util.find_spec(m) for m in ("playwright", "apscheduler", "twilio"))


@unittest.skipUnless(HAY_DEPENDENCIAS, "faltan las dependencias del bot (hotwheels/requirements.txt)")
class PruebasBot(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="ch-bot-"))
        origen = bot.CARPETA
        for f in origen.glob("*.py"):
            if not f.name.startswith("prueba_"):
                shutil.copy(f, cls.dir)
        for carpeta in ("templates", "static"):
            shutil.copytree(origen / carpeta, cls.dir / carpeta)
        (cls.dir / "config.json").write_text(json.dumps({"notifications": {}}), encoding="utf-8")
        os.environ.update({"BOT_EMAILS": DUENO, "COLLECTHUB_EMAIL": DUENO})
        bot.CARPETA = cls.dir

        cls.app = crear_app()
        cls.c = cls.app.test_client()
        cls.token = cls._registrar(DUENO)
        cls.token_otro = cls._registrar(OTRO)

    @classmethod
    def tearDownClass(cls):
        for var in ("HOTWHEELS_ACTIVO", "BOT_EMAILS", "COLLECTHUB_EMAIL"):
            os.environ.pop(var, None)
        while str(cls.dir) in sys.path:
            sys.path.remove(str(cls.dir))
        shutil.rmtree(cls.dir, ignore_errors=True)
        for sufijo in ("", "-wal", "-shm"):
            Path(str(_TMP) + sufijo).unlink(missing_ok=True)

    @classmethod
    def _registrar(cls, email):
        r = cls.c.post("/api/auth/registro", json={"email": email, "password": "coleccion2026"})
        return r.get_json()["token"]

    def _pedir(self, metodo, ruta, token, cuerpo=None):
        return self.c.open(ruta, method=metodo, json=cuerpo, headers={"Authorization": f"Bearer {token}"})

    def test_01_sin_activar_no_hay_bot(self):
        os.environ.pop("HOTWHEELS_ACTIVO", None)
        self.assertFalse(bot.montar(self.app), "sin HOTWHEELS_ACTIVO=1 no se monta (Railway)")
        self.assertFalse(self._pedir("GET", "/api/bot/disponible", self.token).get_json()["disponible"])
        self.assertEqual(self._pedir("POST", "/api/bot/entrar", self.token).status_code, 404)
        self.assertNotIn(b"MONITOR Y COMPRA", self.c.get("/bot/").data)

    def test_02_monta_el_panel(self):
        os.environ["HOTWHEELS_ACTIVO"] = "1"
        self.assertTrue(bot.montar(self.app))
        self.assertTrue(self._pedir("GET", "/api/bot/disponible", self.token).get_json()["disponible"])

    def test_03_otra_cuenta_no_entra(self):
        self.assertFalse(self._pedir("GET", "/api/bot/disponible", self.token_otro).get_json()["disponible"])
        self.assertEqual(self._pedir("POST", "/api/bot/entrar", self.token_otro).status_code, 403)
        self.assertEqual(self.c.post("/api/bot/entrar").status_code, 401, "sin sesión tampoco")

    def test_04_sin_cookie_el_panel_no_responde(self):
        cliente = self.app.test_client()
        self.assertEqual(cliente.get("/bot/api/estado").status_code, 401)
        r = cliente.get("/bot/")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/#bot"))
        self.assertEqual(cliente.post("/bot/run").status_code, 401, "nunca dispara compras sin sesión")

    def test_05_el_dueno_ve_el_panel(self):
        r = self._pedir("POST", "/api/bot/entrar", self.token)
        self.assertEqual(r.status_code, 200)
        cookie = r.headers["Set-Cookie"]
        for parte in ("bot_sesion=", "Path=/bot", "HttpOnly", "SameSite=Strict"):
            self.assertIn(parte, cookie)
        pagina = self.c.get("/bot/")
        self.assertEqual(pagina.status_code, 200)
        html = pagina.get_data(as_text=True)
        self.assertIn("MONITOR Y COMPRA", html)
        self.assertIn('const BASE = "/bot"', html)
        self.assertIn('action="/bot/run"', html)
        self.assertIn("/bot/static/styles.css", html)
        estado = self.c.get("/bot/api/estado")
        self.assertEqual(estado.status_code, 200)
        self.assertIn("monitor", estado.get_json())

    def test_06_compra_va_directo_al_inventario(self):
        import collecthub_bridge as CH
        ok, mensaje = CH.registrar_compra(url="https://creations.mattel.com/products/prueba-bot",
                                          titulo="RLC Prueba del bot", precio_mxn=900, origen="panel")
        self.assertTrue(ok, mensaje)
        nombres = [a["nombre"] for a in self._pedir("GET", "/api/articulos", self.token).get_json()]
        self.assertIn("RLC Prueba del bot", nombres)
        self.assertNotIn("RLC Prueba del bot",
                         [a["nombre"] for a in self._pedir("GET", "/api/articulos", self.token_otro).get_json()])
        self.assertTrue(CH.registrar_compra(url="https://creations.mattel.com/products/prueba-bot")[0])
        nombres = [a["nombre"] for a in self._pedir("GET", "/api/articulos", self.token).get_json()]
        self.assertEqual(nombres.count("RLC Prueba del bot"), 1, "la misma URL no se da de alta dos veces")


if __name__ == "__main__":
    unittest.main()
