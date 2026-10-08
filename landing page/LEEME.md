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

### Asistente (chat) — 2026-09-29
- Botón **"💬 Pregúntame · ¿Buscas una pieza?"** (`asistente.js`, píldora roja abajo a la derecha) y **"Apartar aquí"** en la ficha. Con `LANDING_EMAIL` usa el stock real; con piezas de ejemplo funciona en **vista previa** (busca en esas piezas y no guarda nada).
- **Por llegar**: las piezas "Por recibir" salen con la etiqueta 🚚 "Llega aprox. <fecha>" y su filtro; se pueden apartar (entrega el sábado después de que lleguen).
- Responde con el stock real. **"Lo quiero"** crea un pedido *Apartado* **sin anticipo** para el próximo sábado en Balderas (lo ves en Pedidos); si no hay, **"Avísenme"** deja al cliente en la lista de espera (Compradores). Pide solo nombre y Facebook/Instagram.
- `ASISTENTE_IA=1` (+ `ANTHROPIC_API_KEY`) hace que Claude Haiku entienda mensajes libres; la disponibilidad y el precio siempre salen de la base. `ASISTENTE_IA_TOPE` limita las consultas diarias.
- `CW_TELEGRAM_TOKEN` + `CW_TELEGRAM_CHAT_ID`: te avisa por Telegram de cada apartado (opcional).

El contacto con clientes es solo por Facebook e Instagram.

## Verla en tu PC

Doble clic en `index.html`: se ve con las piezas de ejemplo.

Las fotos de ejemplo son fotos oficiales de producto de Mattel Creations (autos) y de
pokemontcg.io (cartas). Con tu stock real se ven tus propias fotos.
