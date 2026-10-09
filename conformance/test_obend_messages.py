"""Actual native authored effect/receive binding with explicit source dependencies."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'syntaxes'))
import obend_object


def sources(name):
    return [{'name': n, 'source': (ROOT / 'world/lib/prelude' / (n + '.obend')).read_text()}
            for n in ('List', 'Abi', 'Preparation', 'Encounter', 'Emissions')] + [{'name': name, 'source':
                (ROOT / 'protocols/resident-messages' / (name + '.obend')).read_text()}]


class SourceMessageBindingTests(unittest.TestCase):
    def test_real_bell_and_door_source_bind_typed_message_profiles(self):
        for name, command, flags in (('Bell', 'play', {'emit': True, 'receive': False}),
                                      ('Door', 'hear', {'emit': True, 'receive': True}),
                                      ('Lantern', 'glow', {'emit': False, 'receive': True})):
            with self.subTest(resident=name):
                modules = sources(name)
                protocol = obend_object.lower_data_modules(modules)
                transition = protocol['commands'][command]['transition']
                self.assertEqual(transition['profile'], 'delvetalk-source-transition')
                self.assertEqual(transition['messages'], flags)
                self.assertEqual(next(iter(protocol['sourcePackages'].values()))['modules'], modules)
                self.assertEqual(set(protocol['initial']), {'model'})
                self.assertEqual(protocol['viewProgram']['profile'], 'delvetalk-obend-data-menu-v1')

    def test_receive_facts_and_emission_payload_have_exact_checked_abi(self):
        bad_event = sources('Door')
        next(item for item in bad_event if item['name'] == 'Emissions')['source'] = next(item for item in bad_event if item['name'] == 'Emissions')['source'].replace('  originatingPrincipal: String',
            '  originatingPrincipal: String\n  claimedAuthority: String')
        with self.assertRaisesRegex(ValueError, 'CausalEvent|EventFacts|event'):
            obend_object.lower_data_modules(bad_event)
        bad_payload = sources('Bell')
        next(item for item in bad_payload if item['name'] == 'Emissions')['source'] = next(item for item in bad_payload if item['name'] == 'Emissions')['source'].replace('  payload: P.Value', '  payload: String')
        bad_payload[-1]['source'] = bad_payload[-1]['source'].replace('payload: P.oneField("chord", P.Value.text({value: input.chord}))', 'payload: input.chord')
        with self.assertRaisesRegex(ValueError, 'emissions|payload'):
            obend_object.lower_data_modules(bad_payload)
        bad_context = sources('Bell')
        next(item for item in bad_context if item['name'] == 'Abi')['source'] = next(item for item in bad_context if item['name'] == 'Abi')['source'].replace('  inputOrigin: Origin\n', '')
        with self.assertRaisesRegex(ValueError, 'context signature'):
            obend_object.lower_data_modules(bad_context)


if __name__ == '__main__': unittest.main()
