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
import runtime_profile
import town_cards
import translate
import source_object
import history
import world


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


adapter = module('object_adapter', 'syntaxes/obend_object.py')
SOURCE = (ROOT / 'syntaxes/examples/lantern.obend').read_bytes()
MAKER, VISITOR = ('did:plc:' + c * 24 for c in ('a', 'b'))


class SourceObjectTests(unittest.TestCase):
    def test_exact_source_compiles_description_and_every_export(self):
        raw = b'# exact CRLF and UTF-8: \xe9\x9b\xaa\r\n' + SOURCE.replace(b'\n', b'\r\n')
        artifact = translate.translate('objective-bend-object', raw)
        protocol = artifact['lowered']
        self.assertEqual(artifact['source']['text'].encode(), raw)
        self.assertEqual(source_object.state_data({'protocol': protocol, 'state': protocol['initial']}), source_object.data({'lit': False}))
        self.assertEqual(set(protocol['commands']), {'light', 'douse'})
        self.assertEqual(protocol['viewProgram']['profile'], 'delvetalk-obend-data-menu-v1')
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
                with self.assertRaisesRegex(ValueError, 'signature|incompatible serializable state schema'):
                    translate.translate('objective-bend-object', source)

    def test_description_is_pure_bounded_and_has_no_authority_fields(self):
        extra = SOURCE.replace(b'  name: String\n', b'  name: String\n  law: String\n')
        extra = extra.replace(b'{name: "Moth lantern",', b'{name: "Moth lantern", law: "everyone",')
        with self.assertRaisesRegex(ValueError, 'describe.*requires'):
            translate.translate('objective-bend-object', extra)
        looping = SOURCE.replace(b'def describe()', b'def countdown(n: Nat) -> Nat:\n  if n == 0n then 0n else countdown(n - 1n)\ndef describe()')
        looping = looping.replace(b'initial: {lit: false}', b'initial: {lit: countdown(100000n) == 0n}')
        with self.assertRaisesRegex(ValueError, 'tickExhausted|timed out'):
            translate.translate('objective-bend-object', looping)

    def test_enum_forms_and_examples_are_source_owned_but_not_defaults(self):
        source = SOURCE.replace(b'record Method:', b'record Colour:\n  type: String\n  options: {a: String, b: String}\n  example: String\nrecord Method:')
        source = source.replace(b'  fields: {}', b'  fields: {colour: Colour}')
        source = source.replace(b'fields: {}', b'fields: {colour: {type: "enum", options: {a: "amber", b: "violet"}, example: "violet"}}')
        source = source.replace(b'input: {}, context:', b'input: {colour: String}, context:')
        protocol = translate.translate('objective-bend-object', source)['lowered']
        field = protocol['affordances']['light']['fields']['colour']
        self.assertEqual(field, {'type': 'enum', 'options': ['amber', 'violet'], 'example': 'violet'})
        action = {'available': True, 'fields': [affordances._normalize_field('colour', field)]}
        with self.assertRaisesRegex(ValueError, 'missing'):
            affordances.validate_fields(action, {})
        with self.assertRaisesRegex(ValueError, 'enum'):
            translate.translate('objective-bend-object', source.replace(b'example: "violet"', b'example: "silver"'))

    def test_runtime_change_during_description_is_refused(self):
        from unittest.mock import patch
        # Fault injection at the custody comparison, never a fake evaluator.
        original = adapter.runtime_profile.hash_paths
        calls = 0
        def changing(paths, **options):
            nonlocal calls
            calls += 1
            result = original(paths, **options)
            return result if calls == 1 else {**result, 'changed': 'yes'}
        with patch.object(adapter.runtime_profile, 'hash_paths', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                adapter.lower_data(SOURCE.decode())

    def test_source_town_use_authority_and_exact_history_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            database = base / 'world.json'
            artifact = translate.translate('objective-bend-object', SOURCE)
            law = {'profile': 'delvetalk-scoped-law', 'invoke': {'light': [VISITOR], 'douse': [VISITOR]},
                   'reprogram': [MAKER], 'law': [MAKER], 'read': [MAKER, VISITOR], 'view': {'main': 'public'}}
            call = lambda request: world.exchange(database, request, profile='compiled')
            made = call({'op': 'create', 'object': 'lantern', 'principal': MAKER, 'intent': 'create',
                         'protocol': artifact['lowered'], 'law': law})
            self.assertEqual(made['kind'], 'committed', made)
            root = made['data']['root']
            book = town_cards.CardBook.create(base / 'cards', issuer_did=MAKER,
                world_id='moth-lantern', runtime=history.runtime('compiled'))
            public = world.opaque_view(database, 'lantern', principal=MAKER, audience='public')
            captured = book.capture_public('lantern', public, alias='moth-lantern')
            self.assertEqual([a['command'] for a in captured['actions']], ['light'])
            publication = {'uri': 'at://' + MAKER + '/town.delve.feed.post/lantern', 'cid': 'exact-card'}
            record = {'$type': town_cards.FEED, 'text': captured['body']}
            fetch = lambda uri, cid: copy.deepcopy(record)
            book.bind('moth-lantern', publication, fetch, database=database)
            source = {'uri': 'at://' + VISITOR + '/town.delve.feed.post/light', 'cid': 'exact-reply',
                      'author': VISITOR, 'pds': 'https://pds.delve.town'}
            reply = {'$type': town_cards.FEED, 'text': 'delvetalk moth-lantern light', 'reply': {'parent': publication}}
            wire, _ = book.resolve(reply, VISITOR, source, fetch, [MAKER], database=database)
            request = {**wire, 'principal': VISITOR, 'intent': 'delve:' + source['uri']}
            receipt = call(request)
            self.assertEqual(receipt['kind'], 'committed', receipt)
            current = world.capture_roots(database, ['lantern'], principal=MAKER)['roots']['lantern']['root']
            self.assertEqual(source_object.state_data(current), source_object.data({'lit': True}))
            view = world.opaque_view(database, 'lantern', principal=MAKER, audience='public')
            self.assertEqual([key for key, action in view['result']['actions'].items() if action['visible']], ['douse'])
            direct = {'op': 'invoke', 'object': 'lantern', 'principal': VISITOR, 'expected': current, 'command': 'light', 'input': {}, 'intent': 'light-again'}
            self.assertEqual(call(direct)['data'], 'source refused: Already lit.')
            self.assertEqual(call({**request, 'intent': 'stale'})['kind'], 'refused')
            self.assertEqual(call({**direct, 'principal': MAKER, 'intent': 'maker-cannot-invoke'})['data'], 'unauthorized')
            bundle, restored = base / 'history', base / 'restored.json'
            trusted = history.export_history(database, bundle)
            history.verify_history(bundle, output=restored, expected_genesis=trusted['genesis'], expected_head=trusted['head'])
            self.assertEqual(world.exchange(restored, request, profile='compiled'), receipt)
            self.assertEqual(history.loads(restored.read_bytes()), history.loads(database.read_bytes()))
            continued = world.exchange(restored, {'op': 'invoke', 'object': 'lantern', 'principal': VISITOR,
                'intent': 'after-restore', 'expected': current, 'command': 'douse', 'input': {}}, profile='compiled')
            self.assertEqual(continued['kind'], 'committed', continued)


if __name__ == '__main__':
    unittest.main()
