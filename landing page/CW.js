/* Landing page de Chicos Wheels.
 * Solo muestra el stock: lo lee de window.CW_STOCK (archivo stock.js que genera
 * la app con "Publicar stock"). No hay carrito ni pagos: "Me interesa" abre
 * la ficha con el mensaje listo para copiar y mandar por Messenger o Instagram. */
(() => {
  "use strict";

  const STOCK = window.CW_STOCK || { piezas: [], contacto: {}, muestra: true };
  const PIEZAS = Array.isArray(STOCK.piezas) ? STOCK.piezas : [];
  const CONTACTO = STOCK.contacto || {};
  const FIJAS = ["Hot Wheels", "Pokémon"];
  // Categorías del inventario (Barbie, …): las manda la app en stock.js. Si una
  // pieza trae una categoría que no viene en la lista, también se incluye.
  const CATS = (Array.isArray(STOCK.categorias) ? STOCK.categorias : []).filter((c) => c && c.nombre && !FIJAS.includes(c.nombre));
  PIEZAS.forEach((p) => {
    if (p.tipo && !FIJAS.includes(p.tipo) && !CATS.some((c) => c.nombre === p.tipo)) CATS.push({ nombre: p.tipo, emoji: "📦" });
  });
  const emojiDe = (tipo) => (CATS.find((c) => c.nombre === tipo) || {}).emoji || "📦";
  const esPropia = (p) => !FIJAS.includes(p.tipo);
  const DIAS_NUEVO = 14;

  const S = { tipo: "", filtro: "todo", q: "", serie: "", orden: "reciente" };
  const $ = (sel) => document.querySelector(sel);
  const pesos = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const sinAcentos = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

  const diasDesde = (f) => { const t = Date.parse(f); return isNaN(t) ? 999 : (Date.now() - t) / 864e5; };
  const esNueva = (p) => diasDesde(p.fecha) <= DIAS_NUEVO;
  const serieDe = (p) => (p.tipo === "Pokémon" ? p.expansion || p.serie : p.serie) || "";
  const graduada = (p) => !!p.grado && !/^sin/i.test(String(p.grado).trim());

  /* Etiqueta de rareza: lo primero que mira un coleccionista. */
  function rareza(p) {
    const s = sinAcentos(serieDe(p));
    if (s.includes("super treasure")) return { txt: "Super TH", c: "r-oro" };
    if (s.includes("rlc") || s.includes("red line club")) return { txt: "RLC", c: "r-oro" };
    if (s.includes("hwc")) return { txt: "HWC Special", c: "r-oro" };
    if (p.grail) return { txt: "Grial", c: "r-oro" };
    if (s.includes("treasure hunt")) return { txt: "Treasure Hunt", c: "r-plata" };
    if (graduada(p)) return { txt: p.grado, c: "r-plata" };
    if (/premium|car culture|boulevard|pop culture/.test(s)) return { txt: "Premium", c: "r-rojo" };
    if (esNueva(p)) return { txt: "Nuevo", c: "" };
    return null;
  }
  const esRara = (p) => { const r = rareza(p); return !!r && r.txt !== "Nuevo"; };

  /* ---------- Contacto ---------- */
  // Solo Facebook (Messenger) e Instagram: el negocio no atiende por WhatsApp.
  const usuario = (v) => String(v || "").replace(/[^A-Za-z0-9._-]/g, "");
  const FB = usuario(CONTACTO.facebook), IG = usuario(CONTACTO.instagram);
  const linkMessenger = (texto) => FB ? `https://m.me/${FB}${texto ? `?text=${encodeURIComponent(texto)}` : ""}` : "";
  const linkInstagram = () => IG ? `https://ig.me/m/${IG}` : "";
  const mensajePieza = (p) => `Hola, me interesa ${p.nombre}${serieDe(p) ? ` (${serieDe(p)}${p.anio ? " " + p.anio : ""})` : ""} ` +
    `de ${pesos.format(p.precio)}. ¿Sigue disponible para recoger el sábado en Balderas?`;

  /* ---------- Imágenes de respaldo (sin foto) ---------- */
  const SVG_AUTO = `<svg viewBox="0 0 200 84" aria-hidden="true">
    <path fill="#005bac" d="M8 60c0-8 6-13 18-15l34-5c12-10 27-16 47-16 17 0 29 6 41 16l29 4c10 2 16 7 16 16v4H8z"/>
    <path fill="#fff" fill-opacity=".8" d="M68 40c10-8 22-12 36-12l2 12zM112 28c12 0 21 4 29 12h-29z"/>
    <path fill="#e60012" d="M20 50h160v4H20z"/><path fill="#ffcc00" d="M150 46h30v4h-30z"/>
    <circle cx="50" cy="63" r="15" fill="#222"/><circle cx="50" cy="63" r="7" fill="#d9dce1"/>
    <circle cx="154" cy="63" r="15" fill="#222"/><circle cx="154" cy="63" r="7" fill="#d9dce1"/></svg>`;
  const SVG_CARTA = `<svg viewBox="0 0 64 88" aria-hidden="true">
    <rect x="1" y="1" width="62" height="86" rx="5" fill="#ffcc00"/>
    <rect x="6" y="6" width="52" height="40" rx="2" fill="#fff"/>
    <circle cx="32" cy="26" r="11" fill="none" stroke="#3d7dca" stroke-width="3"/>
    <path d="M21 26h22" stroke="#3d7dca" stroke-width="3"/><circle cx="32" cy="26" r="3.5" fill="#e60012"/>
    <rect x="6" y="52" width="52" height="4" rx="2" fill="#3d7dca" fill-opacity=".55"/>
    <rect x="6" y="60" width="38" height="4" rx="2" fill="#3d7dca" fill-opacity=".35"/>
    <rect x="6" y="68" width="44" height="4" rx="2" fill="#3d7dca" fill-opacity=".35"/></svg>`;
  const imagen = (p) => p.foto
    ? `<img src="${esc(p.foto)}" alt="${esc(p.nombre)}" loading="lazy">`
    : (p.tipo === "Pokémon" ? SVG_CARTA : esPropia(p) ? `<span class="sin-foto" aria-hidden="true">${esc(emojiDe(p.tipo))}</span>` : SVG_AUTO);

  /* ---------- Fichas ---------- */
  function tarjeta(p, i) {
    const r = rareza(p);
    const existencia = p.disponible === 1
      ? `<span class="existencia ultima">Última pieza</span>`
      : `<span class="existencia">Quedan ${p.disponible}</span>`;
    const meta = [serieDe(p), p.anio].filter(Boolean).join(" · ");
    return `<article class="card ${p.tipo === "Pokémon" ? "poke" : esPropia(p) ? "otra" : "hot"}" tabindex="0" data-id="${esc(p.id)}" style="--i:${i}">
      <div class="card-foto">${imagen(p)}
        <div class="etiquetas">${r ? `<span class="rareza ${r.c}">${esc(r.txt)}</span>` : ""}${existencia}</div>
      </div>
      <div class="card-cuerpo">
        <h4>${esc(p.nombre)}</h4>
        <p class="meta">${esc(meta)}</p>
        <div class="card-pie">
          <span class="precio">${pesos.format(p.precio)}<small>MXN</small></span>
          <button class="btn-interes" type="button">Me interesa</button>
        </div>
      </div>
    </article>`;
  }

  /* ---------- Filtros ---------- */
  const FILTROS = [
    { id: "todo", txt: "Todo", f: () => true },
    { id: "hw", txt: "Hot Wheels", f: (p) => p.tipo === "Hot Wheels" },
    { id: "pkm", txt: "Pokémon", f: (p) => p.tipo === "Pokémon" },
    ...CATS.map((c) => ({ id: "cat:" + c.nombre, txt: `${c.emoji || "📦"} ${c.nombre}`, f: (p) => p.tipo === c.nombre })),
    { id: "raras", txt: "Rarezas", f: esRara },
    { id: "nuevas", txt: "Recién llegados", f: esNueva },
  ];
  const ORDENES = {
    reciente: (a, b) => String(b.fecha).localeCompare(String(a.fecha)),
    "precio-asc": (a, b) => a.precio - b.precio,
    "precio-desc": (a, b) => b.precio - a.precio,
    nombre: (a, b) => a.nombre.localeCompare(b.nombre, "es"),
  };

  function visibles() {
    const f = (FILTROS.find((x) => x.id === S.filtro) || FILTROS[0]).f;
    const palabras = sinAcentos(S.q).split(/\s+/).filter(Boolean);
    return PIEZAS.filter((p) => {
      if (!f(p) || (S.serie && serieDe(p) !== S.serie)) return false;
      const texto = sinAcentos([p.nombre, serieDe(p), p.color, p.numero, p.rareza, p.anio].join(" "));
      return palabras.every((w) => texto.includes(w));
    }).sort(ORDENES[S.orden] || ORDENES.reciente);
  }

  function pintarChips() {
    $("#chips").innerHTML = FILTROS.map((x) => {
      const n = PIEZAS.filter(x.f).length;
      if (!n && x.id !== "todo") return "";
      return `<button class="chip" type="button" data-filtro="${esc(x.id)}" aria-pressed="${S.filtro === x.id}">${esc(x.txt)}<small>${n}</small></button>`;
    }).join("");
  }

  function pintarSeries() {
    const series = [...new Set(PIEZAS.map(serieDe).filter(Boolean))].sort((a, b) => a.localeCompare(b, "es"));
    $("#serie").insertAdjacentHTML("beforeend", series.map((s) => `<option>${esc(s)}</option>`).join(""));
    $("#serie").hidden = series.length < 2;
  }

  function render() {
    pintarChips();
    const lista = visibles();
    $("#grid").innerHTML = lista.length
      ? lista.map(tarjeta).join("")
      : `<div class="vacio"><b>${PIEZAS.length ? "No encontramos esa pieza" : "Estamos preparando el stock"}</b>
         ${PIEZAS.length ? "Prueba con otra búsqueda o categoría. Si buscas algo en especial, escríbenos." : "Muy pronto verás aquí las piezas disponibles."}</div>`;
  }

  function pintarRecien() {
    const nuevas = PIEZAS.filter(esNueva).sort(ORDENES.reciente).slice(0, 10);
    $("#recien").hidden = nuevas.length < 2;
    $("#tiraRecien").innerHTML = nuevas.map(tarjeta).join("");
  }

  /* ---------- Ficha ampliada ---------- */
  function abrir(id) {
    const p = PIEZAS.find((x) => x.id === id);
    if (!p) return;
    S.abierta = p;
    const r = rareza(p);
    const filas = p.tipo === "Pokémon"
      ? [["Expansión", serieDe(p)], ["Número", p.numero], ["Rareza", p.rareza], ["Grado", graduada(p) ? p.grado : ""], ["Estado", p.estado], ["Año", p.anio]]
      : esPropia(p)
        ? [["Categoría", p.tipo], ["Línea", serieDe(p)], ["Número", p.numero], ["Variante", p.color], ["Año", p.anio], ["Estado", p.estado]]
        : [["Serie", serieDe(p)], ["Número", p.numero], ["Color", p.color], ["Año", p.anio], ["Estado", p.estado]];
    const m = $("#modal");
    m.innerHTML = `<div class="modal-caja">
      <div class="card-foto">${imagen(p)}
        <div class="etiquetas">${r ? `<span class="rareza ${r.c}">${esc(r.txt)}</span>` : ""}</div></div>
      <div class="modal-info">
        <h2 id="modalTitulo">${esc(p.nombre)}</h2>
        <span class="precio">${pesos.format(p.precio)}<small>MXN</small></span>
        <dl class="datos">${filas.filter((f) => f[1]).map((f) => `<dt>${f[0]}</dt><dd>${esc(f[1])}</dd>`).join("")}
          <dt>Disponibles</dt><dd>${p.disponible === 1 ? "Última pieza" : p.disponible}</dd></dl>
        <div class="interes">
          <b>¿Te interesa? Mándanos este mensaje:</b>
          <textarea id="mensajePieza" readonly rows="3">${esc(mensajePieza(p))}</textarea>
          <div class="interes-botones">
            ${STOCK.asistente ? `<button class="btn-apartar" type="button" data-apartar>Apartar aquí</button>` : ""}
            <button class="btn-interes" type="button" data-copiar>Copiar mensaje</button>
            ${FB ? `<a class="btn-fb" href="${linkMessenger(mensajePieza(p))}" target="_blank" rel="noopener">Messenger</a>` : ""}
            ${IG ? `<a class="btn-ig" href="${linkInstagram()}" target="_blank" rel="noopener">Instagram</a>` : ""}
          </div>
          <p class="nota">${FB || IG ? "Copia el mensaje y pégalo en el chat." : "Cópialo y búscanos en Facebook o Instagram como Chicos Wheels."} Entrega los sábados en Balderas.</p>
        </div>
      </div>
      <button class="cerrar" type="button" aria-label="Cerrar">×</button>
    </div>`;
    m.showModal();
  }

  /* ---------- Modo oscuro ---------- */
  function pintarBotonTema() {
    const oscuro = document.documentElement.getAttribute("data-tema") === "oscuro";
    const b = $("#darkModeToggle");
    b.textContent = oscuro ? "☀️" : "🌙";
    b.setAttribute("aria-label", oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
  }

  /* ---------- Eventos ---------- */
  function eventos() {
    const alTocarFicha = (e) => {
      if (e.target.closest("a")) return;
      const c = e.target.closest(".card");
      if (c) abrir(c.dataset.id);
    };
    const alTeclear = (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("card")) { e.preventDefault(); abrir(e.target.dataset.id); }
    };
    for (const cont of [$("#grid"), $("#tiraRecien")]) {
      cont.addEventListener("click", alTocarFicha);
      cont.addEventListener("keydown", alTeclear);
    }
    $("#chips").addEventListener("click", (e) => {
      const b = e.target.closest(".chip");
      if (b) { S.filtro = b.dataset.filtro; render(); }
    });
    document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => {
      S.filtro = b.dataset.ir === "Pokémon" ? "pkm" : "hw";
      render();
      $("#stock").scrollIntoView();
    }));
    let espera;
    $("#buscar").addEventListener("input", (e) => {
      clearTimeout(espera);
      espera = setTimeout(() => { S.q = e.target.value; render(); }, 120);
    });
    $("#serie").addEventListener("change", (e) => { S.serie = e.target.value; render(); });
    $("#orden").addEventListener("change", (e) => { S.orden = e.target.value; render(); });
    const m = $("#modal");
    m.addEventListener("click", async (e) => {
      if (e.target === m || e.target.closest(".cerrar")) { m.close(); return; }
      if (e.target.closest("[data-apartar]") && window.CWAsistente && S.abierta) {
        m.close();
        window.CWAsistente.apartar(S.abierta);
        return;
      }
      const b = e.target.closest("[data-copiar]");
      if (!b) return;
      const caja = $("#mensajePieza");
      try { await navigator.clipboard.writeText(caja.value); } catch (_) { caja.select(); document.execCommand("copy"); }
      b.textContent = "¡Copiado!";
      setTimeout(() => { b.textContent = "Copiar mensaje"; }, 1800);
    });
    $("#darkModeToggle").addEventListener("click", () => {
      const nuevo = document.documentElement.getAttribute("data-tema") === "oscuro" ? "claro" : "oscuro";
      document.documentElement.setAttribute("data-tema", nuevo);
      try { localStorage.setItem("cw_tema", nuevo); } catch (_) { /* sin almacenamiento */ }
      pintarBotonTema();
    });
  }

  /* ---------- Arranque ---------- */
  function iniciar() {
    const hw = PIEZAS.filter((p) => p.tipo === "Hot Wheels").reduce((n, p) => n + (p.disponible || 0), 0);
    const pk = PIEZAS.filter((p) => p.tipo === "Pokémon").reduce((n, p) => n + (p.disponible || 0), 0);
    $("#conteoHW").textContent = `${hw} ${hw === 1 ? "pieza" : "piezas"} en stock`;
    $("#conteoPKM").textContent = `${pk} ${pk === 1 ? "carta" : "cartas"} en stock`;
    $("#avisoMuestra").hidden = !STOCK.muestra;
    if (STOCK.generado) $("#actualizado").textContent = `Actualizado: ${STOCK.generado}`;

    if (FB) { $("#btnMessenger").href = linkMessenger("Hola, vi tu página de Chicos Wheels y quiero preguntar por una pieza."); $("#btnMessenger").hidden = false; }
    if (IG) { $("#btnInstagram").href = linkInstagram(); $("#btnInstagram").hidden = false; }
    $("#sinRedes").hidden = !!(FB || IG);

    // Fotos de ejemplo con licencia libre: se da crédito a sus autores.
    if (Array.isArray(STOCK.creditos_fotos) && STOCK.creditos_fotos.length) {
      $("#listaCreditos").innerHTML = STOCK.creditos_fotos.map((c) => `<li>${esc(c)}</li>`).join("");
      $("#creditos").hidden = false;
    }

    // Portada: si existe img/portada.png se usa; si no, quedan las tarjetas.
    const portada = $("#portada");
    const usarPortada = () => { $("#heroImagen").hidden = false; $("#heroTarjetas").hidden = true; };
    if (portada.complete && portada.naturalWidth) usarPortada();
    else portada.addEventListener("load", usarPortada, { once: true });

    pintarBotonTema();
    pintarSeries();
    pintarRecien();
    render();
    eventos();
  }

  iniciar();
})();
