# Manual de Chicos Wheels (CollectHub)

_Manual de usuario del sistema de inventario y venta de coleccionables. Refleja el estado del código al 2026-09-25. Regenera los formatos imprimibles con `python generar_manual.py`._

## 1. Qué es

Sistema de inventario, valuación y venta de coleccionables (Hot Wheels y cartas Pokémon), pensado para uno o dos usuarios (negocio pequeño/personal). Corre en `http://localhost:3000` de esta máquina de forma permanente (arrancado por Nexus).

## 2. Cómo entrar

Login con usuario y contraseña propios (sesión con token, 10 intentos por 15 minutos antes de bloquear). Cada cuenta solo ve su propio inventario y sus propias fotos — ni siquiera adivinando la ruta de una foto se puede ver la de otra cuenta.

## 3. Identificar una pieza por foto

Sube o toma una foto de la pieza:
- Se valida que sea una imagen real (no solo por su extensión), se le quita la información de ubicación/cámara oculta y se reduce de tamaño antes de usarla.
- Una IA (Claude) sugiere qué pieza es — es solo una sugerencia, no modifica tu inventario sola.
- Para cartas Pokémon, además cruza contra una base de datos de precios real y solo te da un precio si encuentra una coincidencia clara (con 0 o varias coincidencias, prefiere no adivinar).

## 4. Cómo se trabaja cada semana (el flujo del negocio)

La app existe para un ciclo simple: **comprar → recibir → publicar en Facebook → apartar → entregar el sábado en Balderas → llevar la contabilidad**.

1. **Registrar lo que compraste.**
   - *Compra de Mattel:* botón **🛒 Compra Mattel** (en Inventario). Pega los links de lo que compraste, uno por renglón, y **Traer datos**: trae nombre, foto y precio (convertido a pesos). Se registran como **Por recibir**.
   - *Una sola pieza de Mattel:* en **Registrar pieza**, pega el link y **Traer datos**.
   - *Compra en otro lado (o cartas Pokémon):* **Registrar pieza** a mano, o **📷 Con foto** para que la IA sugiera los datos.
   - Si el monitor/bot del proyecto 15 compra por ti, la pieza llega sola al inventario como **Por recibir**.
2. **Recibir.** En el Panel aparece **Por recibir**: escribe dónde la guardas (ej. Caja A) y pulsa **Ya llegó**.
3. **Publicar en Facebook.** En la pieza, **Publicación** genera el texto listo para copiar (con "entrega en Balderas") y **📸 Foto lista** la deja cuadrada y nítida. Para varias piezas: **Seleccionar varias → Publicar en lote** (con descuento por combo opcional).
4. **Apartar.** Cuando un cliente quiere algo: **Pedidos → + Nuevo pedido** (o **Apartar** en la ficha de la pieza). Elige al cliente o escribe uno nuevo, agrega **una o varias piezas**, deja la fecha (por defecto el **próximo sábado**) y, si dejó dinero, el anticipo y cómo lo pagó. Las piezas quedan reservadas: no se pueden ofrecer a otro.
5. **Estatus de cada pedido:** **Apartado** (reservado, con o sin anticipo) → **En proceso** (ya empacado para el sábado) → **Liquidado** (entregado y pagado). En el Inventario cada pieza reservada dice **para quién y para cuándo**.
6. **Confirmar con el cliente.** El botón **💬** abre WhatsApp con el mensaje del pedido (piezas, total, anticipo, lo que resta y "nos vemos el sábado en Balderas").
7. **Llevar el catálogo.** En **Pedidos** elige el sábado y **🖨 Generar PDF**: trae qué empacar (por ubicación), el detalle por cliente con costo y precio por pieza y total, y el **cruce final** de piezas contra dinero por cobrar (efectivo o depósito). Se imprime y se lleva. Si prefieres una **lista tipo hoja de cálculo**, el botón **📊 Excel** baja el mismo reporte en `.xlsx`: una fila por pieza (con filtros y totales), una hoja "Por cliente" con columnas para anotar lo cobrado en efectivo y depósito y la diferencia, y una hoja "Empacar" con las piezas juntas por ubicación.
8. **Entregar y cobrar.** En Balderas, por cada cliente: **💵** (entregado y cobrado en efectivo) o **🏦** (por depósito) de un toque, o **Entregar…** si hubo descuento o cobró otra cantidad. Cada pieza se vuelve una venta y sale del inventario.
9. **Ver cómo va el negocio.** El **Panel** muestra los pedidos por entregar, lo que falta cobrar, los movimientos por mes y de dónde salen tus mejores piezas.

Entre semana también se puede: en el pedido se cambia la fecha de entrega a otro día (por ejemplo, alrededores de Coyoacán).

## 4b. Inventario y movimientos

- Alta de artículos con valuación, categoría y foto. Vista de **fichas** o de **lista** (como hoja de cálculo, con columnas ordenables y totales).
- Ventas, lotes, intercambios, **pedidos** (varias piezas por cliente) y los **apartados previos** de una sola pieza (esa pantalla solo aparece si ya tenías apartados).
- La ganancia neta la calcula la base de datos misma (no la pantalla ni el servidor) para que no se pueda falsear editando el código.
- **Precio mínimo ("piso")**: lo menos que puedes aceptar y aún ganar tu margen mínimo; aparece en la ficha de la pieza.
- **Lista de espera de clientes**: si alguien pide algo que no tienes, anótalo en Compradores; al abrir una pieza parecida verás su pedido.
- **Respaldo automático diario** de la base de datos (últimos 14 días, en la carpeta `datos/respaldos`).

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
