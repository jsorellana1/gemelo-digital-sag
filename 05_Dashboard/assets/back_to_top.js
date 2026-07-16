// back_to_top.js — Simulador Operacional (rediseno navegacion, 2026-07-14)
//
// Muestra/oculta el boton flotante "Volver arriba" segun scroll. Se
// implementa como listener JS nativo (no un clientside_callback de Dash)
// a proposito: app.py documenta (linea ~380) un bug real ya encontrado y
// revertido con un contador clientside que interactuaba mal con el
// "snapshot" unico de despacho de callbacks de Dash. Un simple toggle de
// clase sobre un elemento por id, sin leer/escribir ningun Store de Dash,
// no entra en ese grafo reactivo y evita la clase de bug por completo.
(function () {
  var SHOW_AFTER_PX = 480;

  function toggleBackToTop() {
    var wrapper = document.getElementById("sim-back-to-top-wrapper");
    if (!wrapper) return;
    if (window.scrollY > SHOW_AFTER_PX) {
      wrapper.classList.remove("d-none");
    } else {
      wrapper.classList.add("d-none");
    }
  }

  function scrollToTopOnClick(evt) {
    var btn = evt.target.closest("#btn-back-to-top");
    if (!btn) return;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  window.addEventListener("scroll", toggleBackToTop, { passive: true });
  document.addEventListener("DOMContentLoaded", toggleBackToTop);
  document.addEventListener("click", scrollToTopOnClick);
})();
