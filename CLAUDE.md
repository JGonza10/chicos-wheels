# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es esto

Chicos Wheels (CollectHub): sistema de inventario, valuación y venta de coleccionables (Hot Wheels y cartas Pokémon), con backend Flask y frontend HTML/CSS/JS plano sin build. Pensado para uno o dos usuarios por instancia (negocio pequeño/personal). Todo el código, comentarios y mensajes de error están en español.

`README.md` ya documenta a fondo características de negocio y stack — léelo primero. Este archivo se enfoca en lo que ese README no cubre: comandos exactos y detalles de implementación no obvios.

## Comandos

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows; en Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py                                        # dev server en http://localhost:3000
python -m unittest discover -s tests -t . -v          # 28 pruebas contra BD temporal
python scripts/generar_iconos_pwa.py                  # regenera static/icon-*.png si cambia el diseño
```

Producción vía Docker (`Dockerfile` + `docker-compose.yml`, volumen persistente `collecthub-datos`):
```bash
docker compose up -d --build
```
o directo con gunicorn (obligatorio un solo worker: SQLite no admite escritura concurrente multi-proceso):
```bash
gunicorn "collecthub:crear_app()" -b 0.0.0.0:3000 -w 1 --threads 8
```

Variables de entorno: copiar `.env.example` a `.env`. `JWT_SECRET` es obligatoria cuando `FLASK_ENV=production` (la app se niega a arrancar sin ella); `docker-compose.yml` la exige igual vía `${JWT_SECRET:?...}`.

En esta máquina la app no arranca sola: se prende a pedido desde el hub local "Nexus" (`python app.py`, proyecto `P2`). Los supervisores/arranque silencioso de Windows se eliminaron el 2026-09-15.

## Arquitectura

- **`app.py`** — entrypoint. Carga `.env` a mano (sin `python-dotenv`, parseo propio de líneas `CLAVE=valor`), crea la app con `collecthub.crear_app()` y sirve con el servidor de desarrollo de Flask si se ejecuta directo.
- **`collecthub/__init__.py`** — application factory. Registra los blueprints de `collecthub/rutas/` bajo `/api/...`, y luego **envuelve automáticamente** todas las vistas de `articulos`, `movimientos`, `catalogos` y `estado` con `requiere_sesion` recorriendo `app.view_functions` por prefijo de endpoint — así una ruta nueva en esos blueprints queda protegida por defecto sin tener que acordarse de decorarla. `auth` y `/api/salud` quedan públicas a propósito. También trae: rate limiting propio en memoria (sin dependencia extra) con dos niveles — 10 intentos/15min en login/registro, 300 peticiones/5min general por IP —, cabeceras de seguridad fijas (CSP, HSTS, X-Frame-Options DENY, etc.) y CORS que **no** manda `Access-Control-Allow-Origin` salvo que `CORS_ORIGIN` esté configurado (el frontend se sirve del mismo origen, no lo necesita).
- **`collecthub/db.py`** — conexión SQLite por petición (WAL, `foreign_keys` ON, transacciones explícitas `BEGIN IMMEDIATE` para multi-tabla). `collecthub/schema.sql` es el esquema completo; la ganancia neta se calcula con una columna `GENERATED ALWAYS` en SQL, deliberadamente fuera del backend/cliente para que no se pueda falsear.
- **`collecthub/auth.py`** — sesiones JWT (`PyJWT`), decorador `requiere_sesion`.
- **`collecthub/vision.py`** — identificación de piezas por foto. `procesar_imagen()` valida con Pillow (`.verify()`, nunca confía en extensión/Content-Type), descarta EXIF y reescala a 1280px antes de usar la imagen para nada. `identificar_foto()` llama a Claude (SDK `anthropic`, salida estructurada `output_config: {"format":{"type":"json_schema",...}}`, mismo patrón que `_interpretar_con_claude()` en `Nexus/nexus.py`) — 503 si falta `ANTHROPIC_API_KEY`, nunca tumba el arranque. `buscar_precio_pokemon()` cruza contra `pokemontcg.io` (sin dependencia extra, `urllib`) y solo devuelve algo con una coincidencia sin ambigüedad; con 0 o varios resultados regresa `None` en vez de adivinar.
- **`collecthub/rutas/articulos.py`** también trae las rutas de foto: `POST /identificar` (sugerencia, no toca la BD), `POST /<id>/foto` (guarda en `datos/fotos/<usuario_id>/<hex(20)>.jpg`, actualiza `articulos.foto` a `local:<archivo>`), `GET /foto/<archivo>` (sirve solo si `g.usuario_id` coincide con la carpeta — así una cuenta no puede ver fotos de otra aunque adivine el nombre). Fotos con URL externa (`https://...`) se siguen sirviendo directo; las `local:` no pueden ir en `<img src>` sin el header `Authorization`, por eso el frontend las trae por `fetch`+blob (`pintarFotosLocales()` en `app.js`).
- **`collecthub/rutas/`** — un blueprint por dominio: `auth.py` (registro/login), `articulos.py` (inventario/valuaciones/foto), `movimientos.py` (ventas, lotes, apartados, intercambios), `catalogos.py` (compradores/plataformas/wishlist/ajustes), `estado.py` (métricas, exportar/seed).
- **Frontend estático** — servido desde `/` y cualquier ruta no-`/api` cae a `static/index.html` si el archivo pedido no existe (patrón SPA). Sin build: se edita `static/app.js`/`styles.css` directo. Es PWA instalable: `static/manifest.json` + `static/sw.js` (cache-first solo de estáticos, nunca de `/api/*`) + `static/icon-*.png` (regenerables con `scripts/generar_iconos_pwa.py`). El registro del service worker vive en `app.js` (al final, función `iniciar()`), no en `index.html`, porque el CSP no admite `<script>` inline.
- **`scripts/backup.py`** — respaldo en caliente vía la API de backup nativa de SQLite (seguro con el servidor corriendo; copiar el `.db` a mano durante escrituras puede corromperlo). **`scripts/generar_plantilla.py`** — no mencionado en el README; revísalo si necesitas la plantilla de importación de inventario en Excel (`MAX_CONTENT_LENGTH` de 8MB en `__init__.py` existe justo para acotar esa carga).

## Reglas a mantener al modificar

- Cualquier vista nueva en `articulos`/`movimientos`/`catalogos`/`estado` queda protegida automáticamente por el bucle de `crear_app()` — no agregues `requiere_sesion` a mano ahí, y no rompas el prefijo de endpoint del que depende ese bucle.
- Cálculos de dinero/ganancia que deban ser invulnerables a manipulación van en SQL (`GENERATED ALWAYS`), no en Python ni en JS — sigue el patrón existente en `schema.sql`.
- Cambios en `Content-Security-Policy` (`collecthub/__init__.py`): `'unsafe-inline'` en `style-src` es necesario porque `app.js` arma vistas con estilos inline — no lo quites sin revisar el frontend completo. `img-src` incluye `blob:` a propósito, para las fotos `local:` que el frontend trae por `fetch` y muestra como object URL.
- **Puede haber una instancia de esta app en el puerto 3000 si se prendió desde Nexus** — antes de levantar `python app.py` para probar algo, revisa si el puerto 3000 ya está ocupado (`netstat -ano | grep :3000`) y usa `PORT=<otro>` para no pisarla ni terminar ese proceso sin avisar. Ambas comparten el mismo `datos/collecthub.db` por defecto si no defines `DB_FILE` distinto — cualquier prueba manual (usuarios, artículos) queda en la base real, bórrala después.

## Cambios del 2026-09-25

- **Vista Lista** del inventario (hoja de cálculo: columnas ordenables, totales, encabezado fijo) y **gráfica de movimientos por mes** en el Panel (3/6/12/24 o N meses); se quitó el formulario "Nuevo movimiento" del Panel.
- **Tema Claro** (`data-tema="claro"`, barra lateral oscura porque su texto está fijo en claro).
- **Reporte PDF configurable** (`collecthub/reporte.py`, `POST /api/reporte-pdf`, dependencia `fpdf2`): secciones, categoría, estatus, orden, orientación y rango de fechas de ventas. Configuración en `localStorage` (`cw_reporte`).
- **Entregas** (Catálogos): ventas con envío + apartados, por fecha; `ventas.fecha_entrega` (migración automática en `db.crear_esquema`, se llena al marcar "Entregado" y se borra si regresa de estatus).
- **Recibo PDF por venta** (`GET /api/ventas/<id>/recibo`, botón 🧾 en Entregas): entrega en Balderas o guía de envío.
- **Canal "Balderas"** (`TG`) para cuentas nuevas y existentes. Gonza vende **solo por Facebook y entrega en Balderas**; Mercado Libre/eBay no se usan por ahora (siguen en el catálogo, no estorban). El texto de "Publicación" ya menciona la entrega en Balderas.
- **Movimientos de precio** en el Panel: piezas cuyo valor cambió ≥15% en su última valuación.
- Al cambiar `app.js`/`styles.css` hay que subir `CACHE_VERSION` en `static/sw.js` (hoy `chicoswheels-v8`).
- **Puente con el proyecto 15**: cada compra confirmada de Mattel se registra aquí (ubicación "Por recibir", foto, valor = reventa estimada). Necesita `COLLECTHUB_EMAIL`/`COLLECTHUB_PASSWORD` en el `.env` del proyecto 15.

### Habilidades agregadas después (mismo día)

- **Balderas** (menú Catálogos → 📍): *Lista de carga* imprimible (marcas lo que llevas; al imprimir solo salen esas, con casilla "Vendida") y *Corte del día* (ventas, cobrado, ganancia, anticipos, entregas). Persistencia local: `cw_carga`, `cw_margenMin`.
- **Precio mínimo ("piso")**: `precioMinimo(a)` en `app.js` = (costo × (1+margen) + comisión fija) ÷ (1 − comisión% − retención%) con el canal Balderas (o Facebook). Margen editable (10% por defecto). Se ve en la lista de carga y en la ficha de la pieza.
- **Publicar en lote** (selección múltiple → "Publicar en lote") y **📸 Foto lista** (`GET /api/articulos/<id>/foto-publicar`: cuadrada 1080×1080, contraste y nitidez; solo fotos locales).
- **Lista de espera de clientes**: tabla `pedidos_cliente`, rutas `/api/pedidos` (POST/PATCH/DELETE), incluida en `/api/estado` como `pedidos`. Se administra en Compradores; al abrir una pieza parecida sale "Te la pidieron".
- Corregido: el menú lateral de los temas Champs y Claro salía ilegible (`#ch button{color:inherit}` ganaba por especificidad a `.nav button`; ahora `#ch .nav button`).
- El proyecto 15 avisa por Telegram (9:00 diario) los apartados que vencen hoy o mañana (`collecthub_bridge.apartados_por_vencer`).

### Negocio de referencia y habilidades del 2026-09-25 (tarde)

El usuario final es un joven emprendedor: consigue Hot Wheels y cartas Pokémon (casi todo en Mattel Creations, vía el monitor/bot del proyecto 15), las publica en Facebook y las revende cada semana en la convención/tianguis de **Balderas**. Toda función nueva debe servir a ese ciclo: conseguir → recibir → publicar → vender en Balderas → reinvertir.

- **Registro desde link de Mattel** (`collecthub/mattel.py`, `POST /api/articulos/desde-mattel`): lee `/products/<handle>.js` de Shopify (solo hosts `*.mattel.com` por https), convierte US$→MXN con tipo de cambio en vivo (fallback 20.0). Solo sugiere; el registro manual sigue igual para compras fuera de Mattel.
- **Por recibir**: el puente deja las piezas con ubicación "Por recibir"; el Panel las lista con "Ya llegó" (una o todas) y quedan fuera de la lista de carga.
- **✨ Sugerir carga** (Balderas): prioriza pedidos de clientes, piezas con tiempo guardadas y mejor margen; nunca las griales.
- **Semana vs semana anterior** en el Corte; **descuento por combo** en la publicación en lote; **rendimiento por fuente** en el Panel.
- **Respaldo automático diario** (`collecthub/respaldo.py`): un `.db` por día en `datos/respaldos/` (últimos 14); se apaga con `COLLECTHUB_SIN_RESPALDO=1` (las pruebas lo apagan). Ojo: en Docker `datos/` es el volumen persistente, así que los respaldos también persisten.
- La fuente "Mattel Creations" es ahora la primera de `FUENTES`; el puente la manda tal cual.
