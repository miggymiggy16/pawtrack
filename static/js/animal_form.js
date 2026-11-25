/* PawTrack: animal registration field validation (visible, as you type). */
(function () {
  'use strict';

  var RULES = [
    { id: 'breed',         strip: /[^A-Za-z .'\-]/g, hint: 'Breed: letters only (spaces, dot, hyphen, apostrophe allowed).' },
    { id: 'age',           strip: /[^0-9.]/g,          hint: 'Age: numbers only (e.g. 2 or 2.5).' },
    { id: 'owner_name',    strip: /[^A-Za-z .'\-]/g, hint: 'Owner name: letters only.' },
    { id: 'owner_mobile',  strip: /[^0-9 +\-]/g,      hint: 'Owner mobile number: numbers only.' }
  ];

  function noteFor(input) {
    var note = input.parentNode.querySelector('.input-error');
    if (!note) {
      note = document.createElement('small');
      note.className = 'input-error';
      note.setAttribute('role', 'alert');
      note.style.color = '#c0392b';
      note.style.display = 'block';
      note.style.marginTop = '4px';
      input.parentNode.appendChild(note);
    }
    return note;
  }

  function flash(input, message) {
    var note = noteFor(input);
    note.textContent = message;
    if (input._errTimer) clearTimeout(input._errTimer);
    input._errTimer = setTimeout(function () { note.textContent = ''; }, 4000);
  }

  // Block invalid characters at the moment they are typed.
  RULES.forEach(function (rule) {
    var input = document.getElementById(rule.id);
    if (!input) return;

    input.addEventListener('input', function () {
      var before = input.value;
      var after = before.replace(rule.strip, '');

      // Age must contain at most one decimal point.
      if (rule.id === 'age' && after.split('.').length > 2) {
        var parts = after.split('.');
        after = parts.shift() + '.' + parts.join('');
      }

      if (after !== before) {
        var caret = Math.max(0, (input.selectionStart || 0) - (before.length - after.length));
        input.value = after;
        try { input.setSelectionRange(caret, caret); } catch (e) { /* older browsers */ }
        flash(input, rule.hint);
      }
    });
  });

  // Show a visible inline message when a constrained field blocks submit.
  var constrained = document.querySelectorAll(
    'input[pattern], input[required], input[type="email"]'
  );
  Array.prototype.forEach.call(constrained, function (input) {
    input.addEventListener('invalid', function () {
      var msg = input.title;
      if (!msg) {
        if (input.type === 'email') msg = 'Enter a valid email address (e.g. juan@email.com).';
        else if (input.required) msg = 'This field is required.';
        else msg = 'Invalid value.';
      }
      noteFor(input).textContent = msg;
    });
  });
})();
