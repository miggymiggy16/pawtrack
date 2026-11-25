(function () {
  var btn = document.getElementById('vmFilterBtn'), panel = document.getElementById('vmFilters');
  if (btn && panel) btn.addEventListener('click', function () {
    var open = panel.classList.toggle('open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  // Record detail popup: click an animal to view, X/outside/Escape to close.
  var modal = document.getElementById('vaxModal');
  if (!modal) return;
  var title = document.getElementById('vaxModalTitle');
  var facts = document.getElementById('vaxModalFacts');

  function open(d) {
    title.textContent = d.animal + ' · ' + d.id;
    var rows = [
      ['Species', d.species], ['Vaccine', d.vaccine], ['Administered', d.given],
      ['Next due', d.due], ['Status', d.status]
    ];
    facts.innerHTML = rows.map(function (r) {
      return '<div><dt>' + r[0] + '</dt><dd>' + (r[1] || '-') + '</dd></div>';
    }).join('');
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }
  function close() {
    modal.hidden = true;
    document.body.style.overflow = '';
  }

  document.querySelectorAll('.vax-open').forEach(function (el) {
    function show() {
      try { open(JSON.parse(el.getAttribute('data-detail'))); }
      catch (e) { /* ignore malformed data */ }
    }
    el.addEventListener('click', function (e) {
      if (e.target.closest('a, button, form')) return;
      show();
    });
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(); }
    });
  });
  modal.querySelectorAll('[data-vax-close]').forEach(function (el) {
    el.addEventListener('click', close);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !modal.hidden) close();
  });
})();
