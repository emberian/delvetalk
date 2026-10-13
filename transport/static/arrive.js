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
