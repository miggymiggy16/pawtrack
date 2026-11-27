(function () {
  var btn = document.getElementById('vmFilterBtn'), panel = document.getElementById('vmFilters');
  if (btn && panel) btn.addEventListener('click', function () {
    var open = panel.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
})();
