'use strict';
// The town unfolded and its inspector (transport/atlas.py, docs/WEB.md "The town unfolded"). Every page here works
// without this script: a room's panel opens as a <details>, a spell is a form that posts to its card's page, the
// workshop's spell posts to the workshop. With it: a room unfolds with its scene, view and spells fetched from its own
// pages; a spell or the workshop's answer comes back in place, a problem's line a link into the box; the drawing,
// the rooms and an inspector's fields and receipts are drawn again whenever the town's journal moves (/live).
(function () {
  if (!window.fetch || !window.DOMParser || !window.FormData) return;
  function page(url, init) {
    return fetch(url, Object.assign({ credentials: 'same-origin', headers: { Accept: 'text/html' } }, init || {}))
      .then(function (r) {
        if (/\/enter$/.test(r.url)) { location.href = r.url; return null; }
        return r.text().then(function (t) { return new DOMParser().parseFromString(t, 'text/html'); });
      });
  }
  function adopt(node) { return node ? document.importNode(node, true) : null; }

  // ---- a room unfolds in place
  function unfold(room) {
    var lazy = room.querySelector('.lazy');
    if (!lazy || lazy.dataset.done) return;
    lazy.dataset.done = '1';
    lazy.classList.add('loading');
    Promise.all([page(lazy.dataset.read), page(lazy.dataset.inspect)]).then(function (got) {
      var read = got[0], seen = got[1];
      lazy.textContent = '';
      if (read) {
        var view = read.querySelector('#view');
        if (view) { view = adopt(view); view.removeAttribute('id'); lazy.appendChild(view); }
        var scene = adopt(read.querySelector('section.scene'));
        if (scene) lazy.appendChild(scene);
        var wants = read.querySelectorAll('main p.wants');
        for (var i = 0; i < wants.length; i++) lazy.appendChild(adopt(wants[i]));
      }
      if (seen) { var verbs = adopt(seen.querySelector('section.verbs')); if (verbs) lazy.appendChild(verbs); }
    }).finally(function () { lazy.classList.remove('loading'); });
  }
  document.addEventListener('toggle', function (ev) {
    var room = ev.target;
    if (room.matches && room.matches('details.room') && room.open) unfold(room);
  }, true);
  function go(hash) {
    var room = hash && document.getElementById(hash.slice(1));
    if (!room || !room.matches('details.room')) return false;
    room.open = true;
    unfold(room);
    room.scrollIntoView({ block: 'start', behavior: 'smooth' });
    document.querySelectorAll('.town-graph a.node.chosen').forEach(function (n) { n.classList.remove('chosen'); });
    var node = document.querySelector('.town-graph a.node[data-id="' + CSS.escape(room.dataset.obj) + '"]');
    if (node) node.classList.add('chosen');
    return true;
  }
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href^="#p-"]');
    if (a && go(a.getAttribute('href'))) { ev.preventDefault(); history.replaceState(null, '', a.getAttribute('href')); }
  });
  if (location.hash) go(location.hash);
  document.querySelectorAll('details.room[open]').forEach(unfold);

  // ---- a spell cast, or the workshop's spell sent, answered in place
  function lines(box, from) {  // the box's line where the block's line `n` stands
    var text = box.value.split('\n'), start = text.findIndex(function (l) { return /^source: <<BEND\s*$/.test(l); });
    return start < 0 ? from : start + from;
  }
  function select(box, line) {
    var text = box.value.split('\n'), at = 0;
    for (var i = 0; i < line && i < text.length; i++) at += text[i].length + 1;
    box.focus();
    box.setSelectionRange(at, at + (text[line] || '').length);
    var high = parseFloat(getComputedStyle(box).lineHeight) || 20;
    box.scrollTop = Math.max(0, (line - 3) * high);
  }
  function diagnosed(reply, box) {  // each `- Module:12: stage: …` line of the workshop's answer, a link to its line in the box
    var pre = reply.querySelectorAll('pre.card'), found = [];
    pre.forEach(function (p) {
      p.textContent.split('\n').forEach(function (l) {
        var m = /^\s*-\s+([A-Za-z0-9_]+):(\d+):\s*(.*)$/.exec(l);
        if (m) found.push({ module: m[1], line: Number(m[2]), says: m[3] });
      });
    });
    if (!found.length) return;
    var list = document.createElement('ol');
    list.className = 'diagnostics';
    found.forEach(function (d) {
      var li = document.createElement('li'), a = document.createElement('a');
      a.href = '#';
      a.textContent = d.module + ':' + d.line;
      a.addEventListener('click', function (ev) { ev.preventDefault(); select(box, lines(box, d.line)); });
      li.appendChild(a);
      li.appendChild(document.createTextNode(' ' + d.says));
      list.appendChild(li);
    });
    reply.insertBefore(list, reply.firstChild);
    select(box, lines(box, found[0].line));
  }
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form.matches || !form.matches('form.cast, form.ws')) return;
    ev.preventDefault();
    var data = new FormData(form);
    if (ev.submitter && ev.submitter.name) data.append(ev.submitter.name, ev.submitter.value);
    var out = form.matches('form.ws') ? form.parentNode.querySelector('.ws-reply') : form.parentNode.querySelector('.cast-reply');
    if (!out) { out = document.createElement('div'); out.className = 'cast-reply'; form.parentNode.appendChild(out); }
    out.textContent = form.matches('form.ws') ? 'The workshop is reading it…' : '…';
    form.classList.add('sending');
    page(form.action, { method: 'POST', body: new URLSearchParams(data) }).then(function (doc) {
      if (!doc) return;
      var reply = doc.querySelector('section.reply') || doc.querySelector('section.refusal');
      out.textContent = '';
      if (reply) {
        reply = adopt(reply);
        reply.querySelectorAll('details.card').forEach(function (d) { if (form.matches('form.ws')) d.open = true; });
        out.appendChild(reply);
        if (form.matches('form.ws')) diagnosed(reply, form.querySelector('textarea'));
      } else out.textContent = 'No answer came back; the page has the receipt.';
    }).finally(function () { form.classList.remove('sending'); });
  });

  // ---- the workshop's three spells: check it, fork its kind with it, or lay a layer of your own over this thing
  var shop = document.getElementById('workshop');
  if (shop) {
    var box = shop.querySelector('textarea'), modes = shop.querySelector('.ws-modes'), kept = box && box.value;
    var obj = shop.dataset.obj, over = shop.dataset.over, kind = shop.dataset.kind;
    var mine = 'my-' + (obj.split('/').filter(function (p) { return !/^\d+$/.test(p); }).pop() || 'thing').replace(/[^a-z0-9-]/g, '');
    var starter = 'form wave:\ndef wave(state: State, context: Abi.Context) -> Activity<Nat>:\n  Super.inscribe(state, "wave", "waved by {context.handle}", context)';
    if (modes && box) {
      modes.hidden = false;
      if (!kind) { var f = modes.querySelector('[data-mode=fork]'); if (f) f.hidden = true; }
      var block = function () { var m = /\nsource: <<BEND\n([\s\S]*)\nBEND\s*$/.exec(box.value); return m ? m[1] : ''; };
      var lastBlock = null;
      modes.addEventListener('click', function (ev) {
        var b = ev.target.closest('[data-mode]');
        if (!b) return;
        var mode = b.dataset.mode, body = block();
        if (mode !== 'layer' && lastBlock !== null) { body = lastBlock; lastBlock = null; }
        if (mode === 'layer') { if (lastBlock === null) lastBlock = body; body = starter; }
        var head = mode === 'check' ? 'delvetalk workshop check' + (over ? '\nover: ' + over : '')
          : mode === 'fork' ? 'delvetalk workshop draft\nname: ' + mine + '\nfrom: ' + kind
          : 'delvetalk workshop draft\nname: ' + mine + '-' + 'layer\nover: ' + obj;
        box.value = head + '\nsource: <<BEND\n' + (body || kept) + '\nBEND';
        modes.querySelectorAll('[data-mode]').forEach(function (x) { x.classList.toggle('on', x === b); });
        if (mode !== 'check') { var at = box.value.indexOf('name: ') + 6; box.focus(); box.setSelectionRange(at, box.value.indexOf('\n', at)); }
      });
      var first = modes.querySelector('[data-mode=check]');
      if (first) first.classList.add('on');
    }
  }

  // ---- live: the page drawn again whenever the town's journal moves
  var live = document.querySelector('[data-live="/live"]');
  if (live && window.EventSource) {
    var busy = false, again = false;
    var redraw = function () {
      if (busy) { again = true; return; }
      busy = true;
      page(location.pathname + location.search).then(function (doc) {
        if (!doc) return;
        var graph = doc.querySelector('svg.town-graph'), mine = document.querySelector('svg.town-graph');
        if (graph && mine) {
          var chosen = mine.querySelector('a.node.chosen');
          mine.replaceWith(adopt(graph));
          if (chosen) { var n = document.querySelector('.town-graph a.node[data-id="' + CSS.escape(chosen.dataset.id) + '"]'); if (n) n.classList.add('chosen'); }
        }
        var lede = doc.querySelector('.atlas-head .lede'), here = document.querySelector('.atlas-head .lede');
        if (lede && here) here.textContent = lede.textContent;
        doc.querySelectorAll('details.room').forEach(function (fresh) {
          var room = document.getElementById(fresh.id);
          if (!room) { var rooms = document.querySelector('section.rooms'); if (rooms) rooms.appendChild(adopt(fresh)); return; }
          if (room.dataset.version === fresh.dataset.version) return;
          room.dataset.version = fresh.dataset.version;
          room.classList.toggle('lit', fresh.classList.contains('lit'));
          ['.now', 'summary .rsum'].forEach(function (sel) { var a = room.querySelector(sel), b = fresh.querySelector(sel); if (a && b) a.innerHTML = b.innerHTML; });
          room.classList.add('moved');
          setTimeout(function () { room.classList.remove('moved'); }, 1600);
          var lazy = room.querySelector('.lazy');
          if (lazy && lazy.dataset.done && !room.open) { delete lazy.dataset.done; lazy.textContent = ''; }  // an open room keeps what was answered in it
        });
        ['#fields', '#receipts', '#rules', '.ins-head dl.facts'].forEach(function (sel) {
          var a = document.querySelector(sel), b = doc.querySelector(sel);
          if (a && b && a.innerHTML !== b.innerHTML) { a.innerHTML = b.innerHTML; a.classList.add('moved'); setTimeout(function () { a.classList.remove('moved'); }, 1600); }
        });
      }).finally(function () { busy = false; if (again) { again = false; redraw(); } });
    };
    var height = live.dataset.height || '';
    new EventSource('/live' + (height ? '?h=' + encodeURIComponent(height) : '')).addEventListener('moved', redraw);
  }
})();
