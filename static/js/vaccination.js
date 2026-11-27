(function () {
  var btn = document.getElementById('vmFilterBtn'), panel = document.getElementById('vmFilters');
  if (!btn || !panel) return;

  function set(open) {
    panel.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  btn.addEventListener('click', function () { set(!panel.classList.contains('open')); });

  document.addEventListener('click', function (e) {
    if (!panel.classList.contains('open')) return;
    if (panel.contains(e.target) || btn.contains(e.target)) return;
    set(false);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !panel.classList.contains('open')) return;
    set(false);
    btn.focus();
  });
})();
