"""
Pruebas de la API contra una base de datos temporal.

Verifican las reglas de negocio que más duelen si fallan:
el dinero, el stock y el aislamiento entre cuentas.

    python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from pathlib import Path

# La base de prueba debe definirse ANTES de importar la app.
_TMP = Path(tempfile.gettempdir()) / f"ch-test-{os.getpid()}.db"
os.environ["DB_FILE"] = str(_TMP)
os.environ["JWT_SECRET"] = "llave-de-prueba"

from collecthub import crear_app  # noqa: E402


class PruebasAPI(unittest.TestCase):
    """Se ejecutan en orden alfabético: los nombres llevan número a propósito."""

    @classmethod
    def setUpClass(cls):
        cls.app = crear_app()
        cls.c = cls.app.test_client()
        cls.token = None
        cls.token2 = None
        cls.articulo = None
        cls.plataforma = None

    @classmethod
    def tearDownClass(cls):
        for sufijo in ("", "-wal", "-shm"):
            Path(str(_TMP) + sufijo).unlink(missing_ok=True)

    # --- ayudantes ---
    def pedir(self, metodo, ruta, cuerpo=None, token="propio"):
        tk = self.token if token == "propio" else token
        cab = {"Authorization": f"Bearer {tk}"} if tk else {}
        r = getattr(self.c, metodo.lower())(ruta, json=cuerpo, headers=cab)
        return r.status_code, (r.get_json() or {})

    # ---------------- Cuentas ----------------

    def test_01_rechaza_datos_invalidos(self):
        s, _ = self.pedir("POST", "/api/auth/registro", {"email": "a@b.co", "password": "123"}, None)
        self.assertEqual(s, 400, "una contraseña de 3 caracteres no debe pasar")
        s, _ = self.pedir("POST", "/api/auth/registro",
                          {"email": "sinarroba", "password": "contrasena1"}, None)
        self.assertEqual(s, 400, "un correo mal escrito no debe pasar")

    def test_02_registro_deja_la_cuenta_lista(self):
        s, d = self.pedir("POST", "/api/auth/registro",
                          {"email": "chicos@wheels.mx", "password": "coleccion2026",
                           "nombre": "Chicos"}, None)
        self.assertEqual(s, 201)
        PruebasAPI.token = d["token"]
        _, plats = self.pedir("GET", "/api/plataformas")
        self.assertEqual(len(plats), 4, "debe traer Mercado Libre, eBay, Facebook y Bazar")
        PruebasAPI.plataforma = next(p["id"] for p in plats if p["codigo"] == "ML")

    def test_03_no_repite_correo(self):
        s, _ = self.pedir("POST", "/api/auth/registro",
                          {"email": "chicos@wheels.mx", "password": "otracosa123"}, None)
        self.assertEqual(s, 409)

    def test_04_sin_token_no_hay_acceso(self):
        s, _ = self.pedir("GET", "/api/estado", token=None)
        self.assertEqual(s, 401)

    def test_05_login_no_revela_si_el_correo_existe(self):
        s, d = self.pedir("POST", "/api/auth/login",
                          {"email": "chicos@wheels.mx", "password": "mala"}, None)
        self.assertEqual(s, 401)
        self.assertIn("Correo o contraseña", d["error"])

    # ---------------- Inventario ----------------

    def test_06_crea_pieza_con_valuacion_inicial(self):
        s, d = self.pedir("POST", "/api/articulos", {
            "tipo": "Hot Wheels", "nombre": "Datsun 240Z", "precio_compra": 100,
            "valor_estimado": 500, "cantidad": 4, "fecha_adq": "2026-01-10", "ubicacion": "Caja A",
        })
        self.assertEqual(s, 201)
        PruebasAPI.articulo = d["id"]
        self.assertEqual(d["disponible"], 4)
        _, det = self.pedir("GET", f"/api/articulos/{d['id']}")
        self.assertEqual(len(det["valuaciones"]), 1,
                         "el valor inicial debe quedar en el historial de precios")

    def test_07_rechaza_pieza_sin_nombre(self):
        s, _ = self.pedir("POST", "/api/articulos", {"tipo": "Hot Wheels", "nombre": "   "})
        self.assertEqual(s, 400)

    # ---------------- Dinero ----------------

    def test_08_la_ganancia_la_calcula_la_base_de_datos(self):
        # 500 cobrados − 100 costo − 25 cuota fija − 65 comisión (13%) − 80 envío − 20 otros = 210
        s, d = self.pedir("POST", "/api/ventas", {
            "articulo_id": self.articulo, "plataforma_id": self.plataforma, "cantidad": 1,
            "precio": 500, "envio": 80, "otros": 20, "fecha": "2026-07-20",
            "ganancia_neta": 999999,   # intento de manipulación desde el cliente
        })
        self.assertEqual(s, 201)
        self.assertAlmostEqual(d["ganancia_neta"], 210, places=2,
                               msg="el número que mandó el cliente debe ignorarse")

    def test_09_vender_descuenta_stock(self):
        _, d = self.pedir("GET", f"/api/articulos/{self.articulo}")
        self.assertEqual(d["cantidad"], 3)

    def test_10_apartado_reserva_y_bloquea(self):
        s, ap = self.pedir("POST", "/api/apartados", {
            "articulo_id": self.articulo, "cantidad": 3, "precio_acordado": 600,
            "anticipo": 200, "fecha_limite": "2099-01-01",
        })
        self.assertEqual(s, 201)

        _, art = self.pedir("GET", f"/api/articulos/{self.articulo}")
        self.assertEqual(art["cantidad"], 3)
        self.assertEqual(art["disponible"], 0, "todo el stock quedó comprometido")

        s, err = self.pedir("POST", "/api/ventas", {
            "articulo_id": self.articulo, "plataforma_id": self.plataforma, "precio": 300})
        self.assertEqual(s, 409, "no debe permitir vender lo que está apartado")
        self.assertIn("apartado", err["error"].lower())

        # Liquidar sí procede y consume el stock reservado.
        s, venta = self.pedir("POST", "/api/ventas", {
            "articulo_id": self.articulo, "plataforma_id": self.plataforma, "cantidad": 3,
            "precio": 600, "apartado_id": ap["id"]})
        self.assertEqual(s, 201)
        self.assertEqual(venta["anticipo_aplicado"], 200)

        _, art = self.pedir("GET", f"/api/articulos/{self.articulo}")
        self.assertEqual(art["cantidad"], 0)
        _, aps = self.pedir("GET", "/api/apartados")
        self.assertEqual(aps[0]["estatus"], "Liquidado")

    def test_11_anticipo_no_supera_el_precio(self):
        _, a = self.pedir("POST", "/api/articulos", {"tipo": "Pokémon", "nombre": "Carta prueba"})
        s, _ = self.pedir("POST", "/api/apartados",
                          {"articulo_id": a["id"], "precio_acordado": 100, "anticipo": 500})
        self.assertEqual(s, 400)

    def test_12_lote_reparte_precio_y_cobra_cuota_una_vez(self):
        _, a1 = self.pedir("POST", "/api/articulos", {
            "tipo": "Hot Wheels", "nombre": "Lote A", "precio_compra": 20, "valor_estimado": 300})
        _, a2 = self.pedir("POST", "/api/articulos", {
            "tipo": "Hot Wheels", "nombre": "Lote B", "precio_compra": 20, "valor_estimado": 100})
        s, d = self.pedir("POST", "/api/ventas/lote", {
            "articulo_ids": [a1["id"], a2["id"]], "plataforma_id": self.plataforma,
            "precio": 400, "envio": 50, "fecha": "2026-07-25"})
        self.assertEqual(s, 201)
        v1, v2 = d["ventas"]
        self.assertAlmostEqual(v1["precio"], 300, places=2, msg="reparte según el valor de mercado")
        self.assertAlmostEqual(v2["precio"], 100, places=2)
        self.assertEqual(v1["com_fija"] + v2["com_fija"], 25, "la cuota fija se cobra una vez")
        self.assertEqual(v1["envio"] + v2["envio"], 50, "el envío es del paquete completo")

    def test_13_lote_necesita_dos_piezas(self):
        s, _ = self.pedir("POST", "/api/ventas/lote",
                          {"articulo_ids": ["x"], "plataforma_id": self.plataforma, "precio": 100})
        self.assertEqual(s, 400)

    def test_14_intercambio_mueve_inventario(self):
        _, a = self.pedir("POST", "/api/articulos", {
            "tipo": "Hot Wheels", "nombre": "Bel Air 57", "valor_estimado": 180})
        s, d = self.pedir("POST", "/api/intercambios", {
            "contraparte": "Puesto 14", "entrega_ids": [a["id"]],
            "recibidos": [{"nombre": "Skyline C210", "tipo": "Hot Wheels", "valor": 420}]})
        self.assertEqual(s, 201)
        self.assertEqual(d["diferencia"], 240, "420 recibidos menos 180 entregados")

        _, est = self.pedir("GET", "/api/estado")
        entregada = next(x for x in est["articulos"] if x["id"] == a["id"])
        self.assertEqual(entregada["cantidad"], 0, "la entregada sale del inventario")
        recibida = next((x for x in est["articulos"] if x["nombre"] == "Skyline C210"), None)
        self.assertIsNotNone(recibida, "la recibida entra al inventario")
        self.assertEqual(recibida["precio_compra"], 0, "entra con costo cero")

    def test_15_cancelar_venta_devuelve_stock(self):
        _, a = self.pedir("POST", "/api/articulos", {
            "tipo": "Hot Wheels", "nombre": "Devolución", "cantidad": 2,
            "precio_compra": 10, "valor_estimado": 50})
        _, v = self.pedir("POST", "/api/ventas", {
            "articulo_id": a["id"], "plataforma_id": self.plataforma, "cantidad": 2, "precio": 100})
        _, d = self.pedir("GET", f"/api/articulos/{a['id']}")
        self.assertEqual(d["cantidad"], 0)
        self.pedir("DELETE", f"/api/ventas/{v['id']}")
        _, d = self.pedir("GET", f"/api/articulos/{a['id']}")
        self.assertEqual(d["cantidad"], 2)

    def test_16_cambiar_comision_no_toca_el_historial(self):
        _, antes = self.pedir("GET", "/api/ventas")
        previos = sorted(v["ganancia_neta"] for v in antes)
        self.pedir("PATCH", f"/api/plataformas/{self.plataforma}",
                   {"nombre": "Mercado Libre", "codigo": "ML", "com_pct": 0.30, "com_fija": 99})
        _, despues = self.pedir("GET", "/api/ventas")
        self.assertEqual(previos, sorted(v["ganancia_neta"] for v in despues),
                         "las ventas ya registradas deben quedar congeladas")

    # ---------------- Valuación y métricas ----------------

    def test_17_valuacion_mueve_precio_y_guarda_tendencia(self):
        s, d = self.pedir("POST", f"/api/articulos/{self.articulo}/valuaciones",
                          {"valor": 750, "fuente": "eBay vendidos"})
        self.assertEqual(s, 201)
        self.assertEqual(d["articulo"]["valor_estimado"], 750)
        self.assertGreaterEqual(len(d["valuaciones"]), 2)

    def test_18_metricas_en_sql_coinciden_con_las_ventas(self):
        _, st = self.pedir("GET", "/api/stats")
        _, ventas = self.pedir("GET", "/api/ventas")
        self.assertAlmostEqual(st["ganancia"], sum(v["ganancia_neta"] for v in ventas), places=2)
        self.assertIsInstance(st["por_canal"], list)

    def test_19_precio_objetivo(self):
        # Para ganar 200 en un canal al 13% + 25 fijos, con 45 de costo:
        # (200 + 45 + 25) / 0.87 = 310.34
        s, d = self.pedir("POST", "/api/calculadora/precio-objetivo", {
            "plataforma_id": self.plataforma, "deseado": 200, "costo_total": 45})
        self.assertEqual(s, 200)
        self.assertGreater(d["precio"], 245, "debe cubrir costo, comisión y ganancia")

    # ---------------- Aislamiento ----------------

    def test_20_una_cuenta_no_ve_la_de_otra(self):
        _, d = self.pedir("POST", "/api/auth/registro",
                          {"email": "ajena@wheels.mx", "password": "otracuenta123"}, None)
        PruebasAPI.token2 = d["token"]
        s, est = self.pedir("GET", "/api/estado", token=self.token2)
        self.assertEqual(len(est["articulos"]), 0, "la cuenta nueva arranca vacía")
        s, _ = self.pedir("GET", f"/api/articulos/{self.articulo}", token=self.token2)
        self.assertEqual(s, 404, "no debe poder leer piezas ajenas")
        s, _ = self.pedir("DELETE", f"/api/articulos/{self.articulo}", token=self.token2)
        self.assertEqual(s, 404, "no debe poder borrar piezas ajenas")

    def test_21_datos_de_ejemplo_completos(self):
        s, d = self.pedir("POST", "/api/seed", {}, token=self.token2)
        self.assertEqual(s, 200)
        self.assertEqual(len(d["articulos"]), 7)
        self.assertEqual(len(d["ventas"]), 4)
        self.assertEqual(len(d["apartados"]), 2)
        self.assertEqual(len(d["intercambios"]), 1)
        self.assertTrue(any(len(a["valuaciones"]) >= 3 for a in d["articulos"]),
                        "debe haber historial de precios para ver la tendencia")

    def test_22_apartado_vencido_se_marca_solo(self):
        _, est = self.pedir("GET", "/api/estado", token=self.token2)
        self.assertTrue(any(a["estatus"] == "Vencido" for a in est["apartados"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
