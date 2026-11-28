/* PawTrack - draw the detailed report chart inside its card or inside the
   centered form modal. Chart.js needs real element dimensions, so drawing is
   deferred until after layout (two animation frames). */
(function () {
  'use strict';
  var C = window.PAW_REPORT;
  if (!C || typeof pawCharts !== 'function') return;

  function draw() {
    if (!pawCharts()) return;                       // Chart.js unavailable
    var el = document.getElementById('reportChart');
    if (!el) return;
    if (window.Chart && typeof Chart.getChart === 'function' && Chart.getChart(el)) return; // already drawn
    pawChart('reportChart', C.type, C.labels, C.values, C.opts);
  }

  // Wait for the dialog/content to be laid out before measuring the canvas.
  requestAnimationFrame(function () { requestAnimationFrame(draw); });
})();
