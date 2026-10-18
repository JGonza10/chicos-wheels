# Bot Hot Wheels (dentro de Chicos Wheels)

Monitor + bot de compra de Mattel Creations. Antes era el proyecto `15 Bot Hot Wheels`. Desde 2026-10-17 corre dentro de la app del 02: un solo proceso y un solo puerto.

1. **El monitor busca** (`monitor.py`, hilo de fondo): piezas nuevas, restock y pocas unidades.
2. **Avisa y registra**: por Telegram (foto + botones) y en la tabla `hallazgos` de `bot.db`.
   - Lo urgente (deseados, vigilados a mano o "Alto impacto" ya calculado) sale primero como **aviso express**: solo texto, con carrito y Comprar/Ignorar, antes de consultar eBay y Mercado Libre. La tarjeta con foto y ganancia llega después.
   - El francotirador revisa primero deseados y vigilados a mano, luego "coming soon" y al final el resto.
   - **Modo drop**: de `MINUTOS_ANTES_DROP` antes a `MINUTOS_DESPUES_DROP` después del drop (día y hora aprendidos; sin datos, martes 11 am CDMX), el ciclo rápido va cada `SEGUNDOS_CICLO_DROP` s.
   - Una sola sesión HTTP (keep-alive). El ciclo rápido rompe la caché de Shopify. Ante un 429, pausa todo lo que pida `Retry-After` (60 s si no dice).
3. **Gonza decide** en el panel (`/bot/`, menú "🤖 Bot Hot Wheels" de Chicos Wheels) o en Telegram. **Nada se compra solo.**
4. Lo comprado se da de alta en el inventario de Chicos Wheels con la cuenta `COLLECTHUB_EMAIL`.
   - Desde 2026-10-18 el destino es Railway (`COLLECTHUB_URL=https://erikg.up.railway.app`, cuenta juangonza@live.com.mx), porque ahí vive el inventario real. Hace login con `COLLECTHUB_PASSWORD`.
   - Si falla, la compra queda en cola (`registros_collecthub`) y se reintenta cada 10 min.
   - Con URL vacía o local, la llamada se atiende en el mismo proceso, sin contraseña.
   - Railway también alimenta "Ya tienes esta", los apartados por vencer y el PDF semanal.

## Arranque

- `python app.py` desde la raíz del 02, con `HOTWHEELS_ACTIVO=1` en `.env`.
  - Monta `dashboard_bot.app` en `/bot` y arranca el monitor, el scheduler, la cola de compras y Telegram (`collecthub/bot.py`).
  - Si otra copia de la app ya los corre (candado `monitor.lock`), esta copia solo sirve el panel.
- La tarea programada `HotWheels_MonitorSiempre` corre `vigilar_siempre.ps1`. Si nada escucha en el puerto 3000, o si `latido.txt` lleva más de 10 minutos sin cambiar, relanza la app.
- En Railway el bot de compra no existe: sin `HOTWHEELS_ACTIVO`, `/bot` no se monta y el enlace no aparece.

## Monitor de relevo en Railway

Para que siempre haya alguien vigilando aunque la PC esté apagada.

1. En Railway corre **solo el monitor** (`HOTWHEELS_MONITOR_NUBE=1`), dentro del mismo proceso de gunicorn.
2. La PC, tras cada barrido completo, manda un latido a `POST /api/bot/latido-pc` con la cuenta `COLLECTHUB_EMAIL`. Lleva `monitor_ok`, que dice si ese barrido sí vio la tienda. Solo pasa si `COLLECTHUB_URL` apunta a Railway.
3. Mientras lleguen latidos con `monitor_ok`, Railway vigila pero no manda nada: no hay avisos dobles.
4. Si pasan 5 min sin un latido sano, Railway avisa "RAILWAY TOMA EL RELEVO" y desde ahí manda los avisos con carrito y "Ver producto". Cuando la PC vuelve, avisa y se calla.
5. **Comprar a distancia:** si la app de la PC sigue viva pero su monitor está ciego, los avisos de Railway traen "🛒 Comprar con el bot (PC)" (`rc:<id>`). Al tocarlo, la PC pide la pieza a `GET /api/bot/pieza-relevo/<id>`, la da de alta en su panel y sigue el flujo de siempre: confirmar, revisar el tope de gasto y comprar. Solo acepta URLs de `creations.mattel.com/products/`. Si la PC está apagada, ese botón no sale.
6. **Listas sincronizadas:** el latido lleva deseados, bloqueados, colecciones y vigilados de la PC cuando cambian (por hash). Railway los valida (listas de objetos planos, con topes de tamaño) y los guarda; si algo no es válido, no toca nada. Las listas que no existen en la PC no viajan.
7. **Pastilla en el panel** `/bot/`: "Relevo Railway listo / ciego / sin respuesta / apagado / avisando por la PC".
8. Si Railway lleva más de 30 min sin poder leer Mattel (por ejemplo, un bloqueo a su IP), la PC te avisa una vez cada 6 h.

Variables en Railway:

| Variable | Valor |
|---|---|
| `HOTWHEELS_MONITOR_NUBE` | `1` |
| `HOTWHEELS_DATOS` | `/app/datos/hotwheels` (dentro del volumen ya montado en `/app/datos`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | los mismos de `config.env` |
| `TELEGRAM_CANAL_ID`, `MERCADOLIBRE_ACCESS_TOKEN` | opcionales |
| `BOT_EMAILS` | la cuenta de `COLLECTHUB_EMAIL` de la PC |

Las piezas que encuentra Railway viven en memoria: si Railway se reinicia, un botón "Comprar con el bot (PC)" viejo responde "No pude traer esa pieza de Railway".

## Acceso

Solo las cuentas de `BOT_EMAILS` (por defecto `juangonza@live.com.mx`):

1. El SPA hace `POST /api/bot/entrar` y recibe una cookie `bot_sesion` (HttpOnly, SameSite=Strict, `Path=/bot`, 12 h).
2. Sin esa cookie el panel responde 401. Si se abre `/bot/` directo, redirige a `/#bot`, que renueva la cookie y regresa al panel.

## Pruebas

```powershell
python prueba_extras.py; python prueba_admin.py; python prueba_integraciones.py
python prueba_hallazgos.py; python prueba_evento_reintentos.py; python prueba_habilidades.py
python prueba_velocidad.py      # express, francotirador, modo drop, 429, Telegram, relevo
python prueba_rapidez_compra.py # compra sin esperas fijas y cronómetro (Chromium real, páginas locales)
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
- El resultado de cada compra (y de cada DRY RUN) trae el cronómetro por paso: `⏱ 21.4 s (navegador 1.2 · producto 4.0 · ...)`. Los pop-ups que pueden no salir se revisan sin esperas fijas.
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
