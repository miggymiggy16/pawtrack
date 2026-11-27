/* PawTrack small helpers: mobile menu, delete confirmations, show/hide password, flash close */
(function () {
  const menu = document.getElementById('menuBtn'), side = document.getElementById('sidebar');
  if (menu && side) menu.addEventListener('click', () => side.classList.toggle('open'));

  // No future dates on record/history fields. Fields whose whole purpose is a
  // future date (next due date, expiry, due-date filters) opt out with data-allow-future.
  // Every date field also rejects years longer than 4 digits.
  (function () {
    const now = new Date();
    const today = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 10);
    document.querySelectorAll('input[type="date"]').forEach(input => {
      if (!input.hasAttribute('data-allow-future') && !input.max) input.max = today;
      input.addEventListener('input', () => {
        const year = (input.value || '').split('-')[0];
        input.setCustomValidity(year.length > 4 ? 'Year must have at most 4 digits.' : '');
      });
    });
  })();

  // Confirmation dialog for any <form data-confirm="message">
  const dlg = document.getElementById('confirmDialog');
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      if (form.dataset.ok === '1') return;
      e.preventDefault();
      if (!dlg || !dlg.showModal) { if (confirm(form.dataset.confirm)) { form.dataset.ok = '1'; form.submit(); } return; }
      dlg.querySelector('[data-msg]').textContent = form.dataset.confirm;
      dlg.showModal();
      dlg.querySelector('[data-yes]').onclick = () => { dlg.close(); form.dataset.ok = '1'; form.submit(); };
      dlg.querySelector('[data-no]').onclick = () => dlg.close();
    });
  });

  document.querySelectorAll('[data-toggle-pw]').forEach(btn => btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.togglePw);
    input.type = input.type === 'password' ? 'text' : 'password';
    btn.textContent = input.type === 'password' ? 'Show' : 'Hide';
  }));
  // Login page: press and HOLD the eye to show the password; release it and the password is masked again.
  document.querySelectorAll('[data-hold-pw]').forEach(btn => {
    const input = document.getElementById(btn.dataset.holdPw);
    if (!input) return;
    let shown = false;
    const show = () => { if (shown) return; shown = true; input.type = 'text'; btn.classList.add('holding'); };
    const hide = () => { if (!shown) return; shown = false; input.type = 'password'; btn.classList.remove('holding'); };
    btn.addEventListener('mousedown', show);
    window.addEventListener('mouseup', hide);            // releasing anywhere masks it again
    btn.addEventListener('touchstart', e => { e.preventDefault(); show(); }, { passive: false });
    window.addEventListener('touchend', hide);
    window.addEventListener('touchcancel', hide);
    btn.addEventListener('keydown', e => {               // hold Space or Enter while focused
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); show(); }
    });
    btn.addEventListener('keyup', e => {
      if (e.key === ' ' || e.key === 'Enter') hide();
    });
    btn.addEventListener('blur', hide);
  });
  document.querySelectorAll('.flash button').forEach(b => b.addEventListener('click', () => b.parentElement.remove()));
  document.querySelectorAll('[data-print]').forEach(b => b.addEventListener('click', () => window.print()));
})();

/* ---------- Theme (light / dark) ----------
   <html data-theme> is set early in <head>; this wires the toggle button(s), saves the choice in
   localStorage and tells the charts to redraw. Colours themselves live in style.css. */
const PAW_THEME_KEY = 'pawtrack-theme';
const pawTheme = () => document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
function pawSyncToggles() {
  const dark = pawTheme() === 'dark', label = dark ? 'Switch to light mode' : 'Switch to dark mode';
  document.querySelectorAll('[data-theme-toggle]').forEach(b => {
    b.setAttribute('aria-label', label); b.title = label; b.setAttribute('aria-pressed', String(dark));
  });
}
function pawSetTheme(t, persist) {
  const root = document.documentElement;
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    root.classList.add('theme-anim'); clearTimeout(window._pawAnim);
    window._pawAnim = setTimeout(() => root.classList.remove('theme-anim'), 300);
  }
  root.setAttribute('data-theme', t);
  if (persist) { try { localStorage.setItem(PAW_THEME_KEY, t); } catch (e) {} }
  pawSyncToggles(); pawRedrawCharts();
}
document.querySelectorAll('[data-theme-toggle]').forEach(b =>
  b.addEventListener('click', () => pawSetTheme(pawTheme() === 'dark' ? 'light' : 'dark', true)));
window.addEventListener('storage', e => {              // keep other open tabs in sync
  if (e.key === PAW_THEME_KEY && (e.newValue === 'light' || e.newValue === 'dark')) pawSetTheme(e.newValue, false);
});
pawSyncToggles();

/* Chart.js defaults + a blue palette used by every chart (re-read on every theme change) */
const PAW_PALETTES = {
  dark: ['#3159A8', '#AFCDF5', '#6C95E0', '#DCEAFF', '#1F3F85', '#8FB4F0', '#4F7BD0', '#C5DCFA', '#2A4C94', '#7FA3E6'],
  light: ['#2A4C94', '#6C95E0', '#1F3F85', '#8FB4F0', '#3B6AC6', '#AFCDF5', '#4F7BD0', '#5C86D6', '#7FA3E6', '#C5DCFA']
};
const PAW_UI = {
  dark: { text: '#DCEAFF', grid: 'rgba(255,255,255,.14)', line: '#AFCDF5', fill: 'rgba(175,205,245,.25)', edge: '#0A0A0A', title: '#fff' },
  light: { text: '#24407F', grid: 'rgba(31,63,133,.14)', line: '#2A4C94', fill: 'rgba(42,76,148,.15)', edge: '#FFFFFF', title: '#0F1B3D' }
};
const PAW_REG = [];                                   // every chart drawn on this page, so it can be redrawn
function pawApplyDefaults() {
  const ui = PAW_UI[pawTheme()];
  Chart.defaults.color = ui.text;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.borderColor = ui.grid;
}
function pawCharts() {
  if (typeof Chart === 'undefined') {
    document.querySelectorAll('.chart-box').forEach(b => b.innerHTML = '<p class="empty">Charts need an internet connection to load Chart.js.</p>');
    return false;
  }
  pawApplyDefaults();
  return true;
}
function pawDraw(r) {
  const ui = PAW_UI[pawTheme()], type = r.type, opts = r.opts, round = type === 'doughnut' || type === 'pie';
  new Chart(r.el, {
    type: type,
    data: { labels: r.labels, datasets: [{
      label: opts.label || '', data: r.values,
      backgroundColor: opts.colors || (type === 'line' ? ui.fill : PAW_PALETTES[pawTheme()]),
      borderColor: type === 'line' ? ui.line : (round ? ui.edge : ui.line),
      borderWidth: type === 'line' ? 3 : (round ? 2 : 1), fill: type === 'line', tension: .3,
      borderRadius: type === 'bar' ? 8 : 0, pointRadius: type === 'line' ? 4 : 0 }] },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: opts.horizontal ? 'y' : 'x',
      plugins: { legend: { display: round, position: 'bottom' }, title: { display: !!opts.title, text: opts.title, color: ui.title, font: { size: 14, weight: '700' } } },
      scales: round ? {} : { y: { beginAtZero: true, max: opts.max, ticks: { precision: 0 } }, x: { grid: { display: false } } } }
  });
}
function pawChart(id, type, labels, values, opts) {
  const el = document.getElementById(id);
  if (!el) return;
  opts = opts || {};
  if (!labels.length || values.every(v => !v)) {
    el.parentElement.innerHTML = '<p class="empty">No data yet.</p>';
    return;
  }
  const r = { el: el, type: type, labels: labels, values: values, opts: opts };
  PAW_REG.push(r); pawDraw(r);
}
function pawRedrawCharts() {
  if (typeof Chart === 'undefined' || !PAW_REG.length) return;
  pawApplyDefaults();
  PAW_REG.forEach(r => { const old = Chart.getChart(r.el); if (old) old.destroy(); pawDraw(r); });
}

/* ---------- Searchable animal picker (Add / Edit vaccination) ----------
   Enhances <select data-animal-search>. The original <select> stays in the form as the
   single source of truth, so the saved vaccination always uses the chosen Animal ID. */
(function () {
  document.querySelectorAll('select[data-animal-search]').forEach(sel => {
    const animals = Array.from(sel.options).filter(o => o.value).map(o => ({
      id: o.value, name: o.dataset.name || '', species: o.dataset.species || '',
      breed: o.dataset.breed || '', owner: o.dataset.owner || ''
    }));
    const label = document.querySelector('label[for="' + sel.id + '"]');
    const wrap = document.createElement('div'); wrap.className = 'combo';
    const input = document.createElement('input');
    input.type = 'text'; input.id = sel.id + '_search'; input.autocomplete = 'off';
    input.placeholder = 'Search by Animal ID or name...';
    input.setAttribute('role', 'combobox'); input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false'); input.setAttribute('aria-controls', sel.id + '_list');
    const list = document.createElement('ul'); list.className = 'combo-list'; list.id = sel.id + '_list';
    list.setAttribute('role', 'listbox'); list.hidden = true;
    const card = document.createElement('div'); card.className = 'combo-selected'; card.hidden = true;
    card.setAttribute('aria-live', 'polite');
    const err = document.createElement('small'); err.className = 'combo-error'; err.hidden = true;
    wrap.append(input, list); sel.insertAdjacentElement('afterend', wrap); wrap.after(card); card.after(err);
    const required = sel.required; sel.required = false; sel.style.display = 'none';
    if (label) label.htmlFor = input.id;

    let shown = [], active = -1, chosenText = '';
    const text = a => a.id + ' \u2014 ' + a.name;
    const add = (parent, tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; e.textContent = txt; parent.append(e); return e; };

    function matches(q) {
      q = q.trim().toLowerCase();
      if (!q) return animals.slice(0, 30);
      const score = a => {
        const id = a.id.toLowerCase(), nm = a.name.toLowerCase();
        if (id === q) return 0; if (id.startsWith(q)) return 1; if (nm.startsWith(q)) return 2;
        if (id.includes(q) || nm.includes(q)) return 3;
        if ((a.species + ' ' + a.breed + ' ' + a.owner).toLowerCase().includes(q)) return 4;
        return 9;
      };
      return animals.map(a => [score(a), a]).filter(p => p[0] < 9).sort((x, y) => x[0] - y[0]).map(p => p[1]).slice(0, 30);
    }
    function open(q) {
      shown = matches(q); active = shown.length ? 0 : -1; list.textContent = '';
      if (!shown.length) add(list, 'li', 'combo-empty', 'No registered animal matches "' + q.trim() + '".');
      shown.forEach((a, i) => {
        const li = add(list, 'li', 'combo-item' + (i === active ? ' active' : ''), '');
        li.setAttribute('role', 'option'); li.dataset.i = i;
        const top = add(li, 'div', 'combo-top', ''); add(top, 'b', '', a.id); top.append(' \u00b7 '); add(top, 'span', 'combo-name', a.name);
        add(li, 'small', '', [a.species, a.breed, a.owner].filter(Boolean).join(' \u00b7 '));
      });
      list.hidden = false; input.setAttribute('aria-expanded', 'true');
    }
    function close() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); }
    function highlight(n) {
      const items = list.querySelectorAll('.combo-item'); if (!items.length) return;
      active = (n + items.length) % items.length;
      items.forEach((li, i) => li.classList.toggle('active', i === active));
      items[active].scrollIntoView({ block: 'nearest' });
    }
    function choose(a) {
      sel.value = a.id; chosenText = text(a); input.value = chosenText; close(); err.hidden = true;
      card.textContent = '';
      add(card, 'b', '', 'Selected animal: '); card.append(text(a));
      add(card, 'div', 'small', [a.species, a.breed].filter(Boolean).join(' \u00b7 ') + ' \u00b7 Owner: ' + (a.owner || '-'));
      const change = add(card, 'button', 'btn sm ghost', 'Change animal'); change.type = 'button';
      change.addEventListener('click', () => { clear(); input.value = ''; input.focus(); open(''); });
      card.hidden = false;
    }
    function clear() { sel.value = ''; chosenText = ''; card.hidden = true; }

    input.addEventListener('focus', () => open(sel.value ? '' : input.value));
    input.addEventListener('input', () => { if (sel.value && input.value !== chosenText) clear(); open(input.value); });
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); list.hidden ? open(input.value) : highlight(active + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(active - 1); }
      else if (e.key === 'Escape') close();
      else if (e.key === 'Enter') {
        if (!list.hidden && shown[active]) { e.preventDefault(); choose(shown[active]); }
        else if (!sel.value) {
          const q = input.value.trim().toLowerCase(), exact = animals.filter(a => a.id.toLowerCase() === q);
          if (exact.length === 1) { e.preventDefault(); choose(exact[0]); }
        }
      }
    });
    list.addEventListener('mousedown', e => {          // mousedown so the input does not lose focus first
      const li = e.target.closest('.combo-item'); if (!li) return;
      e.preventDefault(); choose(shown[+li.dataset.i]);
    });
    document.addEventListener('click', e => { if (!wrap.contains(e.target)) close(); });
    input.addEventListener('blur', () => setTimeout(close, 120));
    if (sel.form) sel.form.addEventListener('submit', e => {
      if (required && !sel.value) {
        e.preventDefault(); err.textContent = 'Please pick an animal from the list before saving.'; err.hidden = false; input.focus(); open(input.value);
      }
    });
    const start = animals.find(a => a.id === sel.value);
    if (start) choose(start);
  });
})();

/* ---------- Inventory form helpers: peso formatting + picture preview ---------- */
(function () {
  const money = document.querySelector('input[data-money]');
  if (money) money.addEventListener('blur', () => {
    const v = parseFloat(String(money.value).replace(/[\u20b1,\s]/g, ''));
    if (!isNaN(v) && v >= 0) money.value = v.toFixed(2);
  });
  const file = document.getElementById('image') || document.getElementById('photo');
  const box = document.getElementById('imagePreview');
  if (file && box) file.addEventListener('change', () => {
    const f = file.files[0], note = document.getElementById('imageNote');
    if (note) note.textContent = '';
    if (!f) return;
    if (!/^image\/(png|jpeg|gif|webp)$/.test(f.type) || f.size > 4 * 1024 * 1024) {
      if (note) note.textContent = 'Please choose a PNG, JPG, GIF or WEBP picture of 4 MB or less.';
      file.value = ''; return;
    }
    const img = box.querySelector('img') || box.appendChild(document.createElement('img'));
    img.src = URL.createObjectURL(f); img.alt = 'Selected picture preview'; box.classList.add('has-img');
    const ph = box.querySelector('.ph'); if (ph) ph.hidden = true;
  });
})();

/* ---------- Drop-in file zone: dropping a picture selects it like the picker would ---------- */
(function () {
  const dz = document.querySelector('.dropzone');
  const file = document.getElementById('image') || document.getElementById('photo');
  if (!dz || !file) return;
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); dz.classList.add('drag');
  }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); dz.classList.remove('drag');
  }));
  dz.addEventListener('drop', e => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    const dt = new DataTransfer();
    dt.items.add(f);
    file.files = dt.files;
    file.dispatchEvent(new Event('change', { bubbles: true }));
  });
})();

/* ---------- Inventory: show vaccine-only fields only for the Vaccines category ---------- */
(function () {
  const cat = document.getElementById('category');
  const boxes = document.querySelectorAll('[data-vaccine-only]');
  if (!cat || !boxes.length) return;
  const sync = () => boxes.forEach(b => { b.hidden = cat.value !== 'Vaccines'; });
  cat.addEventListener('change', sync); sync();
})();

/* ---------- Vaccination form: pre-select the matching vaccine stock when the name is typed ----------
   Only a suggestion. It never overrides a choice the person made, and it only picks when exactly one
   stock item matches. The server still checks everything before any stock is deducted. */
(function () {
  const sel = document.querySelector('select[data-stock-link]');
  const name = document.getElementById('vaccine_name');
  if (!sel || !name) return;
  let auto = false;
  sel.addEventListener('change', () => { auto = false; });
  name.addEventListener('input', () => {
    if (sel.value && !auto) return;
    const q = name.value.trim().toLowerCase();
    if (q.length < 3) return;
    const hits = Array.from(sel.options).filter(o => o.value && !o.disabled && (o.dataset.name || '').toLowerCase().includes(q));
    if (hits.length === 1) { sel.value = hits[0].value; auto = true; }
    else if (auto) { sel.value = ''; auto = false; }
  });
})();

/* ---------- Account menu: close when clicking elsewhere or pressing Escape ---------- */
(function () {
  const menu = document.querySelector('.profile-menu');
  if (!menu) return;
  document.addEventListener('click', e => { if (!menu.contains(e.target)) menu.removeAttribute('open'); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') menu.removeAttribute('open'); });
})();

/* ---------- Notification bell: opens a dropdown panel, does not navigate away ---------- */
(function () {
  const bell = document.getElementById('notifBtn'), panel = document.getElementById('notifPanel');
  if (!bell || !panel) return;
  bell.addEventListener('click', e => { e.stopPropagation(); panel.hidden ? panel.removeAttribute('hidden') : panel.setAttribute('hidden', ''); });
  document.addEventListener('click', e => { if (!panel.contains(e.target) && !bell.contains(e.target)) panel.setAttribute('hidden', ''); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') panel.setAttribute('hidden', ''); });

  // Clicking a notification marks it read, then goes to its record (or refreshes so the unread badge stays accurate)
  document.addEventListener('click', async e => {
    const item = e.target.closest('.notif-item');
    if (!item) return;
    const key = item.dataset.notifKey || '';
    const url = item.dataset.notifUrl || '';
    const wasUnread = item.dataset.notifUnread === '1';
    panel.setAttribute('hidden', '');
    try {
      const tok = document.getElementById('pawCsrf') ? document.getElementById('pawCsrf').value : '';
      await fetch('/notifications/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'csrf_token=' + encodeURIComponent(tok) + '&key=' + encodeURIComponent(key)
      });
    } catch (err) { /* best effort; the badge simply refreshes on next load */ }
    if (url) { location.href = url; return; }
    if (wasUnread) location.reload();
  });
})();


/* ---------- Inventory: All Items full-list toggle ---------- */
(function () {
  const btn = document.getElementById('invAllToggle'), list = document.getElementById('invAllList');
  if (!btn || !list) return;
  btn.addEventListener('click', () => {
    const open = list.hasAttribute('hidden');
    list.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  });
})();

/* ---------- Quick photo upload: choosing a file sends it straight away ---------- */
document.querySelectorAll('input[data-autosubmit]').forEach(inp => inp.addEventListener('change', () => {
  const f = inp.files && inp.files[0];
  if (!f) return;
  if (f.size > 4 * 1024 * 1024) { alert('That picture is larger than 4 MB. Please choose a smaller one.'); inp.value = ''; return; }
  inp.form.submit();
}));

/* ---------- App shell: live clock in the top bar, close the mobile sidebar when tapping outside ---------- */
(function () {
  const clock = document.getElementById('tbClock');
  if (clock) {
    const tick = () => { clock.textContent = new Date().toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit', second: '2-digit' }); };
    tick(); setInterval(tick, 1000);
  }
  const side = document.getElementById('sidebar'), btn = document.getElementById('menuBtn');
  document.addEventListener('click', e => {
    if (side && side.classList.contains('open') && !side.contains(e.target) && !(btn && btn.contains(e.target))) side.classList.remove('open');
  });
})();

/* ---------- Register animal: open the form in a popup instead of navigating ---------- */
(function () {
  const dlg = document.getElementById('animalModal');
  if (!dlg || !dlg.showModal) return;
  const frame = document.getElementById('animalModalFrame');

  function close() {
    frame.src = 'about:blank';
    dlg.close();
  }

  document.querySelectorAll('[data-animal-modal]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const url = new URL(link.href, location.href);
      url.searchParams.set('modal', '1');
      frame.src = url.href;
      dlg.showModal();
    });
  });

  const closeBtn = dlg.querySelector('[data-animal-modal-close]');
  if (closeBtn) closeBtn.addEventListener('click', close);
  dlg.addEventListener('click', e => { if (e.target === dlg) close(); });
  dlg.addEventListener('cancel', e => { e.preventDefault(); close(); });

  // When the form saves (or is cancelled) the iframe navigates away from the
  // form. Follow that destination in the main page and dismiss the popup.
  frame.addEventListener('load', () => {
    let href;
    try { href = frame.contentWindow.location.href; } catch (err) { return; }
    if (!href || href === 'about:blank') return;
    const path = new URL(href).pathname;
    if (path === '/animals/new') return;
    const destination = href.replace(/([?&])modal=1&?/, '$1').replace(/[?&]$/, '');
    close();
    location.href = destination;
  });
})();
