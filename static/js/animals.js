(function () {
  var head = document.querySelector('.page-head');
  var layout = document.querySelector('.an-layout');
  if (!layout) return;
  var form = layout.querySelector('.an-search-form');
  var debounce = null;

  function bindRows() {
    const rows = layout.querySelectorAll('.an-row'), panels = layout.querySelectorAll('.an-panel');
    const detail = layout.querySelector('.an-detail');
    function activateTab(panel, name) {
      panel.querySelectorAll('[data-tab]').forEach(x => {
        const on = x.dataset.tab === name;
        x.classList.toggle('on', on); x.setAttribute('aria-pressed', String(on));
      });
      panel.querySelectorAll('.an-pane').forEach(p => { p.hidden = p.dataset.pane !== name; });
    }
    function show(id) {
      panels.forEach(p => p.hidden = p.dataset.panel !== id);
      rows.forEach(r => r.classList.toggle('selected', r.dataset.select === id));
      const shown = Array.from(panels).find(p => p.dataset.panel === id);
      if (shown) activateTab(shown, 'profile');   // a newly opened animal always starts on its profile
      if (detail) detail.hidden = false;
      if (detail && window.matchMedia('(max-width:1100px)').matches) detail.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
    if (detail) detail.querySelectorAll('[data-tab]').forEach(t => {
      // Vaccination switches to this animal's own records
      t.addEventListener('click', () => activateTab(t.closest('.an-panel'), t.dataset.tab));
    });
    rows.forEach(r => {
      r.addEventListener('click', e => { if (!e.target.closest('a')) show(r.dataset.select); });
      r.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(r.dataset.select); } });
    });
  }

  function bindFilters() {
    form.querySelector('input[name="q"]').addEventListener('input', scheduleReload);
    form.querySelectorAll('select').forEach(s => s.addEventListener('change', scheduleReload));
  }

  function scheduleReload() {
    clearTimeout(debounce);
    debounce = setTimeout(reload, 350);
  }

  function reload() {
    const url = window.location.pathname + '?' + new URLSearchParams(new FormData(form)).toString();
    fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
      .then(r => r.text())
      .then(html => {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const freshLayout = doc.querySelector('.an-layout');
        const freshHead = doc.querySelector('.page-head');
        if (!freshLayout) { window.location = url; return; }   // safety: fall back to plain navigation
        if (head && freshHead) head.replaceWith(freshHead);
        layout.replaceWith(freshLayout);
        layout = document.querySelector('.an-layout');
        head = document.querySelector('.page-head');
        form = layout.querySelector('.an-search-form');
        history.replaceState(null, '', url);
        bindRows();
        bindFilters();
        const q = form.querySelector('input[name="q"]');
        if (q) { const n = q.value.length; q.focus(); q.setSelectionRange(n, n); }
      })
      .catch(function () { /* keep current view on network hiccup */ });
  }

  bindRows();
  bindFilters();
})();
