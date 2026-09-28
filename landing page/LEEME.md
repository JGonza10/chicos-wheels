# Landing page de Chicos Wheels

Página para que los clientes vean **lo que hay en stock**. Vive en esta carpeta, aparte
del resto de la app, y la app la publica en **`/tienda/`** (por ejemplo
`https://tu-app.up.railway.app/tienda/`).

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | La página (basada en el borrador CW.html). |
| `CW.css` | Estilos: rojo, amarillo y azul, flamas y modo oscuro. |
| `CW.js` | Filtros, búsqueda, ficha ampliada, "Me interesa" y modo oscuro. |
| `tema.js` | Aplica el modo claro/oscuro antes de pintar. |
| `stock.js` | Piezas **de ejemplo**. En la app, el stock real se genera al momento y reemplaza a este. |
| `img/portada.png` | Imagen de la portada (la pones tú). La mitad izquierda lleva a Hot Wheels y la derecha a Pokémon. Si no existe, se ven las dos tarjetas de colores. |

## Cómo se llena el stock

Solo. Cada vez que alguien abre `/tienda/`, la app lee el inventario y muestra las piezas
**Disponibles** que ya llegaron y no están apartadas, con sus fotos. Nunca publica costos,
ganancias, proveedores, ubicaciones, notas ni datos de clientes.

Variables en Railway:

- `LANDING_EMAIL`: correo de tu cuenta en la app. Sin ella se ven las piezas de ejemplo.
- `LANDING_FACEBOOK`: tu página de Facebook (usuario o URL), para el botón de Messenger.
- `LANDING_INSTAGRAM`: tu usuario de Instagram, para el botón de mensaje directo.

El contacto con clientes es solo por Facebook e Instagram.

## Verla en tu PC

Doble clic en `index.html`: se ve con las piezas de ejemplo.

Las fotos de ejemplo son fotos oficiales de producto de Mattel Creations (autos) y de
pokemontcg.io (cartas). Con tu stock real se ven tus propias fotos.
