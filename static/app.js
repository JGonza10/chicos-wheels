/* ==========================================================================
   Chicos Wheels · cliente
   Habla con la API por HTTP. La única fuente de verdad es el servidor:
   aquí solo se guarda una copia para pintar rápido, y después de cada
   cambio se vuelve a pedir el estado completo.
   ========================================================================== */
(function () {
'use strict';

/* ---------- Utilidades ---------- */
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
const hoy = () => new Date().toISOString().slice(0, 10);
const dias = (a, b) => (a ? Math.max(0, Math.round((new Date(b || hoy()) - new Date(a)) / 864e5)) : 0);
const suma = (a, f) => a.reduce((s, x) => s + num(f(x)), 0);
let CUR = 'MXN';
const money = (n) => { try { return new Intl.NumberFormat('es-MX', { style: 'currency', currency: CUR, maximumFractionDigits: 2 }).format(n || 0); } catch (e) { return '$' + num(n).toFixed(2); } };
const pct = (n) => (num(n) * 100).toFixed(1) + '%';

const RAREZAS = ['Common', 'Uncommon', 'Rare', 'Holo Rare', 'Reverse Holo', 'Ultra Rare', 'Secret Rare', 'Illustration Rare', 'Promo'];
const SERIES = ['Mainline', 'Treasure Hunt', 'Super Treasure Hunt', 'Premium / Car Culture', 'Team Transport', 'RLC', 'Monster Trucks', 'Otro'];
const FUENTES = ['Mattel Creations', 'Tienda / retail', 'Bazar o tianguis', 'Convención', 'Compra en línea', 'Intercambio', 'Regalo', 'Lote / colección completa'];
const CHECKS = {
  'Hot Wheels': ['Sello TH o STH visible en la carrocería', 'Llantas de goma reales (STH)', 'Tarjeta sin dobleces ni cortes', 'Blíster sellado de fábrica', 'Base metálica con tampo correcto'],
  'Pokémon': ['Textura y relieve correctos al tacto', 'Tipografía y bordes sin pixelado', 'Prueba de luz: capa negra interior', 'Reverso con centrado y color correctos', 'Certificado de graduación verificado'],
};

/* ---------- Tema (las 4 paletas de Nexus, ver Proyectos/nexus-temas.css) ---------- */
const TEMAS = [
  { id: 'nexus', nombre: 'Nexus', descripcion: 'Oro y cian sobre negro azulado. El tema de fábrica.',
    bg: '#05080E', muestra: ['#05080E', '#FFC94A', '#8FE9FF', '#B49CFF', '#D62B34'] },
  { id: 'gonza', nombre: 'Gonza Systems', descripcion: 'Cian y violeta, con dorado cálido en los enlaces.',
    bg: '#040B16', muestra: ['#040B16', '#5FD3FF', '#A98BFF', '#FFC46B', '#F0555C'] },
  { id: 'champs', nombre: 'Champs', descripcion: 'Oro y marino sobre fondo claro, con guiño a medallas.',
    bg: '#EEF1F6', muestra: ['#EEF1F6', '#B8860B', '#0A1F44', '#A0522D', '#C1272D'] },
  { id: 'claro', nombre: 'Claro', descripcion: 'Fondo blanco limpio con azul de acento. Para trabajar de día.',
    bg: '#F6F7F9', muestra: ['#F6F7F9', '#1F6FEB', '#FFD24D', '#1B2433', '#D32F2F'] },
  { id: 'grafito', nombre: 'Grafito', descripcion: 'Gris neutro, sin brillos. Para sesiones largas.',
    bg: '#121417', muestra: ['#121417', '#E7EAEE', '#7FB2D9', '#C9A66B', '#E0645F'] },
  // 'clasico' (azul y dorado sobre marino, el original de Chicos Wheels) se
  // desactivó a petición: los colores todavía no son definitivos. Cuando se
  // decidan, actualiza los valores aquí y en styles.css (#ch[data-tema="clasico"],
  // hoy comentado) y descomenta esta entrada para que reaparezca en Apariencia.
  // { id: 'clasico', nombre: 'Clásico', descripcion: 'Azul y dorado sobre marino — el estilo original de Chicos Wheels.',
  //   bg: '#0A1120', muestra: ['#0A1120', '#FFD84D', '#38D6F0', '#A78BFA', '#FF4B4B'] },
];
const TEMA_KEY = 'collecthub_tema';
const IDS_TEMAS = TEMAS.map((t) => t.id);

function aplicarTema(id) {
  const t = IDS_TEMAS.includes(id) ? id : 'nexus';
  document.getElementById('ch').setAttribute('data-tema', t);
  localStorage.setItem(TEMA_KEY, t);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', TEMAS.find((x) => x.id === t).bg);
}
function temaGuardado() {
  const g = localStorage.getItem(TEMA_KEY);
  return IDS_TEMAS.includes(g) ? g : 'nexus';
}

/* ---------- Capa de API ---------- */
const TOKEN_KEY = 'collecthub_token';
let token = localStorage.getItem(TOKEN_KEY) || '';

async function api(ruta, opciones = {}) {
  const r = await fetch('/api' + ruta, {
    method: opciones.metodo || 'GET',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: opciones.cuerpo ? JSON.stringify(opciones.cuerpo) : undefined,
  });
  let datos = null;
  try { datos = await r.json(); } catch (e) { /* respuesta sin cuerpo */ }
  if (r.status === 401) { salir(true); throw new Error('Tu sesión expiró, vuelve a entrar'); }
  if (!r.ok) throw new Error((datos && datos.error) || 'No se pudo completar la operación');
  return datos;
}
const GET = (r) => api(r);
const POST = (r, c) => api(r, { metodo: 'POST', cuerpo: c });
const PATCH = (r, c) => api(r, { metodo: 'PATCH', cuerpo: c });
const PUT = (r, c) => api(r, { metodo: 'PUT', cuerpo: c });
const DEL = (r) => api(r, { metodo: 'DELETE' });

/* ---------- Estado ---------- */
let db = null;
let usuario = null;
let ui = {
  vista: 'panel', q: '', fTipo: 'todos', fEstatus: 'todos', orden: 'reciente',
  modal: null, ctx: null, formTipo: 'Hot Wheels', sel: [], selMode: false,
  qTipo: 'Compra', stream: null, authTab: 'login', authErr: '', ocupado: false,
  fotoPendiente: null, avisoIA: '', identificando: false,
  modoInv: (() => { try { return localStorage.getItem('cw_modoInv') === 'lista' ? 'lista' : 'fichas'; } catch (e) { return 'fichas'; } })(),
  colOrd: '', colDir: 1, mm: null, encTab: 'activos', encFecha: null, encCostos: true, enc: null, pubDesc: 0, ubLlegada: '',
  margenMin: (() => { try { const v = localStorage.getItem('cw_margenMin'); return v === null ? 10 : Math.max(0, num(v)); } catch (e) { return 10; } })(),
  rep: (() => {
    const base = { titulo: 'Reporte de inventario', secciones: ['resumen', 'inventario'], tipo: 'todos', estatus: 'todos',
      orden: 'nombre', orientacion: 'vertical', desde: '', hasta: '', solo_con_valor: false };
    try { return { ...base, ...JSON.parse(localStorage.getItem('cw_reporte') || '{}') }; } catch (e) { return base; }
  })(),
  mesesGraf: (() => { try { return num(localStorage.getItem('cw_mesesGraf')) || 6; } catch (e) { return 6; } })(),
};
let tT = null;

function toast(m, err) {
  const o = $('.toast'); if (o) o.remove();
  const d = document.createElement('div');
  d.className = 'toast' + (err ? ' err' : ''); d.textContent = m;
  document.getElementById('ch').appendChild(d);
  clearTimeout(tT); tT = setTimeout(() => d.remove(), 3200);
}

/** Ejecuta una acción contra la API, recarga el estado y avisa al usuario. */
async function accion(fn, mensajeOk) {
  if (ui.ocupado) return;
  ui.ocupado = true;
  try {
    const r = await fn();
    await cargarEstado();
    if (mensajeOk) toast(typeof mensajeOk === 'function' ? mensajeOk(r) : mensajeOk);
    return r;
  } catch (e) {
    toast(e.message, true);
    throw e;
  } finally {
    ui.ocupado = false;
  }
}

/**
 * El servidor manda nombres de columna; aquí se traducen a los que usa la
 * interfaz, para que las vistas no tengan que saber cómo es la base de datos.
 */
function normalizar(e) {
  e.ajustes = {
    moneda: e.ajustes.moneda,
    metaMensual: num(e.ajustes.meta_mensual),
    diasEstancado: num(e.ajustes.dias_estancado),
  };
  e.articulos.forEach((a) => {
    a.historial = a.valuaciones || [];
    a.grail = !!a.grail;
    a.checks = Array.isArray(a.checks) ? a.checks : [];
    a.libre = num(a.disponible);
    a.apartadas = num(a.cantidad) - num(a.disponible);
  });
  e.ventas.forEach((v) => {
    v.id_plataforma = v.plataforma_id;
    v.id_comprador = v.comprador_id;
    v.neto = num(v.ganancia_neta);
  });
  e.encargos = e.encargos || [];
  e.apartados.forEach((x) => {
    x.id_articulo = x.articulo_id;
    x.id_comprador = x.comprador_id;
  });
  return e;
}

async function cargarEstado() {
  db = normalizar(await GET('/estado'));
  CUR = db.ajustes.moneda || 'MXN';
  render();
}

/* ---------- Lecturas ---------- */
const plat = (id) => (db.plataformas.find((p) => p.id === id) || { id: '', nombre: '—', codigo: '', com_pct: 0, com_fija: 0, ret_pct: 0 });
const art = (id) => db.articulos.find((a) => a.id === id);
const cli = (id) => db.compradores.find((c) => c.id === id);
const tono = (t) => (t === 'Pokémon' ? 'var(--yellow)' : 'var(--blue)');
const emoji = (t) => (t === 'Pokémon' ? '🃏' : '🏎️');
const libre = (a) => num(a.libre);

/** Fotos con URL externa se pintan directo; las locales ('local:archivo.jpg')
 * no pueden ir en <img src> porque servirlas exige el header Authorization
 * — se pintan como placeholder y pintarFotosLocales() las llena después. */
function imgFoto(a, attrs, estiloFallback) {
  if (!a.foto) return `<span class="gh"${estiloFallback ? ` style="${estiloFallback}"` : ''}>${emoji(a.tipo)}</span>`;
  // Sin comillas dentro del span: va anidado en el atributo onerror (comillas dobles),
  // que a su vez va dentro de un string JS de comillas simples — nada de comillas aquí.
  const fallbackSinComillas = `<span class=gh${estiloFallback ? ` style=${estiloFallback.replace(/"/g, '')}` : ''}>${emoji(a.tipo)}</span>`;
  const comunes = `alt="" ${attrs || ''} onerror="this.parentNode.innerHTML='${fallbackSinComillas}'"`;
  if (a.foto.startsWith('local:')) {
    return `<img data-foto-local="${esc(a.foto.slice(6))}" data-tipo="${esc(a.tipo)}" ${comunes}>`;
  }
  return `<img src="${esc(a.foto)}" ${comunes}>`;
}
let fotosBlobActivas = [];
function pintarFotosLocales() {
  fotosBlobActivas.forEach((u) => URL.revokeObjectURL(u));
  fotosBlobActivas = [];
  $$('[data-foto-local]').forEach(async (img) => {
    try {
      const r = await fetch('/api/articulos/foto/' + img.dataset.fotoLocal,
        { headers: token ? { Authorization: 'Bearer ' + token } : {} });
      if (!r.ok) throw new Error();
      const url = URL.createObjectURL(await r.blob());
      fotosBlobActivas.push(url);
      img.src = url;
    } catch (e) { img.outerHTML = `<span class="gh">${emoji(img.dataset.tipo)}</span>`; }
  });
}

/** Vista previa del neto antes de guardar. Al guardar, manda la base de datos. */
function netoPreview({ precio, costo_unit, cantidad, com_fija, com_pct, ret_pct, envio, otros }) {
  return num(precio) - num(costo_unit) * num(cantidad) - num(com_fija)
    - num(precio) * num(com_pct) - num(precio) * num(ret_pct) - num(envio) - num(otros);
}
function precioObjetivo(deseado, costo, p, envio, otros) {
  const d = 1 - num(p.com_pct) - num(p.ret_pct);
  return d <= 0 ? 0 : (num(deseado) + costo + num(p.com_fija) + num(envio) + num(otros)) / d;
}
function tendencia(a) {
  const h = (a.historial || []).slice().sort((x, y) => x.fecha.localeCompare(y.fecha));
  if (h.length < 2) return null;
  const p = num(h[0].valor), u = num(h[h.length - 1].valor);
  return { ini: p, fin: u, delta: u - p, pct: p ? (u - p) / p : 0, n: h.length, pts: h.map((x) => num(x.valor)) };
}
function chispa(pts, color) {
  if (!pts || pts.length < 2) return '';
  const w = 170, h = 30, mx = Math.max(...pts), mn = Math.min(...pts), rg = mx - mn || 1;
  const d = pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1) * w).toFixed(1)},${(h - 2 - (v - mn) / rg * (h - 6)).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${w}" cy="${(h - 2 - (pts[pts.length - 1] - mn) / rg * (h - 6)).toFixed(1)}" r="2.6" fill="${color}"/></svg>`;
}
function stats() {
  const inv = db.articulos.filter((a) => num(a.cantidad) > 0);
  const capital = suma(inv, (a) => num(a.precio_compra) * num(a.cantidad));
  const mercado = suma(inv, (a) => num(a.valor_estimado) * num(a.cantidad));
  const piezas = suma(inv, (a) => a.cantidad);
  const ing = suma(db.ventas, (v) => v.precio), gan = suma(db.ventas, (v) => v.neto);
  const rot = db.ventas.filter((v) => v.fecha_adq_snap).map((v) => dias(v.fecha_adq_snap, v.fecha));
  const ap = db.apartados.filter((x) => x.estatus === 'Vigente');
  return {
    capital, mercado, piezas, skus: inv.length, ing, gan, plus: mercado - capital,
    margen: ing ? gan / ing : 0, ticket: db.ventas.length ? ing / db.ventas.length : 0,
    rotacion: rot.length ? Math.round(suma(rot, (x) => x) / rot.length) : null,
    estancados: inv.filter((a) => a.estatus === 'Disponible' && a.fecha_adq && dias(a.fecha_adq) > db.ajustes.diasEstancado),
    sinValor: inv.filter((a) => !num(a.valor_estimado)).length,
    agotados: db.articulos.filter((a) => !num(a.cantidad)).length,
    apartados: ap.length, anticipos: suma(ap, (x) => x.anticipo),
    vencidos: db.apartados.filter((x) => x.estatus === 'Vencido').length,
    saldoMes: suma(db.ventas.filter((v) => (v.fecha || '').slice(0, 7) === hoy().slice(0, 7)), (v) => v.neto),
  };
}
/* ---------- Ritmo del negocio: entregas los sábados en Balderas ---------- */
/** Etiquetas que ve el usuario (en la base siguen Pendiente/Empacado/Entregado). */
const ETQ_ENC = { Pendiente: 'Apartado', Empacado: 'En proceso', Entregado: 'Liquidado', Cancelado: 'Cancelado' };
const encDebe = (e) => (e.estatus === 'Entregado' ? Math.max(0, num(e.total_final != null ? e.total_final : e.total) - num(e.anticipo) - num(e.cobrado_entrega)) : 0);
const etqEnc = (e) => (e.estatus === 'Entregado' && encDebe(e) > 0.005 ? `Entregado · debe ${money(encDebe(e))}` : ETQ_ENC[e.estatus] || e.estatus);
const claseEnc = (e) => (e.estatus === 'Entregado' ? (encDebe(e) > 0.005 ? 'y' : 'g') : e.estatus === 'Empacado' ? 'b' : e.estatus === 'Cancelado' ? 'r' : 'y');
/** Sábado de entrega: hoy si es sábado; si no, el que sigue. `extra` = sábados adicionales. */
function proximoSabado(extra) {
  const d = new Date(hoy() + 'T12:00:00');
  d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7) + 7 * (extra || 0));
  return d.toISOString().slice(0, 10);
}
const fmtDia = (f, largo) => { if (!f) return 'Sin fecha de entrega'; const d = new Date(f + 'T12:00:00'); return isNaN(d) ? f : d.toLocaleDateString('es-MX', largo ? { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' } : { weekday: 'short', day: 'numeric', month: 'short' }); };
/** Quién tiene reservada una pieza y para cuándo (encargos activos y apartados vigentes). */
function reservas(a) {
  const r = [];
  (db.encargos || []).filter((e) => e.estatus === 'Pendiente' || e.estatus === 'Empacado').forEach((e) => {
    e.items.filter((i) => i.articulo_id === a.id).forEach((i) => r.push({ cliente: (cli(e.comprador_id) || {}).nombre || 'Cliente', fecha: e.fecha_entrega, cant: i.cantidad, est: ETQ_ENC[e.estatus] }));
  });
  db.apartados.filter((x) => x.articulo_id === a.id && x.estatus === 'Vigente').forEach((x) => r.push({ cliente: (cli(x.id_comprador) || {}).nombre || x.cliente_snap || 'Cliente', fecha: x.fecha_limite, cant: x.cantidad, est: 'Apartado' }));
  return r;
}
const reservasTxt = (a) => reservas(a).map((x) => `${x.cliente}${x.cant > 1 ? ' ×' + x.cant : ''} · ${x.est}${x.fecha ? ' · ' + fmtDia(x.fecha) : ''}`).join('; ');

/* ---------- Estatus de la pieza ---------- */
function semaforo(a) {
  if (a.estatus === 'Conservar') return { c: 'p', t: 'Conservar', col: 'var(--purple)' };
  if (!num(a.cantidad)) return { c: 'r', t: 'Agotado', col: 'var(--red)' };
  if (a.apartadas > 0) { const r = reservas(a); return { c: r.some((x) => x.est === 'En proceso') ? 'b' : 'y', t: r.some((x) => x.est === 'En proceso') ? 'En proceso' : 'Apartado', col: r.some((x) => x.est === 'En proceso') ? 'var(--blue)' : 'var(--yellow)' }; }
  if (a.estatus === 'En negociación') return { c: 'y', t: 'En negociación', col: 'var(--yellow)' };
  return { c: 'g', t: 'Disponible', col: 'var(--green)' };
}
function movimientos() {
  const m = [];
  db.ventas.forEach((v) => m.push({
    f: v.fecha, tit: v.nombre_snap, sub: `Venta · ${v.plataforma_snap || plat(v.id_plataforma).nombre}`,
    amt: v.neto, col: v.neto >= 0 ? 'var(--green)' : 'var(--red)',
  }));
  db.articulos.forEach((a) => { if (a.fecha_adq) m.push({
    f: a.fecha_adq, tit: a.nombre, sub: `Compra · ${a.fuente || a.tipo}`,
    amt: -num(a.precio_compra) * num(a.cant_inicial || a.cantidad || 1), col: 'var(--red)',
  }); });
  db.apartados.forEach((x) => m.push({
    f: x.fecha, tit: x.nombre_snap, sub: `Anticipo · ${cli(x.id_comprador) ? cli(x.id_comprador).nombre : 'Cliente'}`,
    amt: num(x.anticipo), col: 'var(--yellow)',
  }));
  db.intercambios.forEach((x) => m.push({
    f: x.fecha, tit: 'Intercambio con ' + (x.contraparte || '—'),
    sub: `${x.entregados.length} entregadas · ${x.recibidos.length} recibidas`,
    amt: num(x.diferencia), col: num(x.diferencia) >= 0 ? 'var(--green)' : 'var(--red)',
  }));
  return m.sort((a, b) => (b.f || '').localeCompare(a.f || ''));
}

/* ==================== Pantalla de acceso ==================== */
function vistaAuth() {
  const esLogin = ui.authTab === 'login';
  return `<div class="auth"><div class="authbox">
    <div class="logo">CHICOS<i>WHEELS</i></div>
    <div class="sub">Inventario, valuación y venta de coleccionables</div>
    <div class="pnl">
      <div class="authtabs">
        <button data-a="authtab" data-v="login" class="${esLogin ? 'on' : ''}">Entrar</button>
        <button data-a="authtab" data-v="registro" class="${!esLogin ? 'on' : ''}">Crear cuenta</button>
      </div>
      ${ui.authErr ? `<div class="autherr">${esc(ui.authErr)}</div>` : ''}
      ${esLogin ? '' : `<div class="fld"><label class="lbl">Tu nombre</label><input class="in" id="au_nombre" placeholder="Chicos Wheels" autocomplete="name"></div>`}
      <div class="fld"><label class="lbl">Correo</label><input class="in" id="au_email" type="email" placeholder="tucorreo@ejemplo.com" autocomplete="email"></div>
      <div class="fld"><label class="lbl">Contraseña</label>
        <input class="in" id="au_pass" type="password" placeholder="${esLogin ? 'Tu contraseña' : 'Mínimo 8 caracteres'}" autocomplete="${esLogin ? 'current-password' : 'new-password'}"></div>
      <button class="btn pri" data-a="auth" style="width:100%;padding:12px;margin-top:6px">
        ${esLogin ? 'Entrar' : 'Crear mi cuenta'}</button>
    </div>
    <div class="authfoot">Tus datos se guardan en tu propio servidor.<br>Nadie más que tú tiene acceso a tu inventario.</div>
  </div></div>`;
}

async function autenticar() {
  const email = ($('#au_email').value || '').trim();
  const password = $('#au_pass').value || '';
  const nombre = $('#au_nombre') ? $('#au_nombre').value.trim() : '';
  ui.authErr = '';
  try {
    const r = await api(ui.authTab === 'login' ? '/auth/login' : '/auth/registro',
      { metodo: 'POST', cuerpo: { email, password, nombre } });
    token = r.token;
    localStorage.setItem(TOKEN_KEY, token);
    usuario = r.usuario;
    await cargarEstado();
    toast(`Bienvenido, ${usuario.nombre || usuario.email}`);
  } catch (e) {
    ui.authErr = e.message;
    render();
  }
}
function salir(silencioso) {
  token = ''; usuario = null; db = null;
  localStorage.removeItem(TOKEN_KEY);
  ui.vista = 'panel'; ui.modal = null; ui.sel = [];
  render();
  if (!silencioso) toast('Sesión cerrada');
}

/* ==================== Render ==================== */
const NAV = [['panel', '◧', 'Panel'], ['inventario', '▦', 'Inventario'],
  ['SEP1', '', 'Movimientos'], ['ventas', '⇄', 'Ventas'], ['encargos', '🛍', 'Pedidos'], ['apartados', '⏳', 'Apartados previos'], ['intercambios', '⇌', 'Intercambios'],
  ['SEP2', '', 'Catálogos'], ['compradores', '☺', 'Compradores'], ['wishlist', '★', 'Faltantes'],
  ['etiquetas', '▩', 'Etiquetas QR'], ['datos', '⛃', 'Datos']];
const CNT = {
  inventario: () => db.articulos.length, ventas: () => db.ventas.length,
  apartados: () => db.apartados.filter((x) => x.estatus === 'Vigente').length,
  encargos: () => encActivos().length,  intercambios: () => db.intercambios.length, compradores: () => db.compradores.length,
  wishlist: () => db.wishlist.length,
};

function render() {
  if (!token) { $('#app').innerHTML = vistaAuth(); return; }
  if (!db) { $('#app').innerHTML = '<div class="cargando"><div><div class="spin"></div>Cargando tu colección…</div></div>'; return; }
  /* Modo bazar deshabilitado (2026-09-24): vBazar sigue definida, solo sin acceso desde el menú */
  const V = { panel: vPanel, inventario: vInv, ventas: vVentas, apartados: vApart,
    intercambios: vTrade, encargos: vEncargos, compradores: vComp, wishlist: vWish, etiquetas: vQR, datos: vDatos }[ui.vista] || vPanel;
  $('#app').innerHTML = `
  <div class="shell">
    <aside class="side">
      <div class="logo">CHICOS<i>WHEELS</i><small>${esc((usuario && (usuario.nombre || usuario.email)) || '')}</small></div>
      <nav class="nav">${NAV.filter((n) => n[0] !== 'apartados' || db.apartados.length).map((n) => (n[0].startsWith('SEP')
        ? `<div class="navsep">${n[2]}</div>`
        : `<button data-a="nav" data-v="${n[0]}" class="${ui.vista === n[0] ? 'on' : ''}"><span class="ic">${n[1]}</span>${n[2]}<span class="cnt">${CNT[n[0]] ? (CNT[n[0]]() || '') : ''}</span></button>`)).join('')}
        <div class="salir"><button data-a="salir"><span class="ic">⏻</span>Cerrar sesión</button></div>
      </nav>
    </aside>
    <main class="main">${V()}</main>
  </div>
  <button class="fab" data-a="nuevo" title="Registrar pieza" aria-label="Registrar pieza">+</button>
  <nav class="mob">${NAV.filter((n) => !n[0].startsWith('SEP') && (n[0] !== 'apartados' || db.apartados.length)).map((n) =>
    `<button data-a="nav" data-v="${n[0]}" class="${ui.vista === n[0] ? 'on' : ''}"><span class="ic">${n[1]}</span>${n[2].replace('Modo ', '')}</button>`).join('')}</nav>
  ${ui.modal ? `<div class="ov">${(MOD[ui.modal] || (() => ''))()}</div>` : ''}`;
  if (ui.modal === 'venta') pintarVenta();
  if (ui.modal === 'lote') pintarLote();
  if (ui.modal === 'historial') pintarChart();
  if (ui.vista === 'etiquetas') pintarQR();
  pintarFotosLocales();
}

function hdr(t, s, extra) {
  return `<div class="hdr"><div><h1>${t}<span>${s}</span></h1></div><div class="sp"></div>
  ${extra === undefined ? `<div class="srch"><input class="in" placeholder="Nombre, número, ubicación, código…" value="${esc(ui.q)}" data-a="q"></div>
  <button class="btn gh sm" data-a="escanear" title="Escanear código de barras">⌗ Escanear</button>
  <button class="btn gh sm" data-a="fotoia" title="Registrar con foto, la IA sugiere los datos">📷 Con foto</button>
  <button class="btn gh sm" data-a="compramattel" title="Pega los links de lo que compraste en Mattel y se registran todos juntos">🛒 Compra Mattel</button>
  <button class="btn pri" data-a="nuevo">+ Registrar pieza</button>` : extra}
  <div class="emb"><b class="hw">🏎</b><b class="pk">🃏</b></div></div>`;
}
const kpi = (k, v, s, c) => `<div class="kpi" style="--c:${c}"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
const bar = (l, r, w, c) => `<div class="bar"><div class="t"><span>${esc(l)}</span><b>${r}</b></div>
  <div class="tr"><div class="fl" style="width:${Math.max(2, Math.min(100, w))}%;background:${c}"></div></div></div>`;
const vacio = (ic, t, p, btn) => `<div class="empty"><div class="big">${ic}</div><h3>${t}</h3>
  <p style="max-width:430px;margin:0 auto 18px">${p}</p>${btn || ''}</div>`;
const alerta = (t, n, d, c, v) => `<div class="pnl" style="cursor:pointer" data-a="nav" data-v="${v}">
  <div style="font-size:12.5px;color:var(--muted)">${t}</div>
  <div style="font-size:31px;font-weight:800;letter-spacing:-.03em;color:${n ? c : 'var(--muted2)'};margin:5px 0 4px">${n}</div>
  <div style="font-size:12px;color:var(--muted)">${d}</div></div>`;

/** Gráfica de barras por mes: compras (gasto) vs ventas netas de los últimos N meses. */
function graficaMeses() {
  const n = ui.mesesGraf, hoyD = new Date(), meses = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(hoyD.getFullYear(), hoyD.getMonth() - i, 1);
    meses.push({ k: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`, d, compras: 0, ventas: 0 });
  }
  const por = Object.fromEntries(meses.map((m) => [m.k, m]));
  db.ventas.forEach((v) => { const m = por[(v.fecha || '').slice(0, 7)]; if (m) m.ventas += num(v.neto); });
  db.articulos.forEach((a) => { const m = por[(a.fecha_adq || '').slice(0, 7)]; if (m) m.compras += num(a.precio_compra) * num(a.cant_inicial || a.cantidad || 1); });
  const max = Math.max(1, ...meses.map((m) => Math.max(m.compras, Math.abs(m.ventas))));
  const W = 560, H = 190, pl = 6, pb = 24, pt = 8, ancho = (W - pl) / n, bw = Math.min(26, ancho / 2.6), alto = H - pb - pt;
  const y = (v) => pt + alto - (Math.abs(v) / max) * alto;
  const barras = meses.map((m, i) => {
    const cx = pl + ancho * i + ancho / 2, nom = m.d.toLocaleDateString('es-MX', { month: 'short' }).replace('.', '');
    const tip = `${m.d.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' })}: compras ${money(m.compras)} · ventas netas ${money(m.ventas)}`;
    return `<g><title>${esc(tip)}</title>
      <rect x="${cx - bw - 1}" y="${y(m.compras)}" width="${bw}" height="${pt + alto - y(m.compras)}" rx="2" fill="var(--red)" opacity=".85"/>
      <rect x="${cx + 1}" y="${y(m.ventas)}" width="${bw}" height="${pt + alto - y(m.ventas)}" rx="2" fill="${m.ventas >= 0 ? 'var(--green)' : 'var(--yellow)'}" opacity=".9"/>
      ${n <= 12 || i % 2 === 0 ? `<text x="${cx}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--muted)">${esc(nom)}${m.d.getMonth() === 0 || i === 0 ? ' ' + String(m.d.getFullYear()).slice(2) : ''}</text>` : ''}</g>`;
  }).join('');
  const totC = suma(meses, (m) => m.compras), totV = suma(meses, (m) => m.ventas);
  return `<div class="chips" style="margin-bottom:10px">${[3, 6, 12, 24].map((k) => `<button class="chip ${n === k ? 'on' : ''}" data-a="mesesgraf" data-v="${k}">${k} meses</button>`).join('')}
    <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)">Otro
      <input class="in" type="number" min="1" max="36" value="${n}" data-a="mesesgraf_in" style="width:62px;padding:5px 8px"></label></div>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block" role="img" aria-label="Compras y ventas netas por mes">
      <line x1="${pl}" x2="${W}" y1="${pt + alto}" y2="${pt + alto}" stroke="var(--line2)"/>${barras}</svg>
    <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px">
      <span><span class="dt" style="background:var(--red)"></span>Compras <b class="mn" style="color:var(--text)">${money(totC)}</b></span>
      <span><span class="dt" style="background:var(--green)"></span>Ventas netas <b class="mn" style="color:var(--text)">${money(totV)}</b></span>
      <span>Balance <b class="mn ${totV - totC >= 0 ? 'pos' : 'neg'}">${money(totV - totC)}</b></span></div>`;
}

/** Piezas en stock cuyo valor cambió >= 15% entre sus dos últimas valuaciones (últimos 60 días). */
function cambiosPrecio() {
  const corte = new Date(Date.now() - 60 * 864e5).toISOString().slice(0, 10);
  return db.articulos.filter((a) => num(a.cantidad)).map((a) => {
    const h = (a.historial || []).slice().sort((x, y) => x.fecha.localeCompare(y.fecha));
    if (h.length < 2 || h[h.length - 1].fecha < corte) return null;
    const p = num(h[h.length - 2].valor), u = num(h[h.length - 1].valor);
    return p ? { a, p, u, pct: (u - p) / p, fecha: h[h.length - 1].fecha } : null;
  }).filter((x) => x && Math.abs(x.pct) >= 0.15).sort((x, y) => Math.abs(y.pct) - Math.abs(x.pct)).slice(0, 6);
}

/* ---------- Panel ---------- */
function vPanel() {
  const s = stats();
  const titulo = 'CHICOS<i style="color:var(--yellow);font-style:normal">WHEELS</i>';
  if (!db.articulos.length && !db.ventas.length) {
    return hdr(titulo, 'Inventario, valuación y venta de coleccionables') +
      vacio('🏎️', 'Tu vitrina está vacía', 'Registra tu primera pieza y el panel empieza a calcular capital, plusvalía y ganancias solo.',
        `<button class="btn pri" data-a="nuevo">Registrar mi primera pieza</button> <button class="btn gh" data-a="demo">Ver con datos de ejemplo</button>`);
  }
  const porTipo = {};
  db.articulos.forEach((a) => { if (num(a.cantidad)) porTipo[a.tipo] = (porTipo[a.tipo] || 0) + num(a.cantidad); });
  const maxT = Math.max(1, ...Object.values(porTipo));
  const porPlat = {};
  db.ventas.forEach((v) => { const k = v.plataforma_snap || plat(v.id_plataforma).nombre; porPlat[k] = (porPlat[k] || 0) + v.neto; });
  const maxP = Math.max(1, ...Object.values(porPlat).map(Math.abs));
  const meta = db.ajustes.metaMensual;
  const movs = movimientos().slice(0, 9);
  const vendibles = db.articulos.filter((a) => libre(a) > 0);
  return hdr(titulo, 'Inventario, valuación y venta de coleccionables') + `
  <div class="kpis">
    ${kpi('Valor total', money(s.mercado), `${s.piezas} piezas · ${s.skus} modelos`, 'var(--blue)')}
    ${kpi('Piezas en stock', s.piezas, `${s.apartados} apartadas · ${s.agotados} agotadas`, 'var(--red)')}
    ${kpi('Balance del mes', money(s.saldoMes), `Meta ${money(meta)} · ${meta ? pct(s.saldoMes / meta) : '—'}`, 'var(--yellow)')}
    ${kpi('Ganancia acumulada', money(s.gan), `${db.ventas.length} ventas · margen ${pct(s.margen)}`, 'var(--green)')}
  </div>
  <div class="pgrid" style="display:grid;grid-template-columns:1.25fr 1fr;gap:16px">
    <div class="pnl">
      <h2>Movimientos por mes</h2>
      ${graficaMeses()}
    </div>
    <div class="pnl">
      <h2>Historial reciente</h2>
      ${movs.length ? `<div class="feed">${movs.map((m) => `<div class="fi"><span class="dot" style="background:${m.col};--dc:${m.col}"></span>
        <span class="tx"><b>${esc(m.tit)}</b><span>${esc(m.sub)} · ${m.f || '—'}</span></span>
        <span class="am" style="color:${m.col}">${m.amt >= 0 ? '+' : '−'}${money(Math.abs(m.amt))}</span></div>`).join('')}</div>`
        : `<p style="color:var(--muted);font-size:13px">Aún no hay movimientos.</p>`}
    </div>
  </div>
  ${(() => { const ea = encActivos(); return ea.length ? `<div class="pnl" style="margin-top:16px;cursor:pointer" data-a="nav" data-v="encargos"><h2>Pedidos por entregar (${ea.length})</h2>
    <div style="font-size:13px;color:var(--muted)">${suma(ea, (e) => e.piezas)} piezas para ${new Set(ea.map((e) => e.comprador_id)).size} cliente(s) · por cobrar <b class="mn" style="color:var(--text)">${money(suma(ea, (e) => e.resta))}</b> · ganancia esperada <b class="mn pos">${money(suma(ea, (e) => e.ganancia))}</b></div>
    <div style="font-size:12.5px;margin-top:8px">🗓 Próximo sábado <b>${esc(fmtDia(proximoSabado()))}</b>: ${ea.filter((e) => e.fecha_entrega === proximoSabado()).length} pedido(s), ${ea.filter((e) => e.estatus === 'Empacado').length} ya en proceso.</div></div>` : ''; })()}
  ${(() => { const pr = porRecibir(); return pr.length ? `<div class="pnl" style="margin-top:16px;border-color:var(--yellow)"><h2>Por recibir (${pr.length})</h2>
    <p style="font-size:12.5px;color:var(--muted);margin-bottom:10px">Piezas que compraste y aún no llegan. Cuando lleguen, escribe dónde las guardas y márcalas.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px"><input class="in" id="ub_llegada" placeholder="Ubicación, ej. Caja A" value="${esc(ui.ubLlegada)}" style="max-width:240px">
      <button class="btn sm grn" data-a="yallegotodas">Ya llegaron todas</button></div>
    <div class="feed">${pr.map((a) => `<div class="fi"><span class="dot" style="background:var(--yellow)"></span>
      <span class="tx"><b>${esc(a.nombre)}</b><span>${a.cantidad > 1 ? '×' + a.cantidad + ' · ' : ''}${esc(a.fuente || '')} · ${a.fecha_adq || ''}</span></span>
      <button class="btn sm grn" data-a="yallego" data-id="${a.id}">Ya llegó</button></div>`).join('')}</div></div>` : ''; })()}
  ${(() => { const cp = cambiosPrecio(); return cp.length ? `<div class="pnl" style="margin-top:16px"><h2>Movimientos de precio</h2>
    <p style="font-size:12.5px;color:var(--muted);margin-bottom:10px">Piezas cuyo valor cambió 15% o más en su última valuación. Si subió, es buen momento de publicarla; si bajó, revisa antes de vender.</p>
    <div class="feed">${cp.map((c) => `<div class="fi" style="cursor:pointer" data-a="ver" data-id="${c.a.id}"><span class="dot" style="background:${c.pct >= 0 ? 'var(--green)' : 'var(--red)'}"></span>
      <span class="tx"><b>${esc(c.a.nombre)}</b><span>${money(c.p)} → ${money(c.u)} · ${c.fecha}</span></span>
      <span class="am ${c.pct >= 0 ? 'pos' : 'neg'}">${c.pct >= 0 ? '▲' : '▼'} ${pct(Math.abs(c.pct))}</span></div>`).join('')}</div></div>` : ''; })()}
  ${(() => { const rf = rendimientoFuentes(); return rf.length ? `<div class="pnl" style="margin-top:16px"><h2>De dónde salen tus mejores piezas</h2>
    <p style="font-size:12.5px;color:var(--muted);margin-bottom:10px">Retorno = ganancia neta ÷ lo que costaron las piezas vendidas. Compra más donde el retorno es mayor.</p>
    ${rf.slice(0, 6).map((o) => bar(`${o.k} · ${o.n} vendidas`, `${pct(o.roi)} · ${money(o.neto)}`, Math.min(100, Math.max(0, o.roi) * 50), o.roi >= 0 ? 'var(--green)' : 'var(--red)')).join('')}</div>` : ''; })()}
  <div class="sec"><h2>Qué necesita tu atención</h2><span class="ln"></span></div>
  <div class="g3">
    ${alerta('Capital estancado', s.estancados.length, `piezas con más de ${db.ajustes.diasEstancado} días sin venderse`, 'var(--yellow)', 'inventario')}
    ${alerta('Apartados vencidos', s.vencidos, 'anticipos que ya pasaron su fecha límite', 'var(--red)', 'apartados')}
    ${alerta('Sin precio de mercado', s.sinValor, 'piezas que no puedes valuar ni publicar', 'var(--blue)', 'inventario')}
  </div>
  <div class="g2" style="margin-top:16px">
    <div class="pnl"><h2>Piezas por colección</h2>
      ${Object.keys(porTipo).length ? Object.entries(porTipo).map(([t, n]) => bar(t, n + ' pzs', n / maxT * 100, tono(t))).join('') : '<p style="color:var(--muted);font-size:13px">Sin inventario.</p>'}
      <div style="border-top:1px solid var(--line);margin-top:14px;padding-top:14px;font-size:12.5px;color:var(--muted)">
        Capital invertido <b class="mn" style="color:var(--text)">${money(s.capital)}</b> ·
        plusvalía <b class="mn ${s.plus >= 0 ? 'pos' : 'neg'}">${s.plus >= 0 ? '+' : ''}${money(s.plus)}</b>
        ${s.rotacion !== null ? ` · rotación ${s.rotacion} días` : ''}</div>
    </div>
    <div class="pnl"><h2>Ganancia neta por canal</h2>
      ${db.ventas.length ? Object.entries(porPlat).sort((a, b) => b[1] - a[1]).map(([n, g]) => bar(n, money(g), Math.abs(g) / maxP * 100, g >= 0 ? 'var(--green)' : 'var(--red)')).join('')
        : '<p style="color:var(--muted);font-size:13px">Registra ventas para comparar canales.</p>'}
      <div style="border-top:1px solid var(--line);margin-top:14px;padding-top:14px;font-size:12.5px;color:var(--muted)">
        El canal más rentable no es el que más vende, sino el que deja mejor margen.</div>
    </div>
  </div>`;
}

/* ---------- Precio mínimo para regatear ---------- */
/** Piso de precio por pieza: el menor precio con el que aún ganas el margen mínimo elegido
 *  (costo + margen + comisiones del canal de Balderas o, en su defecto, Facebook). */
function precioMinimo(a) {
  const p = db.plataformas.find((x) => x.codigo === 'TG') || db.plataformas.find((x) => x.codigo === 'FB') || { com_pct: 0, com_fija: 0, ret_pct: 0 };
  const div = 1 - num(p.com_pct) - num(p.ret_pct);
  if (div <= 0) return num(a.valor_estimado);
  return (num(a.precio_compra) * (1 + ui.margenMin / 100) + num(p.com_fija)) / div;
}
/** Pedidos de clientes (sin atender) que parecen coincidir con esta pieza. */
function pedidosPara(a) {
  const hay = [a.nombre, a.numero, a.serie, a.color, a.expansion].join(' ').toLowerCase();
  return (db.pedidos || []).filter((p) => !p.atendido).filter((p) => {
    const t = p.descripcion.toLowerCase().split(/[^a-z0-9áéíóúñ]+/).filter((x) => x.length >= 3);
    return t.length && t.filter((x) => hay.includes(x)).length >= Math.min(2, t.length);
  });
}
const esPorRecibir = (a) => num(a.cantidad) > 0 && String(a.ubicacion || '').trim().toLowerCase() === 'por recibir';
const porRecibir = () => db.articulos.filter(esPorRecibir);
/** Ganancia y retorno por fuente de compra (de dónde salen las piezas que mejor se venden). */
function rendimientoFuentes() {
  const por = {};
  db.ventas.forEach((v) => {
    const a = db.articulos.find((x) => x.id === v.articulo_id);
    const k = (a && a.fuente) || 'Sin registrar';
    const o = por[k] || (por[k] = { k, n: 0, neto: 0, costo: 0 });
    o.n += num(v.cantidad); o.neto += num(v.neto); o.costo += num(v.costo_unit) * num(v.cantidad);
  });
  return Object.values(por).filter((o) => o.costo > 0).map((o) => Object.assign(o, { roi: o.neto / o.costo })).sort((a, b) => b.roi - a.roi);
}

/* ---------- Encargos: pedidos de clientes para entregar en Balderas ---------- */
const FORMAS_PAGO = ['Efectivo', 'Depósito', 'Transferencia'];
const encActivos = () => (db.encargos || []).filter((e) => e.estatus === 'Pendiente' || e.estatus === 'Empacado');
function vEncargos() {
  const act = encActivos(), hechos = (db.encargos || []).filter((e) => e.estatus === 'Entregado');
  const lista = ui.encTab === 'entregados' ? hechos : ui.encTab === 'todos' ? (db.encargos || []) : act;
  const fechas = [...new Set(act.map((e) => e.fecha_entrega).filter(Boolean))].sort();
  const fechaSel = ui.encFecha === null ? (fechas.find((f) => f >= hoy()) || '') : ui.encFecha;
  const sel = act.filter((e) => !fechaSel || e.fecha_entrega === fechaSel);
  const S = (f) => suma(sel, f);
  const grupos = {};
  lista.forEach((e) => { const k = e.fecha_entrega || ''; (grupos[k] = grupos[k] || []).push(e); });
  const claves = Object.keys(grupos).sort((a, b) => (a || '9999').localeCompare(b || '9999'));
  const tabs = [['activos', `Por entregar (${act.length})`], ['entregados', `Liquidados (${hechos.length})`], ['todos', 'Todos']];
  const fmt = (f) => fmtDia(f, true) + (f && new Date(f + 'T12:00:00').getDay() !== 6 ? ' (entre semana)' : '');
  return hdr('Pedidos', 'Apartado → En proceso → Liquidado · entregas los sábados en Balderas',
    `<button class="btn pri" data-a="nuevoenc">+ Nuevo pedido</button>`) + `
  ${act.length ? `<div class="pnl" style="margin-bottom:14px;padding:14px 16px">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
      <b style="font-size:13px">Hoja de entrega (imprimir o Excel)</b>
      <select class="sel" data-a="encfecha" style="width:auto;padding:7px 32px 7px 12px;font-size:12.5px">
        <option value="">Todos los pendientes</option>
        ${fechas.map((f) => `<option value="${f}" ${fechaSel === f ? 'selected' : ''}>${esc(fmt(f))}</option>`).join('')}</select>
      <label class="chk" style="margin:0;padding:6px 10px"><input type="checkbox" data-a="enccostos" ${ui.encCostos ? 'checked' : ''}><span>Incluir costos y ganancia</span></label>
      <button class="btn pri sm" data-a="hojaent">🖨 PDF</button>
      <button class="btn sm" data-a="hojaexcel" title="La misma hoja como lista de Excel, con filtros y totales">📊 Excel</button></div>
    <div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin:0">
      ${kpi('Clientes', new Set(sel.map((e) => e.comprador_id)).size, `${sel.length} encargo${sel.length === 1 ? '' : 's'}`, 'var(--blue)')}
      ${kpi('Piezas a llevar', S((e) => e.piezas), 'en total', 'var(--purple)')}
      ${kpi('Costo', money(S((e) => e.costo)), 'lo que te costaron', 'var(--red)')}
      ${kpi('Precio', money(S((e) => e.total)), 'lo que vas a vender', 'var(--yellow)')}
      ${kpi('Por cobrar', money(S((e) => e.resta)), `ya cobrado ${money(S((e) => e.anticipo))}`, 'var(--green)')}
      ${kpi('Ganancia', money(S((e) => e.ganancia)), 'esperada', 'var(--green)')}
    </div></div>` : ''}
  <div class="chips">${tabs.map((t) => `<button class="chip ${ui.encTab === t[0] ? 'on' : ''}" data-a="enctab" data-v="${t[0]}">${t[1]}</button>`).join('')}</div>
  ${claves.length ? claves.map((k) => `
    <div class="sec" style="margin-top:16px"><h2 style="text-transform:capitalize">${esc(fmt(k))}</h2><span class="ln"></span>
      <span class="mn" style="font-size:12px;color:var(--muted)">${grupos[k].length} encargo${grupos[k].length === 1 ? '' : 's'} · ${suma(grupos[k], (e) => e.piezas)} piezas</span></div>
    <div class="pnl wrap" style="padding:6px"><table class="tbl"><thead><tr>
      <th>Cliente</th><th>Piezas</th><th class="num">Costo</th><th class="num">Precio</th><th class="num">Anticipo</th><th class="num">Por cobrar</th><th>Estatus</th><th></th></tr></thead><tbody>
      ${grupos[k].map((e) => { const c = cli(e.comprador_id) || {}; const act1 = e.estatus === 'Pendiente' || e.estatus === 'Empacado';
        return `<tr class="${e.estatus === 'Cancelado' ? 'sold' : ''}"><td><b>${esc(c.nombre || 'Cliente')}</b><div style="font-size:11px;color:var(--muted)">${esc(c.tel || '')}${e.notas ? ' · ' + esc(e.notas) : ''}</div></td>
        <td style="font-size:12.5px">${e.items.map((i) => `${i.cantidad}× ${esc(i.nombre_snap)} <span class="mu">@ ${money(i.precio_unit)}</span>`).join('<br>')}</td>
        <td class="num">${money(e.costo)}</td><td class="num"><b>${money(e.estatus === 'Entregado' && e.total_final != null ? e.total_final : e.total)}</b></td>
        <td class="num">${e.anticipo ? money(e.anticipo) + `<div class="mu" style="font-size:10.5px">${esc(e.forma_anticipo)}</div>` : '—'}</td>
        <td class="num ${e.resta ? '' : 'pos'}">${e.estatus === 'Entregado' ? `<span class="mu">cobrado ${money(e.cobrado_entrega)}</span>` : money(e.resta)}</td>
        <td><span class="tag ${claseEnc(e)}">${esc(etqEnc(e))}</span></td>
        <td style="text-align:right;white-space:nowrap">${act1 ? `
          <button class="btn sm gh" data-a="encempacar" data-id="${e.id}" data-v="${e.estatus === 'Empacado' ? 'Pendiente' : 'Empacado'}" title="${e.estatus === 'Empacado' ? 'Regresar a Apartado' : 'Ya está empacado y listo para llevar'}">${e.estatus === 'Empacado' ? '↩ Apartado' : '📦 En proceso'}</button>
          <button class="btn sm grn" data-a="encrapido" data-id="${e.id}" data-v="Efectivo" title="Entregado y cobrado el resto en efectivo">💵</button>
          <button class="btn sm grn" data-a="encrapido" data-id="${e.id}" data-v="Depósito" title="Entregado y cobrado el resto por depósito">🏦</button>
          <button class="btn sm gh" data-a="encwa" data-id="${e.id}" title="Mensaje de WhatsApp al cliente">💬</button>
          <button class="btn sm gh" data-a="editenc" data-id="${e.id}">Editar</button>
          <button class="btn sm gh" data-a="encentregar" data-id="${e.id}" title="Entregar con otro monto o forma de pago">Entregar…</button>
          <button class="btn sm gh" data-a="enccancelar" data-id="${e.id}" title="Cancelar y liberar las piezas">✕</button>`
          : (e.estatus === 'Cancelado' ? `<button class="btn sm gh" data-a="encborrar" data-id="${e.id}">Borrar</button>` : '')}</td></tr>`; }).join('')}
    </tbody></table></div>`).join('')
    : vacio('🛍', 'Aún no hay encargos', 'Cuando un cliente te pida una o varias piezas, regístralo aquí: se reservan, se empacan y al entregar en Balderas se vuelven ventas.',
      '<button class="btn pri" data-a="nuevoenc">Nuevo encargo</button>')}
  <div class="note"><b>Cómo se lee:</b> <b>Apartado</b> = reservado para un cliente (con o sin anticipo) · <b>En proceso</b> = ya empacado para el sábado · <b>Liquidado</b> = entregado y pagado. 💵 / 🏦 entregan y cobran lo que resta de un toque; <b>Entregar…</b> permite otro monto. Al entregar se convierten en ventas y salen del inventario.</div>`;
}
/** Estado del formulario de encargo: se lee del DOM antes de cada re-pintado. */
function encNuevo() {
  return { id: '', comprador_id: '', cliente_nuevo: '', tel_nuevo: '', fecha_entrega: proximoSabado(), anticipo: '', forma_anticipo: 'Depósito', notas: '', items: [{ articulo_id: '', cantidad: 1, precio_unit: '' }] };
}
function snapEnc() {
  const e = ui.enc; if (!e || !$('#en_comp')) return;
  const v = (id) => $('#' + id).value;
  e.comprador_id = v('en_comp'); e.cliente_nuevo = $('#en_nuevo') ? v('en_nuevo') : e.cliente_nuevo; e.tel_nuevo = $('#en_tel') ? v('en_tel') : e.tel_nuevo;
  e.fecha_entrega = v('en_fecha'); e.anticipo = v('en_ant'); e.forma_anticipo = v('en_forma'); e.notas = v('en_notas');
  e.items = [...document.querySelectorAll('.en_art')].map((el, i) => {
    const prev = e.items[i] || {}, id = el.value;
    const cant = num(document.querySelectorAll('.en_cant')[i].value) || 1;
    let precio = document.querySelectorAll('.en_pre')[i].value;
    if (id !== prev.articulo_id) precio = id && art(id) ? String(art(id).valor_estimado) : '';   // pieza nueva: precio de lista
    return { articulo_id: id, cantidad: cant, precio_unit: precio };
  });
}
/** Mensaje listo para confirmar el pedido con el cliente por WhatsApp (o copiarlo si no hay teléfono). */
function mensajeCliente(e) {
  const c = cli(e.comprador_id) || {};
  const lineas = e.items.map((i) => `• ${i.cantidad}× ${i.nombre_snap} — ${money(i.cantidad * i.precio_unit)}`);
  const txt = [`Hola ${c.nombre || ''} 👋 Te confirmo tu pedido:`, '', ...lineas, '',
    `Total: ${money(e.total)}${e.anticipo ? ` · Anticipo: ${money(e.anticipo)} · Resta: ${money(e.resta)}` : ''}`,
    `📍 Entrega en Balderas${e.fecha_entrega ? ' el ' + fmtDia(e.fecha_entrega, true) : ''}. ¡Nos vemos!`].join('\n');
  const dig = String(c.tel || '').replace(/\D/g, '');
  if (dig.length >= 10) { window.open(`https://wa.me/${dig.length === 10 ? '52' + dig : dig}?text=${encodeURIComponent(txt)}`, '_blank', 'noopener'); return; }
  const t = document.createElement('textarea'); t.value = txt; document.body.appendChild(t); t.select();
  try { document.execCommand('copy'); toast('Mensaje copiado (el cliente no tiene teléfono guardado)'); } catch (x) { toast('No se pudo copiar', true); }
  t.remove();
}
async function mmTraer() {
  const urls = ($('#mm_txt').value || '').split(/\s+/).map((x) => x.trim()).filter(Boolean);
  ui.mm.texto = $('#mm_txt').value;
  if (!urls.length) { toast('Pega al menos un link', true); return; }
  ui.mm.filas = []; ui.mm.cargando = true; render();
  for (const url of urls) {
    try { const d = await POST('/articulos/desde-mattel', { url }); ui.mm.filas.push({ ok: true, url, cantidad: 1, ...d }); }
    catch (e) { ui.mm.filas.push({ ok: false, url, error: e.message }); }
  }
  ui.mm.cargando = false; render();
}
async function mmGuardar() {
  document.querySelectorAll('.mm_cant').forEach((el) => { ui.mm.filas[num(el.dataset.i)].cantidad = Math.max(1, num(el.value) || 1); });
  document.querySelectorAll('.mm_pre').forEach((el) => { ui.mm.filas[num(el.dataset.i)].precio_mxn = num(el.value); });
  const l = ui.mm.filas.filter((r) => r.ok);
  try {
    await accion(async () => {
      for (const r of l) {
        await POST('/articulos', { tipo: /pok[eé]mon/i.test(r.nombre) ? 'Pokémon' : 'Hot Wheels', nombre: r.nombre, cantidad: r.cantidad,
          precio_compra: r.precio_mxn, valor_estimado: r.precio_mxn, fecha_adq: hoy(), fuente: 'Mattel Creations', ubicacion: 'Por recibir',
          foto: r.imagen || '', notas: `Mattel: ${r.url}\nPrecio en Mattel: US$${r.precio_usd} (TC ${r.tipo_cambio})` });
      }
    }, `${l.length} pieza(s) registradas como Por recibir`);
    ui.mm = null; cerrar();
  } catch (e) { /* error ya reportado */ }
}
async function saveEnc() {
  snapEnc();
  const e = ui.enc;
  const cuerpo = { comprador_id: e.comprador_id || null, cliente_nuevo: e.cliente_nuevo.trim(), tel_nuevo: e.tel_nuevo.trim(),
    fecha_entrega: e.fecha_entrega, anticipo: num(e.anticipo), forma_anticipo: e.forma_anticipo, notas: e.notas.trim(),
    items: e.items.filter((i) => i.articulo_id).map((i) => ({ articulo_id: i.articulo_id, cantidad: num(i.cantidad) || 1, precio_unit: i.precio_unit === '' ? null : num(i.precio_unit) })) };
  if (!cuerpo.comprador_id && !cuerpo.cliente_nuevo) { toast('Elige un cliente o escribe su nombre', true); return; }
  if (!cuerpo.items.length) { toast('Agrega al menos una pieza', true); return; }
  try {
    await accion(() => (e.id ? PUT('/encargos/' + e.id, cuerpo) : POST('/encargos', cuerpo)), e.id ? 'Encargo actualizado' : 'Encargo registrado');
    ui.enc = null; cerrar();
  } catch (x) { /* error ya reportado */ }
}

/* ---------- Inventario ---------- */
function filtrar() {
  const q = ui.q.toLowerCase().trim();
  const l = db.articulos.filter((a) => {
    if (ui.fTipo !== 'todos' && a.tipo !== ui.fTipo) return false;
    if (ui.fEstatus === 'disponible' && (a.estatus === 'Conservar' || libre(a) <= 0)) return false;
    if (ui.fEstatus === 'apartado' && !a.apartadas) return false;
    if (ui.fEstatus === 'conservar' && a.estatus !== 'Conservar') return false;
    if (ui.fEstatus === 'agotado' && num(a.cantidad)) return false;
    if (ui.fEstatus === 'estancado' && !(a.estatus === 'Disponible' && num(a.cantidad) && a.fecha_adq && dias(a.fecha_adq) > db.ajustes.diasEstancado)) return false;
    if (!q) return true;
    return [a.nombre, a.numero, a.ubicacion, a.sub, a.serie, a.expansion, a.color, a.rareza, a.codigo, a.cert].join(' ').toLowerCase().includes(q);
  });
  const o = {
    reciente: (a, b) => (b.creado_en || '').localeCompare(a.creado_en || ''),
    valor: (a, b) => num(b.valor_estimado) - num(a.valor_estimado),
    nombre: (a, b) => a.nombre.localeCompare(b.nombre),
    antiguedad: (a, b) => (a.fecha_adq || '').localeCompare(b.fecha_adq || ''),
  };
  l.sort(o[ui.orden] || o.reciente);
  const col = COLS_INV.find((c) => c.k === ui.colOrd);
  if (ui.modoInv === 'lista' && col) {
    l.sort((a, b) => ui.colDir * (col.txt ? String(col.v(a)).localeCompare(String(col.v(b)), 'es', { numeric: true }) : num(col.v(a)) - num(col.v(b))));
  }
  return l;
}
/* Columnas de la vista de lista (hoja de cálculo). txt = se ordena como texto. */
const COLS_INV = [
  { k: 'nombre', t: 'Pieza', txt: 1, v: (a) => a.nombre || '' },
  { k: 'tipo', t: 'Tipo', txt: 1, v: (a) => a.tipo || '' },
  { k: 'numero', t: 'Número', txt: 1, v: (a) => a.numero || '' },
  { k: 'anio', t: 'Año', v: (a) => a.anio || 0 },
  { k: 'detalle', t: 'Serie / Expansión', txt: 1, v: (a) => (a.tipo === 'Hot Wheels' ? a.serie : a.expansion) || '' },
  { k: 'variante', t: 'Color / Rareza', txt: 1, v: (a) => (a.tipo === 'Hot Wheels' ? a.color : a.rareza) || '' },
  { k: 'cantidad', t: 'Cant.', num: 1, v: (a) => num(a.cantidad) },
  { k: 'estatus', t: 'Estatus', txt: 1, v: (a) => semaforo(a).t },
  { k: 'ubicacion', t: 'Ubicación', txt: 1, v: (a) => a.ubicacion || '' },
  { k: 'compra', t: 'Compra', num: 1, v: (a) => num(a.precio_compra) },
  { k: 'valor', t: 'Valor', num: 1, v: (a) => num(a.valor_estimado) },
  { k: 'dif', t: 'Dif.', num: 1, v: (a) => num(a.valor_estimado) - num(a.precio_compra) },
  { k: 'fecha', t: 'Adquirida', txt: 1, v: (a) => a.fecha_adq || '' },
  { k: 'reserva', t: 'Apartada para', txt: 1, v: (a) => reservasTxt(a) },
];
function tablaInv(l) {
  const flecha = (c) => (ui.colOrd === c.k ? (ui.colDir > 0 ? ' ▲' : ' ▼') : '');
  return `<div class="pnl wrap hoja" style="padding:0"><table class="tbl hoja-t"><thead><tr>
    <th class="rn">#</th>${COLS_INV.map((c) => `<th class="${c.num ? 'num' : ''} ord" data-a="ordcol" data-v="${c.k}" title="Ordenar por ${c.t}">${c.t}${flecha(c)}</th>`).join('')}</tr></thead><tbody>
    ${l.map((a, i) => {
      const s = semaforo(a), dif = num(a.valor_estimado) - num(a.precio_compra), ago = !num(a.cantidad);
      return `<tr class="${ui.sel.includes(a.id) ? 'sel2' : ''} ${ago ? 'sold' : ''}" data-a="ver" data-id="${a.id}">
      <td class="rn">${i + 1}</td>
      <td><b>${a.grail ? '👑 ' : ''}${esc(a.nombre)}</b></td><td>${esc(a.tipo)}</td><td class="mn">${esc(a.numero || '')}</td>
      <td class="mn">${esc(a.anio || '')}</td><td>${esc(COLS_INV[4].v(a))}</td><td>${esc(COLS_INV[5].v(a))}</td>
      <td class="num">${num(a.cantidad)}${a.apartadas ? ` <span class="mu">(${a.apartadas} ap.)</span>` : ''}</td>
      <td><span class="dt" style="background:${s.col}"></span>${s.t}</td><td>${esc(a.ubicacion || '—')}</td>
      <td class="num">${money(a.precio_compra)}</td><td class="num"><b>${money(a.valor_estimado)}</b></td>
      <td class="num ${dif >= 0 ? 'pos' : 'neg'}">${dif >= 0 ? '+' : ''}${money(dif)}</td>
      <td class="mn">${esc(a.fecha_adq || '')}</td><td style="font-size:12px">${esc(reservasTxt(a))}</td></tr>`; }).join('')}
    </tbody><tfoot><tr><td class="rn"></td><td colspan="9"><b>Total (${l.length} filas)</b></td>
      <td class="num">${money(suma(l, (a) => num(a.precio_compra) * num(a.cantidad)))}</td>
      <td class="num">${money(suma(l, (a) => num(a.valor_estimado) * num(a.cantidad)))}</td><td></td><td></td><td></td></tr></tfoot></table></div>`;
}
function vInv() {
  const l = filtrar();
  const tipos = [['todos', 'Ambas'], ['Hot Wheels', 'Hot Wheels'], ['Pokémon', 'Pokémon']];
  const est = [['todos', 'Todo'], ['disponible', 'Disponibles'], ['apartado', 'Apartadas'], ['estancado', 'Estancadas'], ['conservar', 'Conservar'], ['agotado', 'Agotadas']];
  return hdr('Inventario', `${l.length} de ${db.articulos.length} piezas${ui.sel.length ? ` · ${ui.sel.length} seleccionadas` : ''}`) + `
  <div class="chips">
    ${tipos.map((t) => `<button class="chip ${ui.fTipo === t[0] ? 'on' : ''}" data-a="ftipo" data-v="${t[0]}">${t[1]}</button>`).join('')}
    <span style="width:1px;height:22px;background:var(--line2)"></span>
    <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted)">Estatus
      <select class="sel" data-a="festatus_sel" style="width:auto;padding:7px 32px 7px 12px;font-size:12.5px">
        ${est.map((c) => `<option value="${c[0]}" ${ui.fEstatus === c[0] ? 'selected' : ''}>${c[1]}</option>`).join('')}
      </select></label>
    <span style="width:1px;height:22px;background:var(--line2)"></span>
    <button class="chip ${ui.selMode ? 'on' : ''}" data-a="selmode">☑ Seleccionar varias</button>
    <span style="width:1px;height:22px;background:var(--line2)"></span>
    <button class="chip ${ui.modoInv === 'fichas' ? 'on' : ''}" data-a="modoinv" data-v="fichas" title="Ver como fichas">▦ Fichas</button>
    <button class="chip ${ui.modoInv === 'lista' ? 'on' : ''}" data-a="modoinv" data-v="lista" title="Ver como hoja de cálculo">☰ Lista</button>
    <select class="sel" data-a="orden" style="width:auto;margin-left:auto;padding:7px 32px 7px 12px;font-size:12.5px">
      ${[['reciente', 'Más recientes'], ['valor', 'Mayor valor'], ['nombre', 'A–Z'], ['antiguedad', 'Más tiempo guardadas']].map((o) => `<option value="${o[0]}" ${ui.orden === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}
    </select></div>
  ${ui.selMode && !ui.sel.length ? `<div class="note" style="margin-top:0">Toca las piezas que quieras agrupar. Con dos o más puedes venderlas como lote o usarlas en un intercambio.</div>` : ''}
  ${ui.sel.length ? `<div class="pnl" style="margin-bottom:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:13px 16px">
    <b>${ui.sel.length} piezas seleccionadas</b>
    <span style="font-size:12.5px;color:var(--muted)">Valor de mercado ${money(suma(ui.sel.map(art).filter(Boolean), (a) => a.valor_estimado))}</span>
    <span style="flex:1"></span>
    <button class="btn pri sm" data-a="lote">Vender como lote</button>
    <button class="btn sm" data-a="tradeSel">Usar en intercambio</button>
    <button class="btn sm" data-a="publote">Publicar en lote</button>
    <button class="btn gh sm" data-a="limpiarsel">Quitar selección</button></div>` : ''}
  ${l.length ? (ui.modoInv === 'lista' ? tablaInv(l) : `<div class="rack">${l.map(ficha).join('')}</div>`)
    : vacio('🔍', 'Nada coincide con ese filtro', 'Cambia los filtros o registra la pieza que buscas.', '<button class="btn pri" data-a="nuevo">Registrar pieza</button>')}`;
}
function ficha(a) {
  const s = semaforo(a), t = tono(a.tipo), ago = !num(a.cantidad);
  const det = a.tipo === 'Hot Wheels' ? [a.serie, a.color].filter(Boolean).join(' · ') : [a.expansion, a.rareza].filter(Boolean).join(' · ');
  const dif = num(a.valor_estimado) - num(a.precio_compra);
  const tr = tendencia(a);
  return `<div class="pc ${ago ? 'sold' : ''} ${ui.sel.includes(a.id) ? 'sel2' : ''}" style="--tone:${t}" data-a="ver" data-id="${a.id}">
    <div class="strip"></div>${ago ? '<div class="rb">Vendida</div>' : (a.apartadas ? '<div class="rb ap">Apartada</div>' : '')}
    ${a.grail ? '<div class="crown" title="Pieza grial">👑</div>' : ''}
    <div class="ph">${imgFoto(a, 'loading="lazy"')}</div>
    <div class="bd">
      <div class="eb">${esc([a.numero, a.anio, det].filter(Boolean).join(' · ') || a.tipo)}</div>
      <div class="nm">${esc(a.nombre)}</div>
      <div class="row"><span><span class="dt" style="background:${s.col}"></span><span class="mu">${s.t}${num(a.cantidad) > 1 ? ' ×' + a.cantidad : ''}</span></span>
        <b class="mn" style="color:${t}">${money(a.valor_estimado)}</b></div>
      ${a.apartadas ? `<div class="mu" style="margin-top:5px;font-size:11px;color:var(--yellow)">${esc(reservasTxt(a))}</div>` : ''}
      <div class="row" style="margin-top:6px"><span class="mu">${esc(a.ubicacion || 'Sin ubicar')}</span>
        <span class="mu mn ${dif >= 0 ? 'pos' : 'neg'}">${dif >= 0 ? '+' : ''}${money(dif)}</span></div>
      ${tr ? chispa(tr.pts, tr.delta >= 0 ? 'var(--green)' : 'var(--red)') : ''}
    </div></div>`;
}

/* ---------- Modo bazar ---------- */
function vBazar() {
  const l = db.articulos.filter((a) => libre(a) > 0 && a.estatus !== 'Conservar')
    .filter((a) => !ui.q || [a.nombre, a.numero, a.codigo].join(' ').toLowerCase().includes(ui.q.toLowerCase()));
  const hoyV = db.ventas.filter((v) => v.fecha === hoy());
  return hdr('Modo bazar', 'Toca una pieza y se vende al precio de lista',
    `<div class="srch"><input class="in" placeholder="Busca o escanea…" value="${esc(ui.q)}" data-a="q"></div>
     <button class="btn gh sm" data-a="escanear">⌗ Escanear</button>`) + `
  <div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))">
    ${kpi('Ventas de hoy', hoyV.length, 'toques registrados', 'var(--blue)')}
    ${kpi('Cobrado hoy', money(suma(hoyV, (v) => v.precio)), 'antes de costos', 'var(--yellow)')}
    ${kpi('Neto de hoy', money(suma(hoyV, (v) => v.neto)), 'ya con comisiones', 'var(--green)')}
  </div>
  <div class="note w"><b>Cómo funciona:</b> un toque abre el cobro con el precio de lista ya puesto y el canal en Bazar. Confirmas y listo, sin formularios largos.</div>
  ${l.length ? `<div class="rack" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">
    ${l.map((a) => `<div class="pc" style="--tone:${tono(a.tipo)}" data-a="bazarvender" data-id="${a.id}">
      <div class="strip"></div>
      <div class="ph" style="height:88px">${imgFoto(a)}</div>
      <div class="bd" style="padding:11px">
        <div class="nm" style="font-size:13px;margin-bottom:6px">${esc(a.nombre)}</div>
        <div class="row"><span class="mu">${libre(a)} disp.</span>
          <b class="mn" style="font-size:15px;color:${tono(a.tipo)}">${money(a.valor_estimado)}</b></div>
      </div></div>`).join('')}</div>`
    : vacio('⚡', 'Nada disponible para vender', 'Todas tus piezas están apartadas, agotadas o marcadas como conservar.', '')}`;
}

/* ---------- Ventas ---------- */
function vVentas() {
  const l = db.ventas;
  return hdr('Ventas', `${l.length} transacciones · ${money(suma(l, (v) => v.neto))} netos`,
    `<button class="btn gh sm" data-a="csvventas">Exportar CSV</button>`) +
  (l.length ? `<div class="pnl wrap" style="padding:16px 6px"><table class="tbl"><thead><tr>
    <th>Pieza</th><th>Fecha</th><th>Canal</th><th>Comprador</th><th class="num">Cobrado</th><th class="num">Comisión</th>
    <th class="num">Retención</th><th class="num">Envío</th><th class="num">Neto</th><th>Envío</th><th></th></tr></thead><tbody>
    ${l.map((v) => { const com = num(v.com_fija) + num(v.precio) * num(v.com_pct), ret = num(v.precio) * num(v.ret_pct);
      return `<tr><td><b>${esc(v.nombre_snap)}</b>
      <div style="font-size:11px;color:var(--muted)">${v.cantidad > 1 ? '×' + v.cantidad + ' · ' : ''}${v.lote_id ? '<span class="tag b">Lote</span> ' : ''}${num(v.anticipo_aplicado) ? '<span class="tag y">Apartado liquidado</span> ' : ''}${esc(v.id)}</div></td>
      <td class="mn" style="font-size:12.5px">${v.fecha}</td><td>${esc(v.plataforma_snap || plat(v.id_plataforma).nombre)}</td>
      <td>${esc(cli(v.id_comprador) ? cli(v.id_comprador).nombre : '—')}</td>
      <td class="num">${money(v.precio)}</td><td class="num" style="color:var(--muted)">${com ? '−' + money(com) : '—'}</td>
      <td class="num" style="color:var(--muted)">${ret ? '−' + money(ret) : '—'}</td>
      <td class="num" style="color:var(--muted)">${num(v.envio) ? '−' + money(v.envio) : '—'}</td>
      <td class="num ${v.neto >= 0 ? 'pos' : 'neg'}"><b>${money(v.neto)}</b></td>
      <td><select class="sel" data-a="envio" data-id="${v.id}" style="width:auto;padding:5px 28px 5px 9px;font-size:11.5px">
        ${['Sin envío', 'Pendiente', 'Enviado', 'Entregado'].map((e) => `<option ${v.estatus_envio === e ? 'selected' : ''}>${e}</option>`).join('')}</select></td>
      <td><button class="btn sm gh" data-a="delventa" data-id="${v.id}" title="Cancelar venta y devolver stock">✕</button></td></tr>`; }).join('')}
    </tbody></table></div>
    <div class="note">Cancelar una venta devuelve la pieza al inventario automáticamente.</div>`
    : vacio('⇄', 'Aún no registras ventas', 'Abre una pieza del inventario y usa Registrar venta. La ganancia neta la calcula la base de datos.',
      '<button class="btn pri" data-a="nav" data-v="inventario">Ir al inventario</button>'));
}

/* ---------- Apartados ---------- */
function vApart() {
  const l = db.apartados;
  const vig = l.filter((x) => x.estatus === 'Vigente');
  return hdr('Apartados', `${vig.length} vigentes · ${money(suma(vig, (x) => x.anticipo))} en anticipos`,
    `<button class="btn pri" data-a="nuevoapartado">+ Nuevo apartado</button>`) +
  (l.length ? `<div class="pnl wrap" style="padding:16px 6px"><table class="tbl"><thead><tr>
    <th>Pieza</th><th>Cliente</th><th>Entrega en</th><th class="num">Acordado</th><th class="num">Anticipo</th><th class="num">Resta</th>
    <th>Límite</th><th>Estatus</th><th></th></tr></thead><tbody>
    ${l.map((x) => { const resta = num(x.precio_acordado) - num(x.anticipo);
      const vence = x.estatus === 'Vigente' && x.fecha_limite && x.fecha_limite >= hoy()
        ? Math.round((new Date(x.fecha_limite) - new Date(hoy())) / 864e5) : null;
      const est = { Vigente: 'g', Liquidado: 'b', Vencido: 'r', Cancelado: '' }[x.estatus] || '';
      return `<tr><td><b>${esc(x.nombre_snap)}</b><div style="font-size:11px;color:var(--muted)">×${x.cantidad}${x.notas ? ' · ' + esc(x.notas) : ''}</div></td>
      <td><b>${esc(cli(x.id_comprador) ? cli(x.id_comprador).nombre : (x.cliente_snap || '—'))}</b></td>
      <td style="font-size:12.5px">${esc(x.lugar_entrega || 'Balderas')}</td>
      <td class="num">${money(x.precio_acordado)}</td><td class="num" style="color:var(--yellow)">${money(x.anticipo)}</td>
      <td class="num"><b>${money(resta)}</b></td>
      <td class="mn" style="font-size:12.5px">${x.fecha_limite || '—'}${vence !== null && vence <= 3 ? `<div style="color:var(--red);font-size:11px">vence en ${vence} d</div>` : ''}</td>
      <td><span class="tag ${est}">${x.estatus}</span></td>
      <td style="text-align:right;white-space:nowrap">
        ${x.estatus === 'Vigente' || x.estatus === 'Vencido' ? `<button class="btn sm grn" data-a="liquidar" data-id="${x.id}">Liquidar</button>
        <button class="btn sm gh" data-a="cancelapartado" data-id="${x.id}">Cancelar</button>` : ''}</td></tr>`; }).join('')}
    </tbody></table></div>
    <div class="note"><b>Cómo funciona el anticipo:</b> la pieza queda bloqueada en la base de datos y el servidor rechaza cualquier intento de venderla por otro lado. Al liquidar, el anticipo ya cobrado queda registrado en la venta. Si vence la fecha, el apartado pasa a Vencido solo.</div>`
    : vacio('⏳', 'Sin apartados activos', 'Cuando alguien te deje un anticipo, regístralo aquí: la pieza se bloquea y no la vendes dos veces por error.',
      '<button class="btn pri" data-a="nuevoapartado">Registrar apartado</button>'));
}

/* ---------- Intercambios ---------- */
function vTrade() {
  const l = db.intercambios;
  return hdr('Intercambios', `${l.length} cambios · balance ${money(suma(l, (x) => x.diferencia))}`,
    `<button class="btn pri" data-a="nuevotrade">+ Registrar intercambio</button>`) +
  (l.length ? l.map((x) => `<div class="pnl" style="margin-bottom:12px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <b style="font-size:15px">${esc(x.contraparte || 'Sin nombre')}</b><span class="tag">${x.fecha}</span>
      <span style="flex:1"></span>
      <span class="mn" style="font-size:15px;font-weight:700;color:${num(x.diferencia) >= 0 ? 'var(--green)' : 'var(--red)'}">
        ${num(x.diferencia) >= 0 ? 'Ganaste ' : 'Perdiste '}${money(Math.abs(x.diferencia))} de valor</span>
      <button class="btn sm gh" data-a="deltrade" data-id="${x.id}">✕</button></div>
    <div class="g2">
      <div><div class="lbl">Entregaste — ${money(suma(x.entregados, (e) => e.valor))}</div>
        ${x.entregados.map((e) => `<div class="fi" style="margin-bottom:6px"><span class="dot" style="background:var(--red);--dc:var(--red)"></span>
          <span class="tx"><b>${esc(e.nombre)}</b></span><span class="am">${money(e.valor)}</span></div>`).join('') || '<span style="color:var(--muted);font-size:12.5px">Nada</span>'}</div>
      <div><div class="lbl">Recibiste — ${money(suma(x.recibidos, (e) => e.valor))}</div>
        ${x.recibidos.map((e) => `<div class="fi" style="margin-bottom:6px"><span class="dot" style="background:var(--green);--dc:var(--green)"></span>
          <span class="tx"><b>${esc(e.nombre)}</b><span>${esc(e.tipo)}</span></span><span class="am">${money(e.valor)}</span></div>`).join('') || '<span style="color:var(--muted);font-size:12.5px">Nada</span>'}</div>
    </div>${x.notas ? `<div class="note" style="margin-bottom:0">${esc(x.notas)}</div>` : ''}</div>`).join('')
    : vacio('⇌', 'Sin intercambios registrados', 'Un cambio no mueve dinero pero sí valor. Si entregas una pieza de $800 por una de $400, esa pérdida hoy sería invisible.',
      '<button class="btn pri" data-a="nuevotrade">Registrar intercambio</button>'));
}

/* ---------- Compradores ---------- */
function vComp() {
  const r = db.compradores.map((c) => {
    const vs = db.ventas.filter((v) => v.id_comprador === c.id);
    return { c, n: vs.length, total: suma(vs, (v) => v.precio), ult: vs.map((v) => v.fecha).sort().pop(),
      ap: db.apartados.filter((x) => x.id_comprador === c.id && x.estatus === 'Vigente').length };
  }).sort((a, b) => b.total - a.total);
  return hdr('Compradores', 'A quién le avisas primero', `<button class="btn pri" data-a="nuevocomp">+ Agregar comprador</button>`) +
  (r.length ? `<div class="pnl wrap" style="padding:16px 6px"><table class="tbl"><thead><tr>
    <th>Cliente</th><th>Le interesa</th><th>Contacto</th><th class="num">Compras</th><th class="num">Gastado</th><th>Última</th><th></th></tr></thead><tbody>
    ${r.map((x) => `<tr><td><b>${esc(x.c.nombre)}</b>${x.total > 2000 ? ' <span class="tag y">VIP</span>' : ''}${x.ap ? ` <span class="tag b">${x.ap} apartado</span>` : ''}
      <div style="font-size:11.5px;color:var(--muted)">${esc(x.c.notas || '')}</div></td>
      <td><span class="tag">${esc(x.c.interes)}</span></td><td class="mn" style="font-size:12.5px">${esc(x.c.tel || '—')}</td>
      <td class="num">${x.n}</td><td class="num">${money(x.total)}</td>
      <td class="mn" style="font-size:12.5px;color:var(--muted)">${x.ult || '—'}</td>
      <td style="text-align:right"><button class="btn sm gh" data-a="editcomp" data-id="${x.c.id}">Editar</button></td></tr>`).join('')}
    </tbody></table></div>`
    : vacio('☺', 'Sin clientes registrados', 'Guarda a quien te compra. Cuando llegue una pieza de su interés sabrás a quién escribirle antes de publicarla.',
      '<button class="btn pri" data-a="nuevocomp">Agregar comprador</button>')) + vPedidos();
}
function vPedidos() {
  const l = db.pedidos || [];
  return `<div class="sec" style="margin-top:22px"><h2>Lista de espera</h2><span class="ln"></span>
    <button class="btn sm pri" data-a="nuevoped">+ Pedido de cliente</button></div>
  ${l.length ? `<div class="pnl wrap" style="padding:6px"><table class="tbl"><tbody>${l.map((p) => `<tr class="${p.atendido ? 'sold' : ''}"><td><b>${esc(p.descripcion)}</b>
    <div style="font-size:11.5px;color:var(--muted)">${cli(p.comprador_id) ? esc(cli(p.comprador_id).nombre) : 'Sin cliente'}${cli(p.comprador_id) && cli(p.comprador_id).tel ? ' · ' + esc(cli(p.comprador_id).tel) : ''}${num(p.tope) ? ' · hasta ' + money(p.tope) : ''} · ${esc((p.creado_en || '').slice(0, 10))}</div></td>
    <td style="text-align:right;white-space:nowrap">${p.atendido ? `<button class="btn sm gh" data-a="pedok" data-id="${p.id}" data-v="0">Reabrir</button>` : `<button class="btn sm grn" data-a="pedok" data-id="${p.id}" data-v="1">Atendido</button>`}
    <button class="btn sm gh" data-a="delped" data-id="${p.id}">✕</button></td></tr>`).join('')}</tbody></table></div>`
    : '<p style="color:var(--muted);font-size:13px">Cuando un cliente te pida algo que no tienes, anótalo aquí: al registrar o abrir una pieza parecida verás a quién avisarle.</p>'}`;
}

/* ---------- Faltantes ---------- */
function vWish() {
  const l = db.wishlist;
  return hdr('Faltantes', `${l.length} piezas buscadas · presupuesto ${money(suma(l, (w) => w.tope))}`,
    `<button class="btn pri" data-a="nuevowish">+ Agregar faltante</button>`) +
  (l.length ? `<div class="pnl wrap" style="padding:16px 6px"><table class="tbl"><thead><tr>
    <th>Pieza buscada</th><th>Colección</th><th class="num">Precio tope</th><th>Prioridad</th><th></th></tr></thead><tbody>
    ${l.map((w) => `<tr><td><b>${esc(w.nombre)}</b><div style="font-size:11.5px;color:var(--muted)">${esc(w.detalle || '')}</div></td>
      <td><span class="tag" style="color:${tono(w.tipo)};border-color:${tono(w.tipo)}">${esc(w.tipo)}</span></td>
      <td class="num">${money(w.tope)}</td><td style="color:var(--yellow)">${'★'.repeat(num(w.prioridad)) || '—'}</td>
      <td style="text-align:right;white-space:nowrap"><button class="btn sm grn" data-a="wish2art" data-id="${w.id}">La conseguí</button>
      <button class="btn sm gh" data-a="delwish" data-id="${w.id}">✕</button></td></tr>`).join('')}
    </tbody></table></div>`
    : vacio('★', 'Sin faltantes anotados', 'En un bazar decides en veinte segundos. Anota qué persigues y cuánto es lo máximo que pagas.',
      '<button class="btn pri" data-a="nuevowish">Agregar faltante</button>'));
}

/* ---------- Plataformas ---------- */
function vPlat() {
  return hdr('Plataformas', 'Lo que se queda cada canal', `<button class="btn pri" data-a="nuevoplat">+ Agregar canal</button>`) + `
  <div class="pnl wrap" style="padding:16px 6px"><table class="tbl"><thead><tr>
    <th>Canal</th><th>Código</th><th class="num">Comisión</th><th class="num">Cuota fija</th><th class="num">Retención fiscal</th>
    <th>Nota</th><th class="num">De $500 recibes</th><th></th></tr></thead><tbody>
    ${db.plataformas.map((p) => `<tr><td><b>${esc(p.nombre)}</b></td><td class="mn">${esc(p.codigo)}</td>
      <td class="num">${pct(p.com_pct)}</td><td class="num">${money(p.com_fija)}</td>
      <td class="num">${num(p.ret_pct) ? pct(p.ret_pct) : '—'}</td>
      <td style="font-size:12px;color:var(--muted);max-width:250px">${esc(p.notas || '')}</td>
      <td class="num"><b>${money(500 - 500 * num(p.com_pct) - 500 * num(p.ret_pct) - num(p.com_fija))}</b></td>
      <td style="text-align:right"><button class="btn sm gh" data-a="editplat" data-id="${p.id}">Editar</button></td></tr>`).join('')}
  </tbody></table></div>
  <div class="note"><b>Las ventas ya registradas no se recalculan.</b> Cada venta congela en la base de datos la comisión y la retención que pagaste ese día, así que puedes actualizar tarifas sin distorsionar tu historial.</div>
  <div class="note w"><b>Retención fiscal:</b> en México las plataformas retienen ISR e IVA y lo reportan al SAT. Al capturar ese porcentaje aquí, tu ganancia neta es la real. Las tasas dependen de tu régimen, conviene confirmarlas con un contador.</div>`;
}

/* ---------- Etiquetas QR ---------- */
function vQR() {
  const ubis = {};
  db.articulos.forEach((a) => { const u = a.ubicacion || 'Sin ubicar';
    if (!ubis[u]) ubis[u] = { n: 0, v: 0 };
    ubis[u].n += num(a.cantidad); ubis[u].v += num(a.valor_estimado) * num(a.cantidad); });
  const ls = Object.entries(ubis).sort((a, b) => b[1].v - a[1].v);
  return hdr('Etiquetas QR', 'Un código por caja para no vaciarla al buscar',
    `<button class="btn gh sm" data-a="imprimir">Imprimir</button>`) + `
  <div class="note noprint"><b>Cómo usarlo:</b> imprime y pega una etiqueta en cada caja, vitrina o carpeta. Al escanearla con la cámara del celular, el texto te dice qué ubicación es; búscala en el inventario y ves todo lo que hay dentro sin abrirla.</div>
  ${ls.length ? `<div class="lblsheet" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px">
    ${ls.map(([u, d], i) => `<div class="lblcard"><div class="qrbox" id="qr${i}" data-txt="${esc(u)}"></div>
      <div class="tx"><b>${esc(u)}</b><span>${d.n} piezas · ${money(d.v)}</span>
      <span style="display:block;margin-top:4px;font-family:var(--m);font-size:10px">CH·${esc(u).toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10)}</span></div></div>`).join('')}
  </div>` : vacio('▩', 'Sin ubicaciones registradas', 'Escribe la ubicación física de tus piezas (Caja A, Vitrina 2, Carpeta azul) y aquí aparecerá una etiqueta por cada una.', '')}`;
}
function pintarQR() {
  $$('.qrbox').forEach((b) => {
    const t = b.dataset.txt; b.innerHTML = '';
    if (window.QRCode) {
      try { new window.QRCode(b, { text: 'Chicos Wheels · ' + t, width: 78, height: 78, colorDark: '#0A1120', colorLight: '#ffffff', correctLevel: window.QRCode.CorrectLevel.M }); return; } catch (e) { /* sin red */ }
    }
    b.innerHTML = `<div style="width:78px;height:78px;display:grid;place-items:center;border:2px dashed #999;border-radius:6px;font-size:9px;color:#555;text-align:center;padding:4px">${esc(t)}</div>`;
  });
}

/* ---------- Datos ---------- */
function vDatos() {
  const s = stats();
  const temaActual = temaGuardado();
  return hdr('Datos', 'Respaldo y ajustes', '') + `
  <div class="g3">
    <div class="pnl"><h2>Ajustes</h2>
      <div class="fld"><label class="lbl">Moneda</label>
        <select class="sel" data-a="set" data-k="moneda">${['MXN', 'USD', 'EUR', 'COP', 'ARS', 'CLP', 'PEN'].map((m) => `<option ${db.ajustes.moneda === m ? 'selected' : ''}>${m}</option>`).join('')}</select></div>
      <div class="fld"><label class="lbl">Meta de ganancia mensual</label>
        <input class="in" type="number" value="${db.ajustes.metaMensual}" data-a="set" data-k="meta_mensual"></div>
      <div class="fld"><label class="lbl">Una pieza se considera estancada después de (días)</label>
        <input class="in" type="number" value="${db.ajustes.diasEstancado}" data-a="set" data-k="dias_estancado"></div>
    </div>
    <div class="pnl"><h2>Respaldo e importación</h2>
      <p style="font-size:12.5px;color:var(--muted);margin-bottom:15px">Tus datos viven en la base de datos del servidor. Descarga un respaldo antes de migrar o actualizar.</p>
      <div style="display:flex;gap:9px;flex-wrap:wrap">
        <button class="btn pri" data-a="export">Descargar respaldo</button>
        <button class="btn" data-a="csv">Inventario en CSV</button>
      </div>

      <div style="margin-top:18px;padding-top:16px;border-top:1px solid var(--line)">
        <p style="font-size:12.5px;color:var(--muted);margin-bottom:11px">Da de alta varias piezas de un jalón: descarga la plantilla, llénala y súbela de vuelta.</p>
        <div style="display:flex;gap:9px;flex-wrap:wrap">
          <a class="btn gh" href="/plantilla-inventario.xlsx" download>📥 Descargar plantilla (.xlsx)</a>
          <label class="btn" for="archivo_importar" style="cursor:pointer">📤 Importar desde Excel</label>
          <input type="file" id="archivo_importar" data-a="importar" accept=".xlsx" style="display:none">
        </div>
      </div>

      <div style="margin-top:18px;padding-top:16px;border-top:1px solid var(--line);display:flex;gap:9px;flex-wrap:wrap">
        <button class="btn gh" data-a="demo">Cargar datos de ejemplo</button>
        <button class="btn dgr" data-a="wipe">Borrar todo</button></div>
      <div class="mn" style="font-size:11.5px;color:var(--muted);margin-top:16px;line-height:1.8">
        ${db.articulos.length} artículos · ${db.ventas.length} ventas · ${db.apartados.length} apartados<br>
        ${db.intercambios.length} intercambios · ${db.compradores.length} clientes · ${s.piezas} piezas físicas</div>
    </div>
    <div class="pnl"><h2>Reporte en PDF</h2>
      <p style="font-size:12.5px;color:var(--muted);margin-bottom:12px">Elige qué incluir y filtra por categoría o estatus. Se recuerda tu configuración.</p>
      <div class="fld"><label class="lbl">Título</label><input class="in" data-a="repcfg" data-k="titulo" maxlength="80" value="${esc(ui.rep.titulo)}"></div>
      <div class="fld"><label class="lbl">Secciones</label><div class="chips">
        ${[['resumen', 'Resumen'], ['inventario', 'Inventario'], ['ventas', 'Ventas'], ['apartados', 'Apartados']].map((x) => `<button class="chip ${ui.rep.secciones.includes(x[0]) ? 'on' : ''}" data-a="repsec" data-v="${x[0]}">${x[1]}</button>`).join('')}</div></div>
      <div class="g2">
        <div class="fld"><label class="lbl">Categoría</label><select class="sel" data-a="repcfg" data-k="tipo">
          ${[['todos', 'Ambas'], ['Hot Wheels', 'Hot Wheels'], ['Pokémon', 'Pokémon']].map((o) => `<option value="${o[0]}" ${ui.rep.tipo === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></div>
        <div class="fld"><label class="lbl">Estatus</label><select class="sel" data-a="repcfg" data-k="estatus">
          ${[['todos', 'Todos'], ['disponible', 'Disponibles'], ['apartado', 'Apartadas'], ['estancado', 'Estancadas'], ['conservar', 'Conservar'], ['agotado', 'Agotadas']].map((o) => `<option value="${o[0]}" ${ui.rep.estatus === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></div>
      </div>
      <div class="g2">
        <div class="fld"><label class="lbl">Ordenar inventario</label><select class="sel" data-a="repcfg" data-k="orden">
          ${[['nombre', 'A–Z'], ['valor', 'Mayor valor'], ['reciente', 'Más recientes'], ['antiguedad', 'Más antiguas']].map((o) => `<option value="${o[0]}" ${ui.rep.orden === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></div>
        <div class="fld"><label class="lbl">Orientación</label><select class="sel" data-a="repcfg" data-k="orientacion">
          ${[['vertical', 'Vertical'], ['horizontal', 'Horizontal']].map((o) => `<option value="${o[0]}" ${ui.rep.orientacion === o[0] ? 'selected' : ''}>${o[1]}</option>`).join('')}</select></div>
      </div>
      <div class="g2">
        <div class="fld"><label class="lbl">Ventas desde</label><input class="in" type="date" data-a="repcfg" data-k="desde" value="${esc(ui.rep.desde)}"></div>
        <div class="fld"><label class="lbl">Ventas hasta</label><input class="in" type="date" data-a="repcfg" data-k="hasta" value="${esc(ui.rep.hasta)}"></div>
      </div>
      <label class="chk" style="margin-bottom:12px"><input type="checkbox" data-a="repcfg" data-k="solo_con_valor" ${ui.rep.solo_con_valor ? 'checked' : ''}> Ocultar piezas sin precio de mercado</label>
      <button class="btn pri" data-a="reportepdf" style="width:100%">📄 Generar PDF</button>
    </div>
    <div class="pnl"><h2>Apariencia</h2>
      <p style="font-size:12.5px;color:var(--muted);margin-bottom:12px">Elige la paleta de colores. Se guarda en este dispositivo.</p>
      <div class="themes">${TEMAS.map((t) => `
        <button class="tcard ${temaActual === t.id ? 'on' : ''}" data-a="tema" data-t="${t.id}">
          <h5>${t.nombre}</h5><p>${t.descripcion}</p>
          <div class="sw">${t.muestra.map((c) => `<i style="background:${c}"></i>`).join('')}</div>
        </button>`).join('')}</div>
    </div>
  </div>`;
}

/* ==================== Modales ==================== */
const MOD = {};
function shell(t, sub, body, foot, w) {
  return `<div class="md" ${w ? `style="max-width:${w}"` : ''} role="dialog" aria-modal="true"><header><h3>${t}</h3>
    ${sub ? `<span class="sub">${esc(sub)}</span>` : ''}<button class="btn sm gh" data-a="cerrar" aria-label="Cerrar">✕</button></header>
    <div class="bdy">${body}</div><footer>${foot}</footer></div>`;
}
const f = (l, inner, hint) => `<div class="fld"><label class="lbl">${l}</label>${inner}${hint ? `<div style="font-size:11.5px;color:var(--muted);margin-top:5px">${hint}</div>` : ''}</div>`;
const inp = (id, v, t, ph) => `<input class="in" id="${id}" type="${t || 'text'}" value="${esc(v == null ? '' : v)}" placeholder="${ph || ''}" ${t === 'number' ? 'step="0.01"' : ''}>`;
const sel = (id, v, o) => `<select class="sel" id="${id}">${o.map((x) => `<option ${x === v ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
const selC = (id, v) => `<select class="sel" id="${id}"><option value="">Sin registrar</option>${db.compradores.map((c) => `<option value="${c.id}" ${v === c.id ? 'selected' : ''}>${esc(c.nombre)}</option>`).join('')}</select>`;
const selP = (id, extra) => `<select class="sel" id="${id}" ${extra || ''}>${db.plataformas.map((p) => `<option value="${p.id}">${esc(p.nombre)} — ${pct(p.com_pct)}${num(p.com_fija) ? ' + ' + money(p.com_fija) : ''}</option>`).join('')}</select>`;

MOD.pieza = function () {
  const a = ui.ctx || {}, t = ui.formTipo, ed = !!a.id;
  return shell(ed ? 'Editar pieza' : '¿Qué vas a registrar hoy?', ed ? a.id : '', `
  ${ui.avisoIA || ''}
  ${ed ? '' : `<div class="seg" style="margin-bottom:18px">
    <button data-a="tipo" data-t="Hot Wheels" class="${t === 'Hot Wheels' ? 'on' : ''}">🏎️ Hot Wheels</button>
    <button data-a="tipo" data-t="Pokémon" class="${t === 'Pokémon' ? 'on y' : ''}">🃏 Pokémon</button></div>`}
  ${ed || t === 'Pokémon' ? '' : f('¿La compraste en Mattel? Pega su link', `<div style="display:flex;gap:8px">${inp('f_mattel', '', 'url', 'https://creations.mattel.com/products/…')}
    <button class="btn" data-a="mattel" style="flex:0 0 auto">Traer datos</button></div>`, 'Llena nombre, foto y precio (convertido a pesos). Revisa lo que traiga antes de guardar.')}
  ${f(t === 'Pokémon' ? 'Nombre de la carta' : 'Nombre del modelo', inp('f_nombre', a.nombre, 'text', t === 'Pokémon' ? 'Charizard ex' : 'Custom Datsun 240Z'))}
  <div class="g2">${f('Número de colección', inp('f_numero', a.numero, 'text', t === 'Pokémon' ? '004/102' : '150/250'))}${f('Año', inp('f_anio', a.anio, 'number', '2024'))}</div>
  ${t === 'Hot Wheels'
    ? `<div class="g2">${f('Serie o segmento', sel('f_serie', a.serie, SERIES))}${f('Color', inp('f_color', a.color, 'text', 'Rojo metálico'))}</div>
       ${f('Tipo de tarjeta', sel('f_sub', a.sub, ['Tarjeta corta', 'Tarjeta larga', 'Blíster especial', 'Suelto / loose', 'Caja o set']))}`
    : `<div class="g2">${f('Expansión', inp('f_expansion', a.expansion, 'text', 'Obsidian Flames'))}${f('Rareza', sel('f_rareza', a.rareza, RAREZAS))}</div>
       <div class="g2">${f('Idioma', sel('f_sub', a.sub, ['Español', 'Inglés', 'Japonés', 'Otro']))}${f('Graduación', sel('f_grado', a.grado, ['Sin graduar', 'PSA 10', 'PSA 9', 'PSA 8', 'BGS 9.5', 'CGC 10', 'Otra']))}</div>
       ${f('Número de certificado', inp('f_cert', a.cert, 'text', 'Solo si está graduada'), 'Guárdalo para verificarlo en el sitio de la graduadora')}`}
  <div class="g3">
    ${f('Estado físico', sel('f_estado', a.estado, t === 'Pokémon' ? ['Mint', 'Near Mint', 'Excelente', 'Jugada', 'Dañada'] : ['Sellado / Mint', 'Excelente', 'Jugado / Desgastado', 'Suelto sin blíster']))}
    ${f('Cantidad', inp('f_cantidad', a.cantidad == null ? 1 : a.cantidad, 'number'))}
    ${f('Estatus', sel('f_estatus', a.estatus, ['Disponible', 'En negociación', 'Conservar']))}
  </div>
  <div class="g3">
    ${f('Precio de compra', inp('f_compra', a.precio_compra, 'number', '0.00'))}
    ${f('Valor de mercado', inp('f_valor', a.valor_estimado, 'number', '0.00'), 'Lo que piden hoy por una igual')}
    ${f('Fecha de adquisición', inp('f_fadq', a.fecha_adq || hoy(), 'date'))}
  </div>
  <div class="g2">${f('Dónde la conseguiste', sel('f_fuente', a.fuente, FUENTES))}${f('Ubicación física', inp('f_ubic', a.ubicacion, 'text', 'Caja A · Vitrina 2 · Carpeta azul'))}</div>
  ${f('Código de barras o SKU', `<div style="display:flex;gap:8px">${inp('f_codigo', a.codigo, 'text', 'Escanéalo o tecléalo')}
    <button class="btn" data-a="escanear" data-target="f_codigo" style="flex:0 0 auto">⌗</button></div>`)}
  ${ui.fotoPendiente
    ? f('Foto', `<div style="display:flex;align-items:center;gap:10px"><img src="${previewUrlFoto}" style="width:44px;height:44px;object-fit:cover;border-radius:8px;border:1px solid var(--line)" alt="">
        <span style="font-size:12.5px;color:var(--muted)">Se guarda la foto que acabas de tomar.</span></div>`)
    : f('Foto (URL)', inp('f_foto', a.foto, 'url', 'https://…'))}
  <div class="fld"><label class="lbl">Verificación de autenticidad</label>
    ${(CHECKS[t] || []).map((c, i) => `<label class="chk"><input type="checkbox" data-chk="${i}" ${(a.checks || []).includes(i) ? 'checked' : ''}><span>${esc(c)}</span></label>`).join('')}</div>
  ${f('Notas', `<textarea class="ta" id="f_notas" rows="2" placeholder="Defectos, procedencia, con quién la cambiaste…">${esc(a.notas || '')}</textarea>`)}
  <label class="chk"><input type="checkbox" id="f_grail" ${a.grail ? 'checked' : ''}><span>👑 Es pieza grial — no se vende, solo se presume</span></label>
  `, `${ed ? `<button class="btn dgr" data-a="delpieza" data-id="${a.id}">Eliminar</button>` : ''}
    <button class="btn gh" data-a="cerrar">Cancelar</button>
    <button class="btn ${t === 'Pokémon' ? 'yel' : 'pri'}" data-a="savepieza">${ed ? 'Guardar cambios' : 'Registrar pieza'}</button>`);
};

MOD.ver = function () {
  const a = ui.ctx; if (!a) return '';
  const s = semaforo(a), t = tono(a.tipo), dif = num(a.valor_estimado) - num(a.precio_compra);
  const roi = num(a.precio_compra) ? dif / num(a.precio_compra) : 0, tr = tendencia(a);
  const vs = db.ventas.filter((v) => v.articulo_id === a.id);
  const ap = db.apartados.filter((x) => x.id_articulo === a.id && x.estatus === 'Vigente');
  const inte = db.compradores.filter((c) => c.interes === a.tipo || c.interes === 'Ambas');
  const det = a.tipo === 'Hot Wheels' ? [['Serie', a.serie], ['Color', a.color], ['Tarjeta', a.sub]]
    : [['Expansión', a.expansion], ['Rareza', a.rareza], ['Idioma', a.sub], ['Graduación', a.grado], ['Certificado', a.cert]];
  const ck = CHECKS[a.tipo] || [], hechos = (a.checks || []).length;
  return shell(a.nombre, a.id, `
  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:18px">
    <div style="width:128px;height:128px;border-radius:12px;background:#101B2C;flex:0 0 auto;display:grid;place-items:center;overflow:hidden;border:1px solid var(--line)">
      ${imgFoto(a, 'style="width:100%;height:100%;object-fit:cover"', 'font-size:44px;opacity:.3')}</div>
    <div style="flex:1;min-width:210px">
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">
        <span class="tag ${s.c}">${s.t}</span><span class="tag" style="color:${t};border-color:${t}">${esc(a.tipo)}</span>
        ${a.grail ? '<span class="tag p">👑 Grial</span>' : ''}
        ${hechos ? `<span class="tag ${hechos === ck.length ? 'g' : ''}">Verificada ${hechos}/${ck.length}</span>` : ''}</div>
      <div class="g2" style="gap:10px">
        <div><div class="lbl" style="margin-bottom:2px">Pagaste</div><div class="mn">${money(a.precio_compra)}</div></div>
        <div><div class="lbl" style="margin-bottom:2px">Vale hoy</div><div class="mn" style="color:${t}">${money(a.valor_estimado)}</div></div>
        <div><div class="lbl" style="margin-bottom:2px">Plusvalía</div><div class="mn ${dif >= 0 ? 'pos' : 'neg'}">${dif >= 0 ? '+' : ''}${money(dif)} (${pct(roi)})</div></div>
        <div><div class="lbl" style="margin-bottom:2px">En tu poder</div><div class="mn">${a.fecha_adq ? dias(a.fecha_adq) + ' días' : '—'}</div></div>
      </div></div></div>
  ${tr ? `<div class="pnl" style="padding:14px;margin-bottom:14px"><div style="display:flex;justify-content:space-between;align-items:baseline">
    <b style="font-size:13px">Cómo se ha movido su valor</b>
    <span class="mn ${tr.delta >= 0 ? 'pos' : 'neg'}" style="font-size:13px">${tr.delta >= 0 ? '▲' : '▼'} ${money(Math.abs(tr.delta))} (${pct(Math.abs(tr.pct))}) en ${tr.n} valuaciones</span></div>
    ${chispa(tr.pts, tr.delta >= 0 ? 'var(--green)' : 'var(--red)')}</div>` : ''}
  <div class="g3" style="gap:11px">
    ${[['Número', a.numero], ['Año', a.anio], ['Estado', a.estado], ['Cantidad', a.cantidad], ['Disponibles', libre(a)],
      ['Ubicación', a.ubicacion], ['Código', a.codigo], ['Origen', a.fuente]].concat(det)
      .filter((d) => d[1] !== '' && d[1] != null).map((d) => `<div><div class="lbl" style="margin-bottom:2px">${d[0]}</div><div style="font-size:13px">${esc(d[1])}</div></div>`).join('')}
  </div>
  ${a.notas ? `<div class="note">${esc(a.notas)}</div>` : ''}
  ${ap.length ? `<div class="note w"><b>Apartada:</b> ${ap.map((x) => `${cli(x.id_comprador) ? esc(cli(x.id_comprador).nombre) : esc(x.cliente_snap || 'un cliente')} dejó ${money(x.anticipo)}, resta ${money(num(x.precio_acordado) - num(x.anticipo))} hasta el ${x.fecha_limite || '—'} · entrega en ${esc(x.lugar_entrega || 'Balderas')}`).join('; ')}.</div>` : ''}
  ${libre(a) ? `<div class="note"><b>Piso para regatear:</b> ${money(precioMinimo(a))} (con margen mínimo de ${ui.margenMin}%). Por debajo de eso ya no ganas lo que quieres.</div>` : ''}
  ${pedidosPara(a).length ? `<div class="note w"><b>Te la pidieron:</b> ${pedidosPara(a).map((p) => `${cli(p.comprador_id) ? esc(cli(p.comprador_id).nombre) : 'un cliente'} (“${esc(p.descripcion)}”)`).join('; ')}. Avísale antes de publicarla.</div>` : ''}
  ${inte.length && libre(a) ? `<div class="note g"><b>Avísale primero a:</b> ${inte.slice(0, 4).map((c) => esc(c.nombre)).join(', ')} — coleccionan justo esto.</div>` : ''}
  ${vs.length ? `<div class="sec" style="margin:18px 0 8px"><h2>Historial de ventas</h2><span class="ln"></span></div>
    ${vs.map((v) => `<div class="calc" style="margin-bottom:8px"><div class="ln"><span>${v.fecha} · ${esc(v.plataforma_snap)} · ×${v.cantidad}</span>
      <b class="${v.neto >= 0 ? 'pos' : 'neg'}">${money(v.neto)} netos</b></div></div>`).join('')}` : ''}
  `, `<button class="btn gh sm" data-a="editpieza" data-id="${a.id}">Editar</button>
     <button class="btn gh sm" data-a="valuar" data-id="${a.id}">Valuar</button>
     <button class="btn gh sm" data-a="publicacion" data-id="${a.id}">Publicación</button>
     ${libre(a) ? `<button class="btn sm" data-a="apartar" data-id="${a.id}">Apartar</button>
     <button class="btn pri sm" data-a="vender" data-id="${a.id}">Registrar venta</button>` : ''}`);
};

MOD.historial = function () {
  const a = ui.ctx; if (!a) return '';
  const h = (a.historial || []).slice().sort((x, y) => y.fecha.localeCompare(x.fecha));
  return shell('Valuación de mercado', a.nombre, `
  <p style="font-size:12.5px;color:var(--muted);margin-bottom:16px">Cada vez que consultes cuánto piden por una igual, anótalo. Con tres o cuatro puntos ya ves si la pieza está subiendo o desinflándose, y decides si vender ahora o esperar.</p>
  <div class="g3">
    ${f('Valor observado', inp('h_valor', a.valor_estimado, 'number', '0.00'))}
    ${f('Fecha', inp('h_fecha', hoy(), 'date'))}
    ${f('Dónde lo viste', sel('h_fuente', '', ['Mercado Libre', 'eBay vendidos', 'Facebook', 'TCGplayer', 'Cardmarket', 'Tienda física', 'Estimación propia']))}
  </div>
  <label class="chk"><input type="checkbox" id="h_actualiza" checked><span>Actualizar también el valor de mercado de la pieza</span></label>
  <div id="h_chart" style="margin-top:16px"></div>
  ${h.length ? `<div class="sec" style="margin:16px 0 10px"><h2>Registros</h2><span class="ln"></span></div>
    ${h.map((x) => `<div class="fi" style="margin-bottom:7px"><span class="dot" style="background:var(--blue);--dc:var(--blue)"></span>
      <span class="tx"><b>${money(x.valor)}</b><span>${x.fecha} · ${esc(x.fuente || '—')}</span></span>
      <button class="btn sm gh" data-a="delval" data-id="${a.id}" data-val="${x.id}">✕</button></div>`).join('')}`
    : '<div class="note">Aún no hay valuaciones registradas para esta pieza.</div>'}
  `, `<button class="btn gh" data-a="cerrar">Cerrar</button><button class="btn pri" data-a="saveval" data-id="${a.id}">Registrar valuación</button>`, '560px');
};
function pintarChart() {
  const a = ui.ctx, box = $('#h_chart'); if (!a || !box) return;
  const tr = tendencia(a);
  box.innerHTML = tr ? `<div class="pnl" style="padding:14px">
    <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px">
      <span style="color:var(--muted)">De ${money(tr.ini)} a ${money(tr.fin)}</span>
      <b class="mn ${tr.delta >= 0 ? 'pos' : 'neg'}">${tr.delta >= 0 ? '▲' : '▼'} ${pct(Math.abs(tr.pct))}</b></div>
    ${chispa(tr.pts, tr.delta >= 0 ? 'var(--green)' : 'var(--red)')}</div>`
    : `<div class="note">Con dos o más valuaciones aparece aquí la gráfica de tendencia.</div>`;
}

MOD.venta = function () {
  const a = ui.ctx; if (!a) return '';
  const ap = ui.apLiq;
  return shell(ap ? 'Liquidar apartado' : 'Registrar venta', a.nombre, `
  ${ap ? `<div class="note w"><b>Apartado en curso:</b> ${esc(cli(ap.id_comprador) ? cli(ap.id_comprador).nombre : 'el cliente')} ya dejó ${money(ap.anticipo)} de anticipo. El precio total acordado fue ${money(ap.precio_acordado)}; hoy te termina de pagar ${money(num(ap.precio_acordado) - num(ap.anticipo))}.</div>` : ''}
  <div class="g2">${f('Canal de venta', selP('v_plat', 'data-a="recalc"'))}${f('Comprador', selC('v_comp', ap ? ap.id_comprador : ''))}</div>
  <div class="g3">
    ${f('Cantidad', `<input class="in" id="v_cant" type="number" min="1" max="${ap ? ap.cantidad : libre(a)}" value="${ap ? ap.cantidad : 1}" data-a="recalc">`)}
    ${f('Precio cobrado', `<input class="in" id="v_precio" type="number" step="0.01" value="${ap ? num(ap.precio_acordado) : (num(a.valor_estimado) || '')}" data-a="recalc" placeholder="0.00">`, 'Total de la operación')}
    ${f('Costo de envío', `<input class="in" id="v_envio" type="number" step="0.01" value="0" data-a="recalc">`, '$0 si lo pagó el cliente')}
  </div>
  <div class="g3">
    ${f('Otros costos', `<input class="in" id="v_otros" type="number" step="0.01" value="0" data-a="recalc">`, 'Burbuja, protector, gasolina')}
    ${f('Fecha', inp('v_fecha', hoy(), 'date'))}
    ${f('Guía de rastreo', inp('v_guia', '', 'text', 'Opcional'))}
  </div>
  <div id="v_calc"></div>
  <div class="note"><b>¿No sabes cuánto pedir?</b> Escribe cuánto quieres ganar limpio y el servidor calcula el precio de publicación.
    <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
      <input class="in" id="v_meta" type="number" step="0.01" placeholder="Quiero ganar…" style="max-width:180px">
      <button class="btn sm" data-a="objetivo">Calcular precio</button></div>
    <div id="v_obj" style="margin-top:10px"></div></div>
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button>
     <button class="btn pri" data-a="saveventa" ${ap ? `data-ap="${ap.id}"` : ''}>${ap ? 'Liquidar y registrar' : 'Confirmar venta'}</button>`);
};
function pintarVenta() {
  const a = ui.ctx; if (!a || !$('#v_calc')) return;
  const p = plat($('#v_plat').value), cant = num($('#v_cant').value) || 1, precio = num($('#v_precio').value);
  const envio = num($('#v_envio').value), otros = num($('#v_otros').value);
  const costo = num(a.precio_compra) * cant, comV = precio * num(p.com_pct), ret = precio * num(p.ret_pct);
  const g = netoPreview({ precio, costo_unit: a.precio_compra, cantidad: cant, com_fija: p.com_fija, com_pct: p.com_pct, ret_pct: p.ret_pct, envio, otros });
  $('#v_calc').innerHTML = `<div class="calc">
    <div class="ln"><span>Te pagan</span><span>${money(precio)}</span></div>
    <div class="ln"><span>− Lo que te costó (×${cant})</span><span>−${money(costo)}</span></div>
    <div class="ln"><span>− Comisión ${esc(p.nombre)} (${pct(p.com_pct)})</span><span>−${money(comV)}</span></div>
    ${num(p.com_fija) ? `<div class="ln"><span>− Cuota fija</span><span>−${money(p.com_fija)}</span></div>` : ''}
    ${ret ? `<div class="ln"><span>− Retención fiscal (${pct(p.ret_pct)})</span><span>−${money(ret)}</span></div>` : ''}
    ${envio ? `<div class="ln"><span>− Envío</span><span>−${money(envio)}</span></div>` : ''}
    ${otros ? `<div class="ln"><span>− Otros costos</span><span>−${money(otros)}</span></div>` : ''}
    <div class="ln tot"><span>Ganancia neta</span><span class="${g >= 0 ? 'pos' : 'neg'}">${money(g)}${precio ? ` · ${pct(g / precio)}` : ''}</span></div></div>
    ${g < 0 ? '<div class="note r">A este precio pierdes dinero. Sube el precio o revisa el costo de envío.</div>' : ''}`;
}

MOD.apartado = function () {
  const a = ui.ctx;
  const lim = new Date(Date.now() + 15 * 864e5).toISOString().slice(0, 10);
  const disp = db.articulos.filter((x) => libre(x) > 0);
  return shell('Apartar con anticipo', a ? a.nombre : '', `
  ${a ? '' : f('Pieza', `<select class="sel" id="ap_art">${disp.map((x) => `<option value="${x.id}">${esc(x.nombre)} · ${libre(x)} disp.</option>`).join('') || '<option value="">Sin piezas disponibles</option>'}</select>`)}
  ${f('Cliente que aparta', `<select class="sel" id="ap_comp" data-a="apcliente"><option value="">— Cliente nuevo —</option>${db.compradores.map((c) => `<option value="${c.id}">${esc(c.nombre)}</option>`).join('')}</select>`)}
  <div id="ap_nuevo" class="g2">${f('Nombre del cliente', `<input class="in" id="ap_nombre" placeholder="Ej. Luis (Facebook)">`)}${f('Teléfono o contacto', `<input class="in" id="ap_tel" placeholder="Opcional">`)}</div>
  ${f('Cantidad', `<input class="in" id="ap_cant" type="number" min="1" value="1" max="${a ? libre(a) : 99}">`)}
  <div class="g3">
    ${f('Precio acordado', inp('ap_precio', a ? a.valor_estimado : '', 'number', '0.00'))}
    ${f('Anticipo recibido', inp('ap_ant', '', 'number', '0.00'))}
    ${f('Fecha límite', inp('ap_lim', lim, 'date'))}
  </div>
  ${f('Lugar de entrega', `${inp('ap_lugar', 'Balderas', 'text', 'Balderas')}<datalist id="lugares_entrega"><option value="Balderas"><option value="Envío por paquetería"><option value="Punto de encuentro"></datalist>`, 'Normalmente Balderas. Puedes escribir otro lugar.')}
  ${f('Notas', inp('ap_notas', '', 'text', 'Paga los viernes · entrega en el metro'))}
  <div class="note w"><b>Mientras el apartado esté vigente</b> la pieza deja de contar como disponible y el servidor rechaza cualquier venta que la incluya. Si pasa la fecha límite sin liquidarse, cambia sola a Vencido.</div>
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn yel" data-a="saveapartado">Registrar apartado</button>`, '560px');
};

MOD.lote = function () {
  const arts = ui.sel.map(art).filter(Boolean);
  return shell('Vender como lote', `${arts.length} piezas`, `
  <p style="font-size:12.5px;color:var(--muted);margin-bottom:16px">El precio del lote se reparte entre las piezas en proporción a su valor de mercado, para que cada una conserve su ganancia individual y tus estadísticas por pieza sigan siendo verdaderas.</p>
  ${arts.map((a) => `<div class="fi" style="margin-bottom:7px"><span class="dot" style="background:${tono(a.tipo)};--dc:${tono(a.tipo)}"></span>
    <span class="tx"><b>${esc(a.nombre)}</b><span>Costó ${money(a.precio_compra)} · vale ${money(a.valor_estimado)}</span></span>
    <span class="am" data-share="${a.id}">—</span></div>`).join('')}
  <div class="g2" style="margin-top:16px">${f('Canal', selP('l_plat', 'data-a="recalcLote"'))}${f('Comprador', selC('l_comp', ''))}</div>
  <div class="g3">
    ${f('Precio del lote', `<input class="in" id="l_precio" type="number" step="0.01" value="${suma(arts, (a) => a.valor_estimado).toFixed(2)}" data-a="recalcLote">`)}
    ${f('Envío', `<input class="in" id="l_envio" type="number" step="0.01" value="0" data-a="recalcLote">`)}
    ${f('Fecha', inp('l_fecha', hoy(), 'date'))}
  </div>
  <div id="l_calc"></div>
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="savelote">Registrar lote</button>`);
};
function pintarLote() {
  const arts = ui.sel.map(art).filter(Boolean); if (!$('#l_calc')) return;
  const p = plat($('#l_plat').value), precio = num($('#l_precio').value), envio = num($('#l_envio').value);
  const base = suma(arts, (a) => a.valor_estimado) || arts.length;
  arts.forEach((a) => { const sh = precio * ((num(a.valor_estimado) || 1) / base);
    const el = $(`[data-share="${a.id}"]`); if (el) el.textContent = money(sh); });
  const costo = suma(arts, (a) => a.precio_compra), com = precio * num(p.com_pct) + num(p.com_fija), ret = precio * num(p.ret_pct);
  const g = precio - costo - com - ret - envio;
  $('#l_calc').innerHTML = `<div class="calc">
    <div class="ln"><span>Precio del lote</span><span>${money(precio)}</span></div>
    <div class="ln"><span>− Costo de las ${arts.length} piezas</span><span>−${money(costo)}</span></div>
    <div class="ln"><span>− Comisión ${esc(p.nombre)}</span><span>−${money(com)}</span></div>
    ${ret ? `<div class="ln"><span>− Retención fiscal</span><span>−${money(ret)}</span></div>` : ''}
    ${envio ? `<div class="ln"><span>− Envío</span><span>−${money(envio)}</span></div>` : ''}
    <div class="ln tot"><span>Ganancia neta del lote</span><span class="${g >= 0 ? 'pos' : 'neg'}">${money(g)}</span></div></div>
    <div class="note">La cuota fija de ${esc(p.nombre)} se cobra una sola vez, no por pieza.</div>`;
}

MOD.trade = function () {
  const dados = (ui.tradeOut || []).map(art).filter(Boolean);
  const recib = ui.tradeIn || [];
  const vOut = suma(dados, (a) => a.valor_estimado), vIn = suma(recib, (r) => r.valor);
  const dif = vIn - vOut;
  return shell('Registrar intercambio', 'Sin dinero, pero sí valor', `
  <div class="g2">${f('Con quién cambiaste', inp('t_quien', ui.tradeQuien || '', 'text', 'Nombre o alias'))}${f('Fecha', inp('t_fecha', hoy(), 'date'))}</div>
  <div class="sec" style="margin:6px 0 10px"><h2>Entregas — ${money(vOut)}</h2><span class="ln"></span></div>
  ${f('Agregar del inventario', `<select class="sel" id="t_add"><option value="">Elige una pieza…</option>
    ${db.articulos.filter((a) => libre(a) > 0 && !(ui.tradeOut || []).includes(a.id)).map((a) => `<option value="${a.id}">${esc(a.nombre)} · ${money(a.valor_estimado)}</option>`).join('')}</select>
    <button class="btn sm" data-a="tradeadd" style="margin-top:8px">Agregar a lo que entregas</button>`)}
  ${dados.length ? dados.map((a) => `<div class="fi" style="margin-bottom:7px"><span class="dot" style="background:var(--red);--dc:var(--red)"></span>
    <span class="tx"><b>${esc(a.nombre)}</b><span>${esc(a.tipo)}</span></span><span class="am">${money(a.valor_estimado)}</span>
    <button class="btn sm gh" data-a="traderm" data-id="${a.id}">✕</button></div>`).join('') : '<p style="color:var(--muted);font-size:12.5px;margin-bottom:10px">Todavía no agregas nada.</p>'}
  <div class="sec" style="margin:18px 0 10px"><h2>Recibes — ${money(vIn)}</h2><span class="ln"></span></div>
  <div class="g3">
    ${f('Qué recibes', inp('t_nom', '', 'text', 'Nombre de la pieza'))}
    ${f('Colección', sel('t_tipo', '', ['Hot Wheels', 'Pokémon']))}
    ${f('Valor de mercado', inp('t_val', '', 'number', '0.00'))}
  </div>
  <button class="btn sm" data-a="tradein">Agregar a lo que recibes</button>
  ${recib.length ? '<div style="margin-top:12px">' + recib.map((r, i) => `<div class="fi" style="margin-bottom:7px"><span class="dot" style="background:var(--green);--dc:var(--green)"></span>
    <span class="tx"><b>${esc(r.nombre)}</b><span>${esc(r.tipo)}</span></span><span class="am">${money(r.valor)}</span>
    <button class="btn sm gh" data-a="tradeinrm" data-i="${i}">✕</button></div>`).join('') + '</div>' : ''}
  <div class="calc" style="margin-top:16px">
    <div class="ln"><span>Valor que entregas</span><span>−${money(vOut)}</span></div>
    <div class="ln"><span>Valor que recibes</span><span>+${money(vIn)}</span></div>
    <div class="ln tot"><span>Balance del cambio</span><span class="${dif >= 0 ? 'pos' : 'neg'}">${dif >= 0 ? '+' : ''}${money(dif)}</span></div></div>
  ${dif < 0 ? '<div class="note r">Estás entregando más valor del que recibes. A veces vale la pena por una pieza que persigues, pero conviene verlo antes de dar la mano.</div>' : ''}
  ${f('Notas', inp('t_notas', ui.tradeNotas || '', 'text', 'Por qué aceptaste el cambio'))}
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="savetrade">Guardar intercambio</button>`);
};

MOD.comprador = function () {
  const c = ui.ctx || {};
  return shell(c.id ? 'Editar comprador' : 'Nuevo comprador', '', `
  ${f('Nombre o alias', inp('c_nombre', c.nombre, 'text', '@pkm_collector99'))}
  <div class="g2">${f('WhatsApp o contacto', inp('c_tel', c.tel, 'text', '55 1234 5678'))}${f('Le interesa', sel('c_interes', c.interes, ['Hot Wheels', 'Pokémon', 'Ambas']))}</div>
  ${f('Qué busca', `<textarea class="ta" id="c_notas" rows="2" placeholder="Solo Treasure Hunt · Cartas en japonés · Paga por adelantado">${esc(c.notas || '')}</textarea>`)}
  `, `${c.id ? `<button class="btn dgr" data-a="delcomp" data-id="${c.id}">Eliminar</button>` : ''}
    <button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="savecomp">Guardar</button>`, '500px');
};
MOD.plataforma = function () {
  const p = ui.ctx || {};
  return shell(p.id ? 'Editar canal' : 'Nuevo canal de venta', '', `
  <div class="g2">${f('Nombre', inp('p_nombre', p.nombre, 'text', 'Mercado Libre'))}${f('Código corto', inp('p_codigo', p.codigo, 'text', 'ML'))}</div>
  <div class="g3">${f('Comisión %', inp('p_pct', p.com_pct != null ? (p.com_pct * 100).toFixed(2) : '', 'number', '13'), '13 = 13%')}
  ${f('Cuota fija', inp('p_fija', p.com_fija, 'number', '25'))}
  ${f('Retención fiscal %', inp('p_ret', p.ret_pct != null ? (p.ret_pct * 100).toFixed(2) : '', 'number', '0'), 'ISR e IVA retenidos')}</div>
  ${f('Nota', inp('p_notas', p.notas, 'text', 'Tarifa que aplica a tu categoría'))}
  `, `${p.id ? `<button class="btn dgr" data-a="delplat" data-id="${p.id}">Eliminar</button>` : ''}
    <button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="saveplat">Guardar</button>`, '560px');
};
MOD.wish = function () {
  const w = ui.ctx || {};
  return shell('Pieza que buscas', '', `
  ${f('Qué buscas', inp('w_nombre', w.nombre, 'text', 'Super Treasure Hunt 2025 — Toyota Supra'))}
  <div class="g3">${f('Colección', sel('w_tipo', w.tipo, ['Hot Wheels', 'Pokémon']))}${f('Precio tope', inp('w_tope', w.tope, 'number', '0.00'))}
  ${f('Prioridad', sel('w_prio', w.prioridad ? String(w.prioridad) : '3', ['1', '2', '3', '4', '5']))}</div>
  ${f('Detalle', inp('w_detalle', w.detalle, 'text', 'Solo tarjeta larga, sin dobleces'))}
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="savewish">Guardar</button>`, '500px');
};
MOD.encargo = function () {
  const e = ui.enc || encNuevo();
  const propias = {}; (e.id ? (db.encargos.find((x) => x.id === e.id) || { items: [] }).items : []).forEach((i) => { propias[i.articulo_id] = (propias[i.articulo_id] || 0) + i.cantidad; });
  const opciones = db.articulos.filter((a) => libre(a) + (propias[a.id] || 0) > 0 || e.items.some((i) => i.articulo_id === a.id))
    .sort((a, b) => a.nombre.localeCompare(b.nombre));
  const filas = e.items.map((i) => { const a = i.articulo_id ? art(i.articulo_id) : null; return { i, a, costo: a ? num(a.precio_compra) : 0, sub: num(i.precio_unit) * num(i.cantidad) }; });
  const total = suma(filas, (r) => r.sub), costo = suma(filas, (r) => r.costo * num(r.i.cantidad)), ant = num(e.anticipo);
  return shell(e.id ? 'Editar pedido' : 'Nuevo pedido', 'Una o varias piezas para un cliente', `
  ${f('Cliente', `<select class="sel" id="en_comp" data-a="encchg"><option value="">— Cliente nuevo —</option>${db.compradores.map((c) => `<option value="${c.id}" ${e.comprador_id === c.id ? 'selected' : ''}>${esc(c.nombre)}</option>`).join('')}</select>`)}
  ${e.comprador_id ? '' : `<div class="g2">${f('Nombre del cliente nuevo', `<input class="in" id="en_nuevo" value="${esc(e.cliente_nuevo)}" placeholder="Ej. Luis (Facebook)">`)}
    ${f('Teléfono o contacto', `<input class="in" id="en_tel" value="${esc(e.tel_nuevo)}" placeholder="Opcional">`)}</div>`}
  ${f('Fecha de entrega en Balderas', `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><input class="in" type="date" id="en_fecha" data-a="encchg" value="${esc(e.fecha_entrega)}" style="max-width:180px">
    <button class="chip ${e.fecha_entrega === proximoSabado() ? 'on' : ''}" data-a="encsab" data-v="${proximoSabado()}">Este sábado ${esc(fmtDia(proximoSabado()))}</button>
    <button class="chip ${e.fecha_entrega === proximoSabado(1) ? 'on' : ''}" data-a="encsab" data-v="${proximoSabado(1)}">Sábado siguiente ${esc(fmtDia(proximoSabado(1)))}</button></div>`, 'Casi siempre es sábado en Balderas; si es entre semana, elige otra fecha.')}
  <div class="fld"><label class="lbl">Piezas del encargo</label>
    ${filas.map((r, n) => `<div style="display:grid;grid-template-columns:minmax(0,1fr) 60px 92px 30px;gap:6px;margin-bottom:6px;align-items:center">
      <select class="sel en_art" data-a="encchg"><option value="">Elige una pieza…</option>${opciones.map((a) => `<option value="${a.id}" ${r.i.articulo_id === a.id ? 'selected' : ''}>${esc(a.nombre)} · ${libre(a) + (propias[a.id] || 0)} disp.</option>`).join('')}</select>
      <input class="in en_cant" type="number" min="1" value="${esc(r.i.cantidad)}" data-a="encchg" title="Cantidad">
      <input class="in en_pre" type="number" step="0.01" value="${esc(r.i.precio_unit)}" data-a="encchg" placeholder="Precio c/u" title="Precio por pieza">
      <button class="btn sm gh" data-a="encrm" data-i="${n}" title="Quitar" ${filas.length === 1 ? 'disabled' : ''}>✕</button>
      <div style="grid-column:1/-1;font-size:11.5px;color:var(--muted);margin:-2px 0 4px">${r.a ? `Costo ${money(r.costo)} c/u · ${money(r.costo * num(r.i.cantidad))} en total · ganas ${money(r.sub - r.costo * num(r.i.cantidad))}` : ''}</div></div>`).join('')}
    <button class="btn sm" data-a="encadd">+ Agregar otra pieza</button></div>
  <div class="calc"><div class="ln"><span>Piezas</span><b>${suma(filas, (r) => num(r.i.cantidad))}</b></div>
    <div class="ln"><span>Costo total</span><b>${money(costo)}</b></div>
    <div class="ln"><span>Precio total</span><b>${money(total)}</b></div>
    <div class="ln"><span>Ganancia</span><b class="${total - costo >= 0 ? 'pos' : 'neg'}">${money(total - costo)}</b></div>
    <div class="ln"><span>Por cobrar en Balderas</span><b>${money(Math.max(0, total - ant))}</b></div></div>
  <div class="g2" style="margin-top:12px">${f('Anticipo recibido (opcional)', `<input class="in" type="number" step="0.01" id="en_ant" data-a="encchg" value="${esc(e.anticipo)}" placeholder="0.00">`)}
    ${f('Cómo lo pagó', `<select class="sel" id="en_forma" data-a="encchg">${FORMAS_PAGO.map((x) => `<option ${e.forma_anticipo === x ? 'selected' : ''}>${x}</option>`).join('')}</select>`)}</div>
  ${f('Notas', `<textarea class="ta" id="en_notas" rows="2" data-a="encchg" placeholder="Ej. Empacar en bolsa, le da pena el precio…">${esc(e.notas)}</textarea>`)}
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="saveenc">${e.id ? 'Guardar cambios' : 'Registrar pedido'}</button>`, '640px');
};
MOD.encentregar = function () {
  const e = ui.ctx; if (!e) return '';
  const c = cli(e.comprador_id) || {};
  return shell('Entregar encargo', c.nombre || '', `
  <div class="calc"><div class="ln"><span>${e.piezas} piezas</span><b>${money(e.total)}</b></div>
    <div class="ln"><span>Anticipo ya recibido${e.forma_anticipo ? ' (' + esc(e.forma_anticipo) + ')' : ''}</span><b>−${money(e.anticipo)}</b></div>
    <div class="ln"><span>Resta por cobrar</span><b>${money(e.resta)}</b></div></div>
  ${f('Total final acordado', `<input class="in" type="number" step="0.01" id="ee_total" value="${e.total}">`, 'Cámbialo solo si le hiciste descuento: las ventas se registran con este total.')}
  <div class="g2">${f('Cobrado ahora', `<input class="in" type="number" step="0.01" id="ee_cobrado" value="${e.resta}">`)}
    ${f('Forma de pago', `<select class="sel" id="ee_forma">${FORMAS_PAGO.map((x) => `<option>${x}</option>`).join('')}</select>`)}</div>
  <div class="note">Se crean las ventas de cada pieza, se descuentan del inventario y el encargo queda como entregado. Si cobras menos de lo que resta, se avisa cuánto te debe.</div>
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="saveentrega" data-id="${e.id}">Confirmar entrega</button>`, '520px');
};
MOD.mattelmulti = function () {
  const m = ui.mm || { texto: '', filas: [] };
  const ok = m.filas.filter((r) => r.ok);
  return shell('Compra de Mattel', 'Pega los links de lo que compraste, uno por renglón', `
  <textarea class="ta" id="mm_txt" rows="4" placeholder="https://creations.mattel.com/products/…&#10;https://creations.mattel.com/products/…">${esc(m.texto)}</textarea>
  <div style="margin:10px 0"><button class="btn pri sm" data-a="mmtraer">${m.cargando ? 'Consultando…' : 'Traer datos'}</button></div>
  ${m.filas.length ? `<div class="pnl wrap" style="padding:6px"><table class="tbl"><thead><tr><th>Pieza</th><th class="num">Cant.</th><th class="num">Costo c/u (MXN)</th></tr></thead><tbody>
    ${m.filas.map((r, i) => r.ok ? `<tr><td><b>${esc(r.nombre)}</b>${r.disponible ? '' : '<div style="font-size:11px;color:var(--yellow)">hoy aparece agotada en Mattel (ya la compraste, solo se registra)</div>'}</td>
      <td class="num"><input class="in mm_cant" type="number" min="1" value="${r.cantidad}" data-i="${i}" style="width:64px;padding:4px 8px"></td>
      <td class="num"><input class="in mm_pre" type="number" step="0.01" value="${r.precio_mxn}" data-i="${i}" style="width:100px;padding:4px 8px"></td></tr>`
      : `<tr><td colspan="3" style="color:var(--red);font-size:12.5px">${esc(r.url)} — ${esc(r.error)}</td></tr>`).join('')}</tbody></table></div>
    <div class="note">Se registran como <b>Por recibir</b> con fuente Mattel Creations y el precio ya convertido a pesos. Cuando lleguen, márcalas desde el Panel.</div>` : ''}
  `, `<button class="btn gh" data-a="cerrar">Cerrar</button>${ok.length ? `<button class="btn pri" data-a="mmguardar">Registrar ${ok.length} pieza${ok.length === 1 ? '' : 's'}</button>` : ''}`, '640px');
};
MOD.publote = function () {
  const l = ui.ctx || [];
  const txt = ['🏎🃏 PIEZAS DISPONIBLES', ''].concat(l.map((a) => {
    const det = [a.numero, a.anio, a.tipo === 'Hot Wheels' ? a.serie : a.expansion, a.estado].filter(Boolean).join(' · ');
    return `• ${a.nombre}${det ? ' (' + det + ')' : ''} — ${money(a.valor_estimado)}`;
  })).concat(ui.pubDesc > 0 && l.length > 1 ? ['', `🔥 Llévate las ${l.length} por ${money(suma(l, (a) => num(a.valor_estimado)) * (1 - ui.pubDesc / 100))} (${ui.pubDesc}% menos)`] : []).concat(['', `📍 Entrega en persona en ${LUGAR_ENTREGA}.`, 'Escríbeme por mensaje para apartar; manejo apartados con anticipo.']).join('\n');
  return shell('Publicación en lote', `${l.length} piezas`, `
  <p style="font-size:12.5px;color:var(--muted);margin-bottom:12px">Un solo texto para tu grupo de Facebook con todas las piezas seleccionadas.</p>
  <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);margin-bottom:10px">Descuento por llevarse todo (%)
    <input class="in" type="number" min="0" max="90" value="${ui.pubDesc}" data-a="pubdesc" style="width:72px;padding:5px 8px"></label>
  <textarea class="ta" id="pub_txt" rows="16" style="font-family:var(--m);font-size:12px">${esc(txt)}</textarea>
  `, `<button class="btn gh" data-a="cerrar">Cerrar</button><button class="btn pri" data-a="copiar">Copiar texto</button>`);
};
MOD.pedido = function () {
  return shell('Lo que pide un cliente', 'Te avisaremos si llega algo parecido', `
  ${f('Cliente', selC('pe_comp', ''))}
  ${f('Qué busca', inp('pe_desc', '', 'text', 'Datsun 240Z verde, tarjeta larga'), 'Escribe el nombre como lo tendrías registrado: al abrir una pieza parecida verás su pedido.')}
  ${f('Presupuesto (opcional)', inp('pe_tope', '', 'number', '0.00'))}
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button><button class="btn pri" data-a="saveped">Guardar</button>`, '500px');
};
MOD.publicacion = function () {
  const a = ui.ctx || {};
  return shell('Publicación lista para copiar', a.nombre || '', `
  <p style="font-size:12.5px;color:var(--muted);margin-bottom:12px">Copia esto en Facebook Marketplace o en tu grupo de Facebook. Ajusta lo que quieras antes de publicar.</p>
  <textarea class="ta" id="pub_txt" rows="15" style="font-family:var(--m);font-size:12px">${esc(textoPub(a))}</textarea>
  `, `<button class="btn gh" data-a="cerrar">Cerrar</button>
     <button class="btn gh" data-a="fotofb" data-id="${a.id}" title="Foto cuadrada con contraste y nitidez, lista para Facebook">📸 Foto lista</button>
     <button class="btn pri" data-a="copiar">Copiar texto</button>`);
};
const LUGAR_ENTREGA = 'Balderas';
function textoPub(a) {
  const L = [], t = [a.tipo === 'Pokémon' ? 'Carta Pokémon' : 'Hot Wheels', a.nombre, a.numero, a.anio].filter(Boolean).join(' ');
  L.push(t.toUpperCase(), '');
  L.push(a.tipo === 'Pokémon'
    ? `Carta original de la expansión ${a.expansion || '—'}. Rareza ${a.rareza || '—'}, idioma ${a.sub || '—'}${a.grado && a.grado !== 'Sin graduar' ? `, graduada ${a.grado}${a.cert ? ` (cert. ${a.cert})` : ''}` : ''}.`
    : `Pieza original Mattel, línea ${a.serie || 'Mainline'}${a.color ? `, color ${a.color}` : ''}${a.sub ? `, ${String(a.sub).toLowerCase()}` : ''}.`);
  L.push('', `Estado: ${a.estado || '—'}`, `Número de colección: ${a.numero || '—'}`, `Año: ${a.anio || '—'}`, `Disponibles: ${libre(a) || a.cantidad || 1}`, '');
  if ((a.checks || []).length) L.push('Verificación de autenticidad:', ...(a.checks || []).map((i) => '· ' + (CHECKS[a.tipo] || [])[i]).filter(Boolean), '');
  L.push(`Precio: ${money(a.valor_estimado)}`, '');
  L.push(`📍 Entrega en persona en ${LUGAR_ENTREGA}.`, '· Acepto preguntas y fotos extra por mensaje.', '· Manejo apartados con anticipo.');
  if (a.notas) L.push('', `Nota: ${a.notas}`);
  return L.join('\n');
}
MOD.escaner = function () {
  return shell('Escanear código', 'Apunta al código de barras', `
  <video class="scan" id="sc_vid" playsinline autoplay muted></video>
  <div id="sc_msg" class="note">Buscando cámara…</div>
  ${f('O escríbelo a mano', `<div style="display:flex;gap:8px"><input class="in" id="sc_man" placeholder="Código">
    <button class="btn pri" data-a="scman" style="flex:0 0 auto">Usar</button></div>`)}
  `, `<button class="btn gh" data-a="cerrar">Cerrar</button>`, '520px');
};

MOD.foto = function () {
  return shell('Con foto', 'La IA sugiere, tú confirmas', `
  ${!previewUrlFoto ? `
    <label class="btn pri" for="fi_foto" style="display:block;text-align:center;cursor:pointer;padding:28px 16px">📷 Tomar o elegir foto</label>
    <input type="file" id="fi_foto" data-a="fotoelegida" accept="image/*" capture="environment" style="display:none">
    <div class="note">Sirve con el auto suelto, en su blíster, o una carta Pokémon suelta o en funda/slab. Si se alcanza a leer texto (nombre, SKU, set), la IA acierta bastante más.</div>
  ` : `
    <div style="text-align:center;margin-bottom:14px">
      <img src="${previewUrlFoto}" style="max-width:100%;max-height:240px;border-radius:12px;border:1px solid var(--line)" alt="Foto elegida">
    </div>
    ${ui.identificando
      ? `<div class="note"><div class="spin" style="display:inline-block;margin-right:8px;vertical-align:middle;width:16px;height:16px"></div>Identificando con IA…</div>`
      : `<div style="display:flex;gap:9px;flex-wrap:wrap;justify-content:center">
           <button class="btn gh" data-a="fotoretomar">Elegir otra</button>
           <button class="btn pri" data-a="fotoidentificar">✨ Identificar con IA</button>
         </div>`}
  `}
  `, `<button class="btn gh" data-a="cerrar">Cancelar</button>`, '480px');
};

/* ==================== Acciones ==================== */
function abrir(m, ctx) { ui.modal = m; ui.ctx = ctx || null; render(); }
function cerrar() {
  pararCam(); limpiarFotoSeleccionada();
  ui.modal = null; ui.ctx = null; ui.apLiq = null; ui.fotoPendiente = null; ui.avisoIA = ''; ui.identificando = false;
  render();
}

document.addEventListener('click', async (e) => {
  if (e.target.classList && e.target.classList.contains('ov')) { cerrar(); return; }
  const el = e.target.closest('[data-a]'); if (!el) return;
  const a = el.dataset.a, id = el.dataset.id;
  switch (a) {
    /* --- acceso --- */
    case 'authtab': ui.authTab = el.dataset.v; ui.authErr = ''; render(); break;
    case 'auth': await autenticar(); break;
    case 'salir': if (confirm('¿Cerrar sesión en este dispositivo?')) salir(); break;
    case 'tema': aplicarTema(el.dataset.t); render(); break;

    /* --- navegación --- */
    case 'nav': ui.vista = el.dataset.v; ui.modal = null; ui.sel = []; ui.selMode = false; render(); window.scrollTo(0, 0); break;
    case 'cerrar': cerrar(); break;
    case 'mesesgraf': ui.mesesGraf = Math.max(1, Math.min(36, num(el.dataset.v))); try { localStorage.setItem('cw_mesesGraf', ui.mesesGraf); } catch (e) { /* sin almacenamiento */ } render(); break;
    case 'repsec': {
      const v = el.dataset.v;
      ui.rep.secciones = ui.rep.secciones.includes(v) ? ui.rep.secciones.filter((x) => x !== v) : ui.rep.secciones.concat(v);
      guardarRep(); render(); break; }
    case 'reportepdf': await reportePDF(); break;
    case 'recibo': await bajarPDF(`/ventas/${id}/recibo`, `recibo-${id}.pdf`, 'GET'); break;
    case 'publote': abrir('publote', ui.sel.map(art).filter(Boolean)); break;
    case 'fotofb': await bajarPDF(`/articulos/${id}/foto-publicar`, `${id}-facebook.jpg`, 'GET'); break;
    case 'nuevoped': abrir('pedido', null); break;
    case 'saveped': await savePedido(); break;
    case 'pedok': await accion(() => PATCH('/pedidos/' + id, { atendido: el.dataset.v === '1' }), 'Pedido actualizado'); break;
    case 'delped': await accion(() => DEL('/pedidos/' + id), 'Pedido quitado'); break;
    case 'mattel': await traerMattel(); break;
    case 'yallego': await yaLlego(id); break;
    case 'yallegotodas': await yaLlego(null); break;
    case 'compramattel': ui.mm = { texto: '', filas: [], cargando: false }; abrir('mattelmulti', null); break;
    case 'mmtraer': await mmTraer(); break;
    case 'mmguardar': await mmGuardar(); break;
    case 'nuevoenc': ui.enc = encNuevo(); abrir('encargo', null); break;
    case 'editenc': { const e = db.encargos.find((x) => x.id === id); ui.enc = { id, comprador_id: e.comprador_id || '', cliente_nuevo: '', tel_nuevo: '', fecha_entrega: e.fecha_entrega || '', anticipo: e.anticipo || '', forma_anticipo: e.forma_anticipo || 'Depósito', notas: e.notas || '', items: e.items.map((i) => ({ articulo_id: i.articulo_id, cantidad: i.cantidad, precio_unit: String(i.precio_unit) })) }; abrir('encargo', null); break; }
    case 'encadd': snapEnc(); ui.enc.items.push({ articulo_id: '', cantidad: 1, precio_unit: '' }); render(); break;
    case 'encrm': snapEnc(); ui.enc.items.splice(num(el.dataset.i), 1); render(); break;
    case 'saveenc': await saveEnc(); break;
    case 'encsab': snapEnc(); ui.enc.fecha_entrega = el.dataset.v; render(); break;
    case 'encrapido': {
      const e = db.encargos.find((x) => x.id === id), c = cli(e.comprador_id) || {};
      if (!confirm(`¿Entregar a ${c.nombre || 'el cliente'} y cobrar ${money(e.resta)} por ${el.dataset.v.toLowerCase()}?`)) break;
      const r = await accion(() => POST(`/encargos/${id}/entregar`, { cobrado: e.resta, forma: el.dataset.v }));
      toast(r.debe > 0 ? `Entregado. Te debe ${money(r.debe)}` : `Liquidado · ${money(e.resta)} en ${el.dataset.v.toLowerCase()}`); break; }
    case 'encwa': mensajeCliente(db.encargos.find((x) => x.id === id)); break;
    case 'enctab': ui.encTab = el.dataset.v; render(); break;
    case 'encempacar': await accion(() => PATCH('/encargos/' + id, { estatus: el.dataset.v }), el.dataset.v === 'Empacado' ? 'Marcado como empacado' : 'Desempacado'); break;
    case 'encentregar': abrir('encentregar', db.encargos.find((x) => x.id === id)); break;
    case 'saveentrega': {
      const r = await accion(() => POST(`/encargos/${id}/entregar`, { total_final: num($('#ee_total').value), cobrado: num($('#ee_cobrado').value), forma: $('#ee_forma').value }));
      cerrar(); toast(r.debe > 0 ? `Entregado. Te debe ${money(r.debe)}` : 'Entregado y registrado como venta'); break; }
    case 'enccancelar': if (confirm('¿Cancelar este encargo? Las piezas quedan libres otra vez.')) await accion(() => PATCH('/encargos/' + id, { estatus: 'Cancelado' }), 'Encargo cancelado'); break;
    case 'encborrar': await accion(() => DEL('/encargos/' + id), 'Encargo borrado'); break;
    case 'hojaexcel': await bajarPDF('/encargos/hoja-entrega-excel', `pedidos-${hoy()}.xlsx`, 'POST', { fecha: ui.encFecha === null ? ([...new Set(encActivos().map((e) => e.fecha_entrega).filter(Boolean))].sort().find((f) => f >= hoy()) || '') : ui.encFecha, incluir_costos: ui.encCostos }); break;
    case 'hojaent': await bajarPDF('/encargos/hoja-entrega', `hoja-entrega-${hoy()}.pdf`, 'POST', { fecha: ui.encFecha === null ? ([...new Set(encActivos().map((e) => e.fecha_entrega).filter(Boolean))].sort().find((f) => f >= hoy()) || '') : ui.encFecha, incluir_costos: ui.encCostos }); break;
    case 'ftipo': ui.fTipo = el.dataset.v; render(); break;
    case 'modoinv': ui.modoInv = el.dataset.v; try { localStorage.setItem('cw_modoInv', ui.modoInv); } catch (e) { /* sin almacenamiento */ } render(); break;
    case 'ordcol': ui.colDir = ui.colOrd === el.dataset.v ? -ui.colDir : 1; ui.colOrd = el.dataset.v; render(); break;
    case 'festatus': ui.fEstatus = el.dataset.v; render(); break;
    case 'selmode': ui.selMode = !ui.selMode; if (!ui.selMode) ui.sel = []; render();
      toast(ui.selMode ? 'Toca las piezas que quieras agrupar' : 'Selección desactivada'); break;
    case 'limpiarsel': ui.sel = []; ui.selMode = false; render(); break;
    case 'ver': if (ui.selMode || e.shiftKey || ui.sel.length) { toggleSel(id); } else abrir('ver', art(id)); break;

    /* --- alta y edición --- */
    case 'nuevo': ui.formTipo = 'Hot Wheels'; abrir('pieza', null); break;
    case 'fotoia': limpiarFotoSeleccionada(); abrir('foto', null); break;
    case 'fotoretomar': limpiarFotoSeleccionada(); render(); break;
    case 'fotoidentificar': await identificarFoto(); break;
    case 'tipo': ui.ctx = snapPieza(); ui.formTipo = el.dataset.t; render(); break;
    case 'editpieza': ui.formTipo = art(id).tipo; abrir('pieza', art(id)); break;
    case 'qtipo': ui.qTipo = el.dataset.t; render(); break;
    case 'qtipo2': ui.formTipo = el.dataset.t; render(); break;
    case 'savepieza': await savePieza(); break;
    case 'delpieza':
      if (confirm('¿Eliminar esta pieza del inventario?')) {
        await accion(() => DEL('/articulos/' + id), 'Pieza eliminada'); cerrar();
      } break;

    /* --- valuación --- */
    case 'valuar': abrir('historial', art(id)); break;
    case 'saveval': await saveVal(id); break;
    case 'delval':
      await accion(() => DEL(`/articulos/${id}/valuaciones/${el.dataset.val}`), 'Valuación eliminada');
      ui.ctx = art(id); render(); break;

    /* --- ventas --- */
    case 'vender': ui.apLiq = null; abrir('venta', art(id)); break;
    case 'bazarvender': {
      ui.apLiq = null; abrir('venta', art(id));
      const s = $('#v_plat');
      if (s) { const bz = db.plataformas.find((p) => /bazar|conven/i.test(p.nombre)); if (bz) s.value = bz.id; pintarVenta(); }
      break; }
    case 'saveventa': await saveVenta(el.dataset.ap); break;
    case 'delventa':
      if (confirm('¿Cancelar esta venta? La pieza regresa al inventario.')) {
        await accion(() => DEL('/ventas/' + id), (r) => `Venta cancelada · ${r.stock_devuelto} pieza(s) de vuelta`);
      } break;
    case 'objetivo': await calcObjetivo(); break;
    case 'usarprecio': $('#v_precio').value = el.dataset.p; pintarVenta(); break;

    /* --- lotes --- */
    case 'lote':
      if (ui.sel.length < 2) { toast('Selecciona al menos dos piezas', true); break; }
      abrir('lote', null); break;
    case 'savelote': await saveLote(); break;

    /* --- apartados --- */
    case 'apartar': ui.enc = encNuevo(); ui.enc.items[0].articulo_id = id; ui.enc.items[0].precio_unit = String((art(id) || {}).valor_estimado || ''); abrir('encargo', null); break;
    case 'nuevoapartado': ui.enc = encNuevo(); abrir('encargo', null); break;
    case 'saveapartado': await saveApartado(); break;
    case 'liquidar': { const x = db.apartados.find((y) => y.id === id); ui.apLiq = x; abrir('venta', art(x.id_articulo)); break; }
    case 'cancelapartado':
      if (confirm('¿Cancelar el apartado y liberar la pieza? El anticipo queda a tu criterio.')) {
        await accion(() => POST(`/apartados/${id}/cancelar`), 'Apartado cancelado, pieza liberada');
      } break;

    /* --- intercambios --- */
    case 'tradeSel': ui.tradeOut = ui.sel.slice(); ui.tradeIn = []; ui.tradeQuien = ''; abrir('trade', null); break;
    case 'nuevotrade': ui.tradeOut = []; ui.tradeIn = []; ui.tradeQuien = ''; abrir('trade', null); break;
    case 'tradeadd': { const v = $('#t_add').value; if (v) { snapTrade(); ui.tradeOut = (ui.tradeOut || []).concat(v); render(); } break; }
    case 'traderm': snapTrade(); ui.tradeOut = (ui.tradeOut || []).filter((x) => x !== id); render(); break;
    case 'tradein': {
      const n = $('#t_nom').value.trim();
      if (!n) { toast('Falta el nombre de lo que recibes', true); break; }
      snapTrade();
      ui.tradeIn = (ui.tradeIn || []).concat({ nombre: n, tipo: $('#t_tipo').value, valor: num($('#t_val').value) });
      render(); break; }
    case 'tradeinrm': snapTrade(); ui.tradeIn = (ui.tradeIn || []).filter((_, i) => i !== num(el.dataset.i)); render(); break;
    case 'savetrade': await saveTrade(); break;
    case 'deltrade':
      if (confirm('¿Eliminar este intercambio del historial? Las piezas no regresan solas.')) {
        await accion(() => DEL('/intercambios/' + id), 'Intercambio eliminado');
      } break;

    /* --- catálogos --- */
    case 'nuevocomp': abrir('comprador', null); break;
    case 'editcomp': abrir('comprador', cli(id)); break;
    case 'savecomp': await saveComp(); break;
    case 'delcomp':
      if (confirm('¿Eliminar este comprador? Sus ventas conservan el historial.')) {
        await accion(() => DEL('/compradores/' + id), 'Comprador eliminado'); cerrar();
      } break;
    case 'nuevoplat': abrir('plataforma', null); break;
    case 'editplat': abrir('plataforma', plat(id)); break;
    case 'saveplat': await savePlat(); break;
    case 'delplat':
      if (confirm('¿Eliminar este canal? Las ventas ya registradas conservan su comisión congelada.')) {
        await accion(() => DEL('/plataformas/' + id), 'Canal eliminado'); cerrar();
      } break;
    case 'nuevowish': abrir('wish', null); break;
    case 'savewish': await saveWish(); break;
    case 'delwish': await accion(() => DEL('/wishlist/' + id), 'Quitado de faltantes'); break;
    case 'wish2art': {
      const w = db.wishlist.find((x) => x.id === id);
      await accion(() => DEL('/wishlist/' + id));
      ui.formTipo = w.tipo;
      abrir('pieza', { nombre: w.nombre, tipo: w.tipo, precio_compra: w.tope });
      break; }

    /* --- herramientas --- */
    case 'publicacion': abrir('publicacion', art(id)); break;
    case 'copiar': {
      const t = $('#pub_txt'); t.select();
      try { document.execCommand('copy'); toast('Texto copiado'); } catch (x) { toast('Selecciona y copia manualmente', true); }
      break; }
    case 'escanear': escanear(el.dataset.target || null); break;
    case 'scman': { const v = $('#sc_man').value.trim(); if (v) aplicarCodigo(v); break; }
    case 'imprimir': window.print(); break;

    /* --- datos --- */
    case 'export': await exportar(); break;
    case 'csv': exportarCSV(); break;
    case 'csvventas': exportarVentasCSV(); break;
    case 'demo':
      if (confirm('Esto reemplaza tus datos actuales por un ejemplo. ¿Continuar?')) {
        await accion(() => POST('/seed'), 'Datos de ejemplo cargados');
      } break;
    case 'wipe':
      if (confirm('Se borra TODO: inventario, ventas, apartados y clientes. ¿Seguro?')) {
        await accion(() => DEL('/estado'), 'Todo borrado');
      } break;
  }
});

document.addEventListener('input', (e) => {
  const el = e.target.closest('[data-a]'); if (!el) return;
  if (el.dataset.a === 'q') {
    ui.q = el.value; const p = el.selectionStart;
    if (ui.vista !== 'inventario' && ui.vista !== 'bazar') ui.vista = 'inventario';
    render();
    const n = $('[data-a="q"]'); if (n) { n.focus(); try { n.setSelectionRange(p, p); } catch (x) {} }
  }
  if (el.dataset.a === 'recalc') pintarVenta();
  if (el.dataset.a === 'recalcLote') pintarLote();
});

const id0 = (el) => el.dataset.id;
document.addEventListener('change', async (e) => {
  const el = e.target.closest('[data-a]'); if (!el) return;
  const a = el.dataset.a;
  if (a === 'orden') { ui.orden = el.value; render(); }
  if (a === 'festatus_sel') { ui.fEstatus = el.value; render(); }
  if (a === 'mesesgraf_in') { ui.mesesGraf = Math.max(1, Math.min(36, num(el.value) || 6)); try { localStorage.setItem('cw_mesesGraf', ui.mesesGraf); } catch (e) { /* sin almacenamiento */ } render(); }
  if (a === 'repcfg') { ui.rep[el.dataset.k] = el.type === 'checkbox' ? el.checked : el.value; guardarRep(); }
  if (a === 'fentrega' && el.value) await accion(() => PATCH('/ventas/' + el.dataset.id, { estatus_envio: 'Entregado', fecha_entrega: el.value }), 'Fecha de entrega guardada');
  if (a === 'apcliente') { $('#ap_nuevo').style.display = el.value ? 'none' : ''; }
  if (a === 'encchg') { snapEnc(); render(); }
  if (a === 'encfecha') { ui.encFecha = el.value; render(); }
  if (a === 'enccostos') { ui.encCostos = el.checked; }
  if (a === 'pubdesc') { ui.pubDesc = Math.max(0, Math.min(90, num(el.value))); render(); }
  if (a === 'recalc') pintarVenta();
  if (a === 'recalcLote') pintarLote();
  if (a === 'envio') await accion(() => PATCH('/ventas/' + el.dataset.id, { estatus_envio: el.value }), 'Estatus de envío actualizado');
  if (a === 'set') {
    const valor = el.type === 'number' ? num(el.value) : el.value;
    await accion(() => PATCH('/ajustes', { [el.dataset.k]: valor }), 'Ajuste guardado');
  }
  if (a === 'importar') {
    const archivo = el.files[0];
    el.value = ''; // permite volver a elegir el mismo archivo después
    if (archivo) importarInventario(archivo);
  }
  if (a === 'fotoelegida') {
    const archivo = el.files[0];
    el.value = '';
    if (archivo) await prepararFoto(archivo);
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && ui.modal) cerrar();
  if (e.key === 'Enter' && !token) autenticar();
});

function toggleSel(id) { ui.sel = ui.sel.includes(id) ? ui.sel.filter((x) => x !== id) : ui.sel.concat(id); render(); }
function snapTrade() {
  if ($('#t_quien')) ui.tradeQuien = $('#t_quien').value;
  if ($('#t_notas')) ui.tradeNotas = $('#t_notas').value;
}

/** Conserva lo escrito cuando el formulario se redibuja al cambiar de tipo. */
function snapPieza() {
  const g = (id, d) => { const e = $('#' + id); return e ? (e.type === 'checkbox' ? e.checked : e.value) : d; };
  const b = Object.assign({}, ui.ctx || {});
  return Object.assign(b, {
    nombre: g('f_nombre', b.nombre), numero: g('f_numero', b.numero), anio: g('f_anio', b.anio),
    serie: g('f_serie', b.serie), color: g('f_color', b.color), expansion: g('f_expansion', b.expansion),
    rareza: g('f_rareza', b.rareza), grado: g('f_grado', b.grado), cert: g('f_cert', b.cert),
    cantidad: g('f_cantidad', b.cantidad), precio_compra: g('f_compra', b.precio_compra),
    valor_estimado: g('f_valor', b.valor_estimado), fecha_adq: g('f_fadq', b.fecha_adq),
    fuente: g('f_fuente', b.fuente), estatus: g('f_estatus', b.estatus), ubicacion: g('f_ubic', b.ubicacion),
    codigo: g('f_codigo', b.codigo), foto: g('f_foto', b.foto), notas: g('f_notas', b.notas), grail: g('f_grail', b.grail),
  });
}

/* ==================== Guardados ==================== */
function leerPieza() {
  return {
    tipo: ui.formTipo,
    nombre: $('#f_nombre').value.trim(),
    numero: $('#f_numero').value.trim(),
    anio: $('#f_anio').value,
    serie: $('#f_serie') ? $('#f_serie').value : '',
    color: $('#f_color') ? $('#f_color').value.trim() : '',
    expansion: $('#f_expansion') ? $('#f_expansion').value.trim() : '',
    rareza: $('#f_rareza') ? $('#f_rareza').value : '',
    grado: $('#f_grado') ? $('#f_grado').value : '',
    cert: $('#f_cert') ? $('#f_cert').value.trim() : '',
    sub: $('#f_sub').value,
    estado: $('#f_estado').value,
    cantidad: num($('#f_cantidad').value),
    estatus: $('#f_estatus').value,
    precio_compra: num($('#f_compra').value),
    valor_estimado: num($('#f_valor').value),
    fecha_adq: $('#f_fadq').value,
    fuente: $('#f_fuente').value,
    ubicacion: $('#f_ubic').value.trim(),
    codigo: $('#f_codigo').value.trim(),
    foto: $('#f_foto') ? $('#f_foto').value.trim() : '',
    notas: $('#f_notas').value.trim(),
    grail: $('#f_grail').checked,
    checks: $$('[data-chk]').filter((c) => c.checked).map((c) => num(c.dataset.chk)),
  };
}
async function savePieza() {
  const datos = leerPieza();
  if (!datos.nombre) { toast('Ponle nombre a la pieza', true); $('#f_nombre').focus(); return; }
  const ed = ui.ctx && ui.ctx.id;
  const fotoPendiente = ui.fotoPendiente; // cerrar() la limpia, hay que guardarla antes
  try {
    const r = await accion(() => (ed ? PATCH('/articulos/' + ed, datos) : POST('/articulos', datos)));
    if (fotoPendiente) {
      try { await subirFotoArticulo(r.id, fotoPendiente); await cargarEstado(); }
      catch (e) { toast('Se guardó la pieza, pero la foto no se pudo adjuntar: ' + e.message, true); }
    }
    cerrar();
    const int = db.compradores.filter((c) => c.interes === datos.tipo || c.interes === 'Ambas').map((c) => c.nombre);
    toast(int.length ? `Guardada. Avísale a ${int.slice(0, 2).join(' y ')}` : 'Pieza registrada');
  } catch (e) { /* el toast de error ya salió */ }
}
async function saveVenta(apId) {
  const a = ui.ctx;
  const precio = num($('#v_precio').value);
  if (!precio) { toast('Falta el precio cobrado', true); $('#v_precio').focus(); return; }
  const cuerpo = {
    articulo_id: a.id, plataforma_id: $('#v_plat').value, comprador_id: $('#v_comp').value,
    cantidad: num($('#v_cant').value) || 1, precio,
    envio: num($('#v_envio').value), otros: num($('#v_otros').value),
    fecha: $('#v_fecha').value || hoy(), guia: $('#v_guia').value.trim(),
    apartado_id: apId || undefined,
  };
  try {
    await accion(() => POST('/ventas', cuerpo), (v) => (v.ganancia_neta >= 0
      ? `Venta registrada · ${money(v.ganancia_neta)} limpios`
      : `Venta registrada · pérdida de ${money(Math.abs(v.ganancia_neta))}`));
    cerrar();
  } catch (e) { /* error ya reportado */ }
}
async function saveVal(id) {
  const valor = num($('#h_valor').value);
  if (!valor) { toast('Escribe el valor observado', true); return; }
  const cuerpo = { valor, fecha: $('#h_fecha').value || hoy(), fuente: $('#h_fuente').value, actualizar: $('#h_actualiza').checked };
  try {
    await accion(() => POST(`/articulos/${id}/valuaciones`, cuerpo));
    ui.ctx = art(id); render();
    const tr = tendencia(ui.ctx);
    toast(tr && tr.n > 1 ? `Valuación guardada · ${tr.delta >= 0 ? 'sube' : 'baja'} ${pct(Math.abs(tr.pct))} desde la primera` : 'Valuación guardada');
  } catch (e) { /* error ya reportado */ }
}
async function saveApartado() {
  const a = ui.ctx || art($('#ap_art') ? $('#ap_art').value : '');
  if (!a) { toast('Elige una pieza', true); return; }
  if (!$('#ap_comp').value && !($('#ap_nombre').value || '').trim()) { toast('Escribe el nombre del cliente que aparta', true); return; }
  const cuerpo = {
    articulo_id: a.id, comprador_id: $('#ap_comp').value, cliente_nuevo: ($('#ap_nombre').value || '').trim(), tel_nuevo: ($('#ap_tel').value || '').trim(),
    cantidad: num($('#ap_cant').value) || 1,
    precio_acordado: num($('#ap_precio').value), anticipo: num($('#ap_ant').value),
    fecha_limite: $('#ap_lim').value, notas: $('#ap_notas').value.trim(), lugar_entrega: $('#ap_lugar').value.trim() || 'Balderas',
  };
  try {
    await accion(() => POST('/apartados', cuerpo),
      (x) => `Apartada · restan ${money(num(x.precio_acordado) - num(x.anticipo))} por cobrar`);
    cerrar();
  } catch (e) { /* error ya reportado */ }
}
async function saveLote() {
  const cuerpo = {
    articulo_ids: ui.sel.slice(), plataforma_id: $('#l_plat').value, comprador_id: $('#l_comp').value,
    precio: num($('#l_precio').value), envio: num($('#l_envio').value), fecha: $('#l_fecha').value || hoy(),
  };
  if (!cuerpo.precio) { toast('Falta el precio del lote', true); return; }
  try {
    const n = ui.sel.length;
    ui.sel = []; ui.selMode = false;
    await accion(() => POST('/ventas/lote', cuerpo), `Lote de ${n} piezas registrado`);
    cerrar();
  } catch (e) { render(); }
}
async function saveTrade() {
  snapTrade();
  const cuerpo = {
    contraparte: ui.tradeQuien || '', notas: ui.tradeNotas || '', fecha: $('#t_fecha').value || hoy(),
    entrega_ids: ui.tradeOut || [], recibidos: ui.tradeIn || [],
  };
  if (!cuerpo.entrega_ids.length && !cuerpo.recibidos.length) { toast('Agrega al menos una pieza', true); return; }
  try {
    await accion(() => POST('/intercambios', cuerpo), (t) => (num(t.diferencia) >= 0
      ? `Intercambio guardado · ganaste ${money(t.diferencia)} de valor`
      : `Intercambio guardado · entregaste ${money(Math.abs(t.diferencia))} de más`));
    ui.tradeOut = []; ui.tradeIn = []; ui.tradeQuien = ''; ui.tradeNotas = ''; ui.sel = []; ui.selMode = false;
    cerrar();
  } catch (e) { /* error ya reportado */ }
}
async function saveComp() {
  const cuerpo = { nombre: $('#c_nombre').value.trim(), tel: $('#c_tel').value.trim(),
    interes: $('#c_interes').value, notas: $('#c_notas').value.trim() };
  if (!cuerpo.nombre) { toast('Falta el nombre', true); return; }
  const ed = ui.ctx && ui.ctx.id;
  try {
    await accion(() => (ed ? PATCH('/compradores/' + ed, cuerpo) : POST('/compradores', cuerpo)), 'Comprador guardado');
    cerrar();
  } catch (e) { /* error ya reportado */ }
}
async function savePlat() {
  const cuerpo = {
    nombre: $('#p_nombre').value.trim(), codigo: $('#p_codigo').value.trim(),
    com_pct: num($('#p_pct').value) / 100, com_fija: num($('#p_fija').value),
    ret_pct: num($('#p_ret').value) / 100, notas: $('#p_notas').value.trim(),
  };
  if (!cuerpo.nombre) { toast('Falta el nombre del canal', true); return; }
  const ed = ui.ctx && ui.ctx.id;
  try {
    await accion(() => (ed ? PATCH('/plataformas/' + ed, cuerpo) : POST('/plataformas', cuerpo)), 'Canal guardado');
    cerrar();
  } catch (e) { /* error ya reportado */ }
}
/** Precarga el formulario con los datos de un link de Mattel (no guarda nada). */
async function traerMattel() {
  const url = ($('#f_mattel').value || '').trim();
  if (!url) { toast('Pega el link de la pieza en Mattel', true); return; }
  try {
    const d = await POST('/articulos/desde-mattel', { url });
    const b = snapPieza();
    ui.ctx = Object.assign(b, {
      nombre: d.nombre, precio_compra: d.precio_mxn, valor_estimado: b.valor_estimado || d.precio_mxn,
      fuente: 'Mattel Creations', foto: d.imagen || b.foto,
      notas: [b.notas, `Mattel: ${d.url}`, `Precio en Mattel: US$${d.precio_usd} (TC ${d.tipo_cambio})`].filter(Boolean).join('\n'),
    });
    if (/\b(pokemon|pokémon)\b/i.test(d.nombre)) ui.formTipo = 'Pokémon';
    render();
    toast(d.disponible ? 'Datos traídos de Mattel' : 'Datos traídos (ojo: hoy aparece agotada en Mattel)');
  } catch (e) { toast(e.message, true); }
}
/** Marca como recibidas las piezas "Por recibir": una sola o todas. */
async function yaLlego(id) {
  const ub = ($('#ub_llegada').value || '').trim();
  if (!ub) { toast('Escribe en qué ubicación las guardas (ej. Caja A)', true); return; }
  ui.ubLlegada = ub;
  const l = id ? [art(id)] : porRecibir();
  try {
    await accion(async () => { for (const a of l) await PATCH('/articulos/' + a.id, { ubicacion: ub }); },
      l.length === 1 ? 'Pieza recibida' : `${l.length} piezas recibidas`);
  } catch (e) { /* error ya reportado */ }
}
async function savePedido() {
  const cuerpo = { comprador_id: $('#pe_comp').value || null, descripcion: $('#pe_desc').value.trim(), tope: num($('#pe_tope').value) };
  if (!cuerpo.descripcion) { toast('¿Qué está buscando el cliente?', true); return; }
  try { await accion(() => POST('/pedidos', cuerpo), 'Pedido guardado'); cerrar(); } catch (e) { /* error ya reportado */ }
}
async function saveWish() {
  const cuerpo = { nombre: $('#w_nombre').value.trim(), tipo: $('#w_tipo').value,
    tope: num($('#w_tope').value), prioridad: num($('#w_prio').value), detalle: $('#w_detalle').value.trim() };
  if (!cuerpo.nombre) { toast('¿Qué estás buscando?', true); return; }
  try { await accion(() => POST('/wishlist', cuerpo), 'Agregado a faltantes'); cerrar(); } catch (e) {}
}

/** El precio objetivo lo calcula el servidor: una sola fórmula para todos. */
async function calcObjetivo() {
  const a = ui.ctx, cant = num($('#v_cant').value) || 1, meta = num($('#v_meta').value);
  if (!meta) { $('#v_obj').innerHTML = '<span style="color:var(--muted);font-size:12.5px">Escribe cuánto quieres ganar.</span>'; return; }
  try {
    const r = await POST('/calculadora/precio-objetivo', {
      plataforma_id: $('#v_plat').value, deseado: meta, costo_total: num(a.precio_compra) * cant,
      envio: num($('#v_envio').value), otros: num($('#v_otros').value),
    });
    $('#v_obj').innerHTML = `<div style="font-size:13px">Publica en <b class="mn pos" style="font-size:17px">${money(r.precio)}</b>
      para ganar ${money(meta)} limpios en ${esc(r.plataforma)}.
      <button class="btn sm" data-a="usarprecio" data-p="${r.precio.toFixed(2)}" style="margin-left:8px">Usar este precio</button></div>`;
  } catch (e) { toast(e.message, true); }
}

/* ==================== Escáner ==================== */
async function escanear(target) {
  ui.scanTarget = target; abrir('escaner', null);
  const msg = $('#sc_msg'), vid = $('#sc_vid');
  if (!window.BarcodeDetector) { msg.innerHTML = 'Tu navegador no soporta el lector de códigos. Escribe el código a mano abajo, funciona igual.'; return; }
  try {
    const st = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    ui.stream = st; vid.srcObject = st; msg.innerHTML = 'Apunta al código de barras del blíster.';
    const det = new window.BarcodeDetector();
    const loop = async () => {
      if (!ui.stream) return;
      try { const c = await det.detect(vid); if (c && c.length) { aplicarCodigo(c[0].rawValue); return; } } catch (e) {}
      setTimeout(loop, 320);
    };
    loop();
  } catch (e) { msg.innerHTML = 'No se pudo abrir la cámara. Revisa los permisos o escribe el código a mano.'; }
}
function pararCam() { if (ui.stream) { ui.stream.getTracks().forEach((t) => t.stop()); ui.stream = null; } }
function aplicarCodigo(code) {
  pararCam();
  const t = ui.scanTarget; ui.scanTarget = null;
  if (t) {
    ui.modal = null; render();
    const el = $('#' + t);
    if (el) { el.value = code; toast('Código capturado'); }
    else { ui.q = code; ui.vista = 'inventario'; render(); }
    return;
  }
  ui.modal = null;
  const enc = db.articulos.find((a) => a.codigo && a.codigo === code);
  if (enc) { abrir('ver', enc); toast('Pieza encontrada'); }
  else { ui.q = code; ui.vista = 'inventario'; render(); toast(`Sin coincidencias para ${code}`); }
}

/* ==================== Foto → IA ====================
 * Redimensionar en el navegador (vía <canvas>) antes de subir: baja el peso
 * (más rápido, más barato del lado de la API) y de paso corrige la
 * orientación EXIF, porque drawImage() ya pinta los píxeles como el
 * navegador los muestra, no como venían crudos del sensor. */
let fotoSeleccionada = null;
let previewUrlFoto = null;

function limpiarFotoSeleccionada() {
  if (previewUrlFoto) URL.revokeObjectURL(previewUrlFoto);
  previewUrlFoto = null; fotoSeleccionada = null;
}

function redimensionarImagen(archivo, ladoMax) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(archivo);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let w = img.naturalWidth, h = img.naturalHeight;
      if (Math.max(w, h) > ladoMax) {
        const escala = ladoMax / Math.max(w, h);
        w = Math.round(w * escala); h = Math.round(h * escala);
      }
      const lienzo = document.createElement('canvas');
      lienzo.width = w; lienzo.height = h;
      lienzo.getContext('2d').drawImage(img, 0, 0, w, h);
      lienzo.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('No se pudo procesar la imagen'))),
        'image/jpeg', 0.85);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Ese archivo no es una imagen válida')); };
    img.src = url;
  });
}

async function prepararFoto(archivo) {
  if (!archivo.type.startsWith('image/')) { toast('Elige un archivo de imagen', true); return; }
  try {
    limpiarFotoSeleccionada();
    fotoSeleccionada = await redimensionarImagen(archivo, 1280);
    previewUrlFoto = URL.createObjectURL(fotoSeleccionada);
    render();
  } catch (e) { toast(e.message, true); }
}

function avisoIA(s) {
  const alta = num(s.confianza) >= 0.7;
  const notas = (s.notas || '').trim();
  return `<div class="note ${alta ? 'g' : 'w'}"><b>${alta ? 'Alta confianza' : 'Revisa estos datos'}</b> — así los interpretó la IA${notas ? ': ' + esc(notas) : ''}<br>Corrige lo que haga falta antes de guardar.</div>`;
}

/** Sube un archivo por multipart a mano, sin pasar por api()/POST (esas
 * siempre mandan JSON) — mismo patrón que importarInventario(). */
async function subirArchivo(ruta, campo, blob, nombre) {
  const fd = new FormData();
  fd.append(campo, blob, nombre);
  const r = await fetch('/api' + ruta, {
    method: 'POST',
    headers: token ? { Authorization: 'Bearer ' + token } : {},
    body: fd,
  });
  let datos = null;
  try { datos = await r.json(); } catch (e) { /* sin cuerpo */ }
  if (r.status === 401) { salir(true); throw new Error('Tu sesión expiró, vuelve a entrar'); }
  if (!r.ok) throw new Error((datos && datos.error) || 'No se pudo completar la operación');
  return datos;
}

async function identificarFoto() {
  if (!fotoSeleccionada || ui.identificando) return;
  ui.identificando = true; render();
  try {
    const sugerencia = await subirArchivo('/articulos/identificar', 'foto', fotoSeleccionada, 'foto.jpg');
    ui.formTipo = sugerencia.tipo === 'Pokémon' ? 'Pokémon' : 'Hot Wheels';
    ui.avisoIA = avisoIA(sugerencia);
    ui.fotoPendiente = fotoSeleccionada;
    ui.identificando = false;
    abrir('pieza', sugerencia);
  } catch (e) {
    ui.identificando = false; render();
    toast(e.message, true);
  }
}

async function subirFotoArticulo(id, blob) {
  return subirArchivo(`/articulos/${id}/foto`, 'foto', blob, 'foto.jpg');
}

/* ==================== Exportar ==================== */
function bajar(n, c, m) {
  const b = new Blob([c], { type: m }), u = URL.createObjectURL(b);
  const a = document.createElement('a'); a.href = u; a.download = n; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 400);
}
const csvq = (s) => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
function guardarRep() { try { localStorage.setItem('cw_reporte', JSON.stringify(ui.rep)); } catch (e) { /* sin almacenamiento */ } }
/** Descarga un PDF del servidor (lleva el token, por eso no es un simple enlace). */
async function bajarPDF(ruta, nombre, metodo, cuerpo) {
  try {
    const r = await fetch('/api' + ruta, {
      method: metodo, headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: cuerpo ? JSON.stringify(cuerpo) : undefined,
    });
    if (r.status === 401) { salir(true); return; }
    if (!r.ok) { let d = null; try { d = await r.json(); } catch (e) { /* sin cuerpo */ } throw new Error((d && d.error) || 'No se pudo generar el archivo'); }
    const blob = await r.blob(), u = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = u; a.download = nombre; a.click();
    setTimeout(() => URL.revokeObjectURL(u), 400);
    toast('Archivo listo');
  } catch (e) { toast(e.message, true); }
}
/** Reporte configurable del panel de Datos. */
async function reportePDF() {
  if (!ui.rep.secciones.length) { toast('Elige al menos una sección', true); return; }
  await bajarPDF('/reporte-pdf', `reporte-${hoy()}.pdf`, 'POST', ui.rep);
}
async function exportar() {
  try {
    const datos = await GET('/exportar');
    bajar(`chicos-wheels-${hoy()}.json`, JSON.stringify(datos, null, 2), 'application/json');
    toast('Respaldo descargado');
  } catch (e) { toast(e.message, true); }
}

/** Sube el .xlsx de inventario al servidor para darlo de alta en lote.
 * No usa api()/POST porque esas siempre mandan JSON; un archivo va como
 * multipart/form-data, y con FormData el navegador arma el boundary solo
 * (por eso no se fija el header Content-Type a mano). */
async function importarInventario(archivo) {
  if (ui.ocupado) return;
  ui.ocupado = true;
  try {
    const formData = new FormData();
    formData.append('archivo', archivo);
    const r = await fetch('/api/articulos/importar', {
      method: 'POST',
      headers: token ? { Authorization: 'Bearer ' + token } : {},
      body: formData,
    });
    let datos = null;
    try { datos = await r.json(); } catch (e) { /* sin cuerpo */ }
    if (r.status === 401) { salir(true); throw new Error('Tu sesión expiró, vuelve a entrar'); }
    if (!r.ok) throw new Error((datos && datos.error) || 'No se pudo importar el archivo');

    await cargarEstado();
    const { insertados, errores } = datos;
    if (!errores.length) {
      toast(`${insertados} pieza(s) importada(s) correctamente.`);
    } else {
      const detalle = errores.slice(0, 3).map((e) => `fila ${e.fila}: ${e.mensaje}`).join(' · ');
      toast(`${insertados} importada(s), ${errores.length} con error — ${detalle}${errores.length > 3 ? '…' : ''}`, insertados === 0);
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    ui.ocupado = false;
  }
}
function exportarCSV() {
  const c = ['id', 'tipo', 'nombre', 'numero', 'anio', 'serie', 'color', 'expansion', 'rareza', 'grado', 'cert', 'sub',
    'estado', 'cantidad', 'disponible', 'estatus', 'precio_compra', 'valor_estimado', 'fecha_adq', 'fuente', 'ubicacion', 'codigo', 'notas'];
  bajar(`inventario-${hoy()}.csv`, [c.join(','), ...db.articulos.map((a) => c.map((k) => csvq(a[k])).join(','))].join('\n'), 'text/csv');
  toast('Inventario exportado');
}
function exportarVentasCSV() {
  const c = ['id', 'fecha', 'nombre_snap', 'cantidad', 'precio', 'costo_unit', 'com_pct', 'com_fija', 'ret_pct',
    'envio', 'otros', 'plataforma_snap', 'lote_id', 'ganancia_neta'];
  bajar(`ventas-${hoy()}.csv`, [c.join(','), ...db.ventas.map((v) => c.map((k) => csvq(v[k])).join(','))].join('\n'), 'text/csv');
  toast('Ventas exportadas');
}

/* ==================== Arranque ==================== */
(async function iniciar() {
  aplicarTema(temaGuardado());
  // El registro vive aquí (JS externo) y no en index.html porque el CSP no
  // permite <script> inline — script-src solo admite 'self' y el CDN de qrcodejs.
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  if (!token) { render(); return; }
  try {
    const r = await GET('/auth/yo');
    usuario = r.usuario;
    await cargarEstado();
  } catch (e) {
    salir(true);
  }
})();

})();
