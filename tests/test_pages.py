"""Every route a browser reaches is a page in the theme's vocabulary, never a JSON dump; JSON stays JSON for agents.

Against the genesis town on a real `serve`, logged in through the login page's forms (the session cookie)."""
import html
import json
import re
import urllib.parse
from html.parser import HTMLParser

from tests.test_turn_world import closure, declared
from tests.test_http import FORM, HANDLE, FrontCase, browser_login

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
        made, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal
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


