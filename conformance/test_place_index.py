"""Two authors exhibit source objects through real typed Bend and retained cards.

Only public repository GET transport is simulated. No builds or publication.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('index_town_helpers', ROOT / 'conformance/test_town_forge_journey.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
import continuation
import source_object
import source_offers
import source_store
import translate
import workspace

PACKAGE = ROOT / 'protocols/place-index'
A, B = helpers.VISITOR, helpers.MAKER


def modules():
    return [{'name': 'Abi', 'source': (ROOT / 'world/lib/prelude/Abi.obend').read_text()},
            {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Encounter', 'source': (ROOT / 'world/lib/prelude/Encounter.obend').read_text()}] + [{'name': name, 'source': (PACKAGE / (name + '.obend')).read_text()}
            for name in ('ExhibitList', 'Main')]


def field(wire, name):
    assert wire['tag'] == 'record'
    return next(item['value'] for item in wire['fields'] if item['name'] == name)


def entries(root):
    """Test-only decoding of typed evidence, never execution or view construction."""
    values, cursor = [], field(root['state']['model'], 'entries')
    while cursor['label'] == 'cons':
        row = field(cursor['payload'], 'head')
        values.append({key: field(row, key)['value'] for key in
                       ('object', 'label', 'addedBy', 'observedVersion')})
        cursor = field(cursor['payload'], 'tail')
    assert cursor == {'tag': 'variant', 'label': 'nil', 'payload': {'tag': 'record', 'fields': []}}
    return values


class PlaceIndexAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adapter = helpers.clerk.module('place_admission_adapter', 'syntaxes/obend_object.py')
        cls.protocol = adapter.lower_data_modules(modules())

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / 'world.json'
        self.serial = 0
        self.law = {'profile': 'delvetalk-scoped-law-v1',
                    'invoke': {n: [B] for n in ('add', 'caption', 'remove', 'reorder')},
                    'reprogram': [B], 'law': [B]}
        self.call({'op': 'create', 'object': 'index', 'protocol': self.protocol, 'law': self.law})
        peer = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'fake': {'require': [], 'set': {},
                     'result': ['record', {'object': ['literal', 'peer'], 'version': ['literal', 0]}],
                     'outbox': []}}}
        self.call({'op': 'create', 'object': 'peer', 'protocol': peer, 'law': [B]})

    def call(self, request, kind='committed', who=B):
        self.serial += 1
        reply = helpers.clerk.world.exchange(self.database,
            {'principal': who, 'intent': str(self.serial), **request}, profile='compiled')
        if request.get('op') != 'inspect':
            self.assertEqual(reply['kind'], kind, reply)
        return reply

    def root(self, object_id='index'):
        return self.call({'op': 'inspect', 'object': object_id})

    def invoke(self, command, values, kind='committed', who=B):
        return self.call({'op': 'invoke', 'object': 'index', 'expected': self.root(),
                         'command': command, 'input': values}, kind, who)

    def add(self, kind='committed', calls=None, reads=None):
        return self.call({'op': 'transaction', 'reads': reads or {'index': self.root(), 'peer': self.root('peer')},
            'calls': calls or [{'op': 'observe', 'object': 'peer'},
                              {'object': 'index', 'command': 'add', 'inputFrom': 0}]}, kind)

    def test_witness_kind_identity_adjacency_current_law_and_atomic_failure(self):
        before = self.root()
        self.invoke('add', {'object': 'peer', 'version': 0}, 'refused')
        self.add('refused', calls=[{'object': 'peer', 'command': 'fake', 'input': {}},
                                  {'object': 'index', 'command': 'add', 'inputFrom': 0}])
        self.add('refused', calls=[{'op': 'observe', 'object': 'peer'},
                                  {'object': 'peer', 'command': 'fake', 'input': {}},
                                  {'object': 'index', 'command': 'add', 'inputFrom': 0}])
        self.add('refused', calls=[{'op': 'observe', 'object': 'peer'},
                                  {'object': 'index', 'command': 'add', 'inputFrom': 0},
                                  {'object': 'index', 'command': 'remove', 'input': {'object': 'missing'}}])
        self.assertEqual(self.root(), before)
        stale_peer = self.root('peer')
        self.call({'op': 'invoke', 'object': 'peer', 'command': 'fake', 'expected': stale_peer, 'input': {}})
        self.add('refused', reads={'index': self.root(), 'peer': stale_peer})
        self.add()
        self.assertEqual(entries(self.root())[0]['observedVersion'], '1')
        self.add('refused')
        self.invoke('caption', {'object': 'peer', 'label': 'Something to see'}, who=A, kind='refused')
        self.invoke('reorder', {'object': 'peer', 'before': 'peer'}, 'refused')
        self.invoke('reorder', {'object': 'peer', 'before': 'missing'}, 'refused')
        self.invoke('reorder', {'object': 'peer', 'before': ''})
        self.invoke('remove', {'object': 'missing'}, 'refused')

    def test_missing_observation_and_target_independent_removal(self):
        self.call({'op': 'transaction', 'reads': {'index': self.root(), 'absent': None},
            'calls': [{'op': 'observe', 'object': 'absent'},
                      {'object': 'index', 'command': 'add', 'inputFrom': 0}]}, 'refused')
        self.add()
        # Isolated fixture models an unavailable target; this is not a host delete API.
        snapshot = helpers.clerk.loads(self.database.read_bytes())
        del snapshot['objects']['peer']
        self.database.write_bytes(helpers.clerk.canonical(snapshot))
        self.invoke('remove', {'object': 'peer'})
        self.assertEqual(entries(self.root()), [])

    def test_bound_and_bad_variant_refuse_without_partial_update(self):
        natural = lambda n: {'tag': 'natural', 'value': str(n)}
        label = lambda s: {'tag': 'label', 'value': s}
        record = lambda fields: {'tag': 'record', 'fields': [{'name': k, 'value': v} for k,v in fields.items()]}
        tail = {'tag': 'variant', 'label': 'nil', 'payload': record({})}
        for i in reversed(range(32)):
            row = record({'object': label('fixture-' + str(i)), 'label': label('Exhibit'),
                          'addedBy': label(B), 'observedVersion': natural(0)})
            tail = {'tag': 'variant', 'label': 'cons', 'payload': record({'head': row, 'tail': tail})}
        full = {'model': record({'entries': tail})}
        # Seed only this isolated boundary fixture: duplicating source in reprogram
        # plus the 32-row model exceeds the normal 64 KiB request envelope.
        snapshot = helpers.clerk.loads(self.database.read_bytes())
        snapshot['objects']['index']['state'] = full
        self.database.write_bytes(helpers.clerk.canonical(snapshot))
        before = self.root()
        self.add('refused')
        self.assertEqual(self.root(), before)
        bad = {'model': record({'entries': {'tag': 'variant', 'label': 'surprise', 'payload': record({})}})}
        snapshot = helpers.clerk.loads(self.database.read_bytes())
        snapshot['objects']['index']['state'] = bad
        self.database.write_bytes(helpers.clerk.canonical(snapshot))
        before = self.root()
        self.invoke('remove', {'object': 'peer'}, 'refused')
        self.assertEqual(self.root(), before)


class PlaceIndexJourney(helpers.TownForgeJourneyTests):
    test_maker_checks_installs_and_revises_a_door_visitors_can_use = None

    def setUp(self):
        original_build, original_law = helpers.forge.build_stateful, helpers.forge.factory_law
        def configured(visitors, compiler):
            initial = translate.translate('objective-bend-spell@2',
                (ROOT / 'syntaxes/examples/lantern.obend').read_bytes())['lowered']
            factories = original_build([A, B], compiler,
                methods=['add', 'caption', 'remove', 'reorder', 'light', 'douse'],
                initial_program=initial)
            source_desks = helpers.clerk.module('place_index_source_desks', 'protocols/source-desk/package.py')
            factories['desks'] = source_desks.factory(compiler, [A, B])
            writing_modules = source_object.read_modules([
                ('List', ROOT / 'world/lib/prelude/List.obend'), ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
                ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
                ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
                ('ExhibitWriting', PACKAGE / 'ExhibitWriting.obend')])
            for name in ('first-lantern', 'second-lantern'):
                factories['exhibit-' + name] = source_object.load(writing_modules,
                    syntax='objective-bend-spell@3', constructor='initial',
                    arguments=[source_object.data({'index': 'objects/exhibition',
                                                  'target': 'objects/' + name})])
            return factories
        with patch.object(helpers.forge, 'build', side_effect=configured), patch.object(
                helpers.forge, 'factory_law', side_effect=lambda makers: original_law([A, B])):
            super().setUp()

    def allocate(self, factory, name, author=B):
        _, response = self.reply(self.capture(factory), {'name': name}, author=author)
        self.committed(response)
        object_id = factory + '/' + name
        self.assertIn(object_id, self.clerk.config()['objects'])
        return object_id

    def interpreted(self, request, author=B, text='Please do this with the objects we just looked at.'):
        self.sequence += 1
        uri = f'at://{author}/{helpers.clerk.FEED}/intention-{self.sequence}'
        cid = 'intent-cid-' + str(self.sequence)
        self.pds.records[uri] = (cid, {'$type': helpers.clerk.FEED, 'text': text})
        decision = {'status': 'act', 'interpreter': 'place journey operator',
                    'basis': text, 'request': copy.deepcopy(request)}
        response = self.operator.receive(uri, cid, interpretation=decision)
        return (uri, cid), response

    def command(self, object_id, command, data, author=B):
        return self.interpreted({'object': object_id, 'command': command,
            'expected': self.root(object_id), 'input': data}, author=author)[1]

    def sealed_post(self, module, author):
        self.sequence += 1
        uri = f'at://{author}/{helpers.clerk.FEED}/source-{self.sequence}'
        cid = 'source-cid-' + str(self.sequence)
        record = {'$type': helpers.clerk.FEED, 'text': module['source']}
        self.pds.records[uri] = (cid, record)
        self.clerk.verify_repository(author)
        fetched = self.clerk.fetch_record(uri, cid, (helpers.clerk.FEED,))
        self.assertEqual(fetched, record)
        helpers.clerk.save(self.base / 'authored-posts' / (cid + '.json'),
                           {'source': {'uri': uri, 'cid': cid, 'author': author}, 'record': fetched})
        return {'name': module['name'], 'sourceRef': source_store.store_bytes(
            self.home / 'artifacts', fetched['text'].encode(), kind='source')}

    def install(self, target, package, author, syntax, examples, migration, name):
        refs = [self.sealed_post(m, A if m['name'] == 'ExhibitList' else author) for m in package]
        proposal = source_store.prepare_module_proposal(self.home / 'artifacts',
            source_store.seal_modules(refs), examples, syntax=syntax)
        candidate = self.allocate('desks', name, author)
        submission, response = self.interpreted({'object': candidate, 'command': 'submit',
            'expected': self.root(candidate), 'input': {'proposal': proposal,
                'migration': migration, 'target': target}}, author=author,
            text='Assemble these exact ordered peer modules and install them here after checking.')
        self.committed(response)
        checked = self.check(candidate, submission)
        self.assertEqual(checked['status'], 'ready', checked)
        card = checked['cards'][0]
        _, adopted = self.reply(card, {}, author=author)
        self.committed(adopted)
        return refs, candidate

    def child(self, parent, key):
        selected = self.operator.capture_child(parent['alias'], key)
        self.assertEqual(selected['status'], 'prepared', selected)
        self.assertNotEqual(selected['card']['alias'], parent['alias'])
        return selected['card']

    def use(self, card, command, author=A):
        action = next(item['id'] for item in card['card']['actions'] if item['command'] == command)
        _, result = self.reply(card, {}, author=author, action=action)
        return result

    def exhibit(self, index, target, label):
        self.assertEqual(index, 'objects/exhibition')
        card = self.capture('exhibit-' + target.rsplit('/', 1)[-1])
        publication = self.publish([card])
        before_index, before_target = self.root(index), self.root(target)
        _, denied = self.reply(card, {'label': label}, author=A, parent=publication)
        self.assertEqual(denied['receipt']['reply']['kind'], 'refused')
        self.assertEqual(self.root(index), before_index)
        self.assertEqual(self.root(target), before_target)
        _, response = self.reply(card, {'label': label}, author=B, parent=publication)
        self.committed(response)
        self.assertEqual(response['receipt']['request']['op'], 'transaction')
        return response

    def test_two_authors_discover_revise_remove_and_restore_real_list(self):
        package = modules()
        adapter = helpers.clerk.module('place_index_adapter', 'syntaxes/obend_object.py')
        lowered = adapter.lower_data_modules(package)
        index = self.allocate('objects', 'exhibition', B)
        refs, candidate = self.install(index, package, B, 'objective-bend-spell@3',
            (PACKAGE / 'index.examples').read_bytes(), lowered['initial'], 'index-source')
        self.assertEqual(entries(self.root(index)), [])
        # B curates; A may visit the list without acquiring curation rights.
        current = self.root(index)
        authority = copy.deepcopy(current['law'])
        authority['invoke'] = {command: [B] for command in ('add', 'caption', 'remove', 'reorder')}
        changed = helpers.clerk.world.exchange(self.clerk.database, {'op': 'law', 'object': index, 'principal': B,
            'intent': 'index-curator-law', 'expected': current, 'law': authority}, profile='compiled')
        self.assertEqual(changed['kind'], 'committed', changed)
        base_source = (ROOT / 'syntaxes/examples/lantern.obend').read_text()
        first, second = self.allocate('objects', 'first-lantern', A), self.allocate('objects', 'second-lantern', B)
        empty_examples = b'examples DelveTalk 1\ncase the light answers\nlaw visitor\nas visitor\nsend light\nexpect result: A small sun for lost moths.\n'
        self.install(first, [{'name': 'Main', 'source': base_source}], A,
            'objective-bend-spell@2', empty_examples, {'lit': False}, 'first-source')
        second_source = base_source.replace('Moth lantern', 'Evening lantern')
        self.install(second, [{'name': 'Main', 'source': second_source}], B,
            'objective-bend-spell@2', empty_examples, {'lit': False}, 'second-source')
        self.exhibit(index, first, 'A lantern from Iris')
        self.exhibit(index, second, 'A lantern from Moss')
        rows = entries(self.root(index))
        self.assertEqual([r['object'] for r in rows], [first, second])
        self.assertTrue(all(r['addedBy'] == B for r in rows))
        parent = self.capture(index)
        self.assertEqual([child['label'] for child in parent['view']['children']],
                         ['A lantern from Iris', 'A lantern from Moss'])
        self.assertIn('A lantern from Iris', parent['body'])
        self.committed(self.use(self.child(parent, parent['view']['children'][0]['key']), 'light', A))
        self.committed(self.use(self.child(parent, parent['view']['children'][1]['key']), 'light', A))
        stale_child = self.child(parent, first)
        revised_source = base_source.replace('Moth lantern', 'A lantern full of moons')
        revised_source = revised_source.replace('The moths dream.', 'The moons dream.')
        revision_examples = b'examples DelveTalk 1\ncase revised light\nlaw visitor\nas visitor\nsend light\nexpect result: A small sun for lost moths.\n'
        self.install(first, [{'name': 'Main', 'source': revised_source}], A,
            'objective-bend-spell@2', revision_examples, {'lit': True}, 'revised-source')
        stale = self.use(stale_child, 'douse', A)
        self.assertEqual(stale['receipt']['reply']['kind'], 'refused')
        fresh = self.child(parent, first)
        self.assertEqual(fresh['card']['title'], 'A lantern full of moons')
        result = self.use(fresh, 'douse', A)
        self.committed(result)
        self.assertEqual(result['receipt']['reply']['data']['result'], 'The moons dream.')
        self.committed(self.command(index, 'reorder', {'object': second, 'before': first}))
        self.assertEqual([r['object'] for r in entries(self.root(index))], [second, first])
        self.committed(self.command(index, 'remove', {'object': first}))
        current_parent = self.capture(index)
        self.assertEqual([c['object'] for c in current_parent['view']['children']], [second])
        denied = self.command(index, 'remove', {'object': second}, A)
        self.assertEqual(denied['receipt']['reply']['kind'], 'refused')
        # Full custody, typed model and both independent peer source histories restore.
        bundle, restored = self.base / 'history', self.base / 'restored'
        exported = workspace.bootstrap.export_bootstrap(self.home, bundle)
        continuation.prepare(bundle, self.base / 'continuation',
            expected_genesis=exported['genesis'], expected_head=exported['head'])
        workspace.bootstrap.restore_bootstrap(bundle, restored,
            expected_genesis=exported['genesis'], expected_head=exported['head'])
        restored_world = helpers.clerk.loads((restored / 'world.json').read_bytes())
        self.assertEqual(restored_world, helpers.clerk.loads(self.clerk.database.read_bytes()))
        for ref in refs:
            self.assertEqual(source_store.read_bytes(restored / 'artifacts', ref['sourceRef'], kind='source'),
                             source_store.read_bytes(self.home / 'artifacts', ref['sourceRef'], kind='source'))
        recovered = helpers.compiler_queue.desk.Desk(restored / 'world.json', restored / 'artifacts', profile='compiled')
        root = recovered.inspect(index)
        self.assertEqual([r['object'] for r in entries(root)], [second])
        view = workspace.bootstrap.room.inspect_object(root, index,
            expected_runtime=workspace.bootstrap.history.runtime('compiled'))
        self.assertEqual([c['object'] for c in view['children']], [second])
        child_root = recovered.inspect(second)
        child_view = workspace.bootstrap.room.inspect_object(child_root, second,
            expected_runtime=workspace.bootstrap.history.runtime('compiled'))
        command = workspace.bootstrap.room.view_request(child_view, 'douse', A, 'restored-douse')
        self.assertEqual(recovered.exchange(command)['kind'], 'committed')
        writer = 'exhibit-' + first.rsplit('/', 1)[-1]
        captured = helpers.clerk.world.capture_roots(recovered.database, [writer, index, first],
                                                     principal=B, profile='compiled')
        writer_view = workspace.bootstrap.room.inspect_object(captured['roots'][writer]['root'], writer,
            expected_runtime=workspace.bootstrap.history.runtime('compiled'))
        invitation = source_offers.capture(writer_view,
            {name: pair['root'] for name, pair in captured['roots'].items()},
            references={name: pair['reference'] for name, pair in captured['roots'].items()})['exhibit']
        request = source_offers.request(invitation, B, 'restore-add',
            {'label': 'Returned moon lantern'}, database=recovered.database)
        self.assertEqual(recovered.exchange(request)['kind'], 'committed')
        self.assertEqual([r['object'] for r in entries(recovered.inspect(index))], [second, first])


if __name__ == '__main__':
    unittest.main()
