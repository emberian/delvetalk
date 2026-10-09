"""Portal read-only navigation from exact typed parent captures to fresh children."""
import copy
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import portal as p


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}


def label(value):
    return {'tag': 'label', 'value': value}


def observation(root, object_id, panel):
    data = {'title': root['protocol']['name'], 'prose': panel, 'actions': {}}
    view = {'format': 'delvetalk-projection-view-v1', 'mode': 'projection',
            'root': copy.deepcopy(root), 'object': object_id, 'panel': panel,
            'data': data, 'actions': {}, 'children': []}
    if root['protocol']['viewProgram']['profile'] == p.bootstrap.projection.DATA_MENU_PROFILE:
        entries = root['state']['exhibits']
        sequence = {'tag': 'variant', 'label': 'nil', 'payload': record()}
        for entry in reversed(entries):
            sequence = {'tag': 'variant', 'label': 'cons', 'payload': record(
                head=record(**{k: label(v) for k, v in entry.items()}), tail=sequence)}
        view.update(children=copy.deepcopy(entries), rawData=record(title=label(data['title']),
            prose=label(panel), actions=record(), children=sequence))
    else:
        data['actions'] = {'touch': {'text': 'Touch the light', 'command': 'touch', 'input': {}}}
        view['actions'] = data['actions']
    return view


class PortalChildrenTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.descriptor = {'key': 'lamp & one', 'label': '<The lantern>', 'object': 'lantern', 'panel': 'glow'}
        self.parent = {'protocol': {'name': 'Exhibition', 'commands': {},
            'viewProgram': {'profile': p.bootstrap.projection.DATA_MENU_PROFILE}},
            'state': {'exhibits': [self.descriptor]}, 'version': 0, 'law': ['curator']}
        self.lantern = {'protocol': {'name': 'Lantern', 'commands': {'touch': {}},
            'viewProgram': {'profile': 'delvetalk-bend-view-v1'},
            'viewPanels': [{'id': 'glow', 'label': 'Its light'}]},
            'state': {}, 'version': 3, 'law': ['visitor']}
        self.objects = {'index': self.parent, 'lantern': self.lantern}
        self.write_world()
        p.save(self.directory / 'manifest.json', {'cafe': 'index', 'runtime': {'name': 'compiled', 'files': {}}})
        self.app = p.Portal(self.directory, public_origin='https://delvetalk.example')
        self.view_patch = patch.object(self.app, '_view', side_effect=observation)
        self.evaluation = self.view_patch.start()
        self.addCleanup(self.view_patch.stop)

    def write_world(self):
        p.save(self.directory / 'world.json', {'objects': self.objects, 'receipts': []})

    def test_child_read_is_fresh_separate_and_keeps_parent_capture_exact(self):
        parent = self.app.object('index')
        self.assertEqual(parent['children'], [self.descriptor])
        self.assertEqual(parent['actions'], [])
        self.assertEqual(self.evaluation.call_count, 1)  # No recursive graph reads.
        first = self.app.child(parent['card'], 'lamp & one')
        card = first['card']
        self.assertEqual(first['status'], 'opened')
        self.assertEqual(first['navigation']['card'], parent['card'])
        self.assertNotEqual(card['card'], parent['card'])
        self.assertEqual((card['object'], card['panel'], card['version']), ('lantern', 'glow', 3))
        self.lantern['version'] = 4
        self.lantern['protocol']['name'] = 'A changed lantern'
        self.parent['state']['exhibits'] = []  # Membership removal does not revoke the old reference.
        self.write_world()
        before = (self.directory / 'world.json').read_bytes()
        fresh = self.app.child(parent['card'], 'lamp & one')['card']
        self.assertEqual((fresh['version'], fresh['title']), (4, 'A changed lantern'))
        self.assertEqual(self.app.card(parent['card']), parent)
        self.assertEqual(self.app.card(card['card']), card)
        prepared = self.app.prepare({'card': fresh['card'], 'action': 'a1'})
        self.assertEqual(prepared['wire']['expected'], self.lantern)
        self.assertEqual(prepared['wire']['object'], 'lantern')
        self.assertEqual(prepared['wire']['expected']['law'], ['visitor'])
        self.assertNotIn('principal', prepared['wire'])
        self.assertEqual((self.directory / 'world.json').read_bytes(), before)
        self.assertFalse((self.directory / 'portal-custody').exists())

    def test_unavailable_children_do_not_replace_or_repair_parent(self):
        parent = self.app.object('index')
        for mutation in ('missing', 'undeclared', 'failed-view'):
            self.objects = {'index': self.parent, 'lantern': copy.deepcopy(self.lantern)}
            if mutation == 'missing': del self.objects['lantern']
            if mutation == 'undeclared': self.objects['lantern']['protocol']['viewPanels'] = []
            self.write_world()
            before = (self.directory / 'world.json').read_bytes()
            captures = len(self.app.preview.records)
            if mutation == 'failed-view':
                with patch.object(self.app, '_view', return_value={'mode': 'raw'}):
                    result = self.app.child(parent['card'], 'lamp & one')
            else: result = self.app.child(parent['card'], 'lamp & one')
            self.assertEqual(result['status'], 'unavailable', result)
            self.assertNotIn('card', result)
            self.assertEqual(len(self.app.preview.records), captures)
            self.assertEqual(self.app.card(parent['card']), parent)
            self.assertEqual((self.directory / 'world.json').read_bytes(), before)

    def test_forged_retained_children_and_unknown_keys_refuse_before_child_read(self):
        parent = self.app.object('index')
        calls = self.evaluation.call_count
        with self.assertRaisesRegex(ValueError, 'unknown captured child'):
            self.app.child(parent['card'], 'not-offered')
        saved = self.app._read('cards', parent['card'])
        saved['view']['children'][0]['object'] = 'forged'
        identity = self.app._store('cards', saved)
        with self.assertRaisesRegex(ValueError, 'differs from its raw'):
            self.app.card(identity)
        with self.assertRaisesRegex(ValueError, 'differs from its raw'):
            self.app.child(identity, 'lamp & one')
        self.assertEqual(self.evaluation.call_count, calls)

    def test_duplicate_catalogue_refuses_capture_instead_of_truncating(self):
        self.parent['state']['exhibits'].append(copy.deepcopy(self.descriptor))
        self.write_world()
        with self.assertRaisesRegex(ValueError, 'duplicate child key'):
            self.app.object('index')
        self.assertEqual(len(self.app.preview.records), 0)

    def test_failed_typed_overview_keeps_exact_inspection_without_child_links(self):
        parent = self.app.object('index')
        self.lantern['protocol']['viewProgram'] = {'profile': p.bootstrap.projection.DATA_MENU_PROFILE}
        self.write_world()
        self.view_patch.stop()
        failed_projection = Mock()
        failed_projection.project.side_effect = ValueError('source view budget exhausted')
        before = (self.directory / 'world.json').read_bytes()
        with patch.object(p.bootstrap.room, 'module', return_value=failed_projection):
            overview = self.app.object('lantern')
            self.assertEqual(overview['mode'], 'raw')
            self.assertEqual(overview['children'], [])
            self.assertEqual(overview['actions'], [])
            self.assertIn('source view budget exhausted', overview['prose'])
            self.assertEqual(self.app.card(overview['card']), overview)
            details = self.app.detail(overview['card'])
            self.assertEqual(details['root'], self.lantern)
            self.assertEqual(details['state'], self.lantern['state'])
            self.assertEqual(details['source']['program'], self.lantern['protocol']['viewProgram'])
            self.assertIn('source view budget exhausted', self.app._read('cards', overview['card'])['view']['reason'])
            # Even injected children on a raw fallback are never displayed or followed.
            saved = self.app._read('cards', overview['card'])
            saved['view']['children'] = [self.descriptor]
            forged = self.app._store('cards', saved)
            self.assertEqual(self.app.card(forged)['children'], [])
            with self.assertRaisesRegex(ValueError, 'unknown captured child'):
                self.app.child(forged, self.descriptor['key'])
            navigation = self.app.child(parent['card'], self.descriptor['key'])
            self.assertEqual(navigation['status'], 'unavailable')
            self.assertNotIn('card', navigation)
        self.assertEqual((self.directory / 'world.json').read_bytes(), before)
        self.assertFalse((self.directory / 'portal-custody').exists())

    def test_native_typed_catalogue_reaches_child_under_its_own_law(self):
        from conformance.test_obend_data_object import SOURCE
        import translate
        import world
        self.view_patch.stop()
        directory = self.directory / 'native'
        directory.mkdir()
        database = directory / 'world.json'
        protocol = translate.translate('objective-bend-spell@3', SOURCE.encode())['lowered']
        child = {'profile': 'delvetalk-local-v1', 'name': 'A real lantern',
            'initial': {'lit': False}, 'commands': {'touch': {'require': [],
                'set': {'lit': ['literal', True]}, 'result': ['literal', 'Lit'], 'outbox': []}},
            'affordances': {'touch': {'label': 'Touch the light', 'fields': {}}}}
        for identity, program, law in [('index', protocol, ['curator']), ('lantern', child, ['visitor'])]:
            reply = world.exchange(database, {'op': 'create', 'object': identity, 'principal': 'maker',
                'intent': 'create-' + identity, 'protocol': program, 'law': law}, profile='compiled')
            self.assertEqual(reply['kind'], 'committed', reply)
        index = p.loads(database.read_bytes())['objects']['index']
        added = world.exchange(database, {'op': 'invoke', 'object': 'index', 'principal': 'curator',
            'intent': 'exhibit-lantern', 'expected': index, 'command': 'add',
            'input': {'object': 'lantern'}}, profile='compiled')
        self.assertEqual(added['kind'], 'committed', added)
        p.save(directory / 'manifest.json', {'cafe': 'index', 'runtime': p.bootstrap.history.runtime('compiled')})
        app = p.Portal(directory, public_origin='https://delvetalk.example')
        before = database.read_bytes()
        parent = app.object('index')
        self.assertEqual(parent['children'], [{'key': 'lantern', 'label': 'An exhibit',
                                              'object': 'lantern', 'panel': 'main'}])
        result = app.child(parent['card'], 'lantern')
        self.assertEqual(result['status'], 'opened', result)
        captured = result['card']
        self.assertEqual(captured['title'], 'A real lantern')
        self.assertNotEqual(captured['card'], parent['card'])
        draft = app.prepare({'card': captured['card'], 'action': 'a1'})
        self.assertEqual(database.read_bytes(), before)
        # The test operator submits explicitly. The public portal never does.
        refused = world.exchange(database, {**draft['wire'], 'principal': 'curator',
            'intent': 'curator-cannot-touch'}, profile='compiled')
        self.assertEqual(refused['kind'], 'refused')
        admitted = world.exchange(database, {**draft['wire'], 'principal': 'visitor',
            'intent': 'visitor-can-touch'}, profile='compiled')
        self.assertEqual(admitted['kind'], 'committed', admitted)
        fresh = app.child(parent['card'], 'lantern')['card']
        self.assertEqual(fresh['version'], captured['version'] + 1)
        self.assertEqual(app.card(captured['card']), captured)
        self.assertEqual(app.card(parent['card']), parent)

    def test_http_child_route_has_same_origin_and_read_only_boundary(self):
        parent = self.app.object('index')
        server = p.make_server(self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown(); server.server_close(); thread.join()
        self.addCleanup(close)
        def get(origin):
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            try:
                client.request('GET', '/api/child?card=' + parent['card'] + '&key=lamp%20%26%20one',
                    headers={'Host': 'delvetalk.example', 'Origin': origin})
                response = client.getresponse()
                return response.status, json.loads(response.read())
            finally: client.close()
        before = (self.directory / 'world.json').read_bytes()
        self.assertEqual(get('https://elsewhere.example')[0], 403)
        status, result = get('https://delvetalk.example')
        self.assertEqual(status, 200)
        self.assertEqual(result['status'], 'opened')
        self.assertEqual(result['card']['object'], 'lantern')
        self.assertEqual((self.directory / 'world.json').read_bytes(), before)
