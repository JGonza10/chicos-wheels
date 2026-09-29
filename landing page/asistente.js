/* Asistente de la tienda: el cliente pregunta por una pieza y el servidor
 * responde con el stock real (/tienda/api/asistente). "Lo quiero" la aparta
 * (sin anticipo, entrega el sábado en Balderas) y "Avísame" deja al cliente en
 * la lista de espera. Solo aparece cuando la app sirve el stock en vivo
 * (STOCK.asistente); con las piezas de ejemplo no se muestra. */
(() => {
  "use strict";

  const STOCK = window.CW_STOCK || {};
  if (!STOCK.asistente) return;

  const pesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const recordar = (k, v) => { try { if (v === undefined) return localStorage.getItem(k) || ""; localStorage.setItem(k, v); } catch (_) { return ""; } return ""; };

  // ---------- Estructura ----------
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "asis-boton";
  boton.innerHTML = `<span aria-hidden="true">💬</span> ¿Buscas una pieza?`;
  const panel = document.createElement("section");
  panel.className = "asis-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Asistente de la tienda");
  panel.innerHTML = `
    <header><div><b>Asistente Chicos Wheels</b><small>Te digo si la tenemos y te la aparto</small></div>
      <button type="button" class="asis-cerrar" aria-label="Cerrar">×</button></header>
    <div class="asis-msgs" role="log" aria-live="polite"></div>
    <form class="asis-entrada" autocomplete="off">
      <input type="text" maxlength="300" placeholder="Ej. ¿Tienes el Skyline R32?" aria-label="Escribe qué pieza buscas" required>
      <button type="submit" aria-label="Enviar">➤</button>
    </form>`;
  document.body.append(boton, panel);
  const msgs = panel.querySelector(".asis-msgs");
  const entrada = panel.querySelector(".asis-entrada input");
  const piezasVistas = new Map();
  const EMOJIS = { "Hot Wheels": "🏎️", "Pokémon": "🃏" };
  (STOCK.categorias || []).forEach((c) => { if (c && c.nombre) EMOJIS[c.nombre] = c.emoji || "📦"; });
  let saludado = false, ocupado = false;

  const bajar = () => { msgs.scrollTop = msgs.scrollHeight; };
  function burbuja(html, quien) {
    const d = document.createElement("div");
    d.className = `asis-msg ${quien}`;
    d.innerHTML = html;
    msgs.append(d);
    bajar();
    return d;
  }
  const bot = (t) => burbuja(esc(t), "bot");

  function abrirPanel() {
    panel.hidden = false;
    boton.hidden = true;
    if (!saludado) { saludado = true; bot("¡Hola! 👋 Dime qué pieza buscas y te digo si la tenemos en stock."); }
    setTimeout(() => entrada.focus(), 50);
  }
  function cerrarPanel() { panel.hidden = true; boton.hidden = false; }

  async function llamar(ruta, cuerpo) {
    const r = await fetch(`api/${ruta}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    let d = {};
    try { d = await r.json(); } catch (_) { /* respuesta vacía */ }
    if (!r.ok) throw new Error(d.error || "No pude responder ahora. Intenta de nuevo en un momento.");
    return d;
  }

  // ---------- Piezas y formularios ----------
  function tarjetas(piezas) {
    piezas.forEach((p) => piezasVistas.set(p.id, p));
    burbuja(piezas.map((p) => `
      <div class="asis-pieza">
        <div class="asis-foto">${p.foto ? `<img src="${esc(p.foto)}" alt="" loading="lazy">` : esc(EMOJIS[p.tipo] || "📦")}</div>
        <div class="asis-info"><b>${esc(p.nombre)}</b>
          <span>${pesos.format(p.precio)} · ${p.disponible === 1 ? "última pieza" : `quedan ${p.disponible}`}</span>
          <button type="button" class="asis-quiero" data-pieza="${esc(p.id)}">Lo quiero</button></div>
      </div>`).join(""), "bot piezas");
  }

  function formulario(titulo, alEnviar) {
    const f = burbuja(`
      <form class="asis-form">
        <b>${esc(titulo)}</b>
        <input name="nombre" maxlength="60" placeholder="Tu nombre" required value="${esc(recordar("cw_asis_nombre"))}">
        <input name="contacto" maxlength="80" placeholder="Tu Facebook o Instagram" required value="${esc(recordar("cw_asis_contacto"))}">
        <input name="sitio" class="asis-trampa" tabindex="-1" autocomplete="off" aria-hidden="true">
        <button type="submit">Enviar</button>
        <small>Solo lo usamos para confirmarte por Facebook o Instagram.</small>
      </form>`, "bot").querySelector("form");
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const datos = Object.fromEntries(new FormData(f));
      const btn = f.querySelector("button");
      btn.disabled = true; btn.textContent = "Enviando…";
      try {
        const r = await alEnviar(datos);
        recordar("cw_asis_nombre", datos.nombre); recordar("cw_asis_contacto", datos.contacto);
        f.closest(".asis-msg").remove();
        bot(r.texto);
      } catch (err) {
        btn.disabled = false; btn.textContent = "Enviar";
        bot(err.message);
      }
    });
    f.querySelector(datosIniciales(f) ? "button" : "input").focus();
  }
  const datosIniciales = (f) => f.nombre.value && f.contacto.value;

  function pedirApartado(p) {
    formulario(`Para apartarte «${p.nombre}» (${pesos.format(p.precio)}) necesito:`,
      (d) => llamar("apartar", { ...d, pieza: p.id }));
  }
  function pedirAviso(busqueda) {
    formulario("¿A quién le avisamos?", (d) => llamar("avisame", { ...d, busqueda }));
  }

  // ---------- Conversación ----------
  async function enviar(texto) {
    if (ocupado || !texto.trim()) return;
    ocupado = true;
    burbuja(esc(texto), "yo");
    const escribiendo = burbuja("<span class='asis-puntos'><i></i><i></i><i></i></span>", "bot");
    try {
      const r = await llamar("asistente", { mensaje: texto });
      escribiendo.remove();
      bot(r.texto);
      if (r.piezas && r.piezas.length) tarjetas(r.piezas);
      if (r.avisame) {
        const d = burbuja(`<button type="button" class="asis-avisame">🔔 Sí, avísenme</button>`, "bot");
        d.querySelector("button").addEventListener("click", () => { d.remove(); pedirAviso(r.busqueda || texto); });
      }
    } catch (err) {
      escribiendo.remove();
      bot(err.message);
    } finally {
      ocupado = false;
    }
  }

  // ---------- Eventos ----------
  boton.addEventListener("click", abrirPanel);
  panel.querySelector(".asis-cerrar").addEventListener("click", cerrarPanel);
  panel.querySelector(".asis-entrada").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = entrada.value;
    entrada.value = "";
    enviar(t);
  });
  msgs.addEventListener("click", (e) => {
    const b = e.target.closest(".asis-quiero");
    if (b && piezasVistas.has(b.dataset.pieza)) pedirApartado(piezasVistas.get(b.dataset.pieza));
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) cerrarPanel(); });

  // Desde la ficha de una pieza ("Apartar aquí"): abre el chat con esa pieza.
  window.CWAsistente = {
    apartar(p) {
      abrirPanel();
      burbuja(esc(`Quiero apartar ${p.nombre}`), "yo");
      tarjetas([p]);
      pedirApartado(p);
    },
  };
})();
