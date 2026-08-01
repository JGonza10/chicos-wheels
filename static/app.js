/* ==========================================================================
   CollectHub · cliente
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
const FUENTES = ['Tienda / retail', 'Bazar o tianguis', 'Convención', 'Compra en línea', 'Intercambio', 'Regalo', 'Lote / colección completa'];
const CHECKS = {
  'Hot Wheels': ['Sello TH o STH visible en la carrocería', 'Llantas de goma reales (STH)', 'Tarjeta sin dobleces ni cortes', 'Blíster sellado de fábrica', 'Base metálica con tampo correcto'],
  'Pokémon': ['Textura y relieve correctos al tacto', 'Tipografía y bordes sin pixelado', 'Prueba de luz: capa negra interior', 'Reverso con centrado y color correctos', 'Certificado de graduación verificado'],
};

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
const DEL = (r) => api(r, { metodo: 'DELETE' });

/* ---------- Estado ---------- */
let db = null;
let usuario = null;
let ui = {
  vista: 'panel', q: '', fTipo: 'todos', fEstatus: 'todos', orden: 'reciente',
  modal: null, ctx: null, formTipo: 'Hot Wheels', sel: [], selMode: false,
  qTipo: 'Compra', stream: null, authTab: 'login', authErr: '', ocupado: false,
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
function semaforo(a) {
  if (a.estatus === 'Conservar') return { c: 'p', t: 'Conservar', col: 'var(--purple)' };
  if (!num(a.cantidad)) return { c: 'r', t: 'Agotado', col: 'var(--red)' };
  if (a.apartadas > 0) return { c: 'y', t: 'Apartado', col: 'var(--yellow)' };
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
    <div class="logo">COLLECT<i>HUB</i></div>
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
const NAV = [['panel', '◧', 'Panel'], ['inventario', '▦', 'Inventario'], ['bazar', '⚡', 'Modo bazar'],
  ['SEP1', '', 'Movimientos'], ['ventas', '⇄', 'Ventas'], ['apartados', '⏳', 'Apartados'], ['intercambios', '⇌', 'Intercambios'],
  ['SEP2', '', 'Catálogos'], ['compradores', '☺', 'Compradores'], ['wishlist', '★', 'Faltantes'],
  ['plataformas', '◈', 'Plataformas'], ['etiquetas', '▩', 'Etiquetas QR'], ['datos', '⛃', 'Datos']];
const CNT = {
  inventario: () => db.articulos.length, ventas: () => db.ventas.length,
  apartados: () => db.apartados.filter((x) => x.estatus === 'Vigente').length,
  intercambios: () => db.intercambios.length, compradores: () => db.compradores.length,
  wishlist: () => db.wishlist.length,
};

function render() {
  if (!token) { $('#app').innerHTML = vistaAuth(); return; }
  if (!db) { $('#app').innerHTML = '<div class="cargando"><div><div class="spin"></div>Cargando tu colección…</div></div>'; return; }
  const V = { panel: vPanel, inventario: vInv, bazar: vBazar, ventas: vVentas, apartados: vApart,
    intercambios: vTrade, compradores: vComp, wishlist: vWish, plataformas: vPlat, etiquetas: vQR, datos: vDatos }[ui.vista] || vPanel;
  $('#app').innerHTML = `
  <div class="shell">
    <aside class="side">
      <div class="logo">COLLECT<i>HUB</i><small>${esc((usuario && (usuario.nombre || usuario.email)) || '')}</small></div>
      <nav class="nav">${NAV.map((n) => (n[0].startsWith('SEP')
        ? `<div class="navsep">${n[2]}</div>`
        : `<button data-a="nav" data-v="${n[0]}" class="${ui.vista === n[0] ? 'on' : ''}"><span class="ic">${n[1]}</span>${n[2]}<span class="cnt">${CNT[n[0]] ? (CNT[n[0]]() || '') : ''}</span></button>`)).join('')}
        <div class="salir"><button data-a="salir"><span class="ic">⏻</span>Cerrar sesión</button></div>
      </nav>
    </aside>
    <main class="main">${V()}</main>
  </div>
  <button class="fab" data-a="nuevo" title="Registrar pieza" aria-label="Registrar pieza">+</button>
  <nav class="mob">${NAV.filter((n) => !n[0].startsWith('SEP')).map((n) =>
    `<button data-a="nav" data-v="${n[0]}" class="${ui.vista === n[0] ? 'on' : ''}"><span class="ic">${n[1]}</span>${n[2].replace('Modo ', '')}</button>`).join('')}</nav>
  ${ui.modal ? `<div class="ov">${(MOD[ui.modal] || (() => ''))()}</div>` : ''}`;
  if (ui.modal === 'venta') pintarVenta();
  if (ui.modal === 'lote') pintarLote();
  if (ui.modal === 'historial') pintarChart();
  if (ui.vista === 'etiquetas') pintarQR();
}

function hdr(t, s, extra) {
  return `<div class="hdr"><div><h1>${t}<span>${s}</span></h1></div><div class="sp"></div>
  ${extra === undefined ? `<div class="srch"><input class="in" placeholder="Nombre, número, ubicación, código…" value="${esc(ui.q)}" data-a="q"></div>
  <button class="btn gh sm" data-a="escanear" title="Escanear código de barras">⌗ Escanear</button>
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

/* ---------- Panel ---------- */
function vPanel() {
  const s = stats();
  const titulo = 'COLLECT<i style="color:var(--yellow);font-style:normal">HUB</i>';
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
      <h2>Nuevo movimiento</h2>
      <div class="fld"><label class="lbl">${ui.qTipo === 'Venta' ? 'Pieza a vender' : 'Nombre de la pieza'}</label>
        ${ui.qTipo === 'Venta'
          ? `<select class="sel" id="q_art">${vendibles.map((a) => `<option value="${a.id}">${esc(a.nombre)} · ${libre(a)} disp.</option>`).join('') || '<option value="">Sin piezas disponibles</option>'}</select>`
          : `<input class="in" id="q_nombre" placeholder="Ej. Nissan Skyline GT-R">`}</div>
      <div class="fld"><label class="lbl">Categoría</label><div class="g2">
        <button class="sel ${ui.formTipo === 'Hot Wheels' ? 'bl' : ''}" data-a="qtipo2" data-t="Hot Wheels" style="text-align:left">🏎️ Hot Wheels</button>
        <button class="sel ${ui.formTipo === 'Pokémon' ? 'bl' : ''}" data-a="qtipo2" data-t="Pokémon" style="text-align:left">🃏 Pokémon</button>
      </div></div>
      <div class="fld"><label class="lbl">Tipo de movimiento</label>
        <div class="seg">${['Compra', 'Venta'].map((t) => `<button data-a="qtipo" data-t="${t}" class="${ui.qTipo === t ? 'on' : ''}">${t}</button>`).join('')}</div></div>
      <div class="g2">
        <div class="fld"><label class="lbl">Cantidad</label><input class="in" id="q_cant" type="number" min="1" value="1"></div>
        <div class="fld"><label class="lbl">Precio ${ui.qTipo === 'Venta' ? 'cobrado' : 'pagado'}</label><input class="in" id="q_precio" type="number" step="0.01" placeholder="0.00"></div>
      </div>
      ${ui.qTipo === 'Venta' ? `<div class="fld"><label class="lbl">Canal</label>
        <select class="sel" id="q_plat">${db.plataformas.map((p) => `<option value="${p.id}">${esc(p.nombre)} — ${pct(p.com_pct)}</option>`).join('')}</select></div>` : ''}
      <button class="btn pri" data-a="qguardar" style="width:100%;padding:12px">Guardar movimiento</button>
    </div>
    <div class="pnl">
      <h2>Historial reciente</h2>
      ${movs.length ? `<div class="feed">${movs.map((m) => `<div class="fi"><span class="dot" style="background:${m.col};--dc:${m.col}"></span>
        <span class="tx"><b>${esc(m.tit)}</b><span>${esc(m.sub)} · ${m.f || '—'}</span></span>
        <span class="am" style="color:${m.col}">${m.amt >= 0 ? '+' : '−'}${money(Math.abs(m.amt))}</span></div>`).join('')}</div>`
        : `<p style="color:var(--muted);font-size:13px">Aún no hay movimientos.</p>`}
    </div>
  </div>
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
  return l.sort(o[ui.orden] || o.reciente);
}
function vInv() {
  const l = filtrar();
  const tipos = [['todos', 'Ambas'], ['Hot Wheels', 'Hot Wheels'], ['Pokémon', 'Pokémon']];
  const est = [['todos', 'Todo'], ['disponible', 'Disponibles'], ['apartado', 'Apartadas'], ['estancado', 'Estancadas'], ['conservar', 'Conservar'], ['agotado', 'Agotadas']];
  return hdr('Inventario', `${l.length} de ${db.articulos.length} piezas${ui.sel.length ? ` · ${ui.sel.length} seleccionadas` : ''}`) + `
  <div class="chips">
    ${tipos.map((t) => `<button class="chip ${ui.fTipo === t[0] ? 'on' : ''}" data-a="ftipo" data-v="${t[0]}">${t[1]}</button>`).join('')}
    <span style="width:1px;height:22px;background:var(--line2)"></span>
    ${est.map((c) => `<button class="chip ${ui.fEstatus === c[0] ? 'on' : ''}" data-a="festatus" data-v="${c[0]}">${c[1]}</button>`).join('')}
    <span style="width:1px;height:22px;background:var(--line2)"></span>
    <button class="chip ${ui.selMode ? 'on' : ''}" data-a="selmode">☑ Seleccionar varias</button>
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
    <button class="btn gh sm" data-a="limpiarsel">Quitar selección</button></div>` : ''}
  ${l.length ? `<div class="rack">${l.map(ficha).join('')}</div>`
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
    <div class="ph">${a.foto ? `<img src="${esc(a.foto)}" alt="" loading="lazy" onerror="this.parentNode.innerHTML='<span class=gh>${emoji(a.tipo)}</span>'">` : `<span class="gh">${emoji(a.tipo)}</span>`}</div>
    <div class="bd">
      <div class="eb">${esc([a.numero, a.anio, det].filter(Boolean).join(' · ') || a.tipo)}</div>
      <div class="nm">${esc(a.nombre)}</div>
      <div class="row"><span><span class="dt" style="background:${s.col}"></span><span class="mu">${s.t}${num(a.cantidad) > 1 ? ' ×' + a.cantidad : ''}</span></span>
        <b class="mn" style="color:${t}">${money(a.valor_estimado)}</b></div>
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
      <div class="ph" style="height:88px">${a.foto ? `<img src="${esc(a.foto)}" alt="">` : `<span class="gh">${emoji(a.tipo)}</span>`}</div>
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
    <th>Pieza</th><th>Cliente</th><th class="num">Acordado</th><th class="num">Anticipo</th><th class="num">Resta</th>
    <th>Límite</th><th>Estatus</th><th></th></tr></thead><tbody>
    ${l.map((x) => { const resta = num(x.precio_acordado) - num(x.anticipo);
      const vence = x.estatus === 'Vigente' && x.fecha_limite && x.fecha_limite >= hoy()
        ? Math.round((new Date(x.fecha_limite) - new Date(hoy())) / 864e5) : null;
      const est = { Vigente: 'g', Liquidado: 'b', Vencido: 'r', Cancelado: '' }[x.estatus] || '';
      return `<tr><td><b>${esc(x.nombre_snap)}</b><div style="font-size:11px;color:var(--muted)">×${x.cantidad}${x.notas ? ' · ' + esc(x.notas) : ''}</div></td>
      <td>${esc(cli(x.id_comprador) ? cli(x.id_comprador).nombre : '—')}</td>
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
      '<button class="btn pri" data-a="nuevocomp">Agregar comprador</button>'));
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
      try { new window.QRCode(b, { text: 'CollectHub · ' + t, width: 78, height: 78, colorDark: '#0A1120', colorLight: '#ffffff', correctLevel: window.QRCode.CorrectLevel.M }); return; } catch (e) { /* sin red */ }
    }
    b.innerHTML = `<div style="width:78px;height:78px;display:grid;place-items:center;border:2px dashed #999;border-radius:6px;font-size:9px;color:#555;text-align:center;padding:4px">${esc(t)}</div>`;
  });
}

/* ---------- Datos ---------- */
function vDatos() {
  const s = stats();
  return hdr('Datos', 'Respaldo y ajustes', '') + `
  <div class="g2">
    <div class="pnl"><h2>Ajustes</h2>
      <div class="fld"><label class="lbl">Moneda</label>
        <select class="sel" data-a="set" data-k="moneda">${['MXN', 'USD', 'EUR', 'COP', 'ARS', 'CLP', 'PEN'].map((m) => `<option ${db.ajustes.moneda === m ? 'selected' : ''}>${m}</option>`).join('')}</select></div>
      <div class="fld"><label class="lbl">Meta de ganancia mensual</label>
        <input class="in" type="number" value="${db.ajustes.metaMensual}" data-a="set" data-k="meta_mensual"></div>
      <div class="fld"><label class="lbl">Una pieza se considera estancada después de (días)</label>
        <input class="in" type="number" value="${db.ajustes.diasEstancado}" data-a="set" data-k="dias_estancado"></div>
    </div>
    <div class="pnl"><h2>Respaldo</h2>
      <p style="font-size:12.5px;color:var(--muted);margin-bottom:15px">Tus datos viven en la base de datos del servidor. Descarga un respaldo antes de migrar o actualizar.</p>
      <div style="display:flex;gap:9px;flex-wrap:wrap">
        <button class="btn pri" data-a="export">Descargar respaldo</button>
        <button class="btn" data-a="csv">Inventario en CSV</button>
      </div>
      <div style="margin-top:18px;padding-top:16px;border-top:1px solid var(--line);display:flex;gap:9px;flex-wrap:wrap">
        <button class="btn gh" data-a="demo">Cargar datos de ejemplo</button>
        <button class="btn dgr" data-a="wipe">Borrar todo</button></div>
      <div class="mn" style="font-size:11.5px;color:var(--muted);margin-top:16px;line-height:1.8">
        ${db.articulos.length} artículos · ${db.ventas.length} ventas · ${db.apartados.length} apartados<br>
        ${db.intercambios.length} intercambios · ${db.compradores.length} clientes · ${s.piezas} piezas físicas</div>
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
  ${ed ? '' : `<div class="seg" style="margin-bottom:18px">
    <button data-a="tipo" data-t="Hot Wheels" class="${t === 'Hot Wheels' ? 'on' : ''}">🏎️ Hot Wheels</button>
    <button data-a="tipo" data-t="Pokémon" class="${t === 'Pokémon' ? 'on y' : ''}">🃏 Pokémon</button></div>`}
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
  ${f('Foto (URL)', inp('f_foto', a.foto, 'url', 'https://…'))}
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
      ${a.foto ? `<img src="${esc(a.foto)}" style="width:100%;height:100%;object-fit:cover" alt="">` : `<span style="font-size:44px;opacity:.3">${emoji(a.tipo)}</span>`}</div>
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
  ${ap.length ? `<div class="note w"><b>Apartada:</b> ${ap.map((x) => `${cli(x.id_comprador) ? esc(cli(x.id_comprador).nombre) : 'un cliente'} dejó ${money(x.anticipo)}, resta ${money(num(x.precio_acordado) - num(x.anticipo))} hasta el ${x.fecha_limite || '—'}`).join('; ')}.</div>` : ''}
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
  <div class="g2">${f('Cliente', selC('ap_comp', ''))}${f('Cantidad', `<input class="in" id="ap_cant" type="number" min="1" value="1" max="${a ? libre(a) : 99}">`)}</div>
  <div class="g3">
    ${f('Precio acordado', inp('ap_precio', a ? a.valor_estimado : '', 'number', '0.00'))}
    ${f('Anticipo recibido', inp('ap_ant', '', 'number', '0.00'))}
    ${f('Fecha límite', inp('ap_lim', lim, 'date'))}
  </div>
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
MOD.publicacion = function () {
  const a = ui.ctx || {};
  return shell('Publicación lista para copiar', a.nombre || '', `
  <p style="font-size:12.5px;color:var(--muted);margin-bottom:12px">Copia esto en Mercado Libre, eBay o el grupo de Facebook. Ajusta lo que quieras antes de publicar.</p>
  <textarea class="ta" id="pub_txt" rows="15" style="font-family:var(--m);font-size:12px">${esc(textoPub(a))}</textarea>
  `, `<button class="btn gh" data-a="cerrar">Cerrar</button><button class="btn pri" data-a="copiar">Copiar texto</button>`);
};
function textoPub(a) {
  const L = [], t = [a.tipo === 'Pokémon' ? 'Carta Pokémon' : 'Hot Wheels', a.nombre, a.numero, a.anio].filter(Boolean).join(' ');
  L.push(t.toUpperCase(), '');
  L.push(a.tipo === 'Pokémon'
    ? `Carta original de la expansión ${a.expansion || '—'}. Rareza ${a.rareza || '—'}, idioma ${a.sub || '—'}${a.grado && a.grado !== 'Sin graduar' ? `, graduada ${a.grado}${a.cert ? ` (cert. ${a.cert})` : ''}` : ''}.`
    : `Pieza original Mattel, línea ${a.serie || 'Mainline'}${a.color ? `, color ${a.color}` : ''}${a.sub ? `, ${String(a.sub).toLowerCase()}` : ''}.`);
  L.push('', `Estado: ${a.estado || '—'}`, `Número de colección: ${a.numero || '—'}`, `Año: ${a.anio || '—'}`, `Disponibles: ${libre(a) || a.cantidad || 1}`, '');
  if ((a.checks || []).length) L.push('Verificación de autenticidad:', ...(a.checks || []).map((i) => '· ' + (CHECKS[a.tipo] || [])[i]).filter(Boolean), '');
  L.push(`Precio: ${money(a.valor_estimado)}`, '');
  L.push('· Se envía protegida en burbuja y caja rígida.', '· Acepto preguntas y fotos extra por mensaje.', '· Manejo apartados con anticipo.');
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

/* ==================== Acciones ==================== */
function abrir(m, ctx) { ui.modal = m; ui.ctx = ctx || null; render(); }
function cerrar() { pararCam(); ui.modal = null; ui.ctx = null; ui.apLiq = null; render(); }

document.addEventListener('click', async (e) => {
  if (e.target.classList && e.target.classList.contains('ov')) { cerrar(); return; }
  const el = e.target.closest('[data-a]'); if (!el) return;
  const a = el.dataset.a, id = el.dataset.id;
  switch (a) {
    /* --- acceso --- */
    case 'authtab': ui.authTab = el.dataset.v; ui.authErr = ''; render(); break;
    case 'auth': await autenticar(); break;
    case 'salir': if (confirm('¿Cerrar sesión en este dispositivo?')) salir(); break;

    /* --- navegación --- */
    case 'nav': ui.vista = el.dataset.v; ui.modal = null; ui.sel = []; ui.selMode = false; render(); window.scrollTo(0, 0); break;
    case 'cerrar': cerrar(); break;
    case 'ftipo': ui.fTipo = el.dataset.v; render(); break;
    case 'festatus': ui.fEstatus = el.dataset.v; render(); break;
    case 'selmode': ui.selMode = !ui.selMode; if (!ui.selMode) ui.sel = []; render();
      toast(ui.selMode ? 'Toca las piezas que quieras agrupar' : 'Selección desactivada'); break;
    case 'limpiarsel': ui.sel = []; ui.selMode = false; render(); break;
    case 'ver': if (ui.selMode || e.shiftKey || ui.sel.length) { toggleSel(id); } else abrir('ver', art(id)); break;

    /* --- alta y edición --- */
    case 'nuevo': ui.formTipo = 'Hot Wheels'; abrir('pieza', null); break;
    case 'tipo': ui.ctx = snapPieza(); ui.formTipo = el.dataset.t; render(); break;
    case 'editpieza': ui.formTipo = art(id).tipo; abrir('pieza', art(id)); break;
    case 'qtipo': ui.qTipo = el.dataset.t; render(); break;
    case 'qtipo2': ui.formTipo = el.dataset.t; render(); break;
    case 'savepieza': await savePieza(); break;
    case 'qguardar': await qGuardar(); break;
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
    case 'apartar': abrir('apartado', art(id)); break;
    case 'nuevoapartado': abrir('apartado', null); break;
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

document.addEventListener('change', async (e) => {
  const el = e.target.closest('[data-a]'); if (!el) return;
  const a = el.dataset.a;
  if (a === 'orden') { ui.orden = el.value; render(); }
  if (a === 'recalc') pintarVenta();
  if (a === 'recalcLote') pintarLote();
  if (a === 'envio') await accion(() => PATCH('/ventas/' + el.dataset.id, { estatus_envio: el.value }), 'Estatus de envío actualizado');
  if (a === 'set') {
    const valor = el.type === 'number' ? num(el.value) : el.value;
    await accion(() => PATCH('/ajustes', { [el.dataset.k]: valor }), 'Ajuste guardado');
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
    foto: $('#f_foto').value.trim(),
    notas: $('#f_notas').value.trim(),
    grail: $('#f_grail').checked,
    checks: $$('[data-chk]').filter((c) => c.checked).map((c) => num(c.dataset.chk)),
  };
}
async function savePieza() {
  const datos = leerPieza();
  if (!datos.nombre) { toast('Ponle nombre a la pieza', true); $('#f_nombre').focus(); return; }
  const ed = ui.ctx && ui.ctx.id;
  try {
    await accion(() => (ed ? PATCH('/articulos/' + ed, datos) : POST('/articulos', datos)));
    cerrar();
    const int = db.compradores.filter((c) => c.interes === datos.tipo || c.interes === 'Ambas').map((c) => c.nombre);
    toast(int.length ? `Guardada. Avísale a ${int.slice(0, 2).join(' y ')}` : 'Pieza registrada');
  } catch (e) { /* el toast de error ya salió */ }
}
async function qGuardar() {
  const cant = num($('#q_cant').value) || 1, precio = num($('#q_precio').value);
  if (ui.qTipo === 'Compra') {
    const nombre = $('#q_nombre').value.trim();
    if (!nombre) { toast('Ponle nombre a la pieza', true); return; }
    await accion(() => POST('/articulos', {
      tipo: ui.formTipo, nombre, cantidad: cant, precio_compra: precio, valor_estimado: precio,
      fecha_adq: hoy(), fuente: 'Compra en línea',
      estado: ui.formTipo === 'Pokémon' ? 'Near Mint' : 'Sellado / Mint',
      sub: ui.formTipo === 'Pokémon' ? 'Español' : 'Tarjeta corta',
    }), 'Compra registrada. Completa los detalles cuando puedas.');
  } else {
    const idA = $('#q_art') ? $('#q_art').value : '';
    if (!idA) { toast('No hay piezas disponibles para vender', true); return; }
    if (!precio) { toast('Falta el precio cobrado', true); return; }
    await accion(() => POST('/ventas', {
      articulo_id: idA, plataforma_id: $('#q_plat').value, cantidad: cant, precio, fecha: hoy(),
    }), (v) => `Venta registrada · ${money(v.ganancia_neta)} netos`);
  }
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
  const cuerpo = {
    articulo_id: a.id, comprador_id: $('#ap_comp').value, cantidad: num($('#ap_cant').value) || 1,
    precio_acordado: num($('#ap_precio').value), anticipo: num($('#ap_ant').value),
    fecha_limite: $('#ap_lim').value, notas: $('#ap_notas').value.trim(),
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

/* ==================== Exportar ==================== */
function bajar(n, c, m) {
  const b = new Blob([c], { type: m }), u = URL.createObjectURL(b);
  const a = document.createElement('a'); a.href = u; a.download = n; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 400);
}
const csvq = (s) => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
async function exportar() {
  try {
    const datos = await GET('/exportar');
    bajar(`collecthub-${hoy()}.json`, JSON.stringify(datos, null, 2), 'application/json');
    toast('Respaldo descargado');
  } catch (e) { toast(e.message, true); }
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
