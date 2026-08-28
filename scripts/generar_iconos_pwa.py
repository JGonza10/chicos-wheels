#!/usr/bin/env python3
"""Genera los íconos PNG de la PWA a partir del mismo diseño ("CW" en
círculo azul) que ya usa el favicon inline de static/index.html — para no
introducir una identidad visual nueva. Se corre una sola vez (o cuando se
quiera cambiar el diseño); los PNG resultantes se versionan en el repo
como cualquier otro estático.

    python scripts/generar_iconos_pwa.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent / "static"
AZUL = (46, 155, 240, 255)   # #2E9BF0, el mismo del favicon inline
BLANCO = (255, 255, 255, 255)


def _icono(lado: int, radio_pct: float, texto_pct: float) -> Image.Image:
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(img)
    dibujo.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=round(lado * radio_pct), fill=AZUL)
    fuente = ImageFont.load_default(size=round(lado * texto_pct))
    caja = dibujo.textbbox((0, 0), "CW", font=fuente)
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    dibujo.text(((lado - ancho) / 2 - caja[0], (lado - alto) / 2 - caja[1]), "CW", font=fuente, fill=BLANCO)
    return img


def main():
    RAIZ.mkdir(parents=True, exist_ok=True)
    for lado in (192, 512):
        _icono(lado, radio_pct=7 / 32, texto_pct=0.42).save(RAIZ / f"icon-{lado}.png")
    # Maskable: Android recorta hasta un círculo inscrito, así que el diseño
    # debe caber en la "zona segura" central (~80%) con el fondo a sangre.
    _icono(512, radio_pct=0, texto_pct=0.32).save(RAIZ / "icon-512-maskable.png")
    print(f"Listo: {RAIZ / 'icon-192.png'}, icon-512.png, icon-512-maskable.png")


if __name__ == "__main__":
    main()
