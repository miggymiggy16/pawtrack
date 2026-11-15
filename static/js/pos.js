/* PawTrack POS - cashier screen.
   The browser only collects WHAT is sold and HOW MANY. The server re-reads every price,
   re-checks stock and works out the total itself, so nothing here can change what is charged. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  var items = JSON.parse($('catalogData').textContent);
  var byKey = {};
  items.forEach(function (p) { byKey[p.kind + ':' + p.id] = p; });
  var cart = {};                         // key -> quantity
  var category = 'All';
  var busy = false;
  var discOn = false;                    // 20% discount switch
  var DISC_RATE = 0.20;
  var VAT_RATE = 0.12;                  // VAT is already inside every shelf price
  var HELD_KEY = 'pawtrack-pos-held';

  var cents = function (n) { return Math.round(n * 100); };
  var peso = function (c) {
    return '₱' + (c / 100).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var el = function (tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  /* small built-in icons (static markup only; category names are never put into HTML) */
  var ICONS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    syringe: '<path d="M18 2l4 4M17 7l3-3M19 9l-8.7 8.7a2 2 0 0 1-2.8 0L6.3 16.5a2 2 0 0 1 0-2.8L15 5M9 11l4 4M5 19l-3 3M14 4l6 6"/>',
    pill: '<path d="M10.5 20.5a5 5 0 0 1-7-7l10-10a5 5 0 0 1 7 7z"/><path d="M8.5 8.5l7 7"/>',
    tag: '<path d="M20.5 13.5l-7 7a2 2 0 0 1-2.8 0L3 12.8V3h9.8l7.7 7.7a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.2"/>',
    box: '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    paw: '<circle cx="6" cy="10" r="2"/><circle cx="10" cy="5.5" r="2"/><circle cx="15" cy="5.5" r="2"/><circle cx="19" cy="10" r="2"/><path d="M12.5 11c-3 0-6 3.5-6 6 0 2 2 2.5 3.5 2 1.2-.4 1.8-.6 2.5-.6s1.3.2 2.5.6c1.5.5 3.5 0 3.5-2 0-2.5-3-6-6-6z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>'
  };
  var svg = function (name) {
    var s = el('span', 'ico-wrap');
    s.innerHTML = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">' + ICONS[name] + '</svg>';
    return s;
  };
  function catIcon(name) {
    var n = (name || '').toLowerCase();
    if (/vaccin|immun|shot/.test(n)) return 'syringe';
    if (/medic|drug|pharm|tablet|supplement/.test(n)) return 'pill';
    if (/service|consult|groom|check/.test(n)) return 'tag';
    if (/pet|food|accessor|supply|supplies/.test(n)) return 'paw';
    return 'box';
  }

  /* ---------- catalogue ---------- */
  function categories() {
    var names = [];
    items.forEach(function (p) { if (names.indexOf(p.category) < 0) names.push(p.category); });
    return names;
  }
  function countIn(name) {
    return items.filter(function (p) { return name === 'All' || p.category === name; }).length;
  }

  function renderCats() {
    var box = $('posCats');
    box.textContent = '';
    ['All'].concat(categories()).forEach(function (n) {
      var b = el('button', 'po-cat' + (n === category ? ' on' : ''));
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', n === category ? 'true' : 'false');
      b.appendChild(svg(n === 'All' ? 'grid' : catIcon(n)));
      b.appendChild(el('span', 'po-cat-name', n));
      b.appendChild(el('span', 'po-cat-n', String(countIn(n))));
      b.addEventListener('click', function () { category = n; renderCats(); renderGrid(); });
      box.appendChild(b);
    });
  }

  function visible() {
    var q = $('posSearch').value.trim().toLowerCase();
    return items.filter(function (p) {
      return (category === 'All' || p.category === category) &&
             (!q || (p.name + ' ' + p.category).toLowerCase().indexOf(q) >= 0);
    });
  }

  function stockNote(p) {
    if (p.kind === 'service') return 'Service';
    if (p.state === 'out') return 'Out of stock';
    if (p.state === 'expired') return 'Expired';
    return p.stock + ' ' + p.unit + (p.low ? ' (low)' : ' in stock');
  }

  function renderGrid() {
    var grid = $('posGrid');
    var list = visible();
    grid.textContent = '';
    $('posNone').hidden = list.length > 0;
    $('posShowing').textContent = 'Showing ' + list.length + ' item' + (list.length === 1 ? '' : 's');
    list.forEach(function (p) {
      var key = p.kind + ':' + p.id;
      var off = p.state !== 'ok';
      var b = el('button', 'pcard' + (off ? ' off' : '') + (cart[key] ? ' in-cart' : ''));
      b.type = 'button';
      b.disabled = off;
      b.setAttribute('aria-label', 'Add ' + p.name + ', ' + peso(cents(p.price)));

      var pic = el('div', 'pc-img');
      if (p.image) {
        var img = el('img');
        img.src = p.image; img.alt = ''; img.loading = 'lazy';
        pic.appendChild(img);
      } else {
        pic.classList.add('ph');
        pic.appendChild(svg(p.kind === 'service' ? 'tag' : catIcon(p.category)));
      }
      if (off) pic.appendChild(el('span', 'pc-flag bad', p.state === 'out' ? 'Out of stock' : 'Expired'));
      else if (p.low) pic.appendChild(el('span', 'pc-flag warn', 'Low stock'));
      if (cart[key]) pic.appendChild(el('span', 'pc-qty', '×' + cart[key]));
      b.appendChild(pic);

      b.appendChild(el('span', 'pc-name', p.name));
      b.appendChild(el('span', 'pc-sub', p.category + ' · ' + stockNote(p)));
      var foot = el('span', 'pc-foot');
      foot.appendChild(el('span', 'pc-price', peso(cents(p.price))));
      b.appendChild(foot);
      b.addEventListener('click', function () { add(key, 1); });
      grid.appendChild(b);
    });
  }

  /* ---------- cart ---------- */
  function message(text, kind) {
    var box = $('posError');
    box.textContent = text || '';
    box.className = 'po-msg' + (kind ? ' ' + kind : '');
    box.hidden = !text;
  }

  function add(key, n) {
    var p = byKey[key];
    var next = (cart[key] || 0) + n;
    if (next <= 0) { delete cart[key]; message(''); }
    else if (p.kind === 'product' && next > p.stock) {
      message('Only ' + p.stock + ' ' + p.unit + ' of ' + p.name + ' in stock.');
      next = p.stock;
      cart[key] = next;
    } else if (next > 9999) { next = 9999; cart[key] = next; message(''); }
    else { cart[key] = next; message(''); }
    renderCart();
    renderGrid();
  }

  function setQty(key, raw) {
    var n = parseInt(raw, 10);
    if (isNaN(n) || n < 1) n = 1;
    cart[key] = 0;
    add(key, n);
  }

  function totals() {
    var sub = 0;
    Object.keys(cart).forEach(function (k) { sub += cents(byKey[k].price) * cart[k]; });
    var disc = discOn ? Math.round(sub * DISC_RATE) : 0;
    var total = sub - disc;
    // 12% VAT already sits inside the shelf price - we only report it, it is never added on top
    var vat = Math.round(total * VAT_RATE / (1 + VAT_RATE));
    return { sub: sub, disc: disc, total: total, vat: vat };
  }

  function renderCart() {
    var ul = $('cartLines');
    var keys = Object.keys(cart);
    var units = 0;
    ul.textContent = '';
    $('cartEmpty').hidden = keys.length > 0;
    keys.forEach(function (k) {
      var p = byKey[k];
      units += cart[k];
      var li = el('li', 'po-line');
      var top = el('div', 'pl-top');
      var info = el('div', 'pl-info');
      info.appendChild(el('b', '', p.name));
      info.appendChild(el('span', 'pl-each', peso(cents(p.price)) + ' each'));
      var rm = el('button', 'pl-x'); rm.type = 'button'; rm.setAttribute('aria-label', 'Remove ' + p.name);
      rm.appendChild(svg('x'));
      rm.addEventListener('click', function () { delete cart[k]; renderCart(); renderGrid(); });
      top.append(info, rm);

      var bot = el('div', 'pl-bot');
      var ctl = el('div', 'pl-ctl');
      var minus = el('button', 'pl-qb'); minus.type = 'button'; minus.setAttribute('aria-label', 'One less ' + p.name);
      minus.appendChild(svg('minus'));
      minus.addEventListener('click', function () { add(k, -1); });
      var qty = el('input'); qty.type = 'number'; qty.min = 1; qty.step = 1; qty.value = cart[k];
      qty.setAttribute('aria-label', 'Quantity of ' + p.name);
      qty.addEventListener('change', function () { setQty(k, qty.value); });
      var plus = el('button', 'pl-qb'); plus.type = 'button'; plus.setAttribute('aria-label', 'One more ' + p.name);
      plus.appendChild(svg('plus'));
      plus.addEventListener('click', function () { add(k, 1); });
      ctl.append(minus, qty, plus);
      bot.append(ctl, el('span', 'pl-amt', peso(cents(p.price) * cart[k])));
      li.append(top, bot);
      ul.appendChild(li);
    });
    $('orderCount').textContent = units + ' item(s)';
    refreshTotals();
  }

  /* payment method chips mirror the (hidden) select, which is what actually gets submitted */
  function renderPayChips() {
    var box = $('payChips'), sel = $('payment_method');
    box.textContent = '';
    Array.prototype.forEach.call(sel.options, function (o) {
      var b = el('button', 'po-pm' + (o.value === sel.value ? ' on' : ''), o.value);
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', o.value === sel.value ? 'true' : 'false');
      b.addEventListener('click', function () { sel.value = o.value; renderPayChips(); refreshTotals(); });
      box.appendChild(b);
    });
  }

  function refreshTotals() {
    var t = totals();
    var has = Object.keys(cart).length > 0;
    $('tSub').textContent = peso(t.sub);
    $('tDisc').textContent = '−' + peso(t.disc);
    $('discount').value = (t.disc / 100).toFixed(2);
    $('discount_reason').value = t.disc > 0 ? '20% discount' : '';
    $('discBtn').classList.toggle('on', discOn);
    $('discBtn').setAttribute('aria-pressed', discOn ? 'true' : 'false');
    $('tTotal').textContent = peso(t.total);
    $('tVat').textContent = peso(t.vat);
    $('payAmt').textContent = peso(t.total);
    var cash = $('payment_method').value === 'Cash';
    $('cashRow').hidden = !cash;
    $('refRow').hidden = cash;
    var box = $('changeBox');
    var got = cents(parseFloat($('amount_tendered').value) || 0);
    box.className = 'change';
    if (cash && has && $('amount_tendered').value !== '') {
      if (got >= t.total) { box.textContent = 'Change: ' + peso(got - t.total); box.classList.add('ok'); }
      else { box.textContent = 'Short by ' + peso(t.total - got); box.classList.add('bad'); }
    } else { box.textContent = ''; }
    var ready = has && t.total > 0 && (!cash || got >= t.total);
    $('payBtn').disabled = !ready || busy;
  }

  /* ---------- 20% discount ---------- */
  $('discBtn').addEventListener('click', function () { discOn = !discOn; refreshTotals(); });

  /* ---------- hold / resume (kept in this browser only) ---------- */
  function readHeld() {
    try { var a = JSON.parse(localStorage.getItem(HELD_KEY) || '[]'); return Array.isArray(a) ? a : []; }
    catch (e) { return []; }
  }
  function writeHeld(list) {
    try { localStorage.setItem(HELD_KEY, JSON.stringify(list)); } catch (e) {}
    renderHeldBadge();
  }
  function renderHeldBadge() {
    var n = readHeld().length;
    $('heldCount').textContent = n;
    $('heldBtn').classList.toggle('has', n > 0);
  }
  function heldTotal(h) {
    var sub = 0;
    Object.keys(h.lines || {}).forEach(function (k) { if (byKey[k]) sub += cents(byKey[k].price) * h.lines[k]; });
    return sub - (h.disc ? Math.round(sub * DISC_RATE) : 0);
  }
  function resetOrderFields() {
    cart = {}; discOn = false; $('amount_tendered').value = '';
  }
  function holdOrder() {
    if (!Object.keys(cart).length) { message('Add items before holding an order.'); return; }
    var list = readHeld();
    list.push({ id: Date.now(), at: new Date().toISOString(), lines: cart,
                disc: discOn });
    writeHeld(list);
    resetOrderFields();
    message('Order held. Open the pause icon at the top to bring it back.', 'ok');
    renderCart(); renderGrid();
  }
  function resumeOrder(id) {
    if (Object.keys(cart).length) { message('Hold or clear the current order first.'); $('heldDialog').close(); return; }
    var list = readHeld(), h = list.filter(function (x) { return x.id === id; })[0];
    if (!h) return;
    Object.keys(h.lines).forEach(function (k) {
      var p = byKey[k]; if (!p || p.state !== 'ok') return;
      var q = h.lines[k]; if (p.kind === 'product' && q > p.stock) q = p.stock;
      if (q > 0) cart[k] = q;
    });
    discOn = !!h.disc;
    writeHeld(list.filter(function (x) { return x.id !== id; }));
    $('heldDialog').close();
    message(Object.keys(cart).length ? '' : 'Those items are no longer available.');
    renderCart(); renderGrid();
  }
  function renderHeldList() {
    var ul = $('heldList'), list = readHeld();
    ul.textContent = '';
    $('heldNone').hidden = list.length > 0;
    list.forEach(function (h) {
      var units = 0; Object.keys(h.lines || {}).forEach(function (k) { units += h.lines[k]; });
      var li = el('li', 'po-held-row');
      var info = el('div', 'hr-info');
      var when = new Date(h.at);
      info.appendChild(el('b', '', when.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit' }) + ' · ' + units + ' item(s)'));
      info.appendChild(el('span', '', peso(heldTotal(h))));
      var go = el('button', 'btn sm', 'Resume'); go.type = 'button';
      go.addEventListener('click', function () { resumeOrder(h.id); });
      var del = el('button', 'btn sm ghost', 'Discard'); del.type = 'button';
      del.addEventListener('click', function () { writeHeld(readHeld().filter(function (x) { return x.id !== h.id; })); renderHeldList(); });
      li.append(info, go, del);
      ul.appendChild(li);
    });
  }
  $('holdBtn').addEventListener('click', holdOrder);
  $('heldBtn').addEventListener('click', function () { renderHeldList(); $('heldDialog').showModal(); });
  $('heldClose').addEventListener('click', function () { $('heldDialog').close(); });

  /* ---------- checkout ---------- */
  $('checkoutForm').addEventListener('submit', function (e) {
    e.preventDefault();
    if (busy) return;
    var t = totals();
    busy = true; $('payBtn').disabled = true; message('');
    $('cartField').value = JSON.stringify(Object.keys(cart).map(function (k) {
      var p = byKey[k]; return { kind: p.kind, id: p.id, qty: cart[k] };
    }));
    fetch(this.action, { method: 'POST', body: new FormData(this), credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }, function () { return { ok: false, j: null }; }); })
      .then(function (res) {
        if (res.ok && res.j && res.j.ok) { window.location.href = res.j.receipt_url; return; }
        busy = false;
        message(res.j && res.j.error ? res.j.error : 'Could not complete the sale. Refresh the page and try again (your session may have expired).');
        refreshTotals();
      })
      .catch(function () {
        busy = false;
        message('No connection to PawTrack. Nothing was charged - check the network and press Checkout again.');
        refreshTotals();
      });
  });

  $('clearBtn').addEventListener('click', function () {
    resetOrderFields(); message(''); renderCart(); renderGrid();
  });
  $('amount_tendered').addEventListener('input', function () {
    var v = this.value.replace(/[^0-9.]/g, '');
    var i = v.indexOf('.'); if (i >= 0) v = v.slice(0, i + 1) + v.slice(i + 1).replace(/\./g, '').slice(0, 2);
    this.value = v; refreshTotals();
  });
  $('posSearch').addEventListener('input', renderGrid);
  $('posSearch').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    var ok = visible().filter(function (p) { return p.state === 'ok'; });
    if (ok.length === 1) { add(ok[0].kind + ':' + ok[0].id, 1); this.value = ''; renderGrid(); }
  });
  document.addEventListener('keydown', function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') { e.preventDefault(); $('posSearch').focus(); }
  });

  /* ---------- draggable splitter: drag it left to widen the order panel ---------- */
  (function () {
    var resizer = $('poResizer');
    var pos2 = document.querySelector('.pos2');
    if (!resizer || !pos2) return;

    var MIN = 300, MAX = 800, DEFAULT = 460;
    var STORE = 'pawtrack-pos-order-width';
    var desired = DEFAULT;   // the width the user asked for
    var shown = DEFAULT;     // the width actually applied (clamped to the screen)
    var dragging = false, startX = 0, startW = 0;

    function maxFor() {
      var box = pos2.getBoundingClientRect().width || window.innerWidth;
      return Math.max(MIN, Math.min(MAX, Math.floor(box * 0.6)));
    }
    function apply(save) {
      desired = Math.max(MIN, Math.min(MAX, Math.round(desired)));   // keep the wish list inside the hard bounds
      var max = maxFor();
      var w = Math.max(MIN, Math.min(max, desired));                  // ...but never wider than the screen allows
      shown = w;
      pos2.style.setProperty('--po-order-w', w + 'px');
      resizer.setAttribute('aria-valuenow', String(w));
      resizer.setAttribute('aria-valuemin', String(MIN));
      resizer.setAttribute('aria-valuemax', String(max));
      if (save) {
        try { localStorage.setItem(STORE, String(desired)); } catch (e) {}
      }
    }

    try { var saved = parseInt(localStorage.getItem(STORE) || '', 10); if (saved > 0) desired = saved; } catch (e) {}
    apply(false);

    resizer.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      dragging = true;
      startX = e.clientX;
      startW = shown;
      resizer.classList.add('dragging');
      document.body.classList.add('po-resizing');
      try { resizer.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
      resizer.focus();
    });

    resizer.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      e.preventDefault();
      desired = startW + (startX - e.clientX);   // drag left -> the order panel gets wider
      apply(false);
    });

    function endDrag(e) {
      if (!dragging) return;
      dragging = false;
      resizer.classList.remove('dragging');
      document.body.classList.remove('po-resizing');
      try { if (e && e.pointerId != null) resizer.releasePointerCapture(e.pointerId); } catch (err) {}
      apply(true);
    }
    resizer.addEventListener('pointerup', endDrag);
    resizer.addEventListener('pointercancel', endDrag);
    resizer.addEventListener('lostpointercapture', endDrag);
    window.addEventListener('blur', function () { endDrag(); });

    /* keyboard: arrows resize, Enter resets */
    resizer.addEventListener('keydown', function (e) {
      var step = e.shiftKey ? 64 : 24, next = null;
      if (e.key === 'ArrowLeft') next = shown + step;
      else if (e.key === 'ArrowRight') next = shown - step;
      else if (e.key === 'Home') next = maxFor();
      else if (e.key === 'End') next = MIN;
      else if (e.key === 'Enter' || e.key === ' ') next = DEFAULT;
      if (next === null) return;
      e.preventDefault();
      desired = next;
      apply(true);
    });

    resizer.addEventListener('dblclick', function () { desired = DEFAULT; apply(true); });

    /* keep the panel sensible when the window is resized */
    window.addEventListener('resize', function () { apply(false); });
  })();

  renderCats(); renderPayChips(); renderGrid(); renderCart(); renderHeldBadge();
})();
