(function () {
  var form = document.getElementById('ivFilters');
  if (form) {
    form.querySelectorAll('select').forEach(function (sel) {
      sel.addEventListener('change', function () { form.submit(); });
    });
    var q = form.querySelector('input[name="q"]');
    if (q) {
      q.addEventListener('input', function () {
        if (this.value.length === 0 || this.value.length >= 2) {
          clearTimeout(form._qTimer);
          form._qTimer = setTimeout(function () { form.submit(); }, 400);
        }
      });
    }
  }

  // Item detail popup: click a card to view, X or outside click to close.
  var modal = document.getElementById('ivModal');
  if (!modal) return;
  var photo = document.getElementById('ivModalPhoto');
  var nameEl = document.getElementById('ivModalName');
  var catEl = document.getElementById('ivModalCat');
  var pillsEl = document.getElementById('ivModalPills');
  var factsEl = document.getElementById('ivModalFacts');
  var deleteBtn = document.getElementById('ivModalDelete');
  var currentItem = null;

  function open(data) {
    currentItem = data;
    photo.innerHTML = data.image
      ? '<img src="' + data.image + '" alt="' + data.name + '">'
      : '<span class="iv-ph-none">&#128230;</span>';
    nameEl.textContent = data.name || '';
    catEl.textContent = data.category || '';
    pillsEl.innerHTML = '<span class="iv-pill sev-' + String(data.stock || '').toLowerCase().replace(/\s+/g, '-') + '">' + (data.stock || '') + '</span>'
      + (data.expiry && data.expiry !== 'Valid'
         ? '<span class="iv-pill sev-' + data.expiry.toLowerCase().replace(/\s+/g, '-') + '">' + data.expiry + '</span>' : '');
    var rows = [
      ['Item ID', data.id], ['Quantity', data.quantity + ' ' + (data.unit || '')],
      ['Minimum stock', data.min], ['Unit cost', data.cost], ['Selling price', data.price],
      ['Total value', data.value], ['Expiration', data.expires],
      ['Batch / lot', data.batch], ['Manufacturer', data.manufacturer], ['Supplier', data.supplier]
    ];
    factsEl.innerHTML = rows.map(function (r) {
      return '<div><dt>' + r[0] + '</dt><dd>' + (r[1] || '-') + '</dd></div>';
    }).join('');
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }
  function close() {
    modal.hidden = true;
    currentItem = null;
    document.body.style.overflow = '';
  }

  // Delete only after an explicit confirmation naming the selected item.
  if (deleteBtn) {
    deleteBtn.addEventListener('click', function () {
      if (!currentItem || !currentItem.id) return;
      var name = currentItem.name || currentItem.id;
      var confirmDlg = document.getElementById('confirmDialog');
      if (!confirmDlg || !confirmDlg.showModal) {
        if (!window.confirm('Delete ' + name + ' from inventory? This cannot be undone.')) return;
      } else {
        confirmDlg.querySelector('[data-msg]').textContent =
          'Delete ' + name + ' (' + currentItem.id + ') from inventory? This cannot be undone.';
        confirmDlg.showModal();
      }
      var proceed = function () {
        if (confirmDlg && confirmDlg.open) confirmDlg.close();
        var url = '/inventory/' + encodeURIComponent(currentItem.id) + '/delete';
        var tok = document.getElementById('pawCsrf');
        var body = new URLSearchParams();
        if (tok) body.append('csrf_token', tok.value);
        fetch(url, {
          method: 'POST', body: body, credentials: 'same-origin',
          headers: { 'X-Requested-With': 'fetch' }
        }).then(function (r) {
          if (!r.ok) throw new Error(String(r.status));
          return r.text().then(function (html) {
            var doc = new DOMParser().parseFromString(html, 'text/html');
            var fl = doc.querySelector('.flashes');
            close();                                     // close only the detail popup
            if (window.pawRefreshPage) window.pawRefreshPage(fl ? fl.innerHTML : '');
            else window.location.reload();
          });
        }).catch(function () {
          var w = document.createElement('div');
          w.className = 'flash error';
          w.textContent = 'Could not delete the item. Please try again.';
          var box = document.querySelector('main.content');
          if (box) box.insertBefore(w, box.firstChild);
        });
      };
      if (!confirmDlg || !confirmDlg.showModal) { proceed(); return; }
      var yes = confirmDlg.querySelector('[data-yes]');
      var no = confirmDlg.querySelector('[data-no]');
      yes.onclick = proceed;
      no.onclick = function () { confirmDlg.close(); };   // cancel: close only, delete nothing
    });
  }

  document.querySelectorAll('.iv-open-detail').forEach(function (card) {
    function show() {
      try { open(JSON.parse(card.getAttribute('data-detail'))); }
      catch (e) { /* ignore malformed data */ }
    }
    card.addEventListener('click', function (e) {
      if (e.target.closest('[data-no-modal]')) return;
      show();
    });
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(); }
    });
  });
  modal.querySelectorAll('[data-modal-close]').forEach(function (el) {
    el.addEventListener('click', close);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !modal.hidden) close();
  });
})();
