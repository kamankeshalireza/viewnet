/* Variant picker: reads server-rendered JSON, finds the variant matching the chosen axes. */
(function () {
  var dataEl = document.getElementById('variants-data');
  var root = document.getElementById('product-purchase');
  if (!dataEl || !root) return;
  var data = JSON.parse(dataEl.textContent);
  var priceEl = document.getElementById('product-price');
  var compareEl = document.getElementById('product-compare');
  var skuEl = document.getElementById('product-sku');
  var msgEl = document.getElementById('variant-message');
  var buy = document.getElementById('add-to-cart-btn');

  function selection() {
    var sel = {};
    root.querySelectorAll('input[data-axis]:checked').forEach(function (i) { sel[i.dataset.axis] = i.value; });
    return sel;
  }
  function matches(v, sel) {
    return data.axes.every(function (ax) { return String(v.axes[ax.key] || '') === String(sel[ax.key] || ''); });
  }
  function update() {
    var sel = selection();
    var v = data.variants.find(function (x) { return matches(x, sel); });
    if (!v) {
      msgEl.textContent = 'این ترکیب موجود نیست.';
      msgEl.hidden = false;
      if (buy) buy.disabled = true;
      return;
    }
    msgEl.hidden = true;
    priceEl.textContent = v.price;
    compareEl.textContent = v.compare || '';
    compareEl.hidden = !v.compare;
    skuEl.textContent = v.sku;
    if (buy) { buy.disabled = false; buy.dataset.variant = v.id; }
  }
  root.addEventListener('change', update);
  update();

  // Gallery thumbnails
  var main = document.getElementById('gallery-main');
  var mainLink = document.getElementById('gallery-main-link');
  document.querySelectorAll('[data-gallery-thumb]').forEach(function (t) {
    t.addEventListener('click', function (e) {
      e.preventDefault();
      if (main) main.src = t.dataset.detail;
      if (mainLink) mainLink.href = t.dataset.zoom;
    });
  });
})();
