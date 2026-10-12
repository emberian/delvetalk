"""Every route a browser reaches is a page in the theme's vocabulary, never a JSON dump; JSON stays JSON for agents.

Against the genesis town on a real `serve`, logged in through the login page's forms (the session cookie).

Evidence for FOUNDATION §7 (layer: transport).
"""
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser

from transport.pages import text as pages_text
from tests.test_http import DID, FORM, HANDLE, FrontCase, browser_login
from tests.wire import nat, record
from tests.bend import closure, counter_modules, declared

HTML = {'Accept': 'text/html,application/xhtml+xml'}
A_DID = re.compile(r'did:plc:[a-z2-7]{24}')


def read(page):
    """What a person reads of a page as prose: its text, never a tag's attributes (an href may carry an id that is a DID)
    nor a <pre> (a card, a law, a source: verbatim, and a law may name the opener's DID)."""
    return html.unescape(re.sub(r'<[^>]*>', ' ', re.sub(r'<pre\b.*?</pre>', ' ', page, flags=re.S)))


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
        from tests.town import furnish
        made, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal
        furnish(cls.root, cls.OPENER)
        r = cls.root.send({'op': 'world-create', 'principal': cls.OPENER, 'identity': 'mk-picker', 'object': 'picker',
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


    def test_a_did_shows_as_its_handle_or_a_stranger_and_stays_in_the_json(self):
        stranger = 'did:plc:' + 'q' * 20 + 'wxyz'  # a principal the registry knows no avatar for
        made = self.host.send({'op': 'world-create', 'principal': stranger, 'identity': 'mk-' + stranger, 'object': 'note/' + stranger,
                               'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(made['status'], 'created', made)
        home = read(self.page('/'))
        self.assertIn('talkie.delve.town', home)
        self.assertIn('note/a stranger …wxyz', home)
        self.assertIn(f'href="/o/{DID}"', self.page('/'))  # the link still names the object by its id
        slips = read(self.page(f'/o/{self.c}'))
        self.assertIn('talkie.delve.town', slips)
        tok = self.cookie.split('=', 1)[1]
        s, h, body = self.request('GET', '/AGENTS.md/world', headers={'Authorization': 'Bearer ' + tok})
        self.assertIn(DID, json.loads(body)['ids'])  # an agent's JSON keeps the DID

    def test_an_objects_text_view_is_brief_unless_all_is_asked(self):
        for i in range(7):  # more receipts than the brief view keeps
            self.page('/play/garden', method='POST', form={'method': 'plant', 'colour': 'amber', 'seed': 'brief %d' % i})
        full = self.page('/o/garden')
        s, h, body = self.request('GET', '/o/garden?text=1', headers={'Cookie': self.cookie})
        brief = body.decode()
        card = html.unescape(re.search(r'<pre class="card">(.*?)</pre>', full, re.S)[1])
        self.assertIn(card, brief)  # the card, its spells in it
        self.assertEqual(len(re.findall(r'^[●§…◦] ', brief, re.M)), 5)  # the newest five receipts
        self.assertGreater(len(re.findall(r'class="slip ', full)), 5)
        for gone in ('--- law ---', 'POST /play/garden'):
            self.assertNotIn(gone, brief)
        self.assertIn('/o/garden?all=1&text=1', brief)
        self.assertLess(len(brief), len(pages_text(full)))
        s, h, whole = self.request('GET', '/o/garden?all=1&text=1', headers={'Cookie': self.cookie})
        self.assertIn('--- law ---', whole.decode())

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
                ('/o/garden', 'GET', None, True, 200), ('/o/garden', 'GET', None, False, 200), ('/o/commonplace', 'GET', None, True, 200),
                ('/o/picker', 'GET', None, True, 200), ('/o/tide', 'GET', None, True, 200), ('/play/', 'GET', None, True, 200),
                ('/play/garden', 'GET', None, True, 200), ('/play/garden', 'POST', {'method': 'plant', 'colour': 'amber', 'seed': 'a text fern'}, True, 200),
                ('/AGENTS.md/world/garden/source', 'GET', None, True, 200), ('/AGENTS.md/me', 'GET', None, True, 200),
                ('/AGENTS.md/pending', 'GET', None, True, 200), ('/AGENTS.md/offers', 'GET', None, True, 200), ('/AGENTS.md/api', 'GET', None, False, 200),
                ('/style/', 'GET', None, False, 200), ('/nowhere', 'GET', None, False, 404), ('/AGENTS.md/world/nope', 'GET', None, True, 404),
                ('/AGENTS.md/world', 'GET', None, False, 401), ('/xrpc/com.atproto.repo.describeRepo?repo=did:plc:other', 'GET', None, False, 400),
                ('/AGENTS.md/challenge', 'POST', {'handle': HANDLE}, False, 200), ('receipt', 'GET', None, True, 200)):
            path = f'/AGENTS.md/receipt/{slug}' if path == 'receipt' else path
            page = self.page(path, code=code, cookie=cookie, method=method, form=form)
            self.assertEqual(A_DID.findall(read(page)), [], path)  # a person reads a handle, or `a stranger` and the DID's last four
            self.now[0] += 3
            sep = '&' if '?' in path else '?'
            headers = {**HTML, **({'Cookie': self.cookie} if cookie else {}), **({'Content-Type': FORM} if form else {})}
            raw = urllib.parse.urlencode({**form, 'seed': 'a text fern, again'} if form and 'seed' in form else form) if form else None
            s, h, body = self.request(method, path + sep + 'text=1&all=1', raw=raw, headers=headers)  # ?all=1: the whole page, as the HTML has it
            text = body.decode()
            self.assertEqual((s, dict(h)['Content-Type']), (code, 'text/plain; charset=utf-8'), (path, text[:300]))
            self.assertNotIn('<!doctype', text)
            prose = re.sub(r'^--- [^\n]* ---\n.*?\n---$', '', re.sub(r'(?:<|\] )/\S*', '', text), flags=re.S | re.M)  # hrefs and <pre> fences stay verbatim
            self.assertEqual(A_DID.findall(prose), [], path)
            seen = Actions(page)
            links, forms = text_actions(text)
            made = lambda hrefs: sorted(re.sub(r'%2F\d+%20', '%2FN%20', h or '') for h in hrefs)  # a POST twice plants two bells
            self.assertEqual((made(links), sorted(forms)), (made(seen.links), sorted(seen.forms)), path)
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
        self.assertIn('Speak to it </play/garden>', body.decode())
        s, h, body = self.request('GET', '/AGENTS.md/world/garden', headers={'Accept': 'application/json, text/plain', 'Authorization': 'Bearer ' + tok})
        self.assertEqual(dict(h)['Content-Type'], 'application/json; charset=utf-8')  # an agent that also takes text still gets JSON


