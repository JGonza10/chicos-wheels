"""
Pruebas del monitor de relevo en Railway (collecthub/bot.py, HOTWHEELS_MONITOR_NUBE).

Copia temporal del código de hotwheels/ y base temporal. El monitor no llega a
vigilar: sin TELEGRAM_BOT_TOKEN su main() termina solo, sin tocar la red.

    python -m unittest tests.test_relevo -v
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

_TMP = Path(tempfile.gettempdir()) / f"ch-test-relevo-{os.getpid()}.db"
os.environ.setdefault("DB_FILE", str(_TMP))
os.environ.setdefault("JWT_SECRET", "llave-de-prueba")
os.environ["COLLECTHUB_SIN_RESPALDO"] = "1"

from collecthub import bot, crear_app  # noqa: E402

DUENO = "dueno-relevo@prueba.mx"
OTRO = "otro-relevo@prueba.mx"
_MODULOS = ("monitor", "hw_extras", "hallazgos")


class PruebasRelevo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="ch-relevo-"))
        cls.datos = cls.dir / "datos"
        cls.carpeta_original = bot.CARPETA
        # La carpeta real (otras pruebas dejan bot.CARPETA en una temporal ya borrada).
        for f in (Path(bot.__file__).resolve().parent.parent / "hotwheels").glob("*.py"):
            if not f.name.startswith("prueba_"):
                shutil.copy(f, cls.dir)
        for m in _MODULOS:
            sys.modules.pop(m, None)
        os.environ.update({"BOT_EMAILS": DUENO, "HOTWHEELS_DATOS": str(cls.datos)})
        for var in ("HOTWHEELS_ACTIVO", "HOTWHEELS_MONITOR_NUBE", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            os.environ.pop(var, None)
        bot.CARPETA = cls.dir
        bot._NUBE = None
        cls.app = crear_app()
        cls.c = cls.app.test_client()
        cls.token = cls._registrar(DUENO)
        cls.token_otro = cls._registrar(OTRO)

    @classmethod
    def tearDownClass(cls):
        bot._NUBE = None
        bot.CARPETA = cls.carpeta_original
        for var in ("BOT_EMAILS", "HOTWHEELS_DATOS", "HOTWHEELS_MONITOR_NUBE"):
            os.environ.pop(var, None)
        while str(cls.dir) in sys.path:
            sys.path.remove(str(cls.dir))
        for m in _MODULOS:
            sys.modules.pop(m, None)
        shutil.rmtree(cls.dir, ignore_errors=True)
        for sufijo in ("", "-wal", "-shm"):
            Path(str(_TMP) + sufijo).unlink(missing_ok=True)

    @classmethod
    def _registrar(cls, email):
        r = cls.c.post("/api/auth/registro", json={"email": email, "password": "coleccion2026"})
        return r.get_json()["token"]

    def _latido(self, token):
        return self.c.post("/api/bot/latido-pc", headers={"Authorization": f"Bearer {token}"})

    def test_01_sin_variable_no_hay_relevo(self):
        self.assertFalse(bot.iniciar_monitor_nube())
        self.assertEqual(self._latido(self.token).status_code, 404)

    def test_02_en_la_pc_no_arranca_el_relevo(self):
        os.environ.update({"HOTWHEELS_MONITOR_NUBE": "1", "HOTWHEELS_ACTIVO": "1"})
        try:
            self.assertFalse(bot.iniciar_monitor_nube(), "con HOTWHEELS_ACTIVO=1 manda el monitor completo")
        finally:
            os.environ.pop("HOTWHEELS_ACTIVO", None)
            os.environ.pop("HOTWHEELS_MONITOR_NUBE", None)

    def test_03_relevo_y_latido(self):
        os.environ["HOTWHEELS_MONITOR_NUBE"] = "1"
        self.assertTrue(bot.iniciar_monitor_nube())
        m = bot._NUBE
        self.assertTrue(m.MODO_RELEVO)
        self.assertIsNone(m.HALLAZGOS, "en Railway no se registran piezas: sin botones de compra")
        self.assertEqual(Path(m.ARCHIVO_ESTADO).parent, self.datos, "los datos van al volumen")
        self.assertTrue(m.pc_vigilando(), "al arrancar espera el latido de la PC antes de hablar")

        self.assertEqual(self._pedir_sin_sesion().status_code, 401)
        self.assertEqual(self._latido(self.token_otro).status_code, 403)

        m._PC_LATIDO = time.monotonic() - 3600
        self.assertFalse(m.pc_vigilando())
        r = self._latido(self.token)
        self.assertEqual(r.status_code, 200)
        self.assertIn("minutos_sin_ver", r.get_json())
        self.assertTrue(m.pc_vigilando(), "el latido de la PC calla al relevo")

    def _pedir_sin_sesion(self):
        return self.c.post("/api/bot/latido-pc")


if __name__ == "__main__":
    unittest.main()
