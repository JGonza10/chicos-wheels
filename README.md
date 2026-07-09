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

Ya está completo: login/roles, CRUD de catálogo, cobro por código de
barras/QR/voz, carrito + checkout con Mercado Pago, chatbot (FAQ + IA),
redes sociales (login social + publicación automática de ofertas),
frontend en React con el diseño del boceto, y dashboard de ventas.

Falta: subir todo a GitHub y desplegar en Railway (guía abajo) y, más
adelante, alertas por email (Resend) como en Sistema GONZA.

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

## Subir a GitHub

```powershell
cd chicos-wheels
git init
git add .
git commit -m "Chicos Wheels: backend, frontend, dashboard y redes sociales"
git branch -M main
git remote add origin https://github.com/JGonza10/chicos-wheels.git
git push -u origin main
```

(Antes crea el repo vacío en github.com/new con el nombre `chicos-wheels`, sin README.)

## Desplegar en Railway (dos servicios, igual que Sistema GONZA)

1. **Base de datos**: en tu proyecto de Railway, `+ New` → `Database` → `PostgreSQL`.
   Luego abre la pestaña `Query` y pega el contenido de `docs/migracion.sql` para crear las tablas.

2. **Backend (Flask)**: `+ New` → `GitHub Repo` → selecciona `chicos-wheels`.
   En `Settings` → `Root Directory` pon `backend`. Railway detecta el `Procfile` solo.
   En `Variables` agrega (copian los valores de `backend/.env.example`):
   - `DATABASE_URL` → click derecho en el servicio de Postgres → `Copy DATABASE_URL`, pégalo aquí.
   - `SECRET_KEY`, `MP_ACCESS_TOKEN`, `ANTHROPIC_API_KEY` (opcional), credenciales sociales (opcional).
   - `FRONTEND_URL` → lo llenas después de crear el frontend (paso 3).

3. **Frontend (React)**: `+ New` → `GitHub Repo` → mismo repo `chicos-wheels`.
   En `Settings` → `Root Directory` pon `frontend`.
   En `Settings` → `Build`: build command `npm run build`, start command `npm run preview -- --host 0.0.0.0 --port $PORT`.
   En `Variables` agrega `VITE_API_URL` con la URL pública que Railway le dio al backend (paso 2).

4. Regresa al servicio de **backend** y actualiza `FRONTEND_URL` con la URL pública que Railway le dio al frontend, para que las cookies de sesión y los `back_urls` de Mercado Pago apunten al lugar correcto.

5. En Railway, cada servicio tiene un botón `Generate Domain` en `Settings` → `Networking` para obtener su URL pública (`https://algo.up.railway.app`).
