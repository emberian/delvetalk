"""The town unfolded, every thing inspected, the library read (docs/WEB.md "The town at a glance"; transport/atlas.py): /town
draws every door a reader may see and every room as a panel, /inspect/<id> sets a thing's Bend in type beside its spells,
its law's verdicts, its rules and fields, and hands the workshop its check spell; /library, /lib and /kinds read the
library's pages, the town's modules and its kinds; /live tells a page the journal moved.

Evidence for docs/WEB.md (layer: transport).

Refuted by: a room that only its own doors join to the town missing from the drawing or the rooms; a room no door
reaches unlisted; a line of the town's own (its opener, the weather, an inhabitant, a deploy's check) shown as a
resident's, or a resident's hidden; /town past 40 KB on its fixture; a door drawn that the host's `ways` does not hold; a resident's word reaching the markup unescaped; a
declaration of a thing's Bend with no anchor; a spell offered with no form, or a form that casts anything but the
reader's own turn of that spell; a verdict in "who may do what" that is not the host's `admits`; the workshop's spell on
the page not checking the Bend shown, or a broken line not named by its number; a library page, module or kind the host
holds missing from its page; a page not told within two seconds that the journal moved."""
import html
import re
import threading
import time
import urllib.parse

from tests.test_http import FORM, HANDLE, PEOPLE, InTown
from transport.host import PUBLIC, plain

ATTACK = '"\'><script>alert(1)</script><img src=x onerror=alert(1)>'


class Atlas(InTown):
    OPENER = 'did:plc:' + 'z' * 24  # the town; the browser (talkie) is a resident
    strip = {}

    def say(self, card, text):
        s, _, page = self.play('/play/' + card, text)
        self.assertEqual(s, 200, page[:400])
        return html.unescape(page.decode())

    def rooms(self):
        return sorted(self.host.send({'op': 'world-objects', 'principal': PUBLIC, 'prefix': 'room/'})['ids'])

    def setUp(self):
        super().setUp()
        if not Atlas.strip:  # a strip joined to the town only by its own door, and a room no door reaches
            before = self.rooms()
            self.say('kind/room', 'delvetalk kind/room make / name: the crossroads / spween: Two roads cross under one light.')
            self.say('kind/room', 'delvetalk kind/room make / name: ' + ATTACK[:60] + ' / spween: A jar on a shelf.')
            strip, lone = [r for r in self.rooms() if r not in before]
            self.say(strip, f'delvetalk {strip} door / label: to the moss gate / to: rooms')
            self.say(strip, f'delvetalk {strip} enter')
            self.say(strip, f'delvetalk {strip} say / line: {ATTACK}')
            Atlas.strip = {'strip': strip, 'lone': lone}

    def page(self, path):
        s, headers, page = self.play(path)
        self.assertEqual(s, 200, page[:400])
        return page.decode()

    def test_the_town_draws_every_door_and_every_room_its_own_doors_join(self):
        strip, lone = self.strip['strip'], self.strip['lone']
        page = self.page('/town')
        ways = self.host.send({'op': 'world-surface', 'principal': PEOPLE[HANDLE], 'read': 'map', 'fields': {}})['ways']
        pairs = {frozenset((w['from'], w['to'])) for w in ways if w['from'] != w['to']}
        self.assertEqual(page.count('<path class="door'), len(pairs))  # one curve a door, or a pair of doors back and forth
        self.assertIn(f'data-id="{strip}"', page)  # reached only by its own door to the moss gate
        self.assertIn(f'<details class="room lit" id="p-{strip.replace("/", "-")}" data-obj="{strip}"', page)  # someone is in it
        panel = re.search(rf'id="p-{strip.replace("/", "-")}".*?</details>', page, re.S)[0]
        self.assertIn('the crossroads', panel)
        self.assertIn('>to the moss gate</a>', panel)
        self.assertIn('talkie.delve.town is here.</p>', panel)
        self.assertNotIn('<script>', page)
        self.assertIn(html.escape(ATTACK), panel)  # a resident's line, escaped, the panel's summary
        self.assertNotIn(f'data-id="{lone}"', page)  # not drawn: no door touches it
        quiet = page[page.index('<p class="quiet-places">'):]
        self.assertIn(f'href="/o/{lone}"', quiet)  # nothing happens there: one name among the quiet places
        self.assertRegex(self.page(f'/town?open={lone}'), rf'<details class="room" id="p-{lone.replace("/", "-")}" data-obj="{lone}" data-version="\d+" open>')  # unfolded with no script
        self.assertIn(f'<b>talkie.delve.town</b> in <a href="#p-{strip.replace("/", "-")}">the crossroads</a>', page)  # who is around, first
        for gone in ('The way here', 'the door map, as the commonplace writes it', 'inspect its Bend', 'Read it'):
            self.assertNotIn(gone, page)
        self.assertLess(len(page.encode()), 40_000)
        text = self.page('/town?text=1')
        self.assertIn('the crossroads', text)
        self.assertIn('Doors: to the moss gate', text)

    def test_the_towns_own_lines_are_counted_and_a_residents_shown(self):
        from deploy import genesis
        strip = self.strip['strip']
        genesis.said(self.root, self.OPENER, strip, 'write', [('text', 'the town kept its hours')], 'atlas-books')
        panel = re.search(rf'id="p-{strip.replace("/", "-")}".*?</details>', self.page('/town'), re.S)[0]
        self.assertNotIn('the town kept its hours', panel)
        self.assertRegex(panel, r"and \d+ lines? of the town's own")
        self.assertIn(html.escape(ATTACK), panel)

    def test_a_residents_line_is_a_residents_and_a_deploys_check_is_not(self):
        from transport import atlas
        town, probes = 'did:web:t.example', ('deploycheck',)
        cases = {'guest:t.example:yue': True, 'did:plc:' + 'q' * 24: True, town: False, '@station/bee': False, 'weather': False,
                 'guest:t.example:deploycheck20': False, '': False}
        self.assertEqual({p: atlas.resident_of(p, town, probes) for p in cases}, cases)

    def test_the_inspector_sets_its_bend_in_type_and_casts_its_spells_as_the_reader(self):
        strip = self.strip['strip']
        page = self.page('/inspect/' + strip)
        seen = self.host.send({'op': 'world-inspect', 'principal': PEOPLE[HANDLE], 'object': strip, 'source': True})
        named = {m['name'] for m in seen['methods'] if m.get('context')}
        source = seen['madeFrom']['components'][0]['body'] if seen.get('madeFrom') else seen['source']
        for name in re.findall(r'(?m)^def ([A-Za-z_]\w*)', source):
            self.assertIn(f'id="src-def-{name}"', page, name)
        for action in seen['offered']:
            form = re.search(rf'<li class="verb" id="verb-{action}"><form class="cast" method="post" action="/play/{re.escape(strip)}".*?</form>', page, re.S)
            self.assertTrue(form, action)
            self.assertIn(f'<input type="hidden" name="do" value="{action}">', form[0])
            self.assertEqual(action in named, f'href="/inspect/{strip}#src-def-{action}"' in page, action)  # a grown verb has no line
        self.assertIn('<a class="mod" href="/lib/Record">./Record.obend</a>', page)
        self.assertNotIn('<script>', page)
        self.now[0] += 3
        s, _, back = self.request('POST', '/play/' + strip, raw=urllib.parse.urlencode({'do': 'say', 'f.line': 'from the inspector'}),
                                  headers={'Cookie': self.cookie, 'Content-Type': FORM})
        self.assertEqual(s, 200, back[:300])
        newest = self.host.send({'op': 'world-history', 'principal': self.OPENER, 'object': strip, 'reverse': True, 'limit': 1})['entries'][0]
        self.assertEqual((newest['identity']['principal'], newest['outcome']['tag']), (PEOPLE[HANDLE], 'admitted'))
        stranger = self.request('GET', '/inspect/' + strip)[2].decode()
        self.assertNotIn('class="cast-go"', stranger)  # a stranger reads the spells and is told the way in
        self.assertIn('<code class="vspell">delvetalk', stranger)

    def test_who_may_do_what_is_the_laws_own_verdict(self):
        for obj in ('anthology', self.strip['strip'], 'commonplace'):
            page = self.page('/inspect/' + obj)
            mine = {m['name']: m.get('admits') for m in self.host.send({'op': 'world-inspect', 'principal': PEOPLE[HANDLE], 'object': obj})['methods']}
            anyone = {m['name']: m.get('admits') for m in self.host.send({'op': 'world-inspect', 'principal': PUBLIC, 'object': obj})['methods']}
            rows = re.findall(r'<tr><td><a href="#src-def-(\w+)"><code>\w+</code></a></td>(.*?)</tr>', page)
            self.assertTrue(rows, obj)
            for name, cells in rows:
                got = re.findall(r'<td class="(yes|no|unknown)">(?:§ <code>([^<]*)</code>)?', cells)
                want = [('yes', '') if a is True else ('no', a['clause']) for a in (mine[name], anyone[name])]
                self.assertEqual(got, want, (obj, name))

    def test_the_workshops_spell_checks_the_bend_shown_and_names_a_broken_line(self):
        page = self.page('/inspect/' + self.strip['strip'])
        spell = html.unescape(re.search(r'<textarea class="ws-text" name="text"[^>]*>(.*?)</textarea>', page, re.S)[1])
        self.assertTrue(spell.startswith('delvetalk workshop check\nover: kind/record\nsource: <<BEND\n'), spell[:120])
        self.assertIn('Checked: it compiles.', self.say('workshop', spell))
        lines = spell.split('\n')
        at = next(i for i, l in enumerate(lines) if l.startswith('def '))
        lines[at] = lines[at].replace('(', '(oops ', 1)
        broken = self.say('workshop', '\n'.join(lines))
        self.assertIn(f'Layer1:{at - 2}:', broken)  # its line in the block: the spell's three lines come before it

    def test_the_inspector_sets_its_bend_in_type_once_and_the_rest_on_asking(self):
        """obend 10-14: /inspect/room/14 was 429 KB, its 659 lines set in type as the entry module and again as its kind's
        layer (one line apart), and once more in the workshop's box for a stranger who could not send it. The entry is set in
        type once; a layer a few lines off it is those lines; any part is drawn on asking; a panel's fetch draws none."""
        strip = self.strip['strip']
        page = self.page('/inspect/' + strip)
        self.assertEqual(len(re.findall(r'<pre class="bend" id="', page)), 1, re.findall(r'<pre class="bend" id="([^"]+)"', page))
        self.assertIn('<pre class="bend" id="src">', page)
        self.assertNotIn('<details class="more" open>', page)  # its receipts folded, as its fields
        seen = self.host.send({'op': 'world-inspect', 'principal': PEOPLE[HANDLE], 'object': strip, 'source': True})
        layers = [c['at'] for c in (seen.get('madeFrom') or {}).get('components') or [] if c['body'].strip() != seen['source'].strip()]
        for at in layers:
            self.assertIn(f'href="?bend=layer{at}#src{at}"', page)
            asked = self.page(f'/inspect/{strip}?bend=layer{at}')
            self.assertIn(f'<pre class="bend" id="src{at}">', asked)
            self.assertIn('<pre class="bend" id="src">', asked)  # the entry stays, so every link to its lines holds
        none = self.page(f'/inspect/{strip}?bend=none')
        self.assertNotIn('<pre class="bend" id="', none)
        self.assertIn('section class="verbs"', none)
        self.assertIn(f'data-inspect="/inspect/{strip}?bend=none"', self.page('/town'))  # what a panel fetches
        stranger = self.request('GET', '/inspect/' + strip, headers={'Accept': 'text/html'})[2].decode()
        self.assertNotIn('class="ws-text"', stranger)
        self.assertIn('To send it, <a href="/enter">come in</a>', stranger)
        self.assertLess(len(stranger), len(page))
        # An adversarial ?bend= names no part: the default page, nothing echoed.
        odd = self.page('/inspect/' + strip + '?bend=' + urllib.parse.quote(ATTACK))
        self.assertNotIn('<script>', odd)
        self.assertIn('<pre class="bend" id="src">', odd)

    def test_near_a_layer_is_its_lines_against_the_entry(self):
        from transport import atlas
        entry = '\n'.join(f'def f{i}() -> Nat:\n  {i}n' for i in range(400))
        layer = entry.replace('  7n', '  8n')
        diff, n = atlas.near_diff(entry, layer)
        self.assertEqual(n, 2)
        self.assertIn('-  7n\n+  8n', diff)
        far = '\n'.join(f'def g{i}() -> Nat:\n  {i}n' for i in range(400))
        self.assertIsNone(atlas.near_diff(entry, far))

    def test_a_private_thing_is_said_to_be_private_and_the_way_to_what_holds_it(self):
        """obend 10-14: /inspect/mending/drawer answered 404 "no object". The drawer is there and private."""
        for path in ('/inspect/mending/drawer', '/o/mending/drawer'):
            s, _, page = self.request('GET', path, headers={'Accept': 'text/html'})
            text = html.unescape(page.decode())
            self.assertEqual(s, 403, path)
            self.assertIn('mending/drawer is private: it is there, and its law lets only some read it.', text)
            self.assertIn('href="/o/mending"', text)
        s, _, page = self.request('GET', '/inspect/no-such-thing', headers={'Accept': 'text/html'})
        self.assertEqual(s, 404)
        self.assertNotIn(b'is private', page)

    def test_a_stranger_reading_a_page_asks_for_no_paint(self):
        """A crawl of every /o/ page (obend 10-14 09:05) queues no paint: an anonymous page shows only one already made."""
        self.host.send({'op': 'world-renders'})  # a worker is present, so a signed-in read would queue
        before = {i['key'] for i in self.host.send({'op': 'world-renders'})['pending']}
        for obj in ('commonplace', self.strip['strip'], 'anthology'):
            s, _, _ = self.request('GET', '/o/' + obj, headers={'Accept': 'text/html'})
            self.assertEqual(s, 200, obj)
        self.assertEqual({i['key'] for i in self.host.send({'op': 'world-renders'})['pending']}, before)
        self.page('/o/anthology')  # the control: the same page, signed in, queues its paint
        self.assertGreater({i['key'] for i in self.host.send({'op': 'world-renders'})['pending']} - before, set())

    def test_the_library_the_modules_and_the_kinds_are_pages(self):
        lib = plain(self.host.send({'op': 'world-view', 'principal': PUBLIC, 'object': 'library'})['state'])
        names = [p['name'] for p in lib['pages']['items']]
        page = self.page('/library')
        for n in names:
            self.assertIn(f'<a href="/library/{urllib.parse.quote(n)}">{n}</a>', page)
        first = next(p for p in lib['pages']['items'])
        self.assertIn(html.escape(first['body'].split('\n')[0])[:60], self.page('/library/' + first['name']))
        self.assertEqual(self.play('/library/nowhere')[0], 404)
        modules = self.page('/lib')
        self.assertIn('<a href="/lib/Record">Record</a>', modules)
        record = self.page('/lib/Record')
        self.assertIn('id="src-def-', record)
        self.assertIn('<a class="mod" href="/lib/', record)
        self.assertEqual(self.play('/lib/Nothing')[0], 404)
        kinds = self.page('/kinds')
        for k in self.host.send({'op': 'world-objects', 'principal': PUBLIC, 'prefix': 'kind/'})['ids']:
            self.assertIn(f'<a href="/inspect/{k}">{k}</a>', kinds)

    def test_a_page_is_told_within_two_seconds_that_the_journal_moved(self):
        self.front.live_seconds = 6
        height = self.host.send({'op': 'world-status'})['height']
        import http.client
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        c.request('GET', f'/live?h={height}')
        r = c.getresponse()
        self.assertEqual(r.getheader('Content-Type'), 'text/event-stream; charset=utf-8')
        got = []

        def read():
            while True:
                line = r.fp.readline()
                if not line or line.startswith(b'event: moved'):
                    got.append(time.monotonic())
                    return
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        time.sleep(0.5)
        moved = time.monotonic()
        self.say(self.strip['strip'], f"delvetalk {self.strip['strip']} say / line: a moth")
        reader.join(5)
        c.close()
        self.assertTrue(got, 'no event')
        self.assertLess(got[0] - moved, 2.0)
