(function () {
  var form = document.getElementById('ivFilters');
  if (form) {
    form.querySelectorAll('select').forEach(function (sel) {
      sel.addEventListener('change', function () { form.submit(); });
    });
  }
})();
