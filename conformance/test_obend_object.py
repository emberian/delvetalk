"""One authored Bend object: typed description, real receiving, desk and town."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import desk
import runtime_profile
import town_cards
import translate
import workspace


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


adapter = module('object_adapter', 'syntaxes/obend_object.py')
room = module('object_room', 'scene/room.py')
SOURCE = (ROOT / 'syntaxes/examples/lantern.obend').read_bytes()
EXAMPLES = (ROOT / 'syntaxes/examples/lantern.examples').read_bytes()
MAKER, VISITOR = ('did:plc:' + c * 24 for c in ('a', 'b'))


class SourceObjectTests(unittest.TestCase):
    def test_exact_source_compiles_description_and_every_export(self):
        raw = b'# exact CRLF and UTF-8: \xe9\x9b\xaa\r\n' + SOURCE.replace(b'\n', b'\r\n')
        artifact = translate.translate('objective-bend-spell@2', raw)
        protocol = artifact['lowered']
        self.assertEqual(artifact['source']['text'].encode(), raw)
        self.assertEqual(protocol['initial'], {'lit': False})
        self.assertEqual(set(protocol['commands']), {'light', 'douse'})
        self.assertEqual(protocol['viewProgram']['profile'], 'delvetalk-obend-menu-v1')
        self.assertNotIn('law', protocol)
        for method, command in protocol['commands'].items():
            self.assertEqual(set(command), {'transition'})
            package = command['transition']['package']
            self.assertEqual(package['entry'], method)
            self.assertEqual(package['format'], 'delvetalk-source-package-ref-v1')
            self.assertEqual(protocol['sourcePackages'][package['name']]['modules'], [{'name': 'Main', 'source': raw.decode()}])
        self.assertTrue(set(runtime_profile.paths('compiled')) <= set(artifact['translation']['files']))
        self.assertIn('.lake/build/bin/delvetalk-obend', artifact['translation']['files'])

    def test_compiler_types_reject_incoherent_object_abi(self):
        samples = [
            SOURCE.replace(b'input: {}, context:', b'input: {word: String}, context:'),
            SOURCE.replace(b'context: Context', b'context: {}'),
            SOURCE.replace(b'  state: State\n', b'  state: {}\n').replace(b'state: {lit: true}', b'state: {}').replace(b'state: {lit: false}', b'state: {}'),
            SOURCE.replace(b'view(state: State, panel: String)', b'view(state: {}, panel: String)').replace(b'fix(Moth, {}).inscription(state)', b'"A lantern"').replace(b'visible: state.lit == false', b'visible: true').replace(b'visible: state.lit', b'visible: false'),
        ]
        for source in samples:
            with self.subTest(source=source[-160:]):
                with self.assertRaisesRegex(ValueError, 'signature|declared state|view must'):
                    translate.translate('objective-bend-spell@2', source)

    def test_description_is_pure_bounded_and_has_no_authority_fields(self):
        extra = SOURCE.replace(b'  name: String\n', b'  name: String\n  law: String\n')
        extra = extra.replace(b'{name: "Moth lantern",', b'{name: "Moth lantern", law: "everyone",')
        with self.assertRaisesRegex(ValueError, 'requires exactly'):
            translate.translate('objective-bend-spell@2', extra)
        looping = SOURCE.replace(b'def describe()', b'def countdown(n: Nat) -> Nat:\n  if n == 0n then 0n else countdown(n - 1n)\ndef describe()')
        looping = looping.replace(b'initial: {lit: false}', b'initial: {lit: countdown(100000n) == 0n}')
        with self.assertRaisesRegex(ValueError, 'tickExhausted|timed out'):
            translate.translate('objective-bend-spell@2', looping)

    def test_enum_forms_and_examples_are_source_owned_but_not_defaults(self):
        source = SOURCE.replace(b'record Method:', b'record Colour:\n  type: String\n  options: {a: String, b: String}\n  example: String\nrecord Method:')
        source = source.replace(b'  fields: {}', b'  fields: {colour: Colour}')
        source = source.replace(b'fields: {}', b'fields: {colour: {type: "enum", options: {a: "amber", b: "violet"}, example: "violet"}}')
        source = source.replace(b'input: {}, context:', b'input: {colour: String}, context:')
        protocol = translate.translate('objective-bend-spell@2', source)['lowered']
        field = protocol['affordances']['light']['fields']['colour']
        self.assertEqual(field, {'type': 'enum', 'options': ['amber', 'violet'], 'example': 'violet'})
        view = {'mode': 'raw', 'object': 'lantern', 'root': {'protocol': protocol,
                'state': protocol['initial'], 'law': [], 'version': 0}}
        action = affordances.card(view)['actions'][0]
        with self.assertRaisesRegex(ValueError, 'missing'):
            affordances.validate_fields(action, {})
        with self.assertRaisesRegex(ValueError, 'enum'):
            translate.translate('objective-bend-spell@2', source.replace(b'example: "violet"', b'example: "silver"'))

    def test_runtime_change_during_description_is_refused(self):
        from unittest.mock import patch
        # Fault injection at the custody comparison, never a fake evaluator.
        original = adapter.runtime_profile.file_hashes
        calls = 0
        def changing(profile):
            nonlocal calls
            calls += 1
            result = original(profile)
            return result if calls == 1 else {**result, 'changed': 'yes'}
        with patch.object(adapter.runtime_profile, 'file_hashes', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                adapter.lower(SOURCE.decode())

    def test_real_desk_adoption_town_use_and_exact_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            directory = base / 'world'
            scoped = lambda calls, edits=(): {'profile': 'delvetalk-scoped-law-v1',
                'invoke': calls, 'reprogram': list(edits), 'law': [MAKER]}
            target = {'profile': 'delvetalk-local-v1', 'name': 'An unlit workshop object',
                      'initial': {}, 'commands': {}}
            seeds = [
                {'id': 'lantern', 'syntax': 'protocol-json@1', 'source': desk.canonical(target),
                 'law': scoped({'light': [VISITOR], 'douse': [VISITOR]}, [MAKER])},
                {'id': 'writing', 'syntax': 'protocol-json@1',
                 'source': (ROOT / 'protocols/source-desk/protocol.json').read_bytes(),
                 'law': scoped({'submit': [MAKER], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': [MAKER]})},
            ]
            seed = workspace.initialize(directory, seeds, entry_objects=['lantern', 'writing'],
                principal='operator', profile='compiled', world_id='moth-lantern')
            client = desk.Desk(directory / 'world.json', directory / 'artifacts', profile='compiled')
            old = client.inspect('lantern')
            pending = client.submit('writing', MAKER, 'write', client.inspect('writing'),
                'objective-bend-spell@2', SOURCE, EXAMPLES, {'lit': False}, 'lantern')['data']['root']
            checked = client.check('writing', 'compiler', 'check', pending)
            self.assertEqual(checked['kind'], 'committed', checked)
            ready = checked['data']['root']
            self.assertEqual(ready['state']['status'], 'ready', ready)
            self.assertEqual(client.inspect('lantern'), old)
            adopted = client.adopt('writing', 'lantern', MAKER, 'adopt', ready, old)
            self.assertEqual(adopted['kind'], 'committed', adopted)
            root = client.inspect('lantern')
            self.assertEqual(root['law'], old['law'])
            book = town_cards.CardBook.create(base / 'cards', issuer_did=MAKER,
                world_id='moth-lantern', runtime=desk.history.runtime('compiled'))
            captured = book.capture(room.inspect_object(root, 'lantern', expected_runtime=book.metadata()['runtime']), 'moth-lantern')
            self.assertEqual([a['command'] for a in captured['card']['actions']], ['light'])
            publication = {'uri': 'at://' + MAKER + '/town.delve.feed.post/lantern', 'cid': 'exact-card'}
            record = {'$type': town_cards.FEED, 'text': captured['body']}
            fetch = lambda uri, cid: copy.deepcopy(record)
            book.bind('moth-lantern', publication, fetch)
            source = {'uri': 'at://' + VISITOR + '/town.delve.feed.post/light', 'cid': 'exact-reply',
                      'author': VISITOR, 'pds': 'https://pds.delve.town'}
            reply = {'$type': town_cards.FEED, 'text': 'delvetalk moth-lantern light', 'reply': {'parent': publication}}
            wire, _ = book.resolve(reply, VISITOR, source, fetch, [MAKER])
            request = {**wire, 'principal': VISITOR, 'intent': 'delve:' + source['uri']}
            receipt = client.exchange(request)
            self.assertEqual(receipt['kind'], 'committed', receipt)
            current = client.inspect('lantern')
            self.assertEqual(current['state'], {'lit': True})
            self.assertEqual(list(room.inspect_object(current, 'lantern')['actions']), ['douse'])
            refused = client.exchange({**request, 'expected': current, 'intent': 'light-again'})
            self.assertEqual(refused['data'], 'source refused: Already lit.')
            self.assertEqual(client.exchange({**request, 'intent': 'stale'})['data'], 'stale read root')
            self.assertEqual(client.exchange({**request, 'principal': 'stranger', 'intent': 'stranger'})['data'], 'unauthorized')
            bundle, restored = base / 'history', base / 'restored'
            exported = workspace.bootstrap.export_bootstrap(directory, bundle)
            workspace.bootstrap.restore_bootstrap(bundle, restored, expected_genesis=seed['genesis'],
                expected_head=exported['head'], base_head=seed['head'])
            continued = desk.Desk(restored / 'world.json', restored / 'artifacts', profile='compiled')
            self.assertEqual(continued.inspect('lantern'), current)
            self.assertEqual(continued.exchange(request), receipt)
            self.assertEqual(desk.loads(continued.database.read_bytes()), desk.loads(client.database.read_bytes()))
            self.assertEqual(continued.exchange({'op': 'invoke', 'object': 'lantern', 'principal': VISITOR,
                'intent': 'after-restore', 'expected': current, 'command': 'douse', 'input': {}})['kind'], 'committed')


if __name__ == '__main__':
    unittest.main()
