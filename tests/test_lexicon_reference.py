"""Reference checks: malformed documents, invalid wire values and every emitted GSB shape refute these tests."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from transport.lexicon import DIR, reference_problems

SCRIPT = Path(__file__).with_name('lexicon_reference.mjs')


class ReferenceCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, unavailable, _ = reference_problems()
        if unavailable:
            raise unittest.SkipTest('reference validator unavailable: ' + unavailable)

    def check(self, samples=(), directory=DIR):
        result = subprocess.run(['node', str(SCRIPT), str(directory)],
                                input=json.dumps(samples), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)


class Reference(ReferenceCheck):
    def test_normal_node_resolution_finds_the_package_from_the_callers_directory(self):
        package = os.environ.get('ATPROTO_LEXICON_PACKAGE')
        if not package:
            self.skipTest('ATPROTO_LEXICON_PACKAGE supplies the installed package for the cwd resolution fixture')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / 'node_modules' / '@atproto'
            modules.mkdir(parents=True)
            (modules / 'lexicon').symlink_to(Path(package).resolve(), target_is_directory=True)
            env = dict(os.environ)
            env.pop('ATPROTO_LEXICON_PACKAGE', None)
            result = subprocess.run(['node', str(SCRIPT.resolve()), str(DIR)], input='[]',
                                    capture_output=True, text=True, cwd=root, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['validator'], '@atproto/lexicon 0.7.16')

    def test_every_file_passes_the_reference_document_schema_and_collection(self):
        report = self.check()
        self.assertEqual(report['validator'], '@atproto/lexicon 0.7.16')
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(report['files']), len(list(DIR.rglob('*.json'))))

    def test_publication_records_pass_assert_valid_record(self):
        from transport.lexicons import records, COLLECTION
        self.check([{'kind': 'record', 'nsid': COLLECTION, 'value': value, 'label': nsid}
                    for (_, nsid), value in records().items()])

    def test_invalid_document_and_unresolved_reference_are_reported_per_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = [('bad', {'main': {'type': 'ref', 'ref': '#missing'}}),
                    ('dangling', {'main': {'type': 'object', 'properties': {
                        'target': {'type': 'ref', 'ref': 'online.fg-goose.gsb.absent'}}}})]
            for name, defs in docs:
                (root / (name + '.json')).write_text(json.dumps({
                    'lexicon': 1, 'id': 'online.fg-goose.gsb.' + name, 'defs': defs}))
            result = subprocess.run(['node', str(SCRIPT), directory], input='[]', capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            errors = json.loads(result.stdout)['errors']
            self.assertTrue(any('bad.json' in error for error in errors))
            self.assertTrue(any('dangling' in error and 'absent' in error for error in errors))


class EmittedShapes(ReferenceCheck):
    """Reuse the pure-Python host fixtures, never start or build a Lean process."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            import cryptography  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('cryptography is required by the transport code paths')

    def samples(self, root):
        from tests.test_xrpc_acts import ActsWorld, DID
        from tests.test_xrpc_sessions import SessionsWorld
        from tests.test_repo import World, ProjectionWorld
        from tests.test_requests import request
        from tests.wire import record, label
        from transport import bridge, mirror, sessions
        from transport.host import place
        from transport.repo import Repo, NS
        from transport.atproto.cbor import block
        from transport.atproto.sign import Key
        from transport.state import State
        from transport.config import Config

        samples = []
        def add(kind, nsid, value, label=None):
            samples.append({'kind': kind, 'nsid': NS + nsid, 'value': value, 'label': label or nsid + ':' + kind})
        def emitted(value, label=None):
            add('record', value['$type'].removeprefix(NS), value, label)

        cid = str(block({'example': True})[0])
        world = ActsWorld()
        turn = {'op': 'world-turn', 'principal': DID, 'object': 'diary', 'method': 'receive',
                'identity': 'reference', 'argument': record(text=label('hello'))}
        reply = world.send(turn)
        view = bridge.caller_view(reply)
        preview = bridge.caller_view(world.send({**turn, 'op': 'world-try'}), preview=True)
        for proc in ('act', 'plan'):
            add('output', proc, view)
            add('output', proc, preview, proc + ':preview variant')
        add('output', 'try', preview)
        st = State(root, config=Config())
        obs = {'uri': f'at://{DID}/{NS}request/3aaaaaaaaaaa2', 'cid': cid}
        for source in (bridge.request_source(obs), bridge.xrpc_source(DID, '🪿' * 64)):
            bridge.write_answer(st, source, view)
            emitted(json.loads(bridge.answer_path(st, source).read_text()), source['$type'])
        # Batch replies exercise nested turn views and positive maximum journal positions.
        batch = bridge.caller_view({'status': 'spells', 'turns': [reply] * 4})
        add('output', 'act', batch, 'four turn answer')
        bridge.write_answer(st, bridge.xrpc_source(DID, 'batch'), batch)
        emitted(json.loads(bridge.answer_path(st, bridge.xrpc_source(DID, 'batch')).read_text()))

        home = SessionsWorld()
        add('input', 'openSession', {'name': 'a' * 32, 'from': {'world': 'town', 'height': 1}})
        opened = sessions.opened(home, DID, {'name': 'lab'})
        add('output', 'openSession', opened)
        scratch = home.at('scratch/lab')
        add('params', 'getSession', {'session': 'scratch/lab'})
        add('output', 'getSession', sessions.get_session(home, scratch, DID, 'scratch/lab'))
        # Actual mirror renderer with nonempty wants/doors and cached paint as well as exact card bytes.
        here = place(scratch, DID, 'diary', paint=False)
        here.update(paint='painted 🪿', wants=[{'object': 'diary', 'want': 'hello'}],
                    doors=[{'label': 'outside', 'to': {'object': 'gate'}}])
        with patch.object(mirror, 'place', return_value=here):
            card = mirror.card_record(scratch, 'diary', DID)
        emitted(card)
        pages = [{'name': 'guide', 'kind': 'page', 'title': 'Guide', 'body': '🪿' * 4096, 'place': 0}]
        emitted(mirror.page_record(pages[0]))
        emitted(mirror.index_record({'diary': 0}, pages, 7))
        emitted(mirror.index_record({'diary': 0}, pages, 7, 8), 'incoherent index')
        emitted(mirror.checkpoint_record('did:web:gsb.example', '3aaaaaaaaaaa2', cid, (1 << 53) - 1))
        # The actual signed entry record is decoded by the facade, including its IPLD link.
        signed_world = World()
        signed_world.append(DID, 'reference entry')
        repo = Repo('https://gsb.example', Key.generate(), ledger=st.repo_ledger)
        repo.head(signed_world, {}, None)
        emitted(repo.signed_record(1)['value'])
        add('params', 'getEntry', {'entry': signed_world.entries[0]['hash']})
        add('output', 'getEntry', {'$bytes': 'AA=='}, 'CAR has no Lexicon output schema')
        for collection in ('card', 'entry'):
            query = {'session': 'scratch/lab', 'collection': NS + collection, 'limit': 100}
            add('params', 'listSessionRecords', query)
            if collection == 'entry':
                scratch.send(turn)
            listed = sessions.list_records(scratch, DID, {**query, 'limit': '100'})
            add('output', 'listSessionRecords', listed, collection + ' session listing')
            for row in listed['records']:
                emitted(row['value'])

        # Render every untagged host projection kind through the existing facade fixture.
        projection_world = ProjectionWorld()
        facade = Repo('https://gsb.example')
        for kind in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
            listed = facade.list_projections(projection_world, {'kind': kind, 'limit': '100'}, DID)
            add('params', 'listProjections', {'kind': kind, 'limit': 100, 'reverse': False})
            add('output', 'listProjections', listed, kind + ' projection listing')
            for projection in listed['projections']:
                add('output', 'getProjection', projection, kind + ' projection')
                add('object', 'getProjection#' + kind, projection['value'], kind + ' subject')
        for value in (card, mirror.page_record(pages[0]), mirror.index_record({'diary': 0}, pages, 7)):
            projection = facade.projection(None, value['$type'].removeprefix(NS), 'self', None, value)
            add('output', 'getProjection', projection)
            add('output', 'listProjections', {'projections': [projection]})
        add('params', 'getProjection', {'kind': 'card', 'key': 'diary', 'cid': cid})
        emitted(request('hello', witnessPost={'uri': f'at://{DID}/{NS}request/3aaaaaaaaaaa2', 'cid': cid}))
        # Planned paint has no writer yet, but its published record schema still receives a boundary sample.
        emitted({'$type': NS + 'paint', 'object': 'x' * 128, 'version': 0,
                 'card': {'uri': f'at://{DID}/{NS}card/diary', 'cid': cid}, 'text': '🪿' * 1000})
        pin = {'object': 'x' * 128, 'version': 0, 'cid': cid}
        emitted(request('🪿' * 1024, mode='plan', calls=[{'spell': '🪿' * 1024}] * 8, **{'if': [pin] * 16}),
                'maximum request calls, pins and spell bytes')
        for proc in ('act', 'try'):
            add('input', proc, {'call': {'spell': '🪿' * 1024}, 'intent': '🪿' * 64, 'if': [pin] * 16})
            add('input', proc, {'call': {'object': 'x' * 128, 'verb': 'v' * 128, 'fields': {'value': 1}},
                                'intent': 'one'})
        add('input', 'plan', {'calls': [{'spell': '🪿' * 1024}] * 8, 'intent': '🪿' * 64, 'if': [pin] * 16})
        return samples

    def test_actual_records_projections_and_xrpc_values_pass_reference_methods(self):
        with tempfile.TemporaryDirectory() as root:
            samples = self.samples(root)
            self.check(samples)
        from transport.lexicon import DOCS
        record_ids = {nsid for nsid, doc in DOCS.items() if doc['defs'].get('main', {}).get('type') == 'record'}
        self.assertEqual({s['nsid'] for s in samples if s['kind'] == 'record'}, record_ids)
        for nsid, doc in DOCS.items():
            main = doc['defs'].get('main', {})
            for kind, field in (('params', 'parameters'), ('input', 'input'), ('output', 'output')):
                if field in main:
                    self.assertTrue(any(s['nsid'] == nsid and s['kind'] == kind for s in samples), (nsid, kind))

    def test_reference_rejects_adversarial_samples_and_overlong_wire_values(self):
        from transport.repo import NS
        samples = [
            {'kind': 'record', 'nsid': NS + 'entry', 'value': {'$type': NS + 'entry', 'height': 1, 'entry': {'$link': 'bafy'}}},
            {'kind': 'params', 'nsid': NS + 'listSessionRecords', 'value': {
                'session': 'scratch/lab', 'collection': NS + 'card', 'limit': 101}},
            {'kind': 'input', 'nsid': NS + 'act', 'value': {'call': {'spell': '🪿' * 1025}, 'intent': 'one'}},
            {'kind': 'input', 'nsid': NS + 'plan', 'value': {'calls': [{'spell': 'hi'}] * 9, 'intent': 'one'}},
            {'kind': 'input', 'nsid': NS + 'openSession', 'value': {'name': 'a' * 33}},
            {'kind': 'output', 'nsid': NS + 'act', 'value': {'$type': NS + 'defs#previewView', 'outcome': {'status': 'admitted', 'line': 'bad'}}},
            {'kind': 'record', 'nsid': NS + 'answer', 'value': {'$type': NS + 'answer', 'source': {'$type': NS + 'answer#bogus'},
                                                           'outcome': {'status': 'admitted', 'line': 'bad'}}},
            {'kind': 'record', 'nsid': NS + 'request', 'value': {'$type': NS + 'request', 'service': 'did:web:gsb.example',
                                                             'mode': 'act', 'calls': [], 'createdAt': '2026-10-13T12:00:00Z'}},
            {'kind': 'output', 'nsid': NS + 'getSession', 'value': {'session': 'scratch/lab', 'status': 'world', 'expires': True}},
            {'kind': 'output', 'nsid': NS + 'listProjections', 'value': {'projections': [{'kind': 'not-a-kind', 'key': 'x', 'value': {}}]}},
            {'kind': 'output', 'nsid': NS + 'listSessionRecords', 'value': {'records': [{'key': 'x', 'value': {}}]}},
        ]
        result = subprocess.run(['node', str(SCRIPT), str(DIR)], input=json.dumps(samples), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['errors']), len(samples))


if __name__ == '__main__':
    unittest.main()
