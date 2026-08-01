# CollectHub · versión Python

Sistema de inventario, valuación y venta de coleccionables **Hot Wheels** y **cartas Pokémon**.
Backend en **Flask**, base de datos **SQLite**, frontend sin compilación.

La interfaz es exactamente la misma de la versión anterior. Lo que cambió es el servidor.

---

## Correrlo en tu computadora

Necesitas **Python 3.10 o superior**. En Mac y Linux ya viene instalado; en Windows descárgalo de [python.org](https://www.python.org/downloads/) y **marca la casilla "Add Python to PATH"** durante la instalación.

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Mac y Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Abre **http://localhost:3000**, crea tu cuenta con cualquier correo y una contraseña de al menos 8 caracteres, y presiona **Ver con datos de ejemplo** para explorar la app llena.

No hace falta configurar nada para probarlo: si no existe el archivo `.env`, el programa usa valores por defecto y crea la base de datos solo.

> **Sobre el entorno virtual (`venv`)**: aísla las librerías de este proyecto de las del resto de tu sistema. Cada vez que abras una terminal nueva para trabajar aquí, vuelve a activarlo (`.venv\Scripts\activate` o `source .venv/bin/activate`). Sabrás que está activo porque el nombre `(.venv)` aparece al inicio de la línea.

---

## Probar que todo funciona

```bash
python -m unittest discover -s tests -t . -v
```

Corren 22 pruebas contra una base de datos temporal. Verifican lo que más duele si falla:

- La ganancia neta la calcula la base de datos, no el cliente (aunque el navegador mande un número falso).
- Vender descuenta stock; cancelar una venta lo devuelve.
- Un apartado bloquea la pieza y el servidor rechaza venderla por otro lado.
- El lote reparte el precio en proporción al valor y cobra la cuota fija una sola vez.
- Cambiar la comisión de una plataforma **no** altera las ventas ya registradas.
- Una cuenta no puede leer ni borrar los datos de otra.

---

## Qué hace

**Inventario de doble perfil.** Los campos cambian según registres un coche (serie, color, tipo de tarjeta) o una carta (expansión, rareza, idioma, graduación, número de certificado), con checklist de autenticidad distinto para cada uno.

**Historial de precios.** Cada vez que consultas el mercado lo anotas y la ficha dibuja la tendencia. Ves si una pieza sube o se desinfla antes de decidir si vender o esperar.

**Apartados con anticipo.** La pieza queda bloqueada: deja de aparecer como disponible y el servidor rechaza cualquier venta que la incluya. Al vencer la fecha límite pasa a *Vencido* sola.

**Lotes.** Vendes varias piezas como paquete. El precio se reparte según el valor de mercado de cada una, para que tus estadísticas por pieza sigan siendo verdaderas.

**Intercambios.** Un cambio no mueve dinero pero sí valor. Las piezas que entregas salen del inventario, las que recibes entran con costo cero, y ves el balance real de la operación.

**Modo bazar**, **calculadora de precio inverso**, **etiquetas QR** por ubicación, **escáner de código de barras**, generador de texto de publicación, CRM de compradores, faltantes con precio tope y respaldo en JSON y CSV.

---

## Cómo está armado

```
collecthub/
├── app.py                    Punto de entrada
├── requirements.txt          Solo dos dependencias
├── collecthub/
│   ├── __init__.py           Fábrica de la app Flask
│   ├── schema.sql            Estructura de la base de datos
│   ├── db.py                 Conexión por petición, transacciones, WAL
│   ├── util.py               Validaciones y fórmulas compartidas
│   ├── auth.py               Sesiones con JWT
│   ├── seed.py               Datos de ejemplo
│   └── rutas/
│       ├── auth.py           Registro, login, sesión
│       ├── articulos.py      Inventario y valuaciones
│       ├── movimientos.py    Ventas, lotes, apartados, intercambios
│       ├── catalogos.py      Compradores, plataformas, faltantes, ajustes
│       └── estado.py         Estado completo, métricas, respaldo
├── static/                   Frontend: HTML, CSS y JS planos
├── tests/test_api.py         22 pruebas de la API
└── scripts/backup.py         Respaldo en caliente
```

**Solo dos dependencias externas:** Flask y PyJWT. El hashing de contraseñas usa `werkzeug.security` (scrypt), que ya viene con Flask, y la base de datos usa el módulo `sqlite3` de la biblioteca estándar. Menos dependencias significa menos actualizaciones de seguridad que perseguir.

**El frontend no se compila.** No hay npm, ni webpack, ni build. Editas `static/app.js`, recargas el navegador y ya.

### Tres decisiones que vale la pena entender

**1. La ganancia neta vive en la base de datos, no en el código.**

En `schema.sql`, la columna es *generada*:

```sql
ganancia_neta REAL GENERATED ALWAYS AS (
  precio - costo_unit * cantidad - com_fija
  - precio * com_pct - precio * ret_pct - envio - otros
) STORED
```

Nadie puede escribirla: ni el navegador, ni un bug del backend, ni tú por accidente desde la consola de SQLite. La fórmula está escrita una sola vez en todo el sistema. Hay una prueba que manda `ganancia_neta: 999999` desde el cliente y la base responde 210, que es lo correcto.

**2. Cada venta congela sus costos.**

La venta guarda `costo_unit`, `com_pct`, `com_fija` y `ret_pct` del día en que ocurrió. Por eso el día que Mercado Libre suba su tarifa del 13% al 16% y actualices ese canal, tu historial no se recalcula solo. Sin esto, tus ganancias pasadas cambiarían de valor cada vez que tocas una tarifa.

**3. Una conexión de base de datos por petición.**

SQLite no permite compartir una conexión entre hilos y el servidor atiende peticiones en paralelo. En `db.py` cada petición abre la suya con `flask.g` y se cierra al terminar. Las operaciones que tocan varias tablas (vender, apartar, intercambiar) van dentro de `with transaccion()`: o pasan todas, o no pasa ninguna. Eso es lo que evita que una venta descuente el stock sin quedar registrada.

### API

Todo bajo `/api`. Menos `/auth/*` y `/salud`, todo exige el encabezado `Authorization: Bearer <token>`.

| Método | Ruta | Qué hace |
| :--- | :--- | :--- |
| POST | `/auth/registro` · `/auth/login` | Crear cuenta y entrar |
| GET | `/estado` | Todo lo que el frontend necesita, en una llamada |
| GET | `/stats` | Métricas calculadas en SQL |
| GET POST PATCH DELETE | `/articulos` | Inventario |
| POST DELETE | `/articulos/:id/valuaciones` | Historial de precios |
| GET POST PATCH DELETE | `/ventas` | Ventas (cancelar devuelve stock) |
| POST | `/ventas/lote` | Venta por lote con reparto proporcional |
| GET POST | `/apartados` · `/apartados/:id/cancelar` | Apartados con anticipo |
| GET POST DELETE | `/intercambios` | Intercambios |
| GET POST PATCH DELETE | `/compradores` · `/plataformas` · `/wishlist` | Catálogos |
| GET PATCH | `/ajustes` | Moneda, meta mensual, días de estancamiento |
| POST | `/calculadora/precio-objetivo` | A cuánto publicar para ganar X |
| GET | `/exportar` | Respaldo completo en JSON |
| POST DELETE | `/seed` · `/estado` | Cargar ejemplo · borrar todo |

Ejemplo:

```bash
# Entrar
curl -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"tu@correo.com","password":"tucontrasena"}'

# Consultar el inventario
curl http://localhost:3000/api/articulos -H "Authorization: Bearer TU_TOKEN"
```

---

## Respaldos

```bash
python scripts/backup.py                  # guarda en ./respaldos/
python scripts/backup.py /ruta/que/uses   # o donde tú quieras
```

Usa la API de respaldo de SQLite, que produce un archivo consistente aunque haya escrituras en ese momento. **Copiar el archivo `.db` con `cp` mientras el servidor corre puede darte una base corrupta.**

Desde la app, *Datos → Descargar respaldo* baja un JSON con todo.

---

## Pasarlo a producción

### Antes de publicarlo, sin excepción

1. **Genera un `JWT_SECRET` largo y aleatorio.** Con `FLASK_ENV=production` el servidor se niega a arrancar sin él.
   ```bash
   python -c "import secrets;print(secrets.token_hex(48))"
   ```
2. **No uses `python app.py` en producción.** El servidor de desarrollo de Flask no está hecho para eso: es lento y no aguanta carga. Usa gunicorn:
   ```bash
   pip install gunicorn
   gunicorn "collecthub:crear_app()" -b 0.0.0.0:3000 -w 1 --threads 8
   ```
   **Un solo worker (`-w 1`).** SQLite no admite varios procesos escribiendo el mismo archivo; los hilos sí, y ocho alcanzan de sobra. Si algún día necesitas varios workers, ese es el momento de migrar a PostgreSQL.
3. **Sirve por HTTPS.** El token viaja en cada petición; sin TLS cualquiera en la misma red lo puede leer.
4. **Fija `CORS_ORIGIN`** a tu dominio exacto. En desarrollo acepta cualquier origen, cómodo para probar y peligroso en abierto.
5. **Programa los respaldos.** Un cron diario a `scripts/backup.py` y copia el resultado fuera del servidor.

### Con Docker

```bash
echo "JWT_SECRET=$(python -c 'import secrets;print(secrets.token_hex(48))')" > .env
docker compose up -d
```

Ya incluye gunicorn y un volumen persistente para la base.

### En un servidor propio

```bash
git clone <tu-repo> && cd collecthub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt gunicorn
cp .env.example .env     # edita JWT_SECRET, FLASK_ENV=production y CORS_ORIGIN
gunicorn "collecthub:crear_app()" -b 127.0.0.1:3000 -w 1 --threads 8
```

Ponlo detrás de nginx o Caddy con HTTPS y déjalo a cargo de `systemd` para que reinicie solo.

### En un servicio administrado

Funciona en Railway, Render, Fly.io o cualquier host con Docker. **Un requisito:** monta un volumen persistente en `/app/datos` y apunta ahí `DB_FILE`. Muchas plataformas tienen sistema de archivos efímero y sin volumen perderías la base en cada despliegue.

### Cuándo cambiar de SQLite a PostgreSQL

SQLite se queda corto si necesitas varios procesos o servidores escribiendo a la vez. Para un negocio de coleccionables con uno o dos usuarios, eso tarda mucho en llegar. Si pasa: el esquema es SQL casi estándar (las excepciones son la columna generada y `datetime('now')`), y las consultas están concentradas en `db.py` y las rutas, así que la migración es acotada, no una reescritura.

---

## Preguntas frecuentes

**"python no se reconoce como comando" en Windows.** No se marcó "Add Python to PATH" al instalar. Reinstala Python marcando esa casilla, o prueba con `py` en lugar de `python`.

**"externally-managed-environment" al hacer pip install.** Estás instalando fuera de un entorno virtual en un Linux reciente. Crea el `venv` como indica arriba y actívalo antes del `pip install`.

**El puerto 3000 está ocupado.** Arráncalo en otro: en Windows `set PORT=3001 && python app.py`, en Mac o Linux `PORT=3001 python3 app.py`.

**Olvidé mi contraseña.** No hay recuperación por correo todavía. Crea una cuenta nueva y restaura tu respaldo, o borra el usuario con `sqlite3 datos/collecthub.db`.

**¿Sirve en el celular?** Sí, la interfaz se adapta. En el bazar conviene abrirla desde el navegador del teléfono.

**El escáner no abre la cámara.** Usa `BarcodeDetector`, que Chrome y Android soportan pero Safari todavía no. Siempre puedes escribir el código a mano. Además el navegador solo da acceso a la cámara por HTTPS o en localhost.

**Los QR salen como recuadros con texto.** La librería de códigos QR se carga desde una CDN. Si tu red la bloquea, la etiqueta se imprime igual con el nombre de la ubicación en texto.

**El "Balance del mes" aparece en cero con los datos de ejemplo.** Es correcto: las ventas de ejemplo tienen fechas del mes pasado, y ese indicador solo suma el mes en curso. Registra una venta con la fecha de hoy y lo verás moverse.

**Las comisiones precargadas.** 13% de Mercado Libre y 13.25% de eBay son aproximadas y cambian por categoría, precio y país. Ajústalas en *Plataformas* con tu tarifa real antes de confiar en los márgenes. La retención fiscal depende de tu régimen: conviene confirmarla con un contador.

---

MIT
