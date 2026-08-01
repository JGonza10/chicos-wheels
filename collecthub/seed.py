"""Datos de ejemplo para explorar la app sin capturar nada."""
from datetime import date, timedelta

from .db import transaccion, uno
from .util import uid


def _dias(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def sembrar(usuario_id: str):
    with transaccion() as con:

        def canal(codigo):
            fila = con.execute("SELECT * FROM plataformas WHERE usuario_id=? AND codigo=?",
                               (usuario_id, codigo)).fetchone()
            return dict(fila)

        compradores = []
        for nombre, tel, interes, notas in [
            ("@pkm_collector99", "55 1234 5678", "Pokémon", "Solo cartas en japonés, paga por adelantado"),
            ("Ricardo Mena", "55 8765 4321", "Hot Wheels", "Busca Treasure Hunt de cualquier año"),
            ("Bazar Roma Norte", "55 2222 1111", "Ambas", "Compra lotes completos"),
        ]:
            id_c = uid("C")
            con.execute("INSERT INTO compradores (id,usuario_id,nombre,tel,interes,notas) "
                        "VALUES (?,?,?,?,?,?)", (id_c, usuario_id, nombre, tel, interes, notas))
            compradores.append(id_c)

        def crear_art(a: dict, valuaciones=()):
            id_a = uid("PKM" if a["tipo"] == "Pokémon" else "HW")
            cols = list(a.keys())
            con.execute(
                f"INSERT INTO articulos (id,usuario_id,cant_inicial,{','.join(cols)}) "
                f"VALUES (?,?,?,{','.join('?' * len(cols))})",
                [id_a, usuario_id, a.get("cantidad", 1)] + [a[c] for c in cols])
            for f, v, fuente in valuaciones:
                con.execute("INSERT INTO valuaciones (id,articulo_id,fecha,valor,fuente) "
                            "VALUES (?,?,?,?,?)", (uid("VAL"), id_a, f, v, fuente))
            return id_a

        crear_art({
            "tipo": "Hot Wheels", "nombre": "Custom Datsun 240Z", "numero": "150/250", "anio": 2023,
            "serie": "Super Treasure Hunt", "color": "Verde perla", "sub": "Tarjeta larga",
            "estado": "Sellado / Mint", "cantidad": 1, "estatus": "Conservar",
            "precio_compra": 35, "valor_estimado": 980, "fecha_adq": _dias(270),
            "fuente": "Tienda / retail", "ubicacion": "Vitrina 2", "codigo": "0194735012345",
            "grail": 1, "checks": "[0,1,2,3]",
            "notas": "Llantas de goma reales, sello STH en el costado.",
        }, [(_dias(270), 620, "Registro inicial"), (_dias(150), 790, "Mercado Libre"),
            (_dias(60), 880, "eBay vendidos"), (_dias(10), 980, "Mercado Libre")])

        skyline = crear_art({
            "tipo": "Hot Wheels", "nombre": "Nissan Skyline GT-R (BNR34)", "numero": "088/250",
            "anio": 2024, "serie": "Mainline", "color": "Azul Bayside", "sub": "Tarjeta corta",
            "estado": "Sellado / Mint", "cantidad": 3, "precio_compra": 28, "valor_estimado": 120,
            "fecha_adq": _dias(196), "fuente": "Tienda / retail", "ubicacion": "Caja A",
            "codigo": "0194735098765",
        }, [(_dias(196), 95, "Registro inicial"), (_dias(80), 110, "Facebook"),
            (_dias(5), 120, "Mercado Libre")])

        crear_art({
            "tipo": "Hot Wheels", "nombre": "Porsche 911 GT3 RS", "numero": "12/20", "anio": 2022,
            "serie": "Premium / Car Culture", "color": "Blanco", "sub": "Blíster especial",
            "estado": "Excelente", "cantidad": 1, "estatus": "En negociación",
            "precio_compra": 180, "valor_estimado": 210, "fecha_adq": _dias(340),
            "fuente": "Convención", "ubicacion": "Vitrina 1",
        }, [(_dias(340), 240, "Registro inicial"), (_dias(120), 225, "eBay vendidos"),
            (_dias(15), 210, "Mercado Libre")])

        crear_art({
            "tipo": "Pokémon", "nombre": "Charizard ex", "numero": "223/197", "anio": 2023,
            "expansion": "Obsidian Flames", "rareza": "Illustration Rare", "sub": "Inglés",
            "grado": "Sin graduar", "estado": "Near Mint", "cantidad": 1, "precio_compra": 420,
            "valor_estimado": 1420, "fecha_adq": _dias(240), "fuente": "Compra en línea",
            "ubicacion": "Carpeta azul · hoja 3", "checks": "[0,1,3]",
        }, [(_dias(240), 900, "Registro inicial"), (_dias(120), 1150, "TCGplayer"),
            (_dias(20), 1420, "Cardmarket")])

        pikachu = crear_art({
            "tipo": "Pokémon", "nombre": "Pikachu VMAX", "numero": "044/185", "anio": 2021,
            "expansion": "Vivid Voltage", "rareza": "Ultra Rare", "sub": "Español",
            "estado": "Excelente", "cantidad": 2, "precio_compra": 150, "valor_estimado": 360,
            "fecha_adq": _dias(140), "fuente": "Bazar o tianguis",
            "ubicacion": "Carpeta azul · hoja 1",
        }, [(_dias(140), 410, "Registro inicial"), (_dias(60), 385, "TCGplayer"),
            (_dias(8), 360, "Mercado Libre")])

        crear_art({
            "tipo": "Pokémon", "nombre": "Mew ex (Special Illustration)", "numero": "205/165",
            "anio": 2023, "expansion": "151", "rareza": "Secret Rare", "sub": "Japonés",
            "grado": "PSA 10", "cert": "87456120", "estado": "Mint", "cantidad": 1,
            "estatus": "Conservar", "precio_compra": 1800, "valor_estimado": 4600,
            "fecha_adq": _dias(69), "fuente": "Compra en línea", "ubicacion": "Caja fuerte",
            "grail": 1, "checks": "[0,1,2,3,4]",
        }, [(_dias(69), 3800, "Registro inicial"), (_dias(30), 4200, "eBay vendidos"),
            (_dias(3), 4600, "Cardmarket")])

        crear_art({
            "tipo": "Hot Wheels", "nombre": "Lamborghini Countach LP 5000", "numero": "201/250",
            "anio": 2021, "serie": "Mainline", "color": "Rojo", "sub": "Tarjeta corta",
            "estado": "Excelente", "cantidad": 1, "precio_compra": 30, "valor_estimado": 95,
            "fecha_adq": _dias(410), "fuente": "Bazar o tianguis", "ubicacion": "Caja A",
        })

        for nombre, tipo, tope, prio, detalle in [
            ("Super Treasure Hunt 2025 — Toyota Supra", "Hot Wheels", 400, 5,
             "Solo tarjeta larga sin dobleces"),
            ("Umbreon VMAX Alt Art", "Pokémon", 6500, 4, "Evolving Skies, mínimo Near Mint"),
        ]:
            con.execute("INSERT INTO wishlist (id,usuario_id,nombre,tipo,tope,prioridad,detalle) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (uid("W"), usuario_id, nombre, tipo, tope, prio, detalle))

        # Ventas históricas: cada una congeló la comisión vigente ese día.
        for nombre, tipo, comp, cod, cant, precio, envio, otros, costo, f, adq in [
            ("Ferrari F40 Competizione", "Hot Wheels", compradores[1], "ML", 1, 450, 85, 0, 30,
             _dias(18), _dias(180)),
            ("Gengar VMAX Alt Art", "Pokémon", compradores[0], "EB", 1, 2900, 220, 60, 1400,
             _dias(25), _dias(260)),
            ("Lote 12 Mainline surtidos", "Hot Wheels", compradores[2], "BZ", 12, 900, 0, 0, 28,
             _dias(32), _dias(90)),
            ("Snorlax VMAX", "Pokémon", None, "FB", 1, 600, 60, 0, 250, _dias(5), _dias(107)),
        ]:
            p = canal(cod)
            con.execute(
                "INSERT INTO ventas (id,usuario_id,articulo_id,comprador_id,plataforma_id,"
                "nombre_snap,tipo_snap,plataforma_snap,cantidad,precio,envio,otros,costo_unit,"
                "com_pct,com_fija,ret_pct,fecha,fecha_adq_snap,estatus_envio) "
                "VALUES (?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (uid("V"), usuario_id, comp, p["id"], nombre, tipo, p["nombre"], cant, precio,
                 envio, otros, costo, p["com_pct"], p["com_fija"], p["ret_pct"], f, adq,
                 "Entregado" if envio else "Sin envío"))

        # Un apartado vigente y uno vencido, para ver ambos estados.
        con.execute("INSERT INTO apartados (id,usuario_id,articulo_id,comprador_id,nombre_snap,"
                    "cantidad,precio_acordado,anticipo,fecha,fecha_limite,notas) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (uid("AP"), usuario_id, skyline, compradores[1],
                     "Nissan Skyline GT-R (BNR34)", 1, 140, 50, _dias(6), _dias(-9),
                     "Paga el viernes de quincena"))
        con.execute("INSERT INTO apartados (id,usuario_id,articulo_id,comprador_id,nombre_snap,"
                    "cantidad,precio_acordado,anticipo,fecha,fecha_limite,estatus,notas) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'Vencido',?)",
                    (uid("AP"), usuario_id, pikachu, compradores[0], "Pikachu VMAX", 1, 380, 100,
                     _dias(40), _dias(12), "Ya no contestó"))

        # Un intercambio: entregó $320 de valor y recibió $420.
        id_t = uid("T")
        con.execute("INSERT INTO intercambios (id,usuario_id,fecha,contraparte,notas,diferencia) "
                    "VALUES (?,?,?,?,?,?)",
                    (id_t, usuario_id, _dias(48), "Puesto 14 del tianguis",
                     "Acepté porque llevaba meses buscando el Skyline.", 100))
        for direccion, nombre, valor in [
            ("entrega", "Chevrolet Bel Air 57", 180),
            ("entrega", "Datsun 510 Wagon", 140),
            ("recibe", "Nissan Skyline C210 Silhouette", 420),
        ]:
            con.execute("INSERT INTO intercambio_items (id,intercambio_id,direccion,nombre,"
                        "tipo,valor) VALUES (?,?,?,?,?,?)",
                        (uid("TI"), id_t, direccion, nombre, "Hot Wheels", valor))
