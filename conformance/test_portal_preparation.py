"""Source conversation outcomes stay separate from executable portal drafts."""
import copy
from contextlib import ExitStack
import http.client
import os
import shutil
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
import portal
import source_offers
from conformance.test_view_invitations import fixture


class PortalPreparation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.view = fixture()
        self.view.update(object='gestures', panel='main')
        self.root = self.view['root']
        portal.save(self.directory / 'world.json', {'objects': {'gestures': self.root, 'peer': self.root}, 'receipts': []})
        portal.save(self.directory / 'manifest.json', {'cafe': 'gestures', 'runtime': {'name': 'compiled', 'files': {}}})

    def app(self, public=False):
        app = portal.Portal(self.directory, **({'public_origin': 'https://delvetalk.example'} if public else
                            {'principal': 'visitor', 'allow_local_actions': True}))
        # This class uses a synthetic view; native source/retention is exercised
        # by NativePortalPreparation below rather than admitted by this mock.
        with patch.object(app, '_view', return_value=copy.deepcopy(self.view)), patch.object(
                source_offers.world, 'query', side_effect=lambda database, request: {
                    'profile': 'delvetalk-retained-root-v1', 'object': request['object'], 'key': 'test-reference'}):
            card = app.object('gestures')
        return app, card

    def test_source_question_and_refusal_are_retained_without_world_admission(self):
        before = (self.directory / 'world.json').read_bytes()
        for kind in ('question', 'refused'):
            app, card = self.app()
            outcome = {'kind': kind, 'message': '<Which gesture?> & why'}
            if kind == 'question': outcome['needs'] = ['gesture', 'recipient']
            with patch.object(source_offers, 'prepare', return_value=outcome) as native:
                result = app.prepare({'card': card['card'], 'action': 'o1', 'fields': {}})
            self.assertEqual(native.call_args.args[-1], {})
            self.assertEqual(result['outcome'], outcome)
            self.assertFalse(result['canExecute'])
            self.assertNotIn('draft', result)
            self.assertNotIn('request', result)
            self.assertNotIn('wire', result)
            self.assertNotIn('intent', result)
            self.assertEqual(list((app.state / 'drafts').iterdir()), [])
            restarted = portal.Portal(self.directory, principal='visitor', allow_local_actions=True)
            self.assertEqual(restarted.preparation(result['preparation']), result)
            with self.assertRaisesRegex(ValueError, 'Unknown saved reference'):
                restarted.execute({'draft': result['preparation']})
            self.assertEqual((self.directory / 'world.json').read_bytes(), before)

    def test_expanded_bound_still_applies_before_new_local_submission(self):
        app, card = self.app()
        oversized = {'op': 'transaction', 'principal': 'visitor', 'intent': 'oversized',
                     'reads': {}, 'calls': [], 'padding': 'x' * portal.world.MAX_EXPANDED_REQUEST_BYTES}
        with patch.object(app, 'captured_request', return_value=oversized):
            with self.assertRaisesRegex(ValueError, '1 MiB'):
                app.prepare({'card': card['card'], 'action': 'o1'})
        self.assertEqual(list((app.state / 'drafts').iterdir()), [])
        saved = {'request': oversized}
        with patch.object(app, '_retained', return_value=None), patch.object(portal.submission.worker, 'command') as submit:
            with self.assertRaisesRegex(ValueError, '1 MiB'):
                portal.submission.execute(app, saved, None, app.state, lambda _: None)
            submit.assert_not_called()
        retained = {'kind': 'committed', 'data': {}}
        with patch.object(app, '_retained', return_value=retained):
            self.assertEqual(portal.submission.execute(app, saved, None, app.state, lambda _: None), (retained, None))

    def test_public_outcome_is_readable_over_same_origin_and_stays_memory_only(self):
        app, card = self.app(public=True)
        outcome = {'kind': 'question', 'message': 'Who should receive it?', 'needs': ['recipient']}
        with patch.object(source_offers, 'prepare', return_value=outcome):
            result = app.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'wave'}})
        server = portal.make_server(app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
        connection.request('GET', result['links']['self'], headers={'Host': 'delvetalk.example'})
        response = connection.getresponse()
        body = portal.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(body['outcome'], outcome)
        self.assertEqual(body['fields'], {'gesture': 'wave'})
        self.assertFalse((self.directory / 'portal-custody').exists())
        self.assertFalse(any(category == 'drafts' for category, _ in app.preview.records))


class NativePortalPreparation(unittest.TestCase):
    def test_real_source_question_refusal_and_read_only_ready_turn(self):
        from syntaxes import obend_object
        from conformance.test_view_invitations import SOURCE
        source = SOURCE[:SOURCE.index('def prepareGesture(')] + '''def prepareGesture(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  let gesture: String = P.text(P.get(contribution, "gesture"))
  if gesture == "" then P.Preparation.question({message: "Which gesture would you like?", needs: P.Names.cons({head: "gesture", tail: P.Names.nil()})}) else if gesture == "refuse" then P.Preparation.refused({message: "Choose another gesture."}) else P.Preparation.ready({summary: "Offer the gesture", reads: P.Reads.cons({head: P.Read.existing({object: "peer"}), tail: P.Reads.nil()}), calls: P.Effects.cons({head: P.Effect.invoke({object: "peer", command: "touch", input: P.oneField("gesture", P.Value.text({value: gesture}))}), tail: P.Effects.nil()})})
'''
        protocol = obend_object.lower_data_modules([
            {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
            {'name': 'Gallery', 'source': source}])
        root = {'protocol': protocol, 'state': protocol['initial'], 'version': 0, 'law': ['visitor']}
        peer = {'protocol': {'profile': 'delvetalk-local-v1', 'initial': {},
                'commands': {'touch': {'require': [], 'set': {'touched': ['input', 'gesture']},
                                       'result': ['input', 'gesture'], 'outbox': []}}},
                'state': {'pages': ['x' * 20000] * 4}, 'version': 0, 'law': ['visitor']}
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as selected:
            # An explicit isolated receiver selection must select its real closure,
            # view runner, receipt lookup and submission script together.
            binary = Path(os.environ.get('DELVETALK_PREPARATION_BINARY', source_offers.BINARY))
            build = binary.resolve().parents[3]
            if build != ROOT:
                native = build
                build = Path(temporary) / 'runtime'
                for name in ('profiles', 'spec'):
                    shutil.copytree(native / name, build / name)
                for name in ('scripts', 'scene'):
                    (build / name).mkdir(parents=True)
                    for path in (ROOT / name).iterdir():
                        if path.is_file() and path.suffix in ('.py', '.json'):
                            shutil.copyfile(path, build / name / path.name)
                for name in ('lakefile.toml', 'lean-toolchain'):
                    shutil.copyfile(native / name, build / name)
                (build / '.lake/build/bin').mkdir(parents=True)
                for name in ('delvetalk-compiled', 'delvetalk-world', 'delvetalk-obend'):
                    shutil.copy2(native / '.lake/build/bin' / name, build / '.lake/build/bin' / name)
            selected.enter_context(patch.object(portal.bootstrap.history, 'ROOT', build))
            selected.enter_context(patch.object(portal.bootstrap.room, 'ROOT', build))
            selected.enter_context(patch.object(portal.submission, 'ROOT', build))
            selected.enter_context(patch.object(portal.world, 'ROOT', build))
            if build != ROOT:
                # The isolated compilation includes the same FileCustody lookup
                # route; its old sibling world binary has not been rebuilt.
                selected.enter_context(patch.dict(portal.world.PROFILES,
                    {'world': (str(build / '.lake/build/bin/delvetalk-compiled'), 'Compiled.lean')}))
            directory = Path(temporary)
            portal.save(directory / 'world.json', {'objects': {'gestures': root, 'peer': peer}, 'receipts': []})
            portal.save(directory / 'manifest.json', {'cafe': 'gestures', 'runtime': portal.bootstrap.history.runtime('compiled')})
            app = portal.Portal(directory, principal='visitor', allow_local_actions=True)
            card = app.object('gestures')
            before = (directory / 'world.json').read_bytes()
            binary = Path(os.environ.get('DELVETALK_PREPARATION_BINARY', source_offers.BINARY))
            selected.enter_context(patch.object(source_offers, 'BINARY', binary))
            # Explicit full-preimage preparation remains supported separately
            # from compact consumer guards, including real expanded admission.
            view = app._read('cards', card['card'])['view']
            full_invitation = next(iter(source_offers.capture(view, app.snapshot()['objects'], database=None).values()))
            expanded = source_offers.prepare(full_invitation, 'visitor', 'full-preimage', {'gesture': 'expanded'}, binary=binary)
            self.assertGreater(len(portal.world.wire_dumps(expanded['request']).encode()), 76000)
            expanded_database = directory / 'expanded.json'
            portal.save(expanded_database, app.snapshot())
            expanded_reply = portal.world.exchange(expanded_database, expanded['request'], profile='compiled')
            self.assertEqual(expanded_reply['kind'], 'committed', expanded_reply)
            self.assertEqual(portal.world.exchange(expanded_database, expanded['request'], profile='compiled'), expanded_reply)
            question = app.prepare({'card': card['card'], 'action': 'o1', 'fields': {}})
            refused = app.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'refuse'}})
            ready = app.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'wave'}})
            self.assertEqual(question['outcome'], {'kind': 'question', 'message': 'Which gesture would you like?', 'needs': ['gesture']})
            self.assertEqual(refused['outcome'], {'kind': 'refused', 'message': 'Choose another gesture.'})
            self.assertNotIn('draft', question)
            self.assertNotIn('draft', refused)
            self.assertEqual(ready['wire']['calls'][0]['input'], {'gesture': 'wave'})
            self.assertEqual(set(ready['wire']['reads']), {'gestures', 'peer'})
            self.assertEqual(app.preparation(question['preparation']), question)
            self.assertEqual((directory / 'world.json').read_bytes(), before)
            self.assertLess(len(ready['wireJson'].encode()), 1500)
            self.assertEqual(ready['wire']['reads']['peer']['expected']['profile'], 'delvetalk-retained-root-v1')
            prepared = app.repository_prepare({'draft': ready['draft']})
            self.assertIn('recordJson', prepared)
            admitted = app.execute({'draft': ready['draft']})
            self.assertEqual(admitted['kind'], 'committed', admitted)
            self.assertEqual(app.snapshot()['objects']['peer']['state']['touched'], 'wave')
            snapshot = (directory / 'world.json').read_bytes()
            self.assertEqual(app.execute({'draft': ready['draft']}), admitted)
            self.assertEqual((directory / 'world.json').read_bytes(), snapshot)


if __name__ == '__main__':
    unittest.main()
