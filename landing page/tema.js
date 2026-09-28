/* Aplica el tema (claro/oscuro) antes de pintar la página: el guardado por el
 * visitante o, si no eligió, el de su sistema. */
(function () {
  var t = null;
  try { t = localStorage.getItem("cw_tema"); } catch (e) { /* sin almacenamiento */ }
  if (!t) t = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
  document.documentElement.setAttribute("data-tema", t);
})();
