/* PawTrack: open forms (register animal, add vaccination) in a centered popup
   instead of a full page. Any link marked data-modal-form loads its page into
   the dialog and submits it in place; validation errors come back in the popup. */
(function () {
  'use strict';

  var dlg = document.getElementById('formModal');
  if (!dlg) return;
  var body = dlg.querySelector('[data-fm-body]');
  var titleEl = dlg.querySelector('[data-fm-title]');
  var opener = null;
  var scriptNodes = [];

  function clearScripts() {
    scriptNodes.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    scriptNodes = [];
  }

  function close() {
    if (dlg.open) dlg.close();
    finish();                        // finish() is idempotent; do not rely on the 'close' event alone
  }

  function finish() {
    clearScripts();
    body.innerHTML = '';
    dlg.className = 'fm-dialog';
    document.documentElement.classList.remove('fm-open');
    var back = opener;
    opener = null;
    if (back && back.focus) { try { back.focus(); } catch (e) { /* ignore */ } }
  }

  dlg.addEventListener('close', finish);
  dlg.addEventListener('cancel', function (e) { e.preventDefault(); close(); });   // Escape key

  // Run the form page's own scripts (inline + form-specific files) inside the popup,
  // skipping the shared ones the page already loaded.
  function runScripts(doc) {
    var loaded = {};
    Array.prototype.forEach.call(document.scripts, function (s) {
      var src = s.getAttribute('src');
      if (src) loaded[src] = true;
    });
    Array.prototype.forEach.call(doc.body.querySelectorAll('script'), function (s) {
      var src = s.getAttribute('src');
      if (src && loaded[src]) return;
      var node = document.createElement('script');
      if (src) { node.src = src; loaded[src] = true; }
      else node.textContent = s.textContent;
      document.head.appendChild(node);
      scriptNodes.push(node);
    });
  }

  function bind(pageUrl) {
    var form = body.querySelector('form');
    if (!form) return;
    if (!form.getAttribute('action')) form.setAttribute('action', pageUrl);
    if (!form.querySelector('input[name="next"]')) {       // return to the page the popup was opened from
      var next = document.createElement('input');
      next.type = 'hidden';
      next.name = 'next';
      next.value = window.location.pathname + window.location.search;
      form.appendChild(next);
    }
    form.addEventListener('submit', submit);
  }

  function render(html, pageUrl) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var content = doc.querySelector('main.content');
    if (!content) { window.location = pageUrl; return; }   // safety: fall back to a normal page
    var head = content.querySelector('.page-head');
    var h1 = head && head.querySelector('h1');
    if (h1) titleEl.textContent = h1.textContent.trim();
    if (head) head.remove();
    dlg.className = ('fm-dialog ' + doc.body.className.trim()).trim();   // keep page-scoped form styles (af-page)
    clearScripts();
    body.innerHTML = content.innerHTML;
    runScripts(doc);
    bind(pageUrl);
    body.scrollTop = 0;
  }

  function submit(e) {
    e.preventDefault();
    var form = e.currentTarget;
    if (form.dataset.fmBusy) return;
    form.dataset.fmBusy = '1';
    var btn = form.querySelector('[type="submit"]');
    var label = btn && btn.innerHTML;
    if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
    var action = form.getAttribute('action');

    function retry() {
      form.dataset.fmBusy = '';
      if (btn) { btn.disabled = false; btn.innerHTML = label; }
    }

    fetch(action, {
      method: 'POST', body: new FormData(form), credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' }
    }).then(function (r) {
      if (r.redirected || r.url !== new URL(action, window.location.href).href) {
        window.location = r.url || action;      // saved: go to the page that shows the result
        return null;
      }
      return r.text();                          // validation errors: redraw them in the popup
    }).then(function (html) {
      if (html !== null) render(html, action);
    }).catch(function () {
      retry();
      var warn = document.createElement('div');
      warn.className = 'flash error';
      warn.textContent = 'Could not save. Check your connection and try again.';
      body.insertBefore(warn, body.firstChild);
    });
  }

  function open(trigger) {
    var href = trigger.getAttribute('href');
    if (!href) return;
    opener = trigger;
    titleEl.textContent = trigger.dataset.modalTitle || 'Loading...';
    if (!dlg.open) dlg.showModal();
    document.documentElement.classList.add('fm-open');
    body.innerHTML = '<div class="fm-loading"><span class="fm-spin" aria-hidden="true"></span>Loading&hellip;</div>';
    fetch(href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.text(); })
      .then(function (html) { render(html, href); })
      .catch(function () { window.location = href; });
  }

  // Backdrop click and every close button / cancel link (also the injected ones)
  dlg.addEventListener('click', function (e) {
    if (e.target === dlg || e.target.closest('[data-fm-close]')) {
      e.preventDefault();
      close();
    }
  });

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-modal-form]');
    if (!trigger) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;   // keep open-in-new-tab working
    e.preventDefault();
    open(trigger);
  });
})();
