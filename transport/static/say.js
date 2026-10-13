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
// A ring button sounds what a bell or a place rings (docs/HARMONIC.md): each hertz it names, a sine struck and left
// to fade with a faint octave above it, as a singing bowl. Without this script the button stays hidden and the page
// says the hertz in words.
let air;
document.querySelectorAll('button.ring[hidden]').forEach((b) => { b.hidden = false; });
document.addEventListener('click', (event) => {
  const b = event.target.closest && event.target.closest('button.ring');
  const Air = window.AudioContext || window.webkitAudioContext;
  if (!b || !Air) return;
  air = air || new Air();
  const now = air.currentTime, tones = b.dataset.hz.split(' ').map(Number).filter((f) => f > 0);
  for (const f of tones) {
    for (const [over, loud] of [[1, 0.5], [2, 0.08]]) {
      const o = air.createOscillator(), g = air.createGain();
      o.frequency.value = f * over;
      g.gain.setValueAtTime(0.0001, now);
      g.gain.exponentialRampToValueAtTime(loud / tones.length, now + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 4);
      o.connect(g).connect(air.destination);
      o.start(now);
      o.stop(now + 4.1);
    }
  }
});
