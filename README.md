# Chicos Wheels (CollectHub)

Sistema de inventario, valuación y venta de coleccionables **Hot Wheels** y **cartas Pokémon**, con backend en Flask y frontend web sin build.

## Estado actual

Proyecto activo y funcional, de alcance personal/pequeño negocio (pensado para uno o dos usuarios por instancia). Tiene suite de pruebas automatizadas (28 casos), Dockerfile y `docker-compose.yml` listos para desplegar, y un historial de commits reciente con correcciones puntuales. No hay indicios de CI/CD configurado ni de recuperación de contraseña por correo. Es instalable como PWA (ícono en pantalla de inicio del celular).

## Características principales

- **Alta de piezas por foto (IA)**: toma o sube una foto del Hot Wheels o la carta Pokémon y Claude (visión) sugiere nombre, número, serie/color o expansión/rareza — para Pokémon, además cruza contra `pokemontcg.io` y sugiere precio de mercado real. La sugerencia siempre se muestra editable, con un nivel de confianza, antes de guardar; nunca se guarda sola. Requiere `ANTHROPIC_API_KEY`; sin ella, el resto de la app funciona igual.
- **Inventario de doble perfil**: los campos del artículo cambian según sea un Hot Wheels (serie, color) o una carta Pokémon (expansión, rareza, grado, número de certificado).
- **Historial de valuaciones** por artículo, para ver tendencia de precio en el tiempo.
- **Apartados con anticipo**: bloquean el artículo (no se puede vender por otro lado) y vencen solos según fecha límite.
- **Ventas por lote**: reparte el precio entre varias piezas según su valor de mercado y cobra una sola vez la cuota fija.
- **Intercambios**: mueven artículos entre inventario propio y de terceros sin transacción de dinero.
- **Cálculo de ganancia neta hecho en la base de datos** (columna `GENERATED ALWAYS`), no en el backend ni en el cliente, para que no se pueda falsear ni desincronizar.
- **Comisiones y retenciones por plataforma de venta**, congeladas en cada venta al momento de registrarla (cambiar la tarifa de una plataforma no altera ventas pasadas).
- Catálogos de compradores, plataformas y wishlist/faltantes; calculadora de precio objetivo; exportación de respaldo en JSON; generador de etiquetas QR y lector de código de barras (via `BarcodeDetector` del navegador); modo bazar y CRM simple de compradores.
- Autenticación con cuentas por email/contraseña y sesiones JWT; los datos de cada usuario están aislados entre sí — incluidas las fotos que suba (se sirven solo con sesión, nunca por URL directa).

## Stack tecnológico

- **Backend**: Python 3 + [Flask](https://flask.palletsprojects.com/) (`Flask>=3.0`), estructurado como *application factory* (`crear_app()`) con Blueprints por dominio (auth, artículos, movimientos, catálogos, estado).
- **Autenticación**: sesiones basadas en JWT (`PyJWT>=2.8`), hash de contraseñas con `werkzeug.security` (scrypt, incluido con Flask).
- **Base de datos**: SQLite (módulo `sqlite3` de la biblioteca estándar), con modo WAL, `foreign_keys` activado y transacciones explícitas (`BEGIN IMMEDIATE`) para operaciones multi-tabla.
- **Frontend**: HTML, CSS y JavaScript planos servidos como estáticos desde Flask (`static/index.html`, `static/app.js`, `static/styles.css`). **No usa Vue, React ni ningún framework de frontend**, no hay build step, npm ni bundler — se edita el JS y se recarga el navegador. Instalable como PWA (`manifest.json` + `sw.js`).
- **IA para alta por foto**: SDK oficial `anthropic` (visión + salida estructurada vía JSON Schema) y `Pillow` para validar/reescalar/despojar de metadatos la imagen antes de mandarla. Para cartas Pokémon, precio de mercado vía la API pública `pokemontcg.io` (sin dependencia extra, `urllib` de la biblioteca estándar).
- **Dependencias externas mínimas**: Flask, PyJWT, openpyxl, anthropic y Pillow en `requirements.txt`. Para producción se añade `gunicorn`.
- **Contenedores**: `Dockerfile` (base `python:3.12-slim`) y `docker-compose.yml` con volumen persistente para la base de datos (las fotos subidas viven ahí mismo, en `datos/fotos/`).

## Estructura del proyecto

```
app.py                      Punto de entrada (servidor de desarrollo)
requirements.txt            Flask + PyJWT + openpyxl + anthropic + Pillow
collecthub/
├── __init__.py              Application factory de Flask, CORS, límite de intentos de login,
│                             registro de blueprints y manejo de errores
├── db.py                    Conexión SQLite por petición, WAL, transacciones
├── schema.sql                Esquema completo de la base de datos
├── util.py                  Validaciones y helpers compartidos
├── auth.py                   Sesiones JWT y decorador requiere_sesion
├── vision.py                  Identificación de piezas por foto (Claude) y precio Pokémon (pokemontcg.io)
├── seed.py                   Datos de ejemplo para explorar la app
└── rutas/
    ├── auth.py                Registro, login
    ├── articulos.py            Inventario, valuaciones, identificar/subir foto
    ├── movimientos.py          Ventas, lotes, apartados, intercambios
    ├── catalogos.py            Compradores, plataformas, wishlist, ajustes
    └── estado.py                Estado completo, métricas, exportar/seed
static/                      Frontend: index.html, app.js, styles.css (sin build)
                              + manifest.json, sw.js, icon-*.png (PWA)
scripts/backup.py            Respaldo en caliente de la base SQLite
scripts/generar_iconos_pwa.py  Regenera los íconos de la PWA si cambia el diseño
tests/test_api.py            28 pruebas automatizadas de la API
datos/                       collecthub.db + fotos/<usuario_id>/ (fotos subidas)
Dockerfile, docker-compose.yml   Imagen y orquestación para despliegue
```

## Cómo instalar y ejecutar en local

Requiere **Python 3.10 o superior**.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Por defecto queda disponible en **http://localhost:3000**. Si no existe un archivo `.env`, el programa usa valores por defecto y crea la base de datos SQLite automáticamente en `datos/collecthub.db`. Para personalizar variables, copia `.env.example` a `.env` (las claves relevantes son `PORT`, `JWT_SECRET`, `JWT_DIAS`, `DB_FILE`, `CORS_ORIGIN`, `FLASK_ENV`, y opcionalmente `ANTHROPIC_API_KEY`/`IDENTIFICAR_MODELO`/`POKEMONTCG_API_KEY` para la alta por foto; no se incluyen valores reales de secretos en este repositorio).

### Ejecutar pruebas

```bash
python -m unittest discover -s tests -t . -v
```

`tests/test_api.py` contiene 28 pruebas contra una base de datos temporal, cubriendo reglas de negocio como el cálculo de ganancia neta en la base de datos, descuento/devolución de stock en ventas, bloqueo de artículos apartados, reparto proporcional en ventas por lote, congelamiento de comisiones históricas, aislamiento de datos entre cuentas (incluidas las fotos) y la identificación por foto (con Claude/pokemontcg.io mockeados, sin red real ni gasto de API).

## Notas relevantes

- **Base de datos**: SQLite es suficiente para el volumen de uso previsto (un negocio pequeño con uno o dos usuarios). El propio código deja documentado el camino de migración a PostgreSQL si algún día hace falta escritura concurrente desde varios procesos.
- **Producción**: no se debe usar `python app.py` como servidor; el proyecto está preparado para correr con `gunicorn` (`gunicorn "collecthub:crear_app()" -b 0.0.0.0:3000 -w 1 --threads 8`), con un solo worker porque SQLite no admite múltiples procesos escribiendo el mismo archivo. En producción es obligatorio definir `JWT_SECRET` (el servidor rechaza arrancar sin él con `FLASK_ENV=production`) y fijar `CORS_ORIGIN` al dominio real.
- **Despliegue**: hay `Dockerfile` y `docker-compose.yml` listos, pensados también para plataformas administradas tipo Railway/Render/Fly.io (requieren montar un volumen persistente para no perder la base de datos en cada redeploy).
- **Respaldos**: `scripts/backup.py` usa la API de respaldo nativa de SQLite (seguro con el servidor corriendo); copiar el archivo `.db` directamente mientras hay escrituras activas puede corromperlo. También hay exportación de respaldo en JSON desde la propia aplicación.
- **Dependencias externas del frontend**: Google Fonts y una librería de generación de QR se cargan desde CDN; si la red del usuario las bloquea, la app sigue funcionando mostrando la información en texto plano.
- **Alta por foto**: sin `ANTHROPIC_API_KEY` el botón "Con foto" responde con un error claro (503) — el resto de la app no se ve afectado. Las fotos subidas se guardan en `datos/fotos/<usuario_id>/` y solo se sirven con sesión iniciada del dueño (`GET /api/articulos/foto/<archivo>`); no hay URL pública para ellas. Cada llamada a identificar tiene su propio límite de peticiones (aparte del general de la API) porque cuesta dinero real por foto.
- **Repositorio**: alojado en GitHub (`JGonza10/chicos-wheels`), historial de commits corto mostrando ajustes de despliegue en Railway y correcciones de interfaz.

## Licencia

MIT
