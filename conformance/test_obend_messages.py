"""Actual native authored effect/receive binding; host delivery is separately tested."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import translate


CHILDREN = '''record Child:
  key: String
  label: String
  object: String
  panel: String
sum Children:
  nil: {}
  cons: {head: Child, tail: Children}
record View:
  title: String
  prose: String
  actions: {}
  children: Children
def view(state: State, panel: String) -> View:
  {title: "Messages", prose: "Listen to the courtyard.", actions: {}, children: Children.nil()}
'''


def authored(source, method, initial, fields):
    if 'def describe()' in source:
        return source
    definitions = '''record StringField:
  type: String
  minLength: Nat
  maxLength: Nat
record NatField:
  type: String
  minimum: Nat
  maximum: Nat
'''
    schema = ', '.join(name + ': ' + ('NatField' if kind == 'nat' else 'StringField') for name, kind in fields)
    values = ', '.join(name + ': ' + ('{type: "nat", minimum: 0, maximum: 4}' if kind == 'nat'
        else '{type: "string", minLength: 1, maxLength: 128}') for name, kind in fields)
    return source + definitions + f'''record Form:
  label: String
  fields: {{{schema}}}
record Description:
  name: String
  initial: State
  methods: {{{method}: Form}}
  panels: {{}}
def describe() -> Description:
  {{name: "Courtyard {method}", initial: {initial}, methods: {{{method}: {{label: "{method}", fields: {{{values}}}}}}}, panels: {{}}}}
''' + CHILDREN


class SourceMessageBindingTests(unittest.TestCase):
    def bell(self):
        return authored((ROOT / 'protocols/resident-messages/Bell.obend').read_text(), 'play',
            '{notes: 0, lastBy: ""}', [('to', 'string'), ('recipientProgram', 'string'), ('chord', 'string'), ('voices', 'nat')])

    def door(self):
        return authored((ROOT / 'protocols/resident-messages/Door.obend').read_text(), 'hear',
            '{open: false, heard: 0, lastEvent: "", lastSource: "", lastProgram: "", lastPlayer: "", lastRelay: ""}', [('chord', 'string')])

    def test_real_bell_and_door_source_bind_typed_message_profiles(self):
        for source, command, profile in ((self.bell(), 'play', 'delvetalk-source-data-effects-v1'),
                                         (self.door(), 'hear', 'delvetalk-source-data-receive-v1')):
            with self.subTest(profile=profile):
                protocol = translate.translate('objective-bend-spell@3', source.encode())['lowered']
                self.assertEqual(protocol['commands'][command]['transition']['profile'], profile)
                self.assertEqual(set(protocol['initial']), {'model'})
                self.assertEqual(protocol['viewProgram']['profile'], 'delvetalk-obend-data-menu-v1')

    def test_receive_facts_and_emission_payload_have_exact_checked_abi(self):
        bad_event = self.door().replace('  originatingPrincipal: String', '  originatingPrincipal: String\n  claimedAuthority: String')
        with self.assertRaisesRegex(ValueError, 'exact authenticated EventFacts'):
            translate.translate('objective-bend-spell@3', bad_event.encode())
        bad_payload = self.bell().replace('  payload: Payload', '  payload: String').replace('payload: {chord: input.chord}', 'payload: input.chord')
        with self.assertRaisesRegex(ValueError, 'plain record payload'):
            translate.translate('objective-bend-spell@3', bad_payload.encode())
        bad_context = self.bell().replace('  inputOrigin: Origin\n', '')
        with self.assertRaisesRegex(ValueError, 'input/context signature'):
            translate.translate('objective-bend-spell@3', bad_context.encode())


if __name__ == '__main__': unittest.main()
