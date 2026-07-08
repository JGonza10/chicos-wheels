-- Chicos Wheels — script de creación de base de datos (PostgreSQL / Railway)

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'cliente',
    telefono VARCHAR(20),
    activo BOOLEAN DEFAULT TRUE,
    fecha_registro TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categorias (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    slug VARCHAR(80) UNIQUE NOT NULL,
    icono VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS productos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    precio NUMERIC(10, 2) NOT NULL,
    precio_anterior NUMERIC(10, 2),
    stock INTEGER NOT NULL DEFAULT 0,
    edicion_limitada BOOLEAN DEFAULT FALSE,
    destacado BOOLEAN DEFAULT FALSE,
    imagen_url VARCHAR(255),
    codigo_barras VARCHAR(50) UNIQUE,
    clave_producto VARCHAR(30) UNIQUE,
    activo BOOLEAN DEFAULT TRUE,
    creado_por INTEGER REFERENCES usuarios(id),
    fecha_creacion TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ofertas (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    descripcion VARCHAR(255),
    producto_id INTEGER REFERENCES productos(id),
    fecha_inicio TIMESTAMP DEFAULT NOW(),
    fecha_fin TIMESTAMP NOT NULL,
    activa BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS pedidos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    fecha TIMESTAMP DEFAULT NOW(),
    estado VARCHAR(20) DEFAULT 'pendiente',
    metodo_pago VARCHAR(30),
    referencia_pago VARCHAR(120),
    total NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS detalle_pedidos (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL DEFAULT 1,
    precio_unitario NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS resenas (
    id SERIAL PRIMARY KEY,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    calificacion INTEGER NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    comentario TEXT,
    fecha TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carrito_items (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL DEFAULT 1,
    fecha_agregado TIMESTAMP DEFAULT NOW()
);

-- Categorías iniciales
INSERT INTO categorias (nombre, slug, icono) VALUES
    ('Hot Wheels', 'hot-wheels', 'ti-car'),
    ('Pokémon TCG', 'pokemon-tcg', 'ti-cards'),
    ('Accesorios y coleccionables', 'accesorios', 'ti-package')
ON CONFLICT (slug) DO NOTHING;
