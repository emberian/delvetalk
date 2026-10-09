"""Actual Lean authoring lifecycle, authority separation and retained uncertainty."""
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal
import desk
import worker


def law(invoke=None, reprogram=None):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': invoke or {},
            'reprogram': reprogram or [], 'law': ['owner']}


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.client = desk.Desk(self.path / 'world.json', self.path / 'artifacts')
        self.client.create('candidate', 'owner', 'seed-desk', law({
            'submit': ['author'], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['reviewer', 'author']}))
        self.source = (ROOT / 'protocols/counter/protocol.json').read_text()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_text()
        self.client.exchange({'op': 'create', 'object': 'target', 'principal': 'owner', 'intent': 'seed-target',
            'protocol': desk.loads(self.source), 'law': law({'add': ['author']}, ['reviewer'])})
        desk.immutable(self.path / 'manifest.json', {'format': 'delvetalk-workspace-v1',
            'worldId': 'urn:test:authoring', 'title': 'An independent workshop', 'defaultObject': 'target', 'entryObjects': ['target', 'candidate'],
            'runtime': portal.bootstrap.history.runtime('transactions')})

    def app(self, principal=None):
        return portal.Portal(self.path, principal=principal, allow_local_actions=bool(principal))

    def submit(self, source=None):
        app = self.app('author').authoring
        src = app.source({'text': self.source if source is None else source})['source']
        scenarios = app.source({'text': self.scenarios, 'kind': 'scenarios'})['source']
        draft = app.prepare({'operation': 'submit', 'candidate': 'candidate', 'target': 'target',
            'syntax': 'protocol-json@1', 'source': src, 'scenarios': scenarios, 'migrationJson': '{"count":41}'})
        return app, draft

    def ready(self, source=None):
        author, draft = self.submit(source)
        self.assertEqual(author.execute({'draft': draft['draft']})['receipt']['kind'], 'committed')
        compiler = self.app('compiler').authoring
        build = compiler.prepare({'operation': 'compile', 'candidate': 'candidate'})
        queued = compiler.execute({'draft': build['draft']})
        self.assertEqual(queued['phase'], 'queued')
        result = compiler.run({'draft': build['draft']})
        self.assertEqual(result['phase'], 'finished', result)
        self.assertEqual(result['receipt']['kind'], 'committed', result)
        if source != '{ broken source':
            self.assertEqual(self.client.inspect('candidate')['state']['status'], 'ready', result)
        return compiler, build, result

    def test_large_source_full_lifecycle_restart_and_exact_adoption(self):
        # Valid source larger than the entire host wire. Only refs enter the desk.
        compiler, build, result = self.ready(self.source + ' ' * 100000)
        self.assertFalse(result['diagnostics'])
        restarted = self.app('compiler').authoring
        self.assertEqual(restarted.status(build['draft']), result)
        self.assertEqual(restarted.execute({'draft': build['draft']}), result)
        self.assertEqual(restarted.run({'draft': build['draft']}), result)
        reviewer = self.app('reviewer').authoring
        adoption = reviewer.prepare({'operation': 'adopt', 'candidate': 'candidate', 'target': 'target'})
        saved = reviewer._read(adoption['draft'])
        self.assertEqual(saved['request']['reads']['target'], self.client.inspect('target'))
        reply = reviewer.execute({'draft': adoption['draft']})
        self.assertEqual(reply['receipt']['kind'], 'committed', reply)
        self.assertEqual(self.client.inspect('target')['state'], {'count': 41})
        self.assertEqual(self.app('reviewer').authoring.execute({'draft': adoption['draft']}), reply)
        self.assertEqual(desk.loads(result['exactJson'])['receipt'], result['receipt'])
        self.assertEqual(self.app().world()['defaultObject'], 'target')
        self.assertEqual(self.app().world()['title'], 'An independent workshop')

    def test_finished_compile_receipt_survives_missing_or_tampered_build(self):
        compiler, build, completed = self.ready()
        path = compiler.artifacts / 'builds' / (completed['artifact'] + '.json')
        before = self.client.database.read_bytes()
        for corruption in ('missing', 'tampered'):
            if corruption == 'missing':
                path.unlink()
            else:
                path.write_bytes(b'{}')
            with self.subTest(corruption=corruption):
                restarted = self.app('compiler').authoring
                for operation in (lambda: restarted.status(build['draft']),
                                  lambda: restarted.execute({'draft': build['draft']}),
                                  lambda: restarted.run({'draft': build['draft']})):
                    recovered = operation()
                    self.assertEqual(recovered['phase'], 'finished')
                    self.assertEqual(recovered['receipt'], completed['receipt'])
                    self.assertEqual(recovered['artifactStatus'], 'unavailable')
                self.assertEqual(self.client.database.read_bytes(), before)

    def test_spween_upload_compile_adopt_exports_original_bridge(self):
        import workspace
        self.path = self.path / 'workshop'
        workspace.initialize(self.path, [
            {'id': 'candidate', 'syntax': 'protocol-json@1',
             'source': (ROOT / 'protocols/source-desk/protocol.json').read_bytes(),
             'law': law({'submit': ['author'], 'compiled': ['compiler'], 'failed': ['compiler'],
                         'adopt': ['reviewer']})},
            {'id': 'target', 'syntax': 'protocol-json@1', 'source': self.source.encode(),
             'law': law({}, ['reviewer'])}],
            entry_objects=['target', 'candidate'], principal='owner')
        self.client = desk.Desk(self.path / 'world.json', self.path / 'artifacts')
        source = '---\nid: garden\n---\n=== gate\nAn unclaimed path.\n* [Walk]\n  -> END\n'
        scenarios = desk.canonical([{'name': 'start', 'law': ['visitor'], 'steps': [
            {'principal': 'visitor', 'command': 'start', 'input': {},
             'root': 'initial', 'kind': 'committed'}]}]).decode()
        lowered = desk.translate.translate('spween-scene-i64@1', source.encode())
        author = self.app('author').authoring
        submission = author.prepare({'operation': 'submit', 'candidate': 'candidate', 'target': 'target',
            'syntax': 'spween-scene-i64@1', 'source': author.source({'text': source})['source'],
            'scenarios': author.source({'text': scenarios, 'kind': 'scenarios'})['source'],
            'migrationJson': desk.canonical(lowered['lowered']['protocol']['initial']).decode()})
        self.assertEqual(author.execute({'draft': submission['draft']})['receipt']['kind'], 'committed')
        compiler = self.app('compiler').authoring
        draft = compiler.prepare({'operation': 'compile', 'candidate': 'candidate'})
        compiler.execute({'draft': draft['draft']})
        completed = compiler.run({'draft': draft['draft']})
        self.assertEqual(completed['phase'], 'finished', completed)
        self.assertFalse(completed['diagnostics'], completed)
        build = desk.load_artifact(self.client.artifact_store, completed['artifact'])
        dependencies = desk.history.declared_files(build)
        bridge = 'scene/spween-bridge/target/debug/delvetalk-spween'
        bridge_sha = dependencies[bridge]
        for sha in dependencies.values():
            desk.history.read_blob(self.client.artifact_store / 'pins', sha)
        # Existing immutable custody must survive replacement/removal of the installation.
        with patch.object(desk, 'ROOT', self.path / 'absent-installation'):
            desk.preserve_build_dependencies(self.client.artifact_store, build)
        reviewer = self.app('reviewer').authoring
        adoption = reviewer.prepare({'operation': 'adopt', 'candidate': 'candidate', 'target': 'target'})
        self.assertEqual(reviewer.execute({'draft': adoption['draft']})['receipt']['kind'], 'committed')
        attempt = desk.loads(next((self.client.artifact_store / 'attempts').glob('*.json')).read_bytes())
        with patch.object(desk, 'preserve_build_dependencies', side_effect=AssertionError('recover receipt first')):
            self.assertEqual(self.client.check('candidate', 'compiler', attempt['inputs']['intent'],
                                               attempt['inputs']['expected']), completed['receipt'])
        original_open = Path.open
        def without_current_bridge(path, *args, **kwargs):
            if path == ROOT / bridge:
                raise FileNotFoundError('original bridge no longer installed')
            return original_open(path, *args, **kwargs)
        bundle = self.path.parent / 'compiled-bundle'
        with patch.object(Path, 'open', without_current_bridge):
            anchors = workspace.bootstrap.export_bootstrap(self.path, bundle)
        desk.history.read_blob(bundle, bridge_sha)
        restored = self.path.parent / 'restored'
        workspace.bootstrap.restore_bootstrap(bundle, restored,
            expected_genesis=anchors['genesis'], expected_head=anchors['head'])
        self.assertEqual((restored / 'world.json').read_bytes(), self.client.database.read_bytes())
        self.assertEqual(workspace.bootstrap.inspect_view(restored, 'target')['source'], source)

    def test_build_dependency_corruption_and_changed_original_refuse(self):
        import hashlib
        source = self.path / 'compiler-input'
        source.write_bytes(b'original compiler input')
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        artifact = {'format': 'delvetalk-room-artifact-v1', 'content': {'pins': {'compiler-input': sha}}}
        with patch.object(desk, 'ROOT', self.path.resolve()):
            source.write_bytes(b'changed input')
            with self.assertRaisesRegex(ValueError, 'original build dependency'):
                desk.preserve_build_dependencies(self.client.artifact_store, artifact)
            self.assertFalse(desk.history.blob_path(self.client.artifact_store / 'pins', sha).exists())
            source.write_bytes(b'original compiler input')
            desk.preserve_build_dependencies(self.client.artifact_store, artifact)
            retained = desk.history.blob_path(self.client.artifact_store / 'pins', sha)
            retained.write_bytes(b'corrupted custody')
            with self.assertRaisesRegex(ValueError, 'retained build dependency'):
                desk.preserve_build_dependencies(self.client.artifact_store, artifact)

    def test_readonly_prepare_and_principal_binding(self):
        author, draft = self.submit()
        before = self.client.database.read_bytes()
        readonly = self.app().authoring
        self.assertFalse(readonly.draft(draft['draft'])['canExecute'])
        with self.assertRaises(PermissionError): readonly.execute({'draft': draft['draft']})
        with self.assertRaises(PermissionError): self.app('compiler').authoring.execute({'draft': draft['draft']})
        preview = readonly.prepare({'operation': 'adopt', 'candidate': 'candidate', 'target': 'target'})
        self.assertFalse(preview['canExecute'])
        with self.assertRaises(PermissionError): self.app('reviewer').authoring.execute({'draft': preview['draft']})
        self.assertEqual(before, self.client.database.read_bytes())
        with self.assertRaises(ValueError): author.prepare({'operation': 'compile', 'candidate': 'candidate', 'principal': 'compiler'})

    def test_lost_reply_recovers_original_intent_before_runtime_check(self):
        author, draft = self.submit()
        original = worker.command
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise subprocess.TimeoutExpired('lost', 1)
        with patch.object(worker, 'command', side_effect=lose):
            self.assertEqual(author.execute({'draft': draft['draft']})['kind'], 'uncertain')
        before = self.client.database.read_bytes()
        restarted = self.app('author')
        with patch.object(restarted, 'current_runtime', side_effect=AssertionError('recover first')):
            self.assertEqual(restarted.authoring.execute({'draft': draft['draft']})['receipt']['kind'], 'committed')
        self.assertEqual(before, self.client.database.read_bytes())

    def test_compile_diagnostics_and_adoption_refusal(self):
        _, _, result = self.ready('{ broken source')
        self.assertTrue(result['diagnostics'])
        reviewer = self.app('reviewer').authoring
        draft = reviewer.prepare({'operation': 'adopt', 'candidate': 'candidate', 'target': 'target'})
        self.assertEqual(reviewer.execute({'draft': draft['draft']})['receipt']['kind'], 'refused')
        self.assertEqual(self.client.inspect('target')['version'], 0)

    def test_desk_grant_does_not_install_and_stale_target_refuses(self):
        self.ready()
        author = self.app('author').authoring
        denied = author.prepare({'operation': 'adopt', 'candidate': 'candidate', 'target': 'target'})
        candidate = self.client.inspect('candidate')
        self.assertEqual(author.execute({'draft': denied['draft']})['receipt']['kind'], 'refused')
        self.assertEqual(self.client.inspect('candidate'), candidate)
        reviewer = self.app('reviewer').authoring
        stale = reviewer.prepare({'operation': 'adopt', 'candidate': 'candidate', 'target': 'target'})
        root = self.client.inspect('target')
        self.client.exchange({'op': 'invoke', 'object': 'target', 'principal': 'author', 'intent': 'advance',
            'expected': root, 'command': 'add', 'input': {'amount': 1}})
        self.assertEqual(reviewer.execute({'draft': stale['draft']})['receipt']['kind'], 'refused')

    def test_factory_preview_and_receipt_child_links(self):
        protocol = desk.loads((ROOT / 'protocols/factories/object.json').read_bytes())
        self.client.exchange({'op': 'create', 'object': 'workshop', 'principal': 'owner', 'intent': 'factory',
            'protocol': protocol, 'law': law({'make': ['author']})})
        app = self.app('author')
        card = app.object('workshop')
        draft = app.prepare({'card': card['card'], 'action': 'a1', 'fields': {'name': 'lamp'}})
        self.assertEqual(draft['absence'], ['workshop/lamp'])
        result = app.execute({'draft': draft['draft']})
        self.assertEqual(result['kind'], 'committed', result)
        child = result['children'][0]
        self.assertEqual(child['object'], 'workshop/lamp')
        self.assertEqual(child['root'], self.client.inspect('workshop/lamp'))
        self.assertEqual(child['objectRef'], {'format': 'delvetalk-object-ref-v1',
            'world': 'urn:test:authoring', 'object': 'workshop/lamp'})
        self.assertEqual(self.app('author').execute({'draft': draft['draft']}), result)
        self.assertEqual(app.object('workshop/lamp')['object'], child['object'])

    def test_unsupported_affordances_keep_exact_inspection(self):
        protocol = desk.loads(self.source)
        protocol['affordances'] = {'profile': 'unknown-future-metadata'}
        reply = self.client.exchange({'op': 'create', 'object': 'opaque', 'principal': 'owner',
            'intent': 'opaque', 'protocol': protocol, 'law': law()})
        self.assertEqual(reply['kind'], 'committed', reply)
        app = self.app()
        card = app.object('opaque')
        self.assertEqual(card['actions'], [])
        self.assertIn('unsupported', card)
        self.assertEqual(app.detail(card['card'])['root'], reply['data']['root'])
        self.assertEqual(card['objectRef']['object'], 'opaque')
        self.assertNotIn('objectRef', app.object_ref('local\nname'))
        self.assertIn('referenceStatus', app.object_ref('local\nname'))

    def test_pending_runtime_change_and_draft_tampering_refuse(self):
        author, draft = self.submit()
        with patch.object(author.portal, 'current_runtime', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Runtime pins'):
                author.execute({'draft': draft['draft']})
        path = author.state / 'drafts' / (draft['draft'] + '.json')
        saved = desk.loads(path.read_bytes()); saved['request']['intent'] += '-changed'
        path.write_bytes(desk.canonical(saved))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            author.execute({'draft': draft['draft']})
        self.assertEqual(self.client.inspect('candidate')['state']['status'], 'empty')

    def test_enqueue_lost_local_result_recovers_original_job(self):
        import authoring
        author, draft = self.submit()
        author.execute({'draft': draft['draft']})
        compiler = self.app('compiler').authoring
        build = compiler.prepare({'operation': 'compile', 'candidate': 'candidate'})
        with patch.object(authoring, 'save', side_effect=OSError('lost enqueue result')):
            with self.assertRaises(OSError): compiler.execute({'draft': build['draft']})
        restarted = self.app('compiler')
        with patch.object(restarted, 'current_runtime', side_effect=AssertionError('recover job first')):
            recovered = restarted.authoring.execute({'draft': build['draft']})
        self.assertEqual(recovered['phase'], 'queued')
        self.assertEqual(len(list(compiler._queue(build['draft']).state.glob('jobs/*.json'))), 1)

    def test_compile_lost_reply_recovers_job_without_recompiling(self):
        author, draft = self.submit()
        author.execute({'draft': draft['draft']})
        compiler = self.app('compiler').authoring
        build = compiler.prepare({'operation': 'compile', 'candidate': 'candidate'})
        compiler.execute({'draft': build['draft']})
        original = worker.command
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise subprocess.TimeoutExpired('lost compile reply', 1)
        with patch.object(worker, 'command', side_effect=lose):
            result = compiler.run({'draft': build['draft']})
        self.assertEqual(result['phase'], 'queued')
        self.assertTrue(result['errors'])
        before = self.client.database.read_bytes()
        recovered = self.app('compiler').authoring.run({'draft': build['draft']})
        self.assertEqual(recovered['phase'], 'finished', recovered)
        self.assertEqual(recovered['receipt']['kind'], 'committed')
        self.assertEqual(before, self.client.database.read_bytes())

    def test_http_large_upload_bound_ref_and_no_admission(self):
        app = self.app()
        before = self.client.database.read_bytes()
        server = portal.make_server(app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        self.addCleanup(conn.close)
        body = json.dumps({'text': '雪' * 30000})
        conn.request('POST', '/api/authoring/source', body, {'Content-Type': 'application/json', 'X-Delvetalk-CSRF': app.csrf})
        response = conn.getresponse(); result = json.loads(response.read())
        self.assertEqual(response.status, 200, result)
        conn.request('GET', '/api/authoring/source?source=' + result['source'])
        response = conn.getresponse(); read = json.loads(response.read())
        self.assertEqual(read['text'], '雪' * 30000)
        self.assertEqual(read['bytes'], 90000)
        with self.assertRaises(ValueError): app.authoring.source({'text': 'x' * 524289})
        with self.assertRaises(ValueError): app.authoring.read_source('../escape')
        self.assertEqual(before, self.client.database.read_bytes())


if __name__ == '__main__': unittest.main()
