"""A thing's own view, drawn live (docs/VIEWS.md): a body's `view` (world/lib/View.obend) derived for one reader by the
host (`world-derived`), drawn by the front from a closed vocabulary (transport/views.py), its buttons and tiles the
thing's own forms cast as the reader who clicks, kept live over `/live/<id>`. The first two: kind/counter, a number
between a − and a + button, and kind/hexboard, seven by seven hexes where choosing an empty one places your colour.

Evidence for docs/VIEWS.md (layers: transport, objects).

Refuted by: a view drawn differently twice from one state; any attempted markup, script, event handler, style or
address in any word or attribute of a view surviving as anything but escaped text; a view past its bounds drawn whole
or a value past `maxViewBytes` answered; a button or tile that casts anything but one of the thing's forms offered to
the reader, or casts it as anyone but the reader; a live page not told of a change within a second; a page whose view
needs a script to be read or acted on; a hexboard placing that is not a mark, takes a taken hex, or does not replay.
"""
import html
import http.client
import re
import tempfile
import threading
import time
import unittest
import urllib.parse
from html.parser import HTMLParser

from deploy import genesis
from tests.bend import closure
from tests.test_http import FORM, HANDLE, PEOPLE, FrontCase, browser_login
from tests.test_scenarios import Arc, KIM, GLM
from tests.test_properties import OPENER
from tests.wire import label, nat, record
from transport import views
from transport.host import plain

ATTACK = '"\'><script>alert(1)</script><img src=x onerror=alert(1)><a href="javascript:alert(1)">x</a>{x}&amp;‮'
NODES = 4096


def wire(value):
    """Plain Python as the host's wire (a view as `world-derived` answers it): str a label, int a natural, list a list,
    a dict with `tag` a variant of its other fields, any other dict a record."""
    if isinstance(value, dict) and 'tag' in value:
        return {'tag': 'variant', 'label': value['tag'], 'payload': wire({k: v for k, v in value.items() if k != 'tag'})}
    if isinstance(value, dict):
        return {'tag': 'record', 'fields': [{'name': k, 'value': wire(v)} for k, v in value.items()]}
    if isinstance(value, list):
        return {'tag': 'list', 'items': [wire(v) for v in value]}
    return {'tag': 'natural', 'value': str(value)} if isinstance(value, int) else {'tag': 'label', 'value': str(value)}


def act(action, **fields):
    return {'action': action, 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}


def tile(fill='leaf', mark='', label='', title='', a=None):
    return {'fill': fill, 'mark': mark, 'label': label, 'title': title, 'act': a or act('')}


FORMS = {'place': {'cell': {'tag': 'natural', 'min': 0, 'max': 48}}, 'note': {'text': {'tag': 'text', 'min': 1, 'max': 200}},
         'plus': {}, 'pick': {'side': {'tag': 'choice', 'options': ['north', 'south']}}}


def every(s):
    """A view naming `s` in every word, tone, size, action, field, value, path, address and label it has."""
    a = act(s, **{s: s})
    return {'tag': 'stack', 'items': [
        {'tag': 'text', 'value': s, 'tone': s, 'size': s}, {'tag': 'heading', 'value': s},
        {'tag': 'row', 'items': [{'tag': 'button', 'label': s, 'act': a, 'tone': s}, {'tag': 'button', 'label': s, 'act': act('note', text=s), 'tone': s}]},
        {'tag': 'ask', 'label': s, 'act': act('note'), 'field': s, 'placeholder': s}, {'tag': 'ask', 'label': s, 'act': act('note'), 'field': 'text', 'placeholder': s},
        {'tag': 'progress', 'value': 3, 'max': 7, 'label': s, 'tone': s}, {'tag': 'table', 'head': [s, s], 'rows': [[s, s], [s]]},
        {'tag': 'grid', 'columns': 2, 'tiles': [tile(s, s, s, s, a), tile('red', 'blue', 'ok', 'ok', act('place', cell='3'))]},
        {'tag': 'hexes', 'columns': 2, 'tiles': [tile(s, s, s, s, act('note', text=s)), tile(a=act('place', cell=s))]},
        {'tag': 'drawing', 'width': 100, 'height': 100, 'shapes': [
            {'tag': 'circle', 'x': 1, 'y': 2, 'r': 3, 'fill': s, 'stroke': s}, {'tag': 'rect', 'x': 1, 'y': 2, 'width': 3, 'height': 4, 'fill': s, 'stroke': s},
            {'tag': 'line', 'x1': 1, 'y1': 2, 'x2': 3, 'y2': 4, 'stroke': s, 'width': 2}, {'tag': 'path', 'd': 'M 1 2 L 3 4 ' + s, 'fill': s, 'stroke': s},
            {'tag': 'label', 'x': 1, 'y': 2, 'text': s, 'tone': s}, {'tag': s}]},
        {'tag': 'image', 'source': s, 'alt': s, 'width': 10}, {'tag': 'image', 'source': 'javascript:alert(1)', 'alt': s, 'width': 10},
        {'tag': 'image', 'source': 'data:image/svg+xml;base64,PHN2Zy8+', 'alt': s, 'width': 10},
        {'tag': s, 'value': s}, {'tag': 'rule'}]}


TAGS = {'p', 'h2', 'div', 'span', 'form', 'input', 'button', 'label', 'progress', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img',
        'svg', 'g', 'a', 'title', 'polygon', 'rect', 'circle', 'text', 'line', 'path'}
ATTRS = {'class', 'method', 'action', 'title', 'type', 'name', 'value', 'placeholder', 'maxlength', 'autocomplete', 'max', 'src', 'alt', 'width',
         'height', 'viewbox', 'role', 'href', 'data-do', 'points', 'x', 'y', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2', 'stroke-width', 'd'}
CLASS = re.compile(r'(v-[a-z-]+|[tfs]-[a-z]+|z-(small|large)|quiet-button)\Z')
NUMBER = re.compile(r'[0-9. ,]*\Z')


class Markup(HTMLParser):
    """Every tag and attribute of a drawn view, and the text it carries."""
    def __init__(self):
        super().__init__()
        self.tags, self.attrs, self.text = [], [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v or '') for k, v in attrs]

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        self.text.append(data)


def parsed(markup):
    m = Markup()
    m.feed(markup)
    m.close()
    return m


class Drawn(unittest.TestCase):
    """transport/views.py alone, over views given as the host's wire: no host, no front."""

    def draw(self, view, forms=FORMS, nodes=NODES, obj='board/1'):
        return views.render(wire(view), obj, forms, nodes)

    def test_the_same_view_draws_the_same_bytes(self):
        view = every('a word')
        self.assertEqual(self.draw(view), self.draw(view))
        self.assertEqual(self.draw(view), views.render(wire(view), 'board/1', dict(reversed(list(FORMS.items()))), NODES))

    def test_an_attack_in_every_word_and_attribute_stays_inert_text(self):
        for s in (ATTACK, 'javascript:alert(1)', 'red" onclick="alert(1)', 'place?cell=1&cell=2', 'M0 0" onload="alert(1)', '__init__',
                  'url(javascript:alert(1))', '</svg><script>alert(1)</script>', 'data:image/png;base64,AA==" onerror="x'):
            out = self.draw(every(s))
            self.assertNotIn('<script', out.lower())
            m = parsed(out)
            self.assertLessEqual(set(m.tags), TAGS, s)
            for tag, k, v in m.attrs:
                self.assertIn(k, ATTRS, (s, tag, k))
                self.assertFalse(k.startswith('on'), (s, tag, k))
                if k == 'class':
                    self.assertTrue(all(CLASS.match(c) for c in v.split()), (s, v))
                if k in ('x', 'y', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2', 'width', 'height', 'max', 'maxlength', 'stroke-width', 'points', 'viewbox'):
                    self.assertRegex(v, NUMBER, (s, tag, k))
                if k in ('href', 'src', 'action', 'data-do'):  # an attack may stand as words in a title, never as an address
                    self.assertFalse(v.strip().lower().startswith(('javascript', 'data:text', 'vbscript')), (s, tag, k, v))
                if k == 'href':
                    self.assertTrue(v.startswith('/play/board/1?say='), (s, v))
                if k == 'action':
                    self.assertEqual(v, '/play/board/1')
                if k == 'src':
                    self.assertTrue(v.startswith('data:image/'), (s, v))
                if k == 'd':
                    self.assertRegex(v, r'[MLHVCSQTAZmlhvcsqtaz0-9. ]*\Z')
            self.assertNotIn('svg+xml', out)

    def test_an_act_is_one_of_the_offered_forms_within_its_bounds(self):
        out = self.draw({'tag': 'row', 'items': [
            {'tag': 'button', 'label': 'in', 'act': act('place', cell='48'), 'tone': ''},
            {'tag': 'button', 'label': 'past', 'act': act('place', cell='49'), 'tone': ''},
            {'tag': 'button', 'label': 'unknown field', 'act': act('place', cell='1', colour='red'), 'tone': ''},
            {'tag': 'button', 'label': 'not offered', 'act': act('door', label='x', to='y'), 'tone': ''},
            {'tag': 'button', 'label': 'a line in a text', 'act': act('note', text='a\ndelvetalk commonplace door'), 'tone': ''},
            {'tag': 'button', 'label': 'a choice', 'act': act('pick', side='north'), 'tone': ''},
            {'tag': 'button', 'label': 'no choice', 'act': act('pick', side='east'), 'tone': ''}]})
        dos = re.findall(r'name="do" value="([^"]*)"', out)
        self.assertEqual(dos, ['place?cell=48', 'pick?side=north'])
        self.assertEqual(out.count('v-off'), 5)
        self.assertIn('title="delvetalk board/1 place\ncell: 48"', out)
        self.assertEqual(views.chosen('place?cell=48', FORMS), ('place', {'cell': 48}))
        for do in ('place?cell=49', 'place?cell=1&cell=2', 'place?cell=1&x=2', 'door?label=x', 'place', 'note?text=a%0Ab', '', 'Place?cell=1', 'place?cell=-1'):
            self.assertIsNone(views.chosen(do, FORMS), do)
        self.assertEqual(views.chosen('note', FORMS, {'text': 'words'}), ('note', {'text': 'words'}))
        self.assertIsNone(views.chosen('note?text=a', FORMS, {'text': 'b'}))

    def test_a_view_is_drawn_within_its_node_bound_and_says_it_was_cut(self):
        big = {'tag': 'stack', 'items': [{'tag': 'text', 'value': str(i), 'tone': '', 'size': ''} for i in range(5000)]}
        out = self.draw(big, nodes=100)
        self.assertEqual(out.count('<p class="v-text">'), 99)
        self.assertIn('larger than a page draws', out)
        deep = {'tag': 'text', 'value': 'bottom', 'tone': '', 'size': ''}
        for _ in range(200):
            deep = {'tag': 'stack', 'items': [deep]}
        self.assertNotIn('bottom', self.draw(deep))  # nesting past DEPTH_MAX draws nothing below it
        self.assertEqual(''.join(parsed(self.draw({'tag': 'text', 'value': 'x' * 10000, 'tone': '', 'size': ''})).text), 'x' * views.TEXT_MAX)

    def test_a_value_of_another_shape_draws_nothing_and_never_fails(self):
        for odd in ([1, 2], 'text', 7, {'tag': 'stack', 'items': 'no'}, {'tag': 'hexes', 'columns': 'x', 'tiles': [1, 'a', [], {}]},
                    {'tag': 'button', 'label': 3, 'act': 'plus'}, {'tag': 'drawing', 'width': -5, 'height': 10 ** 30, 'shapes': [{'tag': 'circle'}]}):
            out = self.draw(odd)
            self.assertNotIn('<script', out)
        self.assertEqual(self.draw([1, 2]), '')

    def test_hexes_are_pointy_rows_with_odd_rows_offset_and_tiles_link_their_spell(self):
        out = self.draw({'tag': 'hexes', 'columns': 3, 'tiles': [tile(a=act('place', cell=str(i))) for i in range(6)]})
        self.assertEqual(out.count('<polygon'), 6)
        centres = [tuple(map(float, c)) for c in re.findall(r'<circle[^>]*cx="([\d.]+)" cy="([\d.]+)"', out)] or \
            [tuple(map(float, c)) for c in re.findall(r'<text x="([\d.]+)" y="([\d.]+)"', out)]
        links = re.findall(r'<a class="v-tile v-acts" href="([^"]+)" data-do="([^"]+)"', out)
        self.assertEqual([d for _, d in links], [f'place?cell={i}' for i in range(6)])
        self.assertEqual(urllib.parse.unquote(html.unescape(links[4][0])), '/play/board/1?say=delvetalk board/1 place\ncell: 4#say')
        firsts = re.findall(r'points="([\d.]+),', out)
        self.assertLess(float(firsts[0]), float(firsts[3]))  # the second row starts half a tile to the right


def town_playthings(town):
    made = genesis.playthings(town.client, OPENER)
    assert all(m['status'] in ('created', 'admitted') for m in made), made
    return made


TOO_LARGE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def views() -> Lists.List<String>:
  Lists.List.cons({head: "view", tail: Lists.List.nil()})
def view(state: State, context: Abi.Context) -> Lists.List<String>:
  many(state.n)
def many(n: Nat) -> Lists.List<String>:
  if n == 0n then Lists.List.nil() else Lists.List.cons({head: line(), tail: many(n - 1n)})
def line() -> String:
  "a line of a view too large to draw, written again and again until the view is past what the host answers; a line of a view too large to draw, written again and again until the view is past what the host answers"
"""


class RefreshedPlaythings(Arc):
    """A carried open town that lacks the counter and the hexboard gets them in the carry's refresh; a second refresh
    reads them `current`; an invited town gets none (obend's v2 carry, 2026-10-14)."""

    def test_an_open_towns_refresh_places_them_once_and_an_invited_towns_none(self):
        from transport.config import Config
        self.assertEqual(genesis.placed_playthings(self.town.client, OPENER, Config(arrival='invited')), [])
        self.assertNotIn('hexboard', genesis.existing(self.town.client, OPENER))
        rows = genesis.placed_playthings(self.town.client, OPENER, Config(arrival='open'))
        self.assertEqual([(r['object'], r['status']) for r in rows],
                         [('kind/counter', 'refreshed'), ('kind/hexboard', 'refreshed'), ('counter', 'refreshed'), ('hexboard', 'refreshed')], rows)
        self.assertEqual({r['status'] for r in genesis.placed_playthings(self.town.client, OPENER, Config(arrival='open'))}, {'current'})
        self.assertEqual(self.town.send(op='world-derived', principal=OPENER, object='hexboard', view='view').get('status'), 'derived')


class Derived(Arc):
    """The host's side: `world-derived` of a card's `view`, the counter and the hexboard as genesis places them."""

    def setUp(self):
        super().setUp()
        town_playthings(self.town)

    def derived(self, obj, who=OPENER, view='view'):
        return self.town.send(op='world-derived', principal=who, object=obj, view=view)

    def tones(self, who):
        hexes = next(v for v in plain(self.derived('hexboard', who)['value'])['items'] if v['tag'] == 'hexes')
        return [t['mark'] for t in hexes['tiles']]

    def test_the_counter_view_is_its_number_between_its_buttons_and_moves_with_it(self):
        first = self.derived('counter', KIM)
        self.assertEqual((first['status'], first['view']), ('derived', 'view'), first)
        self.assertEqual(first, self.derived('counter', KIM))  # the same state, the same view
        page = views.render(first['value'], 'counter', {'plus': {}, 'minus': {}}, NODES)
        self.assertIn('<p class="v-text z-large">0</p>', page)
        self.assertEqual(re.findall(r'name="do" value="(\w+)"', page), ['minus', 'plus'])
        self.assertEqual(self.say(KIM, 'counter', 'delvetalk counter plus')['status'], 'admitted')
        self.assertEqual(self.say(GLM, 'counter', 'delvetalk counter plus')['status'], 'admitted')
        then = self.derived('counter', KIM)
        self.assertGreater(then['version'], first['version'])
        self.assertIn('<p class="v-text z-large">2</p>', views.render(then['value'], 'counter', {}, NODES))
        self.assertEqual(self.outcome(self.say(KIM, 'counter', 'delvetalk counter minus')), ('admitted', None))
        self.assertEqual(self.outcome(self.say(KIM, 'counter', 'delvetalk counter minus')), ('admitted', None))
        self.assertEqual(self.outcome(self.say(KIM, 'counter', 'delvetalk counter minus'))[0], 'refused')  # never below nought

    def test_a_hexboard_place_is_a_mark_in_the_placers_colour_once_a_hex_and_replays(self):
        self.assertEqual(self.tones(KIM), [''] * 49)
        self.assertEqual(self.say(KIM, 'hexboard', 'delvetalk hexboard place\ncell: 24')['status'], 'admitted')
        self.assertEqual(self.say(GLM, 'hexboard', 'delvetalk hexboard place\ncell: 25')['status'], 'admitted')
        taken = self.say(GLM, 'hexboard', 'delvetalk hexboard place\ncell: 24')
        self.assertEqual(self.outcome(taken)[0], 'refused', taken)
        self.assertIn('taken', str(taken))
        self.assertEqual(self.outcome(self.say(GLM, 'hexboard', 'delvetalk hexboard place\ncell: 49'))[0], 'refused')
        marks = {r['name']: r['who'] for r in plain(self.field('hexboard', 'marks'))['items']}
        self.assertEqual(marks, {'hex 24': KIM, 'hex 25': GLM})
        tones, value = self.tones(KIM), self.derived('hexboard', KIM)
        self.assertEqual((tones[24], tones[25], tones.count('')), ('red', 'blue', 47))
        legend = plain(value['value'])['items'][-1]['value']
        self.assertTrue(legend.startswith('Your colour is red. 2 of 49 placed;'), legend)
        self.assertTrue(plain(self.derived('hexboard', 'did:plc:' + 'q' * 24)['value'])['items'][-1]['value'].startswith('Your colour will be green.'))
        card = self.town.send(op='world-card', principal=KIM, object='hexboard')['text']
        self.assertIn('. . . r b . .', card)
        self.town.reopen()
        self.assertEqual(self.derived('hexboard', KIM), value)  # the journal replays to the same board

    def test_a_view_is_read_with_the_cards_authority_and_bounds(self):
        self.assertEqual((self.derived('porch')['status'], self.derived('porch')['clause']), ('refused', 'noView'))
        self.assertEqual(self.derived('nowhere')['status'], 'unknown')
        self.assertEqual(self.derived('counter', view='quietSince')['clause'], 'noView')
        made = self.town.send(op='world-create', principal=OPENER, identity='mk-large', object='large',
                              modules=closure('Abi', 'List') + [{'name': 'Large', 'source': TOO_LARGE}], entry='initial', seed=record(n=nat(1500)))
        self.assertEqual(made['status'], 'created', made)
        self.assertEqual(self.derived('large')['clause'], 'viewTooLarge')
        made = self.town.send(op='world-create', principal=OPENER, identity='mk-long', object='long',
                              modules=closure('Abi', 'List') + [{'name': 'Large', 'source': TOO_LARGE}], entry='initial', seed=record(n=nat(600)))
        long = self.derived('long')  # a list far longer than the wire's 128 cells: a board's tiles nest as a Document may
        self.assertEqual((long['status'], len(plain(long['value']))), ('derived', 600), {k: v for k, v in long.items() if k != 'value'})
        self.assertLess(long['bytes'], 262144)
        bounds = self.town.send(op='bounds')['host']
        self.assertEqual((bounds['maxViewBytes'], bounds['maxViewNodes']), (262144, 4096))


class Live(FrontCase):
    """The front's side, on a genesis town with the counter and the hexboard: pages, clicks, the live channel."""
    OPENER = 'did:plc:' + 'v' * 24

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        made, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal
        made = genesis.playthings(cls.root, cls.OPENER)
        assert all(m['status'] in ('created', 'admitted') for m in made), made

    def setUp(self):
        super().setUp()
        self.cookie = browser_login(self)
        self.front.live_seconds = 6

    def play(self, path, fields=None, cookie=None):
        self.now[0] += 3  # under the per-credential rate
        headers = {'Cookie': cookie or self.cookie}
        if fields is None:
            return self.request('GET', path, headers=headers)
        return self.request('POST', path, raw=urllib.parse.urlencode(fields), headers={**headers, 'Content-Type': FORM})

    def count(self):
        return int(next(v['value'] for v in plain(self.host.send({'op': 'world-view', 'principal': self.OPENER, 'object': 'counter'})['state'])['vars']
                        if v['name'] == 'count'))

    def test_a_button_casts_its_form_as_the_reader_who_clicks_and_shows_the_receipt_there(self):
        s, headers, page = self.play('/play/counter')
        page = page.decode()
        self.assertEqual(s, 200)
        self.assertIn("script-src 'self'", dict(headers)['Content-Security-Policy'])
        self.assertIn('<section class="view" id="view" data-live="/live/counter?v=', page)
        self.assertRegex(page, r'<form class="v-act" method="post" action="/play/counter" title="delvetalk counter plus"><input type="hidden" name="csrf" value="[0-9a-f]{64}"><input type="hidden" name="do" value="plus">')
        s, _, page = self.play('/play/counter', {'do': 'plus'})
        self.assertEqual(s, 200, page)
        self.assertIn(b'<details class="receipt" open>', page)
        self.assertIn(b'<p class="v-text z-large">1</p>', page)
        self.assertEqual(self.count(), 1)
        newest = self.host.send({'op': 'world-history', 'principal': self.OPENER, 'object': 'counter', 'reverse': True, 'limit': 1})['entries'][0]
        self.assertEqual(newest['identity']['principal'], PEOPLE[HANDLE])  # cast as the reader, nobody else
        for do in ('door?label=x&to=garden', 'plus?n=1', 'minus?x', 'place?cell=1', 'lines?from=0'):
            s, _, page = self.play('/play/counter', {'do': do})
            self.assertEqual(s, 400, (do, page[:300]))
        self.assertEqual(self.count(), 1)

    def test_without_a_script_the_view_is_read_and_its_tiles_fill_the_box(self):
        s, headers, page = self.request('GET', '/o/hexboard')  # nobody signed in
        page = page.decode()
        self.assertEqual(s, 200)
        self.assertEqual(page.count('<polygon'), 49)
        self.assertNotIn('class="v-do"', page)  # a stranger is sent no form a script would fill
        href = html.unescape(re.findall(r'<a class="v-tile v-acts" href="([^"]+)" data-do="place\?cell=3"', page)[0])
        s, _, filled = self.play(href.split('#')[0])
        self.assertIn('>delvetalk hexboard place\ncell: 3</textarea>', html.unescape(filled.decode()))
        s, _, page = self.play('/play/hexboard', {'text': 'delvetalk hexboard place\ncell: 3'})  # the box, sent: the same placing
        self.assertEqual(s, 200)
        marks = {r['name']: r['who'] for r in plain(self.host.send({'op': 'world-view', 'principal': self.OPENER, 'object': 'hexboard'})['state'])['marks']['items']}
        self.assertEqual(marks.get('hex 3'), PEOPLE[HANDLE])
        self.assertRegex(self.request('GET', '/o/counter?text=1')[2].decode(), r'POST /play/counter\n  csrf: [0-9a-f]{64}\n  do: plus\n  \[ \+ \]')  # the text view carries the buttons

    def test_a_hexboard_tile_places_the_readers_colour_and_a_taken_one_is_refused_there(self):
        s, _, page = self.play('/play/hexboard', {'do': 'place?cell=10'})
        self.assertEqual(s, 200)
        self.assertNotIn(b'data-do="place?cell=10"', page)  # the hex is placed: no longer a tile that acts
        other = browser_login(self, 'glm.delve.town')
        s, _, page = self.play('/play/hexboard', {'do': 'place?cell=10'}, cookie=other)
        self.assertEqual(s, 200)
        self.assertIn(b'taken', page)

    def test_a_live_view_is_told_of_a_change_within_a_second(self):
        version = self.host.send({'op': 'world-derived', 'principal': PEOPLE[HANDLE], 'object': 'counter', 'view': 'view'})['version']
        got, opened = [], threading.Event()

        def listen():
            c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
            c.request('GET', f'/live/counter?v={version}', headers={'Cookie': self.cookie})
            r = c.getresponse()
            got.append(r.status)
            opened.set()
            event = b''
            while True:
                line = r.fp.readline()
                if not line:
                    break
                event += line
                if event.endswith(b'\n\n') and b'event: view' in event:
                    got.append((time.monotonic(), event.decode()))
                    break
                if line == b'\n':
                    event = b''
            c.close()
        t = threading.Thread(target=listen, daemon=True)
        t.start()
        self.assertTrue(opened.wait(5))
        time.sleep(0.5)  # the stream is open and waiting on the tail
        other = browser_login(self, 'glm.delve.town')
        s, _, _ = self.play('/play/counter', {'do': 'plus'}, cookie=other)
        sent = time.monotonic()
        self.assertEqual(s, 200)
        t.join(5)
        self.assertEqual(got[0], 200)
        when, event = got[1]
        self.assertLess(when - sent, 1.0)
        self.assertIn('id: ', event)
        self.assertIn('<p class="v-text z-large">', event)
        self.assertRegex(event, r'name="csrf" value="[0-9a-f]{64}"')  # its forms are this browser's
        self.assertEqual(self.request('GET', '/live/porch', headers={'Cookie': self.cookie})[0], 404)  # a thing with no view


if __name__ == '__main__':
    unittest.main()
