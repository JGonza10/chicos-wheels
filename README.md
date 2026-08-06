# Chicos Wheels (CollectHub)

Sistema de inventario, valuación y venta de coleccionables **Hot Wheels** y **cartas Pokémon**, con backend en Flask y frontend web sin build.

## Estado actual

Proyecto activo y funcional, de alcance personal/pequeño negocio (pensado para uno o dos usuarios por instancia). Tiene suite de pruebas automatizadas (22 casos), Dockerfile y `docker-compose.yml` listos para desplegar, y un historial de commits reciente con correcciones puntuales. No hay indicios de CI/CD configurado ni de recuperación de contraseña por correo.

## Características principales

- **Inventario de doble perfil**: los campos del artículo cambian según sea un Hot Wheels (serie, color) o una carta Pokémon (expansión, rareza, grado, número de certificado).
- **Historial de valuaciones** por artículo, para ver tendencia de precio en el tiempo.
- **Apartados con anticipo**: bloquean el artículo (no se puede vender por otro lado) y vencen solos según fecha límite.
- **Ventas por lote**: reparte el precio entre varias piezas según su valor de mercado y cobra una sola vez la cuota fija.
- **Intercambios**: mueven artículos entre inventario propio y de terceros sin transacción de dinero.
- **Cálculo de ganancia neta hecho en la base de datos** (columna `GENERATED ALWAYS`), no en el backend ni en el cliente, para que no se pueda falsear ni desincronizar.
- **Comisiones y retenciones por plataforma de venta**, congeladas en cada venta al momento de registrarla (cambiar la tarifa de una plataforma no altera ventas pasadas).
- Catálogos de compradores, plataformas y wishlist/faltantes; calculadora de precio objetivo; exportación de respaldo en JSON; generador de etiquetas QR y lector de código de barras (via `BarcodeDetector` del navegador); modo bazar y CRM simple de compradores.
- Autenticación con cuentas por email/contraseña y sesiones JWT; los datos de cada usuario están aislados entre sí.

## Stack tecnológico

- **Backend**: Python 3 + [Flask](https://flask.palletsprojects.com/) (`Flask>=3.0`), estructurado como *application factory* (`crear_app()`) con Blueprints por dominio (auth, artículos, movimientos, catálogos, estado).
- **Autenticación**: sesiones basadas en JWT (`PyJWT>=2.8`), hash de contraseñas con `werkzeug.security` (scrypt, incluido con Flask).
- **Base de datos**: SQLite (módulo `sqlite3` de la biblioteca estándar), con modo WAL, `foreign_keys` activado y transacciones explícitas (`BEGIN IMMEDIATE`) para operaciones multi-tabla.
- **Frontend**: HTML, CSS y JavaScript planos servidos como estáticos desde Flask (`static/index.html`, `static/app.js`, `static/styles.css`). **No usa Vue, React ni ningún framework de frontend**, no hay build step, npm ni bundler — se edita el JS y se recarga el navegador.
- **Dependencias externas mínimas**: solo Flask y PyJWT en `requirements.txt`. Para producción se añade `gunicorn`.
- **Contenedores**: `Dockerfile` (base `python:3.12-slim`) y `docker-compose.yml` con volumen persistente para la base de datos.

## Estructura del proyecto

```
app.py                      Punto de entrada (servidor de desarrollo)
requirements.txt            Flask + PyJWT
collecthub/
├── __init__.py              Application factory de Flask, CORS, límite de intentos de login,
│                             registro de blueprints y manejo de errores
├── db.py                    Conexión SQLite por petición, WAL, transacciones
├── schema.sql                Esquema completo de la base de datos
├── util.py                  Validaciones y helpers compartidos
├── auth.py                   Sesiones JWT y decorador requiere_sesion
├── seed.py                   Datos de ejemplo para explorar la app
└── rutas/
    ├── auth.py                Registro, login
    ├── articulos.py            Inventario y valuaciones
    ├── movimientos.py          Ventas, lotes, apartados, intercambios
    ├── catalogos.py            Compradores, plataformas, wishlist, ajustes
    └── estado.py                Estado completo, métricas, exportar/seed
static/                      Frontend: index.html, app.js, styles.css (sin build)
scripts/backup.py            Respaldo en caliente de la base SQLite
tests/test_api.py            22 pruebas automatizadas de la API
datos/                       Ubicación por defecto del archivo collecthub.db
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

Por defecto queda disponible en **http://localhost:3000**. Si no existe un archivo `.env`, el programa usa valores por defecto y crea la base de datos SQLite automáticamente en `datos/collecthub.db`. Para personalizar variables, copia `.env.example` a `.env` (las claves relevantes son `PORT`, `JWT_SECRET`, `JWT_DIAS`, `DB_FILE`, `CORS_ORIGIN` y `FLASK_ENV`; no se incluyen valores reales de secretos en este repositorio).

### Ejecutar pruebas

```bash
python -m unittest discover -s tests -t . -v
```

`tests/test_api.py` contiene 22 pruebas contra una base de datos temporal, cubriendo reglas de negocio como el cálculo de ganancia neta en la base de datos, descuento/devolución de stock en ventas, bloqueo de artículos apartados, reparto proporcional en ventas por lote, congelamiento de comisiones históricas y aislamiento de datos entre cuentas.

## Notas relevantes

- **Base de datos**: SQLite es suficiente para el volumen de uso previsto (un negocio pequeño con uno o dos usuarios). El propio código deja documentado el camino de migración a PostgreSQL si algún día hace falta escritura concurrente desde varios procesos.
- **Producción**: no se debe usar `python app.py` como servidor; el proyecto está preparado para correr con `gunicorn` (`gunicorn "collecthub:crear_app()" -b 0.0.0.0:3000 -w 1 --threads 8`), con un solo worker porque SQLite no admite múltiples procesos escribiendo el mismo archivo. En producción es obligatorio definir `JWT_SECRET` (el servidor rechaza arrancar sin él con `FLASK_ENV=production`) y fijar `CORS_ORIGIN` al dominio real.
- **Despliegue**: hay `Dockerfile` y `docker-compose.yml` listos, pensados también para plataformas administradas tipo Railway/Render/Fly.io (requieren montar un volumen persistente para no perder la base de datos en cada redeploy).
- **Respaldos**: `scripts/backup.py` usa la API de respaldo nativa de SQLite (seguro con el servidor corriendo); copiar el archivo `.db` directamente mientras hay escrituras activas puede corromperlo. También hay exportación de respaldo en JSON desde la propia aplicación.
- **Dependencias externas del frontend**: Google Fonts y una librería de generación de QR se cargan desde CDN; si la red del usuario las bloquea, la app sigue funcionando mostrando la información en texto plano.
- **Repositorio**: alojado en GitHub (`JGonza10/chicos-wheels`), historial de commits corto mostrando ajustes de despliegue en Railway y correcciones de interfaz.

## Licencia

MIT
