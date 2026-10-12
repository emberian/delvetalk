'use strict';
// A suggestion under the reply box fills the box with its spell to edit; it sends nothing. Without this script the
// suggestion is a link that reloads the page with the box filled (?say=), so the page works the same with it off.
document.addEventListener('click', (event) => {
  const a = event.target.closest && event.target.closest('a.say');
  const box = document.getElementById('say');
  if (!a || !box) return;
  event.preventDefault();
  box.value = new URL(a.href).searchParams.get('say') || '';
  box.focus();
});
