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
// The open door's proof (transport/identity.py `arrive`): a nonce for which SHA-256 of `challenge:name:nonce` begins with
// `bits` zero bits, found here before the form is sent, so asking for a key costs a moment's work and a flood costs a lot.
(function () {
  var form = document.getElementById('arrive');
  if (!form || !window.crypto || !crypto.subtle || !window.TextEncoder) return;
  function zeros(d) {
    for (var i = 0, z = 0; i < d.length; i++, z += 8) if (d[i]) return z + Math.clz32(d[i]) - 24;
    return d.length * 8;
  }
  form.addEventListener('submit', async function (ev) {
    if (form.dataset.done) return;
    ev.preventDefault();
    var challenge = form.dataset.challenge, bits = Number(form.dataset.bits), name = form.elements.name.value.trim();
    var encoder = new TextEncoder(), button = form.querySelector('button');
    button.disabled = true;
    form.querySelector('.working').hidden = false;
    for (var n = 0; ; n++) {
      var digest = new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(challenge + ':' + name + ':' + n)));
      if (zeros(digest) >= bits) break;
    }
    form.elements.nonce.value = String(n);
    form.elements.name.value = name;
    form.dataset.done = '1';
    form.submit();
  });
})();
// A thing's view (docs/VIEWS.md) is live: it listens on /live/<id> and is drawn again whenever the thing moves; a button,
// a box or a tile is one click: sent here, and what came back (the reply with its receipt, and the view) is put in
// place. Without this script a button is a form, a tile a link that fills the box with its spell, and a reload is fresh.
(function () {
  var view = document.getElementById('view');
  if (!view || !window.fetch || !window.DOMParser || !window.FormData) return;
  var body = view.querySelector('.v-body');
  if (view.dataset.live && window.EventSource) {
    new EventSource(view.dataset.live).addEventListener('view', function (ev) { body.innerHTML = ev.data; });
  }
  function put(page) {
    var doc = new DOMParser().parseFromString(page, 'text/html');
    var fresh = doc.querySelector('#view .v-body'), reply = doc.querySelector('section.reply'), here = document.querySelector('section.reply');
    if (fresh) body.innerHTML = fresh.innerHTML;
    if (reply) {
      reply = document.importNode(reply, true);
      if (here) here.replaceWith(reply); else view.parentNode.insertBefore(reply, view);
    }
  }
  function send(action, data) {
    view.classList.add('v-sending');
    fetch(action, { method: 'POST', body: new URLSearchParams(data), credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(function (r) { if (/\/enter$/.test(r.url)) { location.href = r.url; return ''; } return r.text(); })
      .then(function (t) { if (t) put(t); })
      .finally(function () { view.classList.remove('v-sending'); });
  }
  view.addEventListener('submit', function (ev) {
    var form = ev.target.closest && ev.target.closest('form.v-act');
    if (!form) return;
    ev.preventDefault();
    var data = new FormData(form);
    if (ev.submitter && ev.submitter.name) data.append(ev.submitter.name, ev.submitter.value);
    send(form.action, data);
  });
  view.addEventListener('click', function (ev) {
    var tile = ev.target.closest && ev.target.closest('a[data-do]'), form = view.querySelector('form.v-do');
    if (!tile || !form) return;
    ev.preventDefault();
    var data = new FormData(form);
    data.set('do', tile.getAttribute('data-do'));
    send(form.action, data);
  });
})();
