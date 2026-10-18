/* ViewNet site behaviors (CSP-friendly: no inline script/eval). */
(function () {
  // Colour swatches: set background from data-hex via CSSOM (allowed even under strict CSP).
  function paintSwatches(root) {
    (root || document).querySelectorAll('[data-hex]').forEach(function (el) {
      el.style.backgroundColor = el.dataset.hex;
    });
  }
  document.addEventListener('DOMContentLoaded', function () { paintSwatches(document); });
  document.body && document.body.addEventListener('htmx:afterSwap', function (e) { paintSwatches(e.target); });
  window.viewnetPaintSwatches = paintSwatches;
})();
