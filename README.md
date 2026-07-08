# Chicos Wheels

Tienda en línea de carros de colección (Hot Wheels) y tarjetas Pokémon TCG.
Stack: Flask + SQLAlchemy + PostgreSQL (backend) · React (frontend) · Railway (hosting).

## Estructura

```
chicos-wheels/
├── backend/
│   ├── app.py            # Application factory
│   ├── models.py         # Usuarios (roles), categorías, productos, pedidos, ofertas, reseñas
│   ├── auth.py            # Login, registro, decorador @requiere_rol
│   ├── routes/
│   │   └── catalogo.py    # CRUD de categorías y productos
│   ├── requirements.txt
│   ├── Procfile
│   └── .env.example
├── frontend/               # (siguiente paso)
└── docs/
    ├── ERD.md
    └── migracion.sql
```

## Roles

- **administrador** — control total del sistema.
- **vendedor** — carga y edita productos, gestiona pedidos.
- **cliente** — navega, compra, deja reseñas.

## Arrancar en local

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # PowerShell en Windows
pip install -r requirements.txt
copy .env.example .env       # y edita DATABASE_URL con tu Postgres local o de Railway
python app.py
```

El servidor queda en `http://localhost:5000`. Prueba con `GET /api/health`.

## Siguiente paso

Ya están: login/roles, CRUD de catálogo, cobro por código de barras/QR/voz,
carrito + checkout con Mercado Pago, chatbot (FAQ + IA de respaldo con
Claude) y redes sociales (login social, publicación automática de ofertas).

Falta: **frontend en React** con el diseño del boceto (home, panel de
cobro con escáner/voz, chat flotante, botones para compartir), alertas
por email (Resend) y dashboard de ventas.

### Redes sociales y chatbot — qué necesitas configurar

- **Chatbot**: crea una API key en console.anthropic.com y ponla en
  `ANTHROPIC_API_KEY`. Sin ella, el chatbot sigue funcionando solo con
  las preguntas frecuentes fijas.
- **Login con Google**: crea credenciales OAuth en console.cloud.google.com.
- **Login con Facebook** y **publicación automática en Facebook/Instagram**:
  se hacen desde la misma app en developers.facebook.com. Instagram debe
  ser una cuenta de negocio vinculada a tu página de Facebook.
- Si no configuras estas variables, esas funciones simplemente se
  desactivan solas (no rompen el resto del sistema).
