# CLAUDE.md

## Qué es

**Erik G** (carpeta y código internos aún se llaman Chicos Wheels / `collecthub`): inventario y control de entregas de Hot Wheels, Pokémon y categorías propias (Barbie…). Flujo del negocio: compra (casi todo Mattel Creations, vía el Bot Hot Wheels de `hotwheels/`) → publica en Facebook → apartado/pedido → entrega el **sábado en Balderas** → contabilidad. Toda función nueva debe servir a ese ciclo.

Incluye una tienda pública para clientes en `/tienda/` (solo muestra stock, apartar sin anticipo y asistente). Desplegada en Railway.

**Bot Hot Wheels** (antes proyecto 15): monitor + bot de compra de Mattel Creations, en el mismo proceso, panel en `/bot/` (menú "🤖 Bot Hot Wheels", solo cuentas de `BOT_EMAILS`). Solo en esta PC con `HOTWHEELS_ACTIVO=1`; en Railway no existe. Detalle y reglas de compra: `hotwheels/README.md`. **El monitor debe quedar vigilando siempre** (tarea `HotWheels_MonitorSiempre` → `hotwheels/vigilar_siempre.ps1`).

## Comandos

```bash
python app.py                                    # http://localhost:3000
python -m unittest discover -s tests -t . -v     # pruebas con BD temporal
```

Variables en `.env` (ver `.env.example`). En producción `JWT_SECRET` es obligatoria. Producción: Docker o gunicorn con **un solo worker** (SQLite).

## Estructura

- `collecthub/__init__.py` — fábrica de la app, rate limit, cabeceras de seguridad (CSP).
- `collecthub/rutas/` — un blueprint por dominio: `auth`, `articulos`, `movimientos` (ventas, encargos/pedidos, cobranza), `catalogos`, `estado`, `tienda` (pública).
- `collecthub/schema.sql` + `db.py` — SQLite (WAL); migraciones automáticas al arrancar.
- Frontend sin build: `static/app.js`, `static/styles.css`. Tienda: `landing page/` (`CW.js`, `asistente.js`).
- Reportes: `reporte.py`, `catalogo.py`, `hoja_entrega.py`, `hoja_excel.py`. Respaldos: `respaldo.py` (diario), `respaldo_cuenta.py` (zip por cuenta).
- `collecthub/bot.py` — monta `hotwheels/dashboard_bot.py` en `/bot`, cookie de acceso y arranque del monitor. `hotwheels/` — código del bot; sus datos y secretos no van a git.

## Reglas

- Las vistas nuevas de `articulos/movimientos/catalogos/estado` quedan protegidas solas por el bucle de `crear_app()`: no agregar `requiere_sesion` a mano ni cambiar el prefijo de endpoint.
- Dinero y ganancia que no deban poder falsearse se calculan en SQL (`GENERATED ALWAYS`); el saldo (`debe`) lo calcula el servidor.
- La tienda publica solo los campos de la lista blanca `CAMPOS` en `landing.py`: nunca costo, ganancia, ubicación ni id interno.
- **Contacto con clientes solo por Facebook (Messenger) e Instagram, nunca WhatsApp** (a menos que solo exista un teléfono).
- Al cambiar `app.js`/`styles.css`, subir `CACHE_VERSION` en `static/sw.js`. El service worker solo maneja el mismo origen y no cachea `/tienda`.
- Los `MOD.x = ...` de `app.js` van después de `const MOD = {}`.
- Categorías: "lo que no es Pokémon usa serie/color"; nunca comparar `=== 'Hot Wheels'`.
- No quitar `'unsafe-inline'` de `style-src` ni `blob:` de `img-src` en el CSP.
- Si el puerto 3000 ya está ocupado (lo mantiene el supervisor del bot; Nexus `P2`), no matar ese proceso: probar con otro `PORT`. Comparten la misma base: borrar los datos de prueba. Una segunda copia no arranca otro monitor (candado `monitor.lock`).
- **Sin `HOTWHEELS_DRY_RUN=1`, "Comprar" del bot paga de verdad.**
