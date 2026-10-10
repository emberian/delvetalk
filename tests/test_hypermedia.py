"""The front's controls: `_links` on every JSON reply, `_actions` projected from the host's method table and forms."""
import http.client
import json
import re
import tempfile
import threading
import unittest

from tests.test_chain import garden_state
from tests.test_http import DID, REPL_COUNTER, FrontCase, StubHost
from transport import delve, identity
from transport.http import CATALOGUE, ERRORS, GUIDE, REFUSALS, Front, resolve
from tests.test_turn_world import closure

LAWFUL = REPL_COUNTER + 'law nobody "only ember writes it": request.kind == 0 implies request.subject == "ember"\n'


def fill(action):
    """Plain values for an action's fields, chosen from its bounds as any client would."""
    return {f['name']: f['bounds']['options'][0] if f['kind'] == 'choice' else f['bounds']['min'] if f['kind'] == 'natural'
            else f"a {f['name']}" for f in action['fields']}


class Controls(FrontCase):
    def setUp(self):
        super().setUp()
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-g', 'object': 'garden',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state(0)})
        self.assertEqual(r['status'], 'created', r)
        self.tok = self.login()

    def get(self, href):
        s, body = self.call('GET', href, token=self.tok)
        self.assertIn('_links', body, (href, body))
        self.assertEqual(body['_links']['self']['href'], href)
        return s, body

    def test_an_object_reply_carries_one_action_per_turnable_method_with_its_form(self):
        s, view = self.get('/AGENTS.md/world/garden')
        self.assertEqual((s, view['status']), (200, 'viewed'))
        self.assertEqual({k: v['href'] for k, v in view['_links'].items() if k != 'self'},
                         {'object': '/AGENTS.md/world/garden', 'card': '/AGENTS.md/world/garden/card', 'source': '/AGENTS.md/world/garden/source',
                          'world': '/AGENTS.md/world', 'offers': '/AGENTS.md/offers'})
        methods = self.host.send({'op': 'world-inspect', 'principal': DID, 'object': 'garden'})['methods']
        acts = {a['name']: a for a in view['_actions']}
        self.assertEqual(sorted(acts), sorted(m['name'] for m in methods if m['context']))
        plant = acts['plant']
        self.assertEqual((plant['method'], plant['href']), ('POST', '/AGENTS.md/world/garden/plant'))
        self.assertEqual(plant['fields'], [{'name': 'colour', 'kind': 'text', 'bounds': {'min': 0, 'max': 1400}},
                                           {'name': 'seed', 'kind': 'text', 'bounds': {'min': 0, 'max': 1400}}])
        self.assertEqual(plant['spell'], 'delvetalk garden plant\ncolour: <text 0..1400>\nseed: <text 0..1400>\n')
        self.assertEqual(acts['receive']['body'], {'intent': 'text', 'spell': "text: any action's spell, or prose"})
        self.assertIn('input', acts['observe'])  # no form for a record input: the host's type, and typed data
        for route in ('card', 'source'):
            self.assertEqual(self.get(f'/AGENTS.md/world/garden/{route}')[1]['_actions'], view['_actions'])

    def test_acting_from_the_reply_alone(self):
        view = self.get('/AGENTS.md/world/garden')[1]
        plant = [a for a in view['_actions'] if a['name'] == 'plant'][0]
        s, t = self.call(plant['method'], plant['href'], {'intent': 'by-form', 'fields': {**fill(plant), 'colour': 'amber'}}, self.tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        links = t['_links']
        self.assertEqual(links['receipt']['href'], '/AGENTS.md/receipt/' + t['receipt']['slug'])
        self.assertEqual(links['offers']['href'], f"/AGENTS.md/offers?after={t['receipt']['height'] - 1}")
        self.assertEqual(links['created'], [{'href': '/AGENTS.md/world/garden/bell/1', 'name': 'garden/bell/1'}])
        s, r = self.get(links['receipt']['href'])
        self.assertEqual((s, r['receipt']['hash']), (200, t['receipt']['hash']))
        self.assertEqual(r['_links']['object']['href'], '/AGENTS.md/world/garden')
        s, bell = self.get(links['created'][0]['href'])
        self.assertEqual((s, bell['object']), (200, 'garden/bell/1'))
        self.assertTrue(all(a['href'].startswith('/AGENTS.md/world/garden/bell/1/') for a in bell['_actions']))
        receive = [a for a in view['_actions'] if a['name'] == 'receive'][0]
        spell = plant['spell'].replace('<text 0..1400>', 'amber', 1).replace('<text 0..1400>', 'a spelled bell')
        s, t = self.call('POST', receive['href'], {'intent': 'by-spell', 'spell': spell}, self.tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, offers = self.get(links['offers']['href'])
        self.assertEqual(offers['_links']['next']['href'], f"/AGENTS.md/offers?after={offers['offers'][-1]['height']}&wait=30")

    def test_a_refusal_links_its_hint_and_the_usage_action(self):
        s, made = self.call('POST', '/AGENTS.md/heap/objects', {'intent': 'mk-l', 'object': 'kept', 'entry': 'initial', 'seed': {},
                                                                'modules': [{'name': 'Kept', 'source': LAWFUL}]}, self.tok)
        self.assertEqual((s, made['status']), (200, 'created'), made)
        self.assertEqual(made['_links']['object']['href'], '/AGENTS.md/heap/world/kept')
        s, t = self.call('POST', '/AGENTS.md/heap/world/kept/bump', {'intent': 'no'}, self.tok)
        self.assertEqual((s, t['status'], t['receipt']['outcome']['class']), (200, 'refused', 'lawRefused'), t)
        self.assertEqual(t['_links']['hint']['href'], '/AGENTS.md/heap/world/kept/source')  # the law is there
        self.assertEqual([a['href'] for a in t['_actions']], ['/AGENTS.md/heap/world/kept/bump'])
        s, e = self.call('POST', '/AGENTS.md/world/c1/bump', {'argument': 7, 'intent': 'bad'}, self.tok)
        self.assertEqual((s, e['_links']['hint']['href'], [a['name'] for a in e['_actions']]), (400, '/AGENTS.md/world/c1/source', ['bump']))
        self.turn(self.tok, 'dup')
        s, d = self.call('POST', '/AGENTS.md/world/c1/bump', {'fields': {'a': 1}, 'intent': 'dup'}, self.tok)
        self.assertEqual((d['class'], d['_links']['hint']['href']), ('duplicateIdentity', '/AGENTS.md/receipt/dup'), d)

    def test_a_listing_links_each_id_and_its_next_page(self):
        s, listed = self.get('/AGENTS.md/world')
        self.assertEqual([i['name'] for i in listed['_links']['item']], listed['ids'])
        self.assertIn({'href': '/AGENTS.md/world/garden', 'name': 'garden'}, listed['_links']['item'])
        self.assertNotIn('next', listed['_links'])
        real = self.host.send
        self.host.send = lambda req: {'status': 'listed', 'ids': ['a', 'b/c'], 'more': True} if req['op'] == 'world-objects' else real(req)
        s, page = self.get('/AGENTS.md/world?prefix=b')
        self.assertEqual(page['_links']['next']['href'], '/AGENTS.md/world?prefix=b&after=b%2Fc')

    def test_every_json_reply_has_links(self):
        for method, path, body in (('GET', '/AGENTS.md/me', None), ('GET', '/AGENTS.md/pending', None), ('POST', '/AGENTS.md/deliver', {}),
                                   ('POST', '/AGENTS.md/check', {'source': REPL_COUNTER, 'entry': 'bump'}),
                                   ('GET', '/AGENTS.md/receipt/nothing', None), ('GET', '/AGENTS.md/offers', None)):
            s, r = self.call(method, path, body, self.tok)
            self.assertEqual(r['_links']['self']['href'], path, (path, r))
        s, ch = self.call('POST', '/AGENTS.md/challenge', {'handle': 'glm.delve.town'})
        self.assertEqual(ch['_links']['verify']['href'], '/AGENTS.md/verify')

    def test_a_suspended_turn_links_its_offers_with_a_wait(self):
        from transport.http import receipt_links
        links = receipt_links('/AGENTS.md', {'status': 'suspended', 'receipt': {'slug': 'babab-dabab', 'height': 12,
                                                                                'roots': [{'object': 'garden', 'version': 3}]}})
        self.assertEqual(links['offers']['href'], '/AGENTS.md/offers?after=12&wait=30')
        self.assertEqual(links['object']['href'], '/AGENTS.md/world/garden')


class Catalogue(unittest.TestCase):
    """The catalogue against a stub host: routes as data, and the router that answers them is the one that describes them."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.front = Front(('127.0.0.1', 0), StubHost(), identity.Identity(self.tmp.name, delve.Client(lambda *a: (404, b''))))
        threading.Thread(target=self.front.serve_forever, daemon=True).start()

    def tearDown(self):
        self.front.shutdown()
        self.front.server_close()
        self.tmp.cleanup()

    def call(self, method, path, headers=None, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', self.front.server_address[1], timeout=30)
        c.request(method, path, raw, headers or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data

    def test_every_route_resolves_from_its_template_to_its_own_entry(self):
        names = [e['name'] for e in CATALOGUE]
        self.assertEqual(len(names), len(set(names)))
        fill = {'object': 'garden%2Fbell%2F1', 'method': 'plant', 'intent': 'plant-1', 'nsid': 'com.atproto.repo.describeRepo', 'file': 'style.css'}
        for e in CATALOGUE:
            for href in (e['href'], e.get('heap')):
                if href:
                    self.assertEqual(resolve(e['method'], re.sub(r'\{(\w+)\}', lambda m: fill[m[1]], href))[0], e['name'], href)
                    if '/world/' in href:  # agents' routes also take an id's slashes as they are
                        self.assertEqual(resolve(e['method'], href.replace('{object}', 'garden/bell/1').replace('{method}', 'plant'))[0], e['name'])

    def test_the_catalogue_is_served_as_data_and_the_guide_links_to_it(self):
        s, h, raw = self.call('GET', '/AGENTS.md/api')
        api = json.loads(raw)
        self.assertEqual((s, api['status'], [r['name'] for r in api['routes']]), (200, 'catalogue', [e['name'] for e in CATALOGUE]))
        self.assertEqual(set(api['errors']), set(ERRORS))
        self.assertEqual({k: v['transient'] for k, v in api['refusals'].items()}, {k: v[0] for k, v in REFUSALS.items()})
        self.assertEqual(api['limits']['bodyBytes'], 65536)
        s, h, raw = self.call('GET', '/AGENTS.md', {'Accept': 'application/json'})
        self.assertEqual({**json.loads(raw), '_links': None}, {**api, '_links': None})
        s, h, text = self.call('GET', '/AGENTS.md')
        self.assertEqual(h['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn(b'/api', text)

    def test_the_guides_class_tables_are_the_catalogues(self):
        guide = GUIDE.read_text()
        rows = set(re.findall(r'^\| ([a-zA-Z, ]+?) \|', guide, re.M))
        documented = {c.strip() for row in rows for c in row.split(',')}
        self.assertLessEqual(set(REFUSALS) - {'duplicateIdentity'}, documented)

    def test_options_answers_the_entries_of_a_path(self):
        s, h, raw = self.call('OPTIONS', '/AGENTS.md/world/garden/bell/1')
        self.assertEqual((s, [r['name'] for r in json.loads(raw)['routes']], h['Allow']), (200, ['object', 'action'], 'GET, POST, OPTIONS'))
        s, h, raw = self.call('OPTIONS', '/AGENTS.md/heap/objects')
        self.assertEqual([r['name'] for r in json.loads(raw)['routes']], ['create'])
        self.assertEqual(self.call('OPTIONS', '/AGENTS.md/nowhere')[0], 404)


if __name__ == '__main__':
    unittest.main()
