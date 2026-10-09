"""Actual native authored effect/receive binding with explicit source dependencies."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'syntaxes'))
import obend_object


def sources(name):
    return [{'name': n, 'source': (ROOT / 'world/lib/prelude' / (n + '.obend')).read_text()}
            for n in ('Abi', 'Encounter')] + [{'name': name, 'source':
                (ROOT / 'protocols/resident-messages' / (name + '.obend')).read_text()}]


class SourceMessageBindingTests(unittest.TestCase):
    def test_real_bell_and_door_source_bind_typed_message_profiles(self):
        for name, command, profile in (('Bell', 'play', 'delvetalk-source-data-effects-v1'),
                                        ('Door', 'hear', 'delvetalk-source-data-receive-v1')):
            with self.subTest(profile=profile):
                modules = sources(name)
                protocol = obend_object.lower_data_modules(modules)
                transition = protocol['commands'][command]['transition']
                self.assertEqual(transition['profile'], profile)
                self.assertEqual(next(iter(protocol['sourcePackages'].values()))['modules'], modules)
                self.assertEqual(set(protocol['initial']), {'model'})
                self.assertEqual(protocol['viewProgram']['profile'], 'delvetalk-obend-data-menu-v1')

    def test_receive_facts_and_emission_payload_have_exact_checked_abi(self):
        bad_event = sources('Door')
        bad_event[0]['source'] = bad_event[0]['source'].replace('  originatingPrincipal: String',
            '  originatingPrincipal: String\n  claimedAuthority: String')
        with self.assertRaisesRegex(ValueError, 'exact authenticated EventFacts'):
            obend_object.lower_data_modules(bad_event)
        bad_payload = sources('Bell')
        bad_payload[-1]['source'] = bad_payload[-1]['source'].replace('  payload: Payload',
            '  payload: String').replace('payload: {chord: input.chord}', 'payload: input.chord')
        with self.assertRaisesRegex(ValueError, 'plain record payload'):
            obend_object.lower_data_modules(bad_payload)
        bad_context = sources('Bell')
        bad_context[0]['source'] = bad_context[0]['source'].replace('  inputOrigin: Origin\n', '')
        with self.assertRaisesRegex(ValueError, 'input/context signature'):
            obend_object.lower_data_modules(bad_context)


if __name__ == '__main__': unittest.main()
