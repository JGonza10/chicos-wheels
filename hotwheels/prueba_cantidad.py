# -*- coding: utf-8 -*-
"""Prueba de la cantidad a comprar: el maximo que permita la pagina.

    python prueba_cantidad.py

Sin red ni navegador: solo la lectura del limite y la regla de cantidad.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_logic as B  # noqa: E402

fallos = 0


def revisa(nombre, obtenido, esperado):
    global fallos
    ok = obtenido == esperado
    fallos += not ok
    print(f"{'✅' if ok else '❌'} {nombre}: {obtenido!r} (esperado {esperado!r})")


# Limite desde la etiqueta del producto (RWB 930: "limit_2") o desde el texto
revisa("etiqueta limit_2", B.limite_desde_datos(["RLC", "limit_2"]), 2)
revisa("texto Limit 3 Per Customer", B.limite_desde_datos([], "Hurry! Limit 3 Per Customer"), 3)
revisa("etiqueta gana al texto", B.limite_desde_datos(["limit_1"], "Limit 4 per order"), 1)
revisa("sin limite", B.limite_desde_datos(["Brand: Hot Wheels"], "Add to Bag"), None)
revisa("plantilla {{ quantity_limit }} no cuenta", B.limite_desde_datos([], "limit of {{ quantity_limit }} per order"), None)

# Cantidad: None = maximo; a mano nunca pasa del limite
revisa("maximo con limite 2", B.cantidad_a_pedir(None, 2), 2)
revisa("maximo sin limite usa HOTWHEELS_MAX_QUANTITY", B.cantidad_a_pedir(None, None), B.MAX_QUANTITY)
revisa("a mano 5 con limite 2", B.cantidad_a_pedir(5, 2), 2)
revisa("a mano 1 con limite 2", B.cantidad_a_pedir(1, 2), 1)
revisa("a mano 3 sin limite", B.cantidad_a_pedir(3, None), 3)

print("\nTodo bien." if not fallos else f"\n{fallos} prueba(s) fallaron.")
sys.exit(1 if fallos else 0)
