"""Every route a browser reaches is a page in the theme's vocabulary, never a JSON dump; JSON stays JSON for agents.

Against the genesis town on a real hostd, logged in through the login page's forms (the session cookie)."""
import html
import json
import os
import re
import unittest
import urllib.parse
from html.parser import HTMLParser

from tests.test_turn_world import ROOT, closure, declared
from tests.test_http import DID, FORM, HANDLE, FrontCase, browser_login
from transport.hostproc import HostClient

HTML = {'Accept': 'text/html,application/xhtml+xml'}


class Actions(HTMLParser):
    """What a page lets you do, read from its HTML independently of transport.pages.text: every link's href, and every form
    as (method, action, the names it posts). The theme toggle (hidden until script runs) and the <head> are not actions."""
    def __init__(self, markup):
        super().__init__()
        self.links, self.forms, self.form, self.hidden = [], [], None, 0
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'head' or 'hidden' in a:
            self.hidden += 1
        elif self.hidden:
            return
        elif tag == 'a':
            self.links.append(a.get('href'))
        elif tag == 'form':
            self.form = [(a.get('method') or 'get').upper(), a.get('action') or '.', []]
        elif tag in ('input', 'textarea', 'select', 'button') and self.form and a.get('name'):
            self.form[2].append(a['name'])

    def handle_endtag(self, tag):
        if tag in ('head', 'button') and self.hidden:
            self.hidden -= 1
        elif tag == 'form' and self.form:
            self.forms.append((self.form[0], self.form[1], tuple(sorted(self.form[2]))))
            self.form = None


def text_actions(text):
    """The same, read from the plain-text view: `[ LABEL ] href` and `label <href>` links, and each form's block."""
    links = re.findall(r'\[ [^\]\n]*? \] ((?:/|https?:|#)\S*)|<((?:/|https?:|#)[^<>\s]*)>', text)
    forms, lines = [], text.split('\n')
    for i, line in enumerate(lines):
        if m := re.fullmatch(r'(GET|POST) (\S+)', line):
            names = []
            for field in lines[i + 1:]:
                if not field.startswith('  '):
                    break
                names += re.findall(r'^  ([^\s:]+(?::[^\s:]+)?): ', field) or re.findall(r'\] (\S+)=', field)
            forms.append((m[1], m[2], tuple(sorted(names))))
    return [a or b for a, b in links], forms
PICKER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
sum Colour:
  amber: {}
  violet: {}
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def pick(state: State, input: {colour: Colour}, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: state.count + 1n
""")


class Pages(FrontCase):
    OPENER = 'did:plc:' + 'f' * 24

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from deploy import genesis
        made, refusal = genesis.run(HostClient(cls.socket), cls.OPENER)
        assert refusal is None, refusal
        r = HostClient(cls.socket).send({'op': 'world-create', 'principal': cls.OPENER, 'identity': 'mk-picker', 'object': 'picker',
                                         'modules': closure('World') + [{'name': 'Picker', 'source': PICKER}], 'entry': 'initial', 'seed': {'tag': 'record', 'fields': []}})
        assert r['status'] == 'created', r

    def setUp(self):
        super().setUp()
        self.cookie = browser_login(self)

    def page(self, path, *classes, code=200, cookie=True, method='GET', form=None):
        self.now[0] += 3  # under the per-credential rate
        headers = {**HTML, **({'Cookie': self.cookie} if cookie else {}), **({'Content-Type': FORM} if form else {})}
        s, h, body = self.request(method, path, raw=urllib.parse.urlencode(form) if form else None, headers=headers)
        text = body.decode()
        self.assertEqual((s, dict(h)['Content-Type']), (code, 'text/html; charset=utf-8'), (path, text[:500]))
        self.assertNotIn('{"', text, f'{path} dumps JSON')
        self.assertTrue(text.startswith('<!doctype html>'), path)
        for c in classes:
            self.assertIn(c, text, path)
        return text

    def test_the_world_is_a_list_of_kind_marked_cards_with_door_words(self):
        text = self.page('/AGENTS.md/world', 'class="cards"', 'class="minicard"', 'data-id="garden"', '<span class="word">GARDEN</span>')
        self.assertIn('class="yours"', text)  # the visitor's own avatar, env and wake
        self.page('/', 'class="cards"', 'data-id="garden"')

    def test_an_object_is_its_card_doors_actions_source_and_slips(self):
        text = self.page('/o/garden', 'class="frame"', 'class="card"', 'class="action"', 'class="listing law"', 'class="listing"')
        self.assertIn('<input name="seed" minlength="1" maxlength="80">', text)  # the garden's own form (forms()) bounds the seed
        self.assertIn('action="/play/garden"', text)
        self.assertIn('<input type="number" name="n:every" min="1" max="1000"', self.page('/o/tide'))  # the tide's form
        picker = self.page('/o/picker', 'class="action"')
        self.assertIn('<select name="c:colour"><option>amber</option><option>violet</option></select>', picker)
        done = self.page('/play/picker', method='POST', form={'method': 'pick', 'c:colour': 'violet'})
        self.assertRegex(done, r'admitted picker v1, entry')
        self.page('/o/directory', 'class="door"', '<span class="kind" data-id="garden"></span>GARDEN')
        self.assertEqual(self.page('/AGENTS.md/world/garden'), text)  # the agent route, for a browser, is the same page
        self.page('/AGENTS.md/world/garden/source', 'class="action"')

    def test_an_action_form_runs_the_turn_the_play_page_runs_and_its_receipt_is_a_page(self):
        text = self.page('/play/garden', 'class="slip admitted', '<span class="stamp">●</span><span class="line">admitted garden', method='POST', form={'method': 'plant', 'colour': 'violet', 'seed': 'a form-grown fern'})
        slug = re.search(r'admitted garden v\d+, entry \d+, receipt ([a-z-]+)', text)[1]
        receipt = self.page(f'/AGENTS.md/receipt/{slug}', 'class="slip admitted"', '<span class="stamp">● admitted</span>', f'<span class="name">{slug}</span>', '<dl>')
        self.assertIn('href="/o/garden"', receipt)  # the roots as shelf marks
        self.page('/o/garden', f'<span class="name">{slug}</span>')  # and in the object's ledger
        self.page('/AGENTS.md/offers', 'class="frame offer"', 'class="slip admitted"', '<span class="stamp">↳ offered</span>')

    def test_the_rest_of_the_agent_routes_render_as_definition_lists(self):
        for path in ('/AGENTS.md/me', '/AGENTS.md/pending'):
            self.page(path, '<dl>', 'class="title"')

    def test_the_catalogue_is_a_table_and_errors_are_refusal_pages(self):
        text = self.page('/AGENTS.md/api', '<table>', '/AGENTS.md/world/{object}/{method}', 'requestTimeout', 'lawRefused', cookie=False)
        self.assertIn('<td><span class="code">POST</span></td>', text)
        self.page('/nowhere', 'class="refusal"', code=404, cookie=False)
        self.page('/hand/', 'class="refusal"', code=404, cookie=False)
        self.page('/xrpc/com.atproto.repo.describeRepo?repo=did:plc:other', 'class="refusal"', 'RepoNotFound', code=400, cookie=False)
        self.page('/AGENTS.md/world/nope', 'class="refusal"', code=404)
        self.page('/AGENTS.md/world', 'class="refusal"', 'unauthenticated', code=401, cookie=False)
        self.page('/style/', 'class="specimen"', cookie=False)
        self.page('/play/', 'class="frame"', 'class="door"')

    def test_json_stays_json_for_agents(self):
        tok = self.cookie.split('=', 1)[1]
        for accept in (None, 'application/json', '*/*'):
            headers = {'Authorization': 'Bearer ' + tok, **({'Accept': accept} if accept else {})}
            for path in ('/AGENTS.md/world', '/AGENTS.md/world/garden', '/AGENTS.md/offers', '/AGENTS.md/me'):
                self.now[0] += 3
                s, h, body = self.request('GET', path, headers=headers)
                self.assertEqual((s, dict(h)['Content-Type']), (200, 'application/json; charset=utf-8'), path)
                self.assertIn('_links', json.loads(body))
        s, h, body = self.request('GET', '/AGENTS.md/api', headers={'Accept': 'application/json'})
        self.assertEqual(json.loads(body)['status'], 'catalogue')
        self.assertEqual(dict(self.request('GET', '/nowhere')[1])['Content-Type'], 'application/json; charset=utf-8')

    def test_every_page_as_plain_text_carries_the_same_actions_and_rules(self):
        """?text=1 (or Accept: text/plain) on every browser route: the same links and forms the HTML offers, the card and the
        law verbatim, each receipt's stamp, the quiet line."""
        slug = None
        for path, method, form, cookie, code in (
                ('/', 'GET', None, False, 200), ('/', 'GET', None, True, 200), ('/AGENTS.md/world', 'GET', None, True, 200),
                ('/o/garden', 'GET', None, True, 200), ('/o/garden', 'GET', None, False, 200), ('/o/directory', 'GET', None, True, 200),
                ('/o/picker', 'GET', None, True, 200), ('/o/tide', 'GET', None, True, 200), ('/play/', 'GET', None, True, 200),
                ('/play/garden', 'GET', None, True, 200), ('/play/garden', 'POST', {'method': 'plant', 'colour': 'amber', 'seed': 'a text fern'}, True, 200),
                ('/AGENTS.md/world/garden/source', 'GET', None, True, 200), ('/AGENTS.md/me', 'GET', None, True, 200),
                ('/AGENTS.md/pending', 'GET', None, True, 200), ('/AGENTS.md/offers', 'GET', None, True, 200), ('/AGENTS.md/api', 'GET', None, False, 200),
                ('/style/', 'GET', None, False, 200), ('/nowhere', 'GET', None, False, 404), ('/AGENTS.md/world/nope', 'GET', None, True, 404),
                ('/AGENTS.md/world', 'GET', None, False, 401), ('/xrpc/com.atproto.repo.describeRepo?repo=did:plc:other', 'GET', None, False, 400),
                ('/AGENTS.md/challenge', 'POST', {'handle': HANDLE}, False, 200), ('receipt', 'GET', None, True, 200)):
            path = f'/AGENTS.md/receipt/{slug}' if path == 'receipt' else path
            page = self.page(path, code=code, cookie=cookie, method=method, form=form)
            self.now[0] += 3
            sep = '&' if '?' in path else '?'
            headers = {**HTML, **({'Cookie': self.cookie} if cookie else {}), **({'Content-Type': FORM} if form else {})}
            raw = urllib.parse.urlencode({**form, 'seed': 'a text fern, again'} if form and 'seed' in form else form) if form else None
            s, h, body = self.request(method, path + sep + 'text=1', raw=raw, headers=headers)
            text = body.decode()
            self.assertEqual((s, dict(h)['Content-Type']), (code, 'text/plain; charset=utf-8'), (path, text[:300]))
            self.assertNotIn('<!doctype', text)
            seen = Actions(page)
            links, forms = text_actions(text)
            self.assertEqual((sorted(links), sorted(forms)), (sorted(seen.links), sorted(seen.forms)), path)
            for kind, inner in re.findall(r'<pre class="([^"]*)">(.*?)</pre>', page, re.S) if method == 'GET' else ():  # verbatim
                self.assertIn(html.unescape(re.sub(r'<[^>]+>', '', inner)), text, (path, kind))  # the card, the spell, the law
            for stamp in re.findall(r'<span class="stamp">([^<]*)</span>', page) if method == 'GET' else ():
                self.assertIn(html.unescape(stamp), text, path)
            if form and 'seed' in form:
                slug = re.search(r'receipt ([a-z]+(?:-[a-z]+)+)', page)[1]
                self.assertRegex(text, r'● +admitted garden v\d+, entry \d+, receipt ')
        tok = self.cookie.split('=', 1)[1]
        s, h, body = self.request('GET', '/o/garden', headers={'Accept': 'text/plain', 'Cookie': self.cookie})
        self.assertEqual(dict(h)['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('[ PLAY garden ] /play/garden', body.decode())
        s, h, body = self.request('GET', '/AGENTS.md/world/garden', headers={'Accept': 'application/json, text/plain', 'Authorization': 'Bearer ' + tok})
        self.assertEqual(dict(h)['Content-Type'], 'application/json; charset=utf-8')  # an agent that also takes text still gets JSON


class Hob(unittest.TestCase):
    """hob's line (docs/VOICE.md) beside a card: its own element, the frog before it, never in the frame."""
    def test_an_offer_whose_first_line_is_hob_renders_hob_beside_the_card_and_as_the_line_in_text(self):
        from transport import pages
        offer = 'hob: I read that as\ndelvetalk garden plant\ncolour: amber\nseed: a moth bell\n'
        for page in (pages.rendered('offers', {'status': 'offers', 'offers': [{'height': 9, 'identity': {'intent': 'p1'}, 'text': offer}]}, {}, None),
                     pages.rendered('receipt', {'status': 'receipt', 'receipt': {'slug': 'tulun-huzif', 'height': 9, 'outcome': {'tag': 'admitted'},
                                                                                 'offers': [{'to': DID, 'text': offer}]}}, {}, None),
                     pages.obj('garden', None, {'status': 'viewed', 'version': 1}, offer, [])):
            hob = re.search(r'<p class="hob"><svg class="frog glyph"[^>]*>.*?</svg><span>(.*?)</span></p>', page, re.S)
            self.assertEqual(hob[1], 'hob: I read that as')
            card = re.search(r'<pre class="card">(.*?)</pre>', page, re.S)[1]
            self.assertNotIn('hob:', card)
            self.assertTrue(card.startswith('delvetalk garden plant'), card)
            self.assertLess(page.index('class="hob"'), page.index('<pre class="card">'))
            self.assertIn('hob: I read that as', pages.text(page).splitlines())
