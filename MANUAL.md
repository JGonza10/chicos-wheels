# Manual de Chicos Wheels (CollectHub)

_Manual de usuario del sistema de inventario y venta de coleccionables. Refleja el estado del código al 2026-09-08. Regenera los formatos imprimibles con `python generar_manual.py`._

## 1. Qué es

Sistema de inventario, valuación y venta de coleccionables (Hot Wheels y cartas Pokémon), pensado para uno o dos usuarios (negocio pequeño/personal). Corre en `http://localhost:3000` de esta máquina de forma permanente (arrancado por Nexus).

## 2. Cómo entrar

Login con usuario y contraseña propios (sesión con token, 10 intentos por 15 minutos antes de bloquear). Cada cuenta solo ve su propio inventario y sus propias fotos — ni siquiera adivinando la ruta de una foto se puede ver la de otra cuenta.

## 3. Identificar una pieza por foto

Sube o toma una foto de la pieza:
- Se valida que sea una imagen real (no solo por su extensión), se le quita la información de ubicación/cámara oculta y se reduce de tamaño antes de usarla.
- Una IA (Claude) sugiere qué pieza es — es solo una sugerencia, no modifica tu inventario sola.
- Para cartas Pokémon, además cruza contra una base de datos de precios real y solo te da un precio si encuentra una coincidencia clara (con 0 o varias coincidencias, prefiere no adivinar).

## 4. Inventario y movimientos

- Alta de artículos con valuación, categoría y foto.
- Ventas, lotes (varias piezas juntas), apartados e intercambios — cada uno con su propio registro.
- La ganancia neta la calcula la base de datos misma (no la pantalla ni el servidor) para que no se pueda falsear editando el código.

## 5. Catálogos de apoyo

Compradores, plataformas de venta, lista de deseos (wishlist), y ajustes generales del sistema — todo en su propia sección.

## 6. Métricas y respaldo

- Pantalla de estado con métricas del inventario.
- Exportar datos, y una plantilla de Excel para importar inventario en lote.
- Respaldo en caliente de la base de datos (seguro con el sistema corriendo — copiar el archivo a mano mientras funciona puede corromperlo).

## 7. En el celular

Es una PWA instalable: "Agregar a pantalla de inicio" desde el navegador del celular. Funciona sin conexión para lo ya cargado (los datos en vivo siempre necesitan conexión).

## 8. Instalación y arranque

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # desarrollo, http://localhost:3000
```

Producción (recomendado, ya en uso en esta máquina):
```bash
docker compose up -d --build
```

`JWT_SECRET` es obligatoria en producción — el sistema se niega a arrancar sin ella.

## 9. Lo que todavía no hace

- No hay build de frontend con librerías modernas — el frontend es HTML/CSS/JS plano a propósito, se edita directo.
- Pensado para uno o dos usuarios, no para una operación con muchos cajeros a la vez (ver el sistema de Abarrotes para eso).
