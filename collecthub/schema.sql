-- ============================================================
--  CollectHub · esquema de base de datos (SQLite)
--  Las reglas de negocio críticas viven aquí, no en el código:
--  la ganancia neta es una columna generada, así que es
--  imposible que un bug del backend la calcule distinto.
-- ============================================================
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
  id            TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  nombre        TEXT NOT NULL DEFAULT '',
  creado_en     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ajustes (
  usuario_id      TEXT PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
  moneda          TEXT    NOT NULL DEFAULT 'MXN',
  meta_mensual    REAL    NOT NULL DEFAULT 5000,
  dias_estancado  INTEGER NOT NULL DEFAULT 120
);

CREATE TABLE IF NOT EXISTS plataformas (
  id         TEXT PRIMARY KEY,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  codigo     TEXT NOT NULL,
  nombre     TEXT NOT NULL,
  com_pct    REAL NOT NULL DEFAULT 0 CHECK (com_pct >= 0 AND com_pct < 1),
  com_fija   REAL NOT NULL DEFAULT 0 CHECK (com_fija >= 0),
  ret_pct    REAL NOT NULL DEFAULT 0 CHECK (ret_pct >= 0 AND ret_pct < 1),
  notas      TEXT NOT NULL DEFAULT '',
  UNIQUE (usuario_id, codigo)
);

CREATE TABLE IF NOT EXISTS compradores (
  id         TEXT PRIMARY KEY,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  nombre     TEXT NOT NULL,
  tel        TEXT NOT NULL DEFAULT '',
  interes    TEXT NOT NULL DEFAULT 'Ambas' CHECK (interes IN ('Hot Wheels','Pokémon','Ambas')),
  notas      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_comp_usuario ON compradores(usuario_id);

CREATE TABLE IF NOT EXISTS articulos (
  id             TEXT PRIMARY KEY,
  usuario_id     TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  tipo           TEXT NOT NULL CHECK (tipo IN ('Hot Wheels','Pokémon')),
  nombre         TEXT NOT NULL,
  numero         TEXT NOT NULL DEFAULT '',
  anio           INTEGER,
  -- perfil Hot Wheels
  serie          TEXT NOT NULL DEFAULT '',
  color          TEXT NOT NULL DEFAULT '',
  -- perfil Pokémon
  expansion      TEXT NOT NULL DEFAULT '',
  rareza         TEXT NOT NULL DEFAULT '',
  grado          TEXT NOT NULL DEFAULT '',
  cert           TEXT NOT NULL DEFAULT '',
  -- comunes a ambos perfiles
  sub            TEXT NOT NULL DEFAULT '',
  estado         TEXT NOT NULL DEFAULT '',
  cantidad       INTEGER NOT NULL DEFAULT 1 CHECK (cantidad >= 0),
  cant_inicial   INTEGER NOT NULL DEFAULT 1,
  estatus        TEXT NOT NULL DEFAULT 'Disponible'
                 CHECK (estatus IN ('Disponible','En negociación','Conservar')),
  precio_compra  REAL NOT NULL DEFAULT 0 CHECK (precio_compra >= 0),
  valor_estimado REAL NOT NULL DEFAULT 0 CHECK (valor_estimado >= 0),
  fecha_adq      TEXT NOT NULL DEFAULT '',
  fuente         TEXT NOT NULL DEFAULT '',
  ubicacion      TEXT NOT NULL DEFAULT '',
  codigo         TEXT NOT NULL DEFAULT '',
  foto           TEXT NOT NULL DEFAULT '',
  notas          TEXT NOT NULL DEFAULT '',
  grail          INTEGER NOT NULL DEFAULT 0,
  checks         TEXT NOT NULL DEFAULT '[]',
  creado_en      TEXT NOT NULL DEFAULT (datetime('now')),
  actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_art_usuario ON articulos(usuario_id);
CREATE INDEX IF NOT EXISTS ix_art_codigo  ON articulos(usuario_id, codigo);
CREATE INDEX IF NOT EXISTS ix_art_ubic    ON articulos(usuario_id, ubicacion);

-- Historial de precios: un renglón cada vez que consultas el mercado
CREATE TABLE IF NOT EXISTS valuaciones (
  id          TEXT PRIMARY KEY,
  articulo_id TEXT NOT NULL REFERENCES articulos(id) ON DELETE CASCADE,
  fecha       TEXT NOT NULL,
  valor       REAL NOT NULL CHECK (valor >= 0),
  fuente      TEXT NOT NULL DEFAULT '',
  creado_en   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_val_art ON valuaciones(articulo_id, fecha);

CREATE TABLE IF NOT EXISTS lotes (
  id         TEXT PRIMARY KEY,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  fecha      TEXT NOT NULL,
  precio     REAL NOT NULL DEFAULT 0,
  piezas     INTEGER NOT NULL DEFAULT 0
);

-- Las ventas CONGELAN costo, comisiones y retención del día en que ocurrieron.
-- Por eso puedes cambiar la tarifa de una plataforma sin corromper el historial.
CREATE TABLE IF NOT EXISTS ventas (
  id                TEXT PRIMARY KEY,
  usuario_id        TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  articulo_id       TEXT REFERENCES articulos(id) ON DELETE SET NULL,
  comprador_id      TEXT REFERENCES compradores(id) ON DELETE SET NULL,
  plataforma_id     TEXT REFERENCES plataformas(id) ON DELETE SET NULL,
  lote_id           TEXT REFERENCES lotes(id) ON DELETE SET NULL,
  nombre_snap       TEXT NOT NULL,
  tipo_snap         TEXT NOT NULL DEFAULT '',
  plataforma_snap   TEXT NOT NULL DEFAULT '',
  cantidad          INTEGER NOT NULL DEFAULT 1 CHECK (cantidad > 0),
  precio            REAL NOT NULL CHECK (precio >= 0),
  envio             REAL NOT NULL DEFAULT 0 CHECK (envio >= 0),
  otros             REAL NOT NULL DEFAULT 0 CHECK (otros >= 0),
  costo_unit        REAL NOT NULL DEFAULT 0,
  com_pct           REAL NOT NULL DEFAULT 0,
  com_fija          REAL NOT NULL DEFAULT 0,
  ret_pct           REAL NOT NULL DEFAULT 0,
  anticipo_aplicado REAL NOT NULL DEFAULT 0,
  fecha             TEXT NOT NULL,
  fecha_adq_snap    TEXT NOT NULL DEFAULT '',
  guia              TEXT NOT NULL DEFAULT '',
  estatus_envio     TEXT NOT NULL DEFAULT 'Sin envío'
                    CHECK (estatus_envio IN ('Sin envío','Pendiente','Enviado','Entregado')),
  creado_en         TEXT NOT NULL DEFAULT (datetime('now')),
  -- La regla de negocio más importante del sistema, escrita una sola vez:
  ganancia_neta     REAL GENERATED ALWAYS AS (
                      precio
                      - costo_unit * cantidad
                      - com_fija
                      - precio * com_pct
                      - precio * ret_pct
                      - envio
                      - otros
                    ) STORED
);
CREATE INDEX IF NOT EXISTS ix_ven_usuario ON ventas(usuario_id, fecha);
CREATE INDEX IF NOT EXISTS ix_ven_art     ON ventas(articulo_id);

CREATE TABLE IF NOT EXISTS apartados (
  id              TEXT PRIMARY KEY,
  usuario_id      TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  articulo_id     TEXT NOT NULL REFERENCES articulos(id) ON DELETE CASCADE,
  comprador_id    TEXT REFERENCES compradores(id) ON DELETE SET NULL,
  nombre_snap     TEXT NOT NULL,
  cantidad        INTEGER NOT NULL DEFAULT 1 CHECK (cantidad > 0),
  precio_acordado REAL NOT NULL CHECK (precio_acordado >= 0),
  anticipo        REAL NOT NULL DEFAULT 0 CHECK (anticipo >= 0),
  fecha           TEXT NOT NULL,
  fecha_limite    TEXT NOT NULL DEFAULT '',
  estatus         TEXT NOT NULL DEFAULT 'Vigente'
                  CHECK (estatus IN ('Vigente','Liquidado','Vencido','Cancelado')),
  notas           TEXT NOT NULL DEFAULT '',
  CHECK (anticipo <= precio_acordado)
);
CREATE INDEX IF NOT EXISTS ix_ap_usuario ON apartados(usuario_id, estatus);
CREATE INDEX IF NOT EXISTS ix_ap_art     ON apartados(articulo_id, estatus);

CREATE TABLE IF NOT EXISTS intercambios (
  id          TEXT PRIMARY KEY,
  usuario_id  TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  fecha       TEXT NOT NULL,
  contraparte TEXT NOT NULL DEFAULT '',
  notas       TEXT NOT NULL DEFAULT '',
  diferencia  REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS intercambio_items (
  id             TEXT PRIMARY KEY,
  intercambio_id TEXT NOT NULL REFERENCES intercambios(id) ON DELETE CASCADE,
  direccion      TEXT NOT NULL CHECK (direccion IN ('entrega','recibe')),
  articulo_id    TEXT REFERENCES articulos(id) ON DELETE SET NULL,
  nombre         TEXT NOT NULL,
  tipo           TEXT NOT NULL DEFAULT '',
  valor          REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ti ON intercambio_items(intercambio_id);

CREATE TABLE IF NOT EXISTS wishlist (
  id         TEXT PRIMARY KEY,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  nombre     TEXT NOT NULL,
  tipo       TEXT NOT NULL DEFAULT 'Hot Wheels',
  tope       REAL NOT NULL DEFAULT 0,
  prioridad  INTEGER NOT NULL DEFAULT 3 CHECK (prioridad BETWEEN 1 AND 5),
  detalle    TEXT NOT NULL DEFAULT ''
);

-- Cuánto puedes vender realmente: la cantidad menos lo comprometido en apartados
CREATE VIEW IF NOT EXISTS v_articulos AS
SELECT a.*,
  a.cantidad - COALESCE((
    SELECT SUM(ap.cantidad) FROM apartados ap
    WHERE ap.articulo_id = a.id AND ap.estatus = 'Vigente'
  ), 0) AS disponible
FROM articulos a;
