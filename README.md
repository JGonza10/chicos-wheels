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

Este es el **paso 1** (login/roles) + **paso 2** (CRUD de catálogo) del patrón de Sistema GONZA.
Falta: carrito/pedidos con checkout, integración de pasarela de pago, frontend en React,
alertas por email (Resend) y dashboard de ventas.
