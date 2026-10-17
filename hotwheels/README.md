# Bot Hot Wheels (dentro de Chicos Wheels)

Monitor + bot de compra de Mattel Creations. Antes era el proyecto `15 Bot Hot Wheels`. Desde 2026-10-17 corre dentro de la app del 02: un solo proceso y un solo puerto.

1. **El monitor busca** (`monitor.py`, hilo de fondo): piezas nuevas, restock y pocas unidades.
2. **Avisa y registra**: por Telegram (foto + botones) y en la tabla `hallazgos` de `bot.db`.
3. **Gonza decide** en el panel (`/bot/`, menú "🤖 Bot Hot Wheels" de Chicos Wheels) o en Telegram. **Nada se compra solo.**
4. Lo comprado se da de alta en el inventario de Chicos Wheels (cuenta `COLLECTHUB_EMAIL`). La llamada se atiende dentro del mismo proceso.

## Arranque

- `python app.py` desde la raíz del 02, con `HOTWHEELS_ACTIVO=1` en `.env`.
  - Monta `dashboard_bot.app` en `/bot` y arranca el monitor, el scheduler, la cola de compras y Telegram (`collecthub/bot.py`).
  - Si otra copia de la app ya los corre (candado `monitor.lock`), esta copia solo sirve el panel.
- La tarea programada `HotWheels_MonitorSiempre` corre `vigilar_siempre.ps1`. Si nada escucha en el puerto 3000, o si `latido.txt` lleva más de 10 minutos sin cambiar, relanza la app.
- En Railway no existe: sin la variable, `/bot` no se monta y el enlace no aparece.

## Acceso

Solo las cuentas de `BOT_EMAILS` (por defecto `juangonza@live.com.mx`):

1. El SPA hace `POST /api/bot/entrar` y recibe una cookie `bot_sesion` (HttpOnly, SameSite=Strict, `Path=/bot`, 12 h).
2. Sin esa cookie el panel responde 401. Si se abre `/bot/` directo, redirige a `/#bot`, que renueva la cookie y regresa al panel.

## Pruebas

```powershell
python prueba_extras.py; python prueba_admin.py; python prueba_integraciones.py
python prueba_hallazgos.py; python prueba_evento_reintentos.py; python prueba_habilidades.py
cd ..; python -m unittest tests.test_bot -v      # montaje, acceso y alta en el inventario
```

Cada prueba corre en una copia temporal: no toca `bot.db`, `estado.json` ni Telegram.

## Datos (solo en esta PC, fuera de git)

- `.env`: tarjeta, envío, SMTP y `COLLECTHUB_EMAIL`.
- `config.env`: Telegram del monitor y ajustes.
- `config.json`: canales de aviso.
- `bot.db`, `historial.db`, `estado.json`, listas `*.json`, `latido.txt` y `capturas_error/`.

## Reglas

- **Sin `HOTWHEELS_DRY_RUN=1`, "Comprar" paga de verdad.**
- Toda compra pasa por `solicitar_compra()`, con un solo navegador a la vez (`_LOCK_DISPARO`). `run_one(url)` sirve para una pieza; nunca `run_all()`.
- `comprar_producto` corre con `headless=False` porque los captchas se resuelven a mano.
- Una pieza comprada nunca se reabre sola.
- Los botones de Telegram van solo al chat personal (`TELEGRAM_CHAT_ID`).
- Checkout de Mattel:
  - Los campos se buscan por `name`.
  - La tarjeta va en iframes de `checkout.pci.shopifyinc.com`.
  - El botón es `#checkout-pay-button`.
  - Nunca usar los `id` aleatorios.
- Fechas en UTC.
- Rutas de datos ancladas a esta carpeta; nunca al directorio de arranque.
- La plantilla usa `request.script_root` (`BASE` en JS): nada de rutas absolutas.
