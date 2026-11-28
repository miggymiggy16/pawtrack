/* PawTrack: open forms/pages in a centered popup instead of navigating away.
   Closing a popup only closes that popup — it never redirects, and it restores
   the exact page, filters, selection and scroll position it was opened from.
   After a successful save the current page is refreshed in place. */
(function () {
  'use strict';

  var dlg = document.getElementById('formModal');
  if (!dlg) return;
  var body = dlg.querySelector('[data-fm-body]');
  var titleEl = dlg.querySelector('[data-fm-title]');
  var opener = null;          // the element that opened the current popup
  var openerHref = null;      // its href (used to re-render nested popups)
  var generation = 0;         // ignore responses from a previous popup
  var scriptNodes = [];
  var linkNodes = [];
  var savedScroll = 0;

  function clearInjected() {
    scriptNodes.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    scriptNodes = [];
    linkNodes.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    linkNodes = [];
  }

  // Load stylesheets the fetched page declares so its scoped styles apply.
  function loadStyles(doc) {
    var loaded = {};
    Array.prototype.forEach.call(document.querySelectorAll('link[rel="stylesheet"]'), function (l) {
      loaded[l.href] = true;
    });
    Array.prototype.forEach.call(doc.querySelectorAll('link[rel="stylesheet"]'), function (l) {
      var href = l.href;
      if (!href || loaded[href]) return;
      var node = document.createElement('link');
      node.rel = 'stylesheet';
      node.href = href;
      document.head.appendChild(node);
      loaded[href] = true;
      linkNodes.push(node);
    });
  }

  // Run the fetched page's own scripts (inline + page-specific files), skipping
  // shared scripts the host page already loaded. Returns nothing; scripts are async.
  function runScripts(doc) {
    var loaded = {};
    Array.prototype.forEach.call(document.scripts, function (s) {
      var src = s.getAttribute('src');
      if (src) { loaded[src] = true; loaded[new URL(src, location.href).href] = true; }
    });
    Array.prototype.forEach.call(doc.body.querySelectorAll('script'), function (s) {
      var src = s.getAttribute('src');
      var abs = src ? new URL(src, location.href).href : null;
      if (src && (loaded[src] || loaded[abs])) return;
      var node = document.createElement('script');
      if (src) { node.src = abs || src; loaded[src] = true; loaded[abs] = true; }
      else node.textContent = s.textContent;
      document.head.appendChild(node);
      scriptNodes.push(node);
    });
  }

  /* ---------- close: only this popup, restore exact previous state ---------- */
  function close() {
    generation++;                       // invalidate any in-flight fetch/render
    if (dlg.open) dlg.close();          // 'close' event -> finish()
    else finish();
  }

  function finish() {
    if (dlg.open) return;               // a newer popup is already open
    clearInjected();
    body.innerHTML = '';
    dlg.className = 'fm-dialog';
    document.documentElement.classList.remove('fm-open');
    var back = opener;
    opener = null;
    openerHref = null;
    if (back && document.contains(back) && back.focus) { try { back.focus(); } catch (e) {} }
    if (savedScroll) { window.scrollTo(0, savedScroll); savedScroll = 0; }
  }

  dlg.addEventListener('close', finish);
  dlg.addEventListener('cancel', function (e) { e.preventDefault(); close(); });

  /* ---------- capture / restore in-page state ---------- */
  function captureState() {
    var state = { scroll: window.scrollY || window.pageYOffset || 0, tabs: [], panels: [] };
    document.querySelectorAll('.an-tabs .tab.on, .ma-tabs a.active, .mv-tabs a.active, .rpt-subtabs a.active')
      .forEach(function (el) { state.tabs.push(el.dataset.tab || el.textContent.trim()); });
    document.querySelectorAll('.an-panel:not([hidden])').forEach(function (el) { state.panels.push(el.dataset.panel); });
    return state;
  }
  function restoreState(state) {
    if (!state) return;
    state.tabs.forEach(function (name) {
      var el = Array.prototype.find.call(document.querySelectorAll('.an-tabs .tab'), function (t) {
        return (t.dataset.tab || t.textContent.trim()) === name;
      });
      if (el) el.click();
    });
    state.panels.forEach(function (id) {
      var panel = document.querySelector('.an-panel[data-panel="' + id + '"]');
      if (panel) panel.hidden = false;
    });
    window.scrollTo(0, state.scroll);
  }

  /* ---------- refresh the host page in place (no redirect / no reload) ---------- */
  function refreshPage(flashes, myGen) {
    var state = captureState();
    return fetch(window.location.href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        if (myGen !== generation) return;
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var fresh = doc.querySelector('main.content');
        var current = document.querySelector('main.content');
        if (!fresh || !current) { window.location.reload(); return; }  // last-resort only
        current.innerHTML = fresh.innerHTML;
        if (flashes) {
          var bar = document.createElement('div');
          bar.className = 'flashes'; bar.setAttribute('role', 'status'); bar.innerHTML = flashes;
          current.insertBefore(bar, current.firstChild);
        }
        // Re-run this page's own scripts so fresh elements get their handlers.
        runScripts(doc);
        restoreState(state);
      })
      .catch(function () { /* leave the current page untouched */ });
  }

  /* ---------- render / bind ---------- */
  function bind(pageUrl) {
    var form = body.querySelector('form');
    if (!form) return;
    if (!form.getAttribute('action')) form.setAttribute('action', pageUrl);
    if (!form.querySelector('input[name="next"]')) {
      var next = document.createElement('input');
      next.type = 'hidden'; next.name = 'next';
      next.value = window.location.pathname + window.location.search;
      form.appendChild(next);
    }
    form.addEventListener('submit', submit);
  }

  function render(html, pageUrl, myGen) {
    if (myGen !== generation) return;
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var content = doc.querySelector('main.content');
    if (!content) { window.location = pageUrl; return; }  // safety fallback
    var head = content.querySelector('.page-head');
    var h1 = head && head.querySelector('h1');
    if (h1) titleEl.textContent = h1.textContent.trim();
    if (head) head.remove();
    dlg.className = ('fm-dialog ' + doc.body.className.trim()).trim();
    clearInjected();
    body.innerHTML = content.innerHTML;
    loadStyles(doc);
    runScripts(doc);
    if (window.pawInitAnimalPicker) window.pawInitAnimalPicker(body);
    bind(pageUrl);
    body.scrollTop = 0;
  }

  function submit(e) {
    e.preventDefault();
    var form = e.currentTarget;
    if (form.dataset.fmBusy) return;
    form.dataset.fmBusy = '1';
    var myGen = generation;
    var btn = form.querySelector('[type="submit"]');
    var label = btn && btn.innerHTML;
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
    var action = form.getAttribute('action');

    function retry() {
      form.dataset.fmBusy = '';
      if (btn && document.contains(btn)) { btn.disabled = false; btn.innerHTML = label; }
    }
    fetch(action, {
      method: 'POST', body: new FormData(form), credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' }
    }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      // A redirect means the save succeeded. NEVER navigate the host page.
      if (r.redirected || r.url !== new URL(action, location.href).href) {
        return r.text().then(function (html) {
          var doc = new DOMParser().parseFromString(html, 'text/html');
          var fl = doc.querySelector('.flashes');
          var nested = dlg.contains(form);
          close();                                    // close only this popup
          if (nested && openerHref) {                  // popup opened from another popup
            generation++;
            dlg.showModal();
            document.documentElement.classList.add('fm-open');
            fetch(openerHref, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
              .then(function (rr) { return rr.text(); })
              .then(function (h) { render(h, openerHref, generation); });
          } else {
            refreshPage(fl ? fl.innerHTML : '', myGen);
          }
          return null;
        });
      }
      return r.text();                                // validation errors -> redraw in popup
    }).then(function (html) {
      if (html !== null) { retry(); render(html, action, myGen); }
    }).catch(function () {
      retry();
      if (myGen !== generation) return;
      var warn = document.createElement('div');
      warn.className = 'flash error';
      warn.textContent = 'Could not save. Check your connection and try again.';
      body.insertBefore(warn, body.firstChild);
    });
  }

  function open(trigger) {
    var href = trigger.getAttribute('href');
    if (!href) return;
    savedScroll = window.scrollY || window.pageYOffset || 0;
    opener = trigger;
    openerHref = trigger.getAttribute('href');
    var myGen = ++generation;
    titleEl.textContent = trigger.dataset.modalTitle || 'Loading...';
    if (!dlg.open) dlg.showModal();
    document.documentElement.classList.add('fm-open');
    body.innerHTML = '<div class="fm-loading"><span class="fm-spin" aria-hidden="true"></span>Loading&hellip;</div>';
    fetch(href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.text(); })
      .then(function (html) { render(html, href, myGen); })
      .catch(function () { close(); });               // never redirect on failure
  }

  // Only clicks inside THIS dialog close it — no cross-popup interference.
  dlg.addEventListener('click', function (e) {
    if (e.target === dlg || (e.target.closest && e.target.closest('[data-fm-close]'))) {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  });

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest && e.target.closest('[data-modal-form]');
    if (!trigger) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // keep open-in-new-tab
    e.preventDefault();
    e.stopPropagation();
    open(trigger);
  });

  // Shared hook for other modules (e.g. inventory delete) to refresh in place.
  window.pawRefreshPage = function (flashes) { return refreshPage(flashes, generation); };
  window.pawPopupClose = close;
})();
