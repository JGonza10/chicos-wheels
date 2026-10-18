"""
Publicar en la página de Facebook y el reporte de lo que deja el bot.

Facebook nunca se llama de verdad: requests.post se sustituye por un doble.

    python -m unittest tests.test_facebook_reporte -v
"""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

_TMP = Path(tempfile.gettempdir()) / f"ch-test-fb-{os.getpid()}.db"
os.environ.setdefault("DB_FILE", str(_TMP))
os.environ.setdefault("JWT_SECRET", "llave-de-prueba")
os.environ["COLLECTHUB_SIN_RESPALDO"] = "1"

from collecthub import crear_app  # noqa: E402


class Resp:
    def __init__(self, status=200, datos=None):
        self.status_code = status
        self._datos = datos or {}

    def json(self):
        return self._datos


class PruebasFacebookYReporte(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = crear_app()
        cls.c = cls.app.test_client()
        r = cls.c.post("/api/auth/registro", json={"email": "fb-reporte@prueba.mx", "password": "coleccion2026"})
        cls.h = {"Authorization": f"Bearer {r.get_json()['token']}"}
        r = cls.c.post("/api/auth/registro", json={"email": "fb-otro@prueba.mx", "password": "coleccion2026"})
        cls.h_otro = {"Authorization": f"Bearer {r.get_json()['token']}"}
        plats = cls.c.get("/api/plataformas", headers=cls.h).get_json()
        cls.plataforma = next(p["id"] for p in plats if p["codigo"] == "TG")

    @classmethod
    def tearDownClass(cls):
        for var in ("FB_PAGE_ID", "FB_PAGE_TOKEN"):
            os.environ.pop(var, None)
        for sufijo in ("", "-wal", "-shm"):
            Path(str(_TMP) + sufijo).unlink(missing_ok=True)

    def _pieza(self, **extra):
        r = self.c.post("/api/articulos", json={"tipo": "Hot Wheels", "nombre": "RWB Porsche 930", **extra},
                        headers=self.h)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    # ---------------- Facebook ----------------
    def test_01_sin_configurar_lo_dice_claro(self):
        os.environ.pop("FB_PAGE_ID", None)
        a = self._pieza()
        self.assertFalse(self.c.get("/api/articulos/facebook", headers=self.h).get_json()["configurado"])
        r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook", json={"texto": "Hola"}, headers=self.h)
        self.assertEqual(r.status_code, 502)
        self.assertIn("FB_PAGE_ID", r.get_json()["error"])

    def test_02_publica_con_foto_propia_y_no_repite(self):
        os.environ.update({"FB_PAGE_ID": "123", "FB_PAGE_TOKEN": "token-secreto"})
        a = self._pieza()
        buf = io.BytesIO()
        Image.new("RGB", (40, 20), (255, 0, 0)).save(buf, format="JPEG")
        buf.seek(0)
        self.c.post(f"/api/articulos/{a['id']}/foto", data={"foto": (buf, "f.jpg")},
                    headers=self.h, content_type="multipart/form-data")
        llamadas = []

        def falso(url, data=None, files=None, timeout=None):
            llamadas.append((url, data, files))
            return Resp(200, {"id": "999", "post_id": "123_999"})

        with patch("collecthub.facebook.requests.post", falso):
            r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook",
                            json={"texto": "RWB Porsche 930 · $1,500"}, headers=self.h)
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertEqual(r.get_json()["post"], "123_999")
            url, data, files = llamadas[0]
            self.assertTrue(url.endswith("/123/photos"))
            self.assertEqual(data["caption"], "RWB Porsche 930 · $1,500")
            img = Image.open(io.BytesIO(files["source"][1]))
            self.assertEqual(img.size, (1080, 1080), "sube la misma foto que '📸 Foto lista'")
            self.assertNotIn("token-secreto", r.get_data(as_text=True), "el token nunca sale en la respuesta")

            r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook", json={"texto": "otra"}, headers=self.h)
            self.assertEqual(r.status_code, 409, "ya publicada: pide confirmar")
            r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook",
                            json={"texto": "otra", "otra_vez": True}, headers=self.h)
            self.assertEqual(r.status_code, 200)
        guardada = self.c.get(f"/api/articulos/{a['id']}", headers=self.h).get_json()
        self.assertEqual(guardada["fb_post"], "123_999")
        self.assertTrue(guardada["fb_publicado_en"])

    def test_03_foto_de_mattel_por_url_y_sin_foto_solo_texto(self):
        os.environ.update({"FB_PAGE_ID": "123", "FB_PAGE_TOKEN": "t"})
        llamadas = []
        falso = lambda url, data=None, files=None, timeout=None: (llamadas.append((url, data)), Resp(200, {"id": "1"}))[1]  # noqa: E731
        with patch("collecthub.facebook.requests.post", falso):
            a = self._pieza(foto="https://cdn.shopify.com/s/files/rwb.jpg")
            self.c.post(f"/api/articulos/{a['id']}/publicar-facebook", json={"texto": "x"}, headers=self.h)
            self.assertEqual(llamadas[-1][1]["url"], "https://cdn.shopify.com/s/files/rwb.jpg")
            b = self._pieza()
            self.c.post(f"/api/articulos/{b['id']}/publicar-facebook", json={"texto": "solo texto"}, headers=self.h)
            self.assertTrue(llamadas[-1][0].endswith("/123/feed"))
            self.assertEqual(llamadas[-1][1]["message"], "solo texto")

    def test_04_errores_de_facebook_amables(self):
        os.environ.update({"FB_PAGE_ID": "123", "FB_PAGE_TOKEN": "t"})
        a = self._pieza()
        vencido = lambda *a, **k: Resp(400, {"error": {"code": 190, "message": "Error validating access token"}})  # noqa: E731
        with patch("collecthub.facebook.requests.post", vencido):
            r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook", json={"texto": "x"}, headers=self.h)
        self.assertEqual(r.status_code, 502)
        self.assertIn("venció", r.get_json()["error"])
        r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook", json={"texto": "x"}, headers=self.h_otro)
        self.assertEqual(r.status_code, 404, "otra cuenta no puede publicar tus piezas")
        r = self.c.post(f"/api/articulos/{a['id']}/publicar-facebook", json={"texto": "x"})
        self.assertEqual(r.status_code, 401)

    def test_05_la_tienda_no_publica_el_post_de_facebook(self):
        from collecthub.landing import CAMPOS
        self.assertNotIn("fb_post", CAMPOS)

    # ---------------- Reporte del bot ----------------
    def test_10_reporte_del_bot(self):
        notas_bot = ("Link original: https://creations.mattel.com/products/x\nOrigen: bot (panel)\n"
                     "Cobrado MXN $1,000.00 en total (incluye envío e impuestos; costo por pieza $500.00)")
        a = self._pieza(cantidad=2, precio_compra=500, valor_estimado=1200, notas=notas_bot,
                        fecha_adq="2026-10-01")
        self._pieza(cantidad=1, precio_compra=300, notas="Resultado del bot: 🎉 Pedido realizado",
                    ubicacion="Por recibir", fecha_adq="2026-10-15")
        self._pieza(cantidad=5, precio_compra=10, notas="comprada en el tianguis")    # no es del bot
        r = self.c.post("/api/ventas", json={"articulo_id": a["id"], "plataforma_id": self.plataforma,
                                             "cantidad": 1, "precio": 1500, "fecha": "2026-10-11"}, headers=self.h)
        self.assertEqual(r.status_code, 201, r.get_json())
        rep = self.c.get("/api/bot-reporte", headers=self.h).get_json()
        self.assertEqual(rep["compradas"], 3)
        self.assertEqual(rep["invertido"], 1300)
        self.assertEqual(rep["vendidas"], 1)
        self.assertEqual(rep["ingresos"], 1500)
        self.assertAlmostEqual(rep["ganancia"], 1000, places=2, msg="1500 − 500 de costo (Balderas sin comisión)")
        self.assertAlmostEqual(rep["retorno"], 2.0, places=2)
        self.assertEqual(rep["dias_para_vender"], 10)
        self.assertEqual(rep["por_recibir"], 1)
        self.assertEqual(rep["en_stock"], 1)
        self.assertEqual(rep["con_costo_real"], 1)
        self.assertEqual(rep["mejores"][0]["nombre"], "RWB Porsche 930")
        otro = self.c.get("/api/bot-reporte", headers=self.h_otro).get_json()
        self.assertEqual(otro["compradas"], 0, "cada cuenta ve solo lo suyo")


if __name__ == "__main__":
    unittest.main()
