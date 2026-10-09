"""Invitation requests are checked against the explicit source prelude schema."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('requests_adapter', ROOT / 'syntaxes/obend_object.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
SOURCE = '''edition ObjectiveBend 1
import ./Preparation.obend as P
import ./Encounter.obend as E
record State:
  ready: Bool
record Form:
  label: String
  fields: {}
record Origin:
  kind: String
  object: String
  command: String
  immediatelyPrevious: Bool
record Context:
  object: String
  principal: String
  inputOrigin: Origin
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: {}
def touch(state: State, input: {}, context: Context) -> Decision:
  {accepted: true, reason: "", state: state, result: {}}
record Description:
  name: String
  initial: State
  methods: {touch: Form}
  panels: {main: String}
def describe() -> Description:
  {name: "Requests", initial: {ready: true}, methods: {touch: {label: "Touch", fields: {}}}, panels: {main: "Main"}}
record Invitation:
  visible: Bool
  text: String
  prepare: String
  fields: {}
  observations: P.Requests
record View:
  title: String
  prose: String
  actions: {}
  children: E.Children
  invitations: {inspect: Invitation}
def view(state: State, panel: String) -> View:
  {title: "Requests", prose: "Inspect a peer", actions: {}, children: E.Children.nil(), invitations: {inspect: {visible: state.ready, text: "Inspect", prepare: "prepareInspect", fields: {}, observations: P.Requests.nil()}}}
'''


class RequestsBinding(unittest.TestCase):
    def test_requests_bind_and_obsolete_string_names_refuse(self):
        modules = [{'name': name, 'source': (ROOT / 'world/lib/prelude' / (name + '.obend')).read_text()}
                   for name in ('Preparation', 'Encounter')]
        result = adapter.lower_data_modules(modules + [{'name': 'Main', 'source': SOURCE}])
        self.assertIn('viewProgram', result)
        with self.assertRaisesRegex(ValueError, 'invitation observations'):
            adapter.lower_data_modules(modules + [{'name': 'Main', 'source': SOURCE.replace('P.Requests', 'P.Names')}])


if __name__ == '__main__': unittest.main()
