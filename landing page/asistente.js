/* Asistente de la tienda: el cliente pregunta por una pieza y el servidor
 * responde con el stock real (/tienda/api/asistente). "Lo quiero" la aparta
 * (sin anticipo, entrega el sábado en Balderas; si viene en camino, el sábado
 * después de que llegue) y "Avísame" deja al cliente en la lista de espera.
 * Con las piezas de ejemplo (sin stock en vivo) también aparece, en modo vista
 * previa: busca en esas piezas aquí mismo y no guarda nada. */
(() => {
  "use strict";

  const STOCK = window.CW_STOCK || {};
  const DEMO = !STOCK.asistente;   // vista previa: sin servidor, nada se guarda

  const pesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // No se guardan los datos del cliente en el navegador: en un celular o compu compartida,
  // el siguiente cliente vería el nombre y el Facebook/Instagram del anterior. Se borra lo
  // que haya quedado de versiones anteriores.
  try { localStorage.removeItem("cw_asis_nombre"); localStorage.removeItem("cw_asis_contacto"); } catch (_) { /* sin almacenamiento */ }

  // ---------- Estructura ----------
  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "asis-boton";
  boton.setAttribute("aria-label", "¿Buscas una pieza? Pregúntale al asistente");
  boton.innerHTML = `<span class="asis-icono" aria-hidden="true">💬</span><span class="asis-etiqueta" aria-hidden="true"><b>Pregúntame</b><small>¿Buscas una pieza?</small></span>`;
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
    if (!saludado) {
      saludado = true;
      bot("¡Hola! 👋 Dime qué pieza buscas y te digo si la tenemos en stock o si viene en camino.");
      if (DEMO) burbuja(`${esc("Vista previa con las piezas de ejemplo.")}<span class="asis-demo">Al publicar el stock real, aquí se aparta de verdad.</span>`, "bot");
    }
    setTimeout(() => entrada.focus(), 50);
  }
  function cerrarPanel() { panel.hidden = true; boton.hidden = false; }

  async function llamar(ruta, cuerpo) {
    if (DEMO) return local(ruta, cuerpo);
    const r = await fetch(`api/${ruta}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    let d = {};
    try { d = await r.json(); } catch (_) { /* respuesta vacía */ }
    if (!r.ok) throw new Error(d.error || "No pude responder ahora. Intenta de nuevo en un momento.");
    return d;
  }

  // ---------- Vista previa (sin servidor) ----------
  // Misma idea que la búsqueda por palabras del servidor (collecthub/asistente.py), en corto.
  const plano = (t) => String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const VACIAS = new Set("hola buenas tienes tienen hay busco quiero me interesa un una el la los las de del en con por para y o a mi es son esta este esa ese disponible precio cuanto cuesta pieza piezas modelo si no".split(" "));
  const raiz = (w) => (w.length > 3 && w.endsWith("s") ? w.slice(0, -1) : w);
  const palabras = (t) => (plano(t).match(/[a-z0-9]+/g) || []).filter((w) => w.length >= 2 && !VACIAS.has(w)).map(raiz);
  function local(ruta, cuerpo) {
    const piezas = Array.isArray(STOCK.piezas) ? STOCK.piezas : [];
    if (ruta === "apartar") return { texto: `Así funciona: con la tienda publicada, aquí quedaría apartada a nombre de ${cuerpo.nombre} para el sábado en Balderas. (Vista previa: no se guardó nada.)` };
    if (ruta === "avisame") return { texto: `Así funciona: con la tienda publicada, le avisaríamos a ${cuerpo.contacto} cuando llegue. (Vista previa: no se guardó nada.)` };
    const q = palabras(cuerpo.mensaje);
    if (!q.length) return { texto: "Dime qué pieza buscas (Hot Wheels, Pokémon…) y te digo si la tenemos." };
    const puntos = piezas.map((p) => {
      const pal = palabras([p.nombre, p.serie, p.expansion, p.color, p.numero, p.anio, p.tipo].join(" "));
      return [q.filter((w) => pal.some((x) => x === w || (w.length >= 3 && x.startsWith(w)))).length, p];
    }).filter(([n]) => n);
    const mejor = Math.max(0, ...puntos.map(([n]) => n));
    const hallas = puntos.filter(([n]) => n === mejor && n >= (q.length > 1 ? Math.ceil(q.length / 2) : 1)).map(([, p]) => p).slice(0, 6);
    if (!hallas.length) return { texto: "Por el momento no la tenemos en stock 😔, pero cada semana llegan piezas nuevas. ¿Te avisamos cuando llegue?", avisame: true, busqueda: cuerpo.mensaje };
    return { texto: hallas.length === 1 ? "¡Sí la tenemos! Toca «Lo quiero» y te la aparto." : `¡Tenemos ${hallas.length} piezas que coinciden! Toca «Lo quiero» en la que te guste.`, piezas: hallas };
  }

  // ---------- Piezas y formularios ----------
  function tarjetas(piezas) {
    piezas.forEach((p) => piezasVistas.set(p.id, p));
    burbuja(piezas.map((p) => `
      <div class="asis-pieza">
        <div class="asis-foto">${p.foto ? `<img src="${esc(p.foto)}" alt="" loading="lazy">` : esc(EMOJIS[p.tipo] || "📦")}</div>
        <div class="asis-info"><b>${esc(p.nombre)}</b>
          <span>${pesos.format(p.precio)} · ${p.por_llegar ? `🚚 por llegar${p.llega ? ` (aprox. ${esc(p.llega.split("-").reverse().slice(0, 2).join("/"))})` : ""}` : p.disponible === 1 ? "última pieza" : `quedan ${p.disponible}`}</span>
          <button type="button" class="asis-quiero" data-pieza="${esc(p.id)}">Lo quiero</button></div>
      </div>`).join(""), "bot piezas");
  }

  function formulario(titulo, alEnviar) {
    const f = burbuja(`
      <form class="asis-form">
        <b>${esc(titulo)}</b>
        <input name="nombre" maxlength="60" placeholder="Tu nombre" required>
        <input name="contacto" maxlength="80" placeholder="Tu Facebook o Instagram" required>
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
        f.closest(".asis-msg").remove();
        bot(r.texto);
      } catch (err) {
        btn.disabled = false; btn.textContent = "Enviar";
        bot(err.message);
      }
    });
    f.querySelector("input").focus();
  }

  function pedirApartado(p) {
    formulario(`Para apartarte «${p.nombre}» (${pesos.format(p.precio)})${p.por_llegar ? ", que viene en camino," : ""} necesito:`,
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

  // ---------- "Avísenme de novedades" (sección de contacto) ----------
  const nov = document.getElementById("novedades");
  if (nov) {
    const cats = ["Todas", "Hot Wheels", "Pokémon", ...(STOCK.categorias || []).map((c) => c.nombre).filter(Boolean)];
    nov.hidden = false;
    nov.innerHTML = `<form class="nov-form">
      <b>🔔 Te avisamos cuando lleguen piezas nuevas</b>
      <div class="nov-campos">
        <input name="nombre" maxlength="60" placeholder="Tu nombre" required>
        <input name="contacto" maxlength="80" placeholder="Tu Facebook o Instagram" required>
        <select name="cat" aria-label="De qué">${cats.map((c) => `<option>${esc(c)}</option>`).join("")}</select>
        <input name="sitio" class="asis-trampa" tabindex="-1" autocomplete="off" aria-hidden="true">
        <button type="submit">Avísenme</button>
      </div>
      <small class="nov-estado" role="status"></small></form>`;
    const f = nov.querySelector("form");
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f));
      const estado = f.querySelector(".nov-estado"), btn = f.querySelector("button");
      btn.disabled = true;
      try {
        const r = await llamar("avisame", { nombre: d.nombre, contacto: d.contacto, sitio: d.sitio, busqueda: `Novedades: ${d.cat}` });
        estado.textContent = r.texto.replace(/«Novedades: [^»]*»/, "algo nuevo");
        f.querySelector(".nov-campos").hidden = true;
      } catch (err) { estado.textContent = err.message; btn.disabled = false; }
    });
  }

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
