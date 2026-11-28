(function () {
  var adv = document.querySelector('[data-adv]'), panel = document.getElementById('rpAdv');
  if (adv && panel) adv.addEventListener('click', function () {
    var open = adv.getAttribute('aria-expanded') !== 'true';
    adv.setAttribute('aria-expanded', open); panel.hidden = !open;
  });

  var table = document.getElementById('rptTable'); if (!table) return;
  var groups = Array.from(table.tBodies, function (tb) {
    var head = tb.querySelector('.rpt-ghead');
    return { tb: tb, head: head, closed: false,
             btn: head && head.querySelector('[data-gtoggle]'),
             gcount: head && head.querySelector('.rpt-gcount'),
             rows: Array.from(tb.rows).filter(function (r) { return r.classList.contains('rpt-row'); }) };
  });
  var rows = groups.flatMap(function (g) { return g.rows; });
  var pager = document.getElementById('rptPager'), info = document.getElementById('rptInfo'),
      count = document.getElementById('rptCount'), box = document.getElementById('rptSearch');
  var page = 1, size = 10, term = '';

  rows.forEach(function (r) {
    r.dataset.all = (r.dataset.search + ' ' + r.textContent).toLowerCase().replace(/\s+/g, ' ');
  });
  function matches(r) {
    return !term || r.dataset.all.indexOf(term) >= 0;
  }
  function pbtn(label, on, opts) {
    opts = opts || {};
    var b = document.createElement('button');
    b.type = 'button'; b.textContent = label;
    if (opts.active) b.classList.add('active');
    if (opts.disabled) b.disabled = true;
    if (opts.aria) b.setAttribute('aria-label', opts.aria);
    b.addEventListener('click', on);
    return b;
  }
  function render() {
    var shown = rows.filter(matches), pages = Math.max(1, Math.ceil(shown.length / size));
    page = Math.min(page, pages);
    var start = (page - 1) * size, slice = shown.slice(start, start + size);
    rows.forEach(function (r) { r.hidden = true; });

    groups.forEach(function (g) {
      var onPage = slice.filter(function (r) { return g.rows.indexOf(r) >= 0; });
      if (!g.closed) onPage.forEach(function (r) { r.hidden = false; });
      if (!g.head) return;
      var total = g.rows.filter(matches).length;
      g.tb.classList.toggle('closed', g.closed);
      g.head.hidden = !total || !onPage.length;
      g.btn.setAttribute('aria-expanded', String(!g.closed));
      g.gcount.textContent = onPage.length + ' of ' + total + ' on this page';
    });

    count.textContent = shown.length + ' record' + (shown.length === 1 ? '' : 's');
    info.textContent = shown.length
      ? 'Showing ' + (start + 1) + '-' + Math.min(start + size, shown.length) + ' of ' + shown.length + ' record' + (shown.length === 1 ? '' : 's')
      : 'No matching records';
    pager.textContent = '';
    if (pages > 1) {
      pager.append(pbtn('\u2039', function () { page--; render(); }, { disabled: page === 1, aria: 'Previous page' }));
      for (var p = 1; p <= pages; p++) {
        if (pages > 7 && p !== 1 && p !== pages && Math.abs(p - page) > 1) {
          if (p === 2 || p === pages - 1) { var d = document.createElement('span'); d.textContent = '\u2026'; d.className = 'muted'; pager.append(d); }
          continue;
        }
        (function (n) {
          pager.append(pbtn(n, function () { page = n; render(); }, { active: n === page, aria: 'Page ' + n }));
        })(p);
      }
      pager.append(pbtn('\u203A', function () { page++; render(); }, { disabled: page === pages, aria: 'Next page' }));
    }
    if (rows.length > 10) {
      var sel = document.createElement('select');
      sel.setAttribute('aria-label', 'Rows per page');
      [10, 25, 50, 100].forEach(function (n) {
        var o = document.createElement('option'); o.value = n; o.textContent = n + ' / page'; o.selected = n === size; sel.append(o);
      });
      sel.addEventListener('change', function () { size = +sel.value; page = 1; render(); });
      pager.append(sel);
    }
  }

  groups.forEach(function (g) {
    if (g.btn) g.btn.addEventListener('click', function () { g.closed = !g.closed; render(); });
  });
  box.addEventListener('input', function () { term = box.value.trim().toLowerCase(); page = 1; render(); });
  var searchBox = document.getElementById('rptSearchBox');
  if (searchBox) {
    var openSearch = function (on) { searchBox.classList.toggle('open', on); };
    searchBox.addEventListener('click', function () { openSearch(true); box.focus(); });
    box.addEventListener('focus', function () { openSearch(true); });
    box.addEventListener('blur', function () { if (!box.value) openSearch(false); });
    // the search lives inside the filter form: never submit it on Enter
    box.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
    if (box.value) openSearch(true);
  }
  window.addEventListener('beforeprint', function () {
    rows.forEach(function (r) { r.hidden = !matches(r); });
    groups.forEach(function (g) {
      if (!g.head) return;
      var total = g.rows.filter(matches).length;
      g.head.hidden = !total;
      g.tb.classList.remove('closed');
      // "3 of 3 on this page" makes no sense on paper: show the plain total instead
      g.gcount.textContent = total + ' record' + (total === 1 ? '' : 's');
    });
  });
  window.addEventListener('afterprint', render);
  render();
})();
