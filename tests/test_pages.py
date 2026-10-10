"""Every route a browser reaches is a page in the theme's vocabulary, never a JSON dump; JSON stays JSON for agents.

Against the genesis town on a real hostd, logged in through the login page's forms (the session cookie)."""
import json
import re
import urllib.parse

from tests.test_turn_world import declared
from tests.test_http import DID, FORM, FrontCase, browser_login
from transport.hostproc import HostClient

HTML = {'Accept': 'text/html,application/xhtml+xml'}
PICKER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
sum Colour:
  amber: {}
  violet: {}
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {count: 0n}
def pick(state: State, input: {colour: Colour}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
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
                                         'modules': [{'name': 'Picker', 'source': PICKER}], 'entry': 'initial', 'seed': {'tag': 'record', 'fields': []}})
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
        self.assertIn('<input name="seed" minlength="0" maxlength="1400">', text)  # the method table's form: plant takes text
        self.assertIn('action="/play/garden"', text)
        self.assertIn('<input type="number" name="n:every" min="0" max="1000000000"', self.page('/o/tide'))
        picker = self.page('/o/picker', 'class="action"')
        self.assertIn('<select name="c:colour"><option>amber</option><option>violet</option></select>', picker)
        done = self.page('/play/picker', method='POST', form={'method': 'pick', 'c:colour': 'violet'})
        self.assertRegex(done, r'admitted picker v1 at height')
        self.page('/o/directory', 'class="door"', '<span class="kind" data-id="garden"></span>GARDEN')
        self.assertEqual(self.page('/AGENTS.md/world/garden'), text)  # the agent route, for a browser, is the same page
        self.page('/AGENTS.md/world/garden/source', 'class="action"')

    def test_an_action_form_runs_the_turn_the_play_page_runs_and_its_receipt_is_a_page(self):
        text = self.page('/play/garden', 'class="slip admitted', method='POST', form={'method': 'plant', 'colour': 'violet', 'seed': 'a form-grown fern'})
        slug = re.search(r'admitted garden v\d+ at height \d+, receipt ([a-z-]+)', text)[1]
        receipt = self.page(f'/AGENTS.md/receipt/{slug}', 'class="slip admitted"', f'<span class="name">{slug}</span>', '<dl>')
        self.assertIn('href="/o/garden"', receipt)  # the roots as shelf marks
        self.page('/o/garden', f'<span class="name">{slug}</span>')  # and in the object's ledger
        self.page('/AGENTS.md/offers', 'class="frame offer"', 'class="slip admitted"')

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
