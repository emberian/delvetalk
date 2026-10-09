"""Explicit typed source binding, native schema equivalence and legacy separation."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import translate

spec = importlib.util.spec_from_file_location('data_object_adapter', ROOT / 'syntaxes/obend_object.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

SOURCE = '''edition ObjectiveBend 1
record Child:
  key: String
  label: String
  object: String
  panel: String
sum Children:
  nil: {}
  cons: {head: Child, tail: Children}
record State:
  entries: Children
record Origin:
  kind: String
  object: String
  command: String
  program: String
  immediatelyPrevious: Bool
record Context:
  object: String
  principal: String
  inputOrigin: Origin
record Input:
  object: String
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: String
record Field:
  type: String
  minLength: Nat
  maxLength: Nat
record Method:
  label: String
  fields: {object: Field}
record Description:
  name: String
  initial: State
  methods: {add: Method}
  panels: {}
record Action:
  visible: Bool
  text: String
  command: String
  input: {}
record View:
  title: String
  prose: String
  actions: {add: Action}
  children: Children
def describe() -> Description:
  {name: "A typed shelf", initial: {entries: Children.nil()}, methods: {add: {label: "Exhibit", fields: {object: {type: "string", minLength: 1, maxLength: 64}}}}, panels: {}}
def add(state: State, input: Input, context: Context) -> Decision:
  {accepted: true, reason: "", state: {entries: Children.cons({head: {key: input.object, label: "An exhibit", object: input.object, panel: "main"}, tail: state.entries})}, result: "Exhibited"}
def view(state: State, panel: String) -> View:
  {title: "A typed shelf", prose: "Choose an exhibit.", actions: {add: {visible: true, text: "Exhibit", command: "add", input: {}}}, children: state.entries}
'''


class TypedSourceBindingTests(unittest.TestCase):
    def test_explicit_typed_description_preserves_variant_model_and_menu(self):
        artifact = translate.translate('objective-bend-object', SOURCE.encode())
        protocol = artifact['lowered']
        self.assertEqual(protocol['initial']['model']['format'], 'delvetalk-compact-state')
        self.assertEqual(protocol['commands']['add']['transition']['profile'], 'delvetalk-source-transition')
        self.assertEqual(protocol['viewProgram']['profile'], 'delvetalk-obend-data-menu-v1')
        self.assertEqual(artifact['source']['text'], SOURCE)

    def test_initial_nil_does_not_hide_incompatible_method_state(self):
        bad = SOURCE.replace('record State:', 'sum WrongChildren:\n  nil: {}\n  cons: {head: Nat, tail: WrongChildren}\nrecord WrongState:\n  entries: WrongChildren\nrecord State:')
        bad = bad.replace('def add(state: State,', 'def add(state: WrongState,')
        bad = bad.replace('tail: state.entries', 'tail: Children.nil()')
        with self.assertRaisesRegex(ValueError, 'incompatible serializable state schema'):
            translate.translate('objective-bend-object', bad.encode())

    def test_unselected_executable_alternative_and_wrong_children_schema_refuse(self):
        hidden = SOURCE.replace('  nil: {}\n', '  nil: {}\n  executable: Nat -> Nat\n', 1)
        with self.assertRaises(ValueError): translate.translate('objective-bend-object', hidden.encode())
        wrong = SOURCE.replace('  panel: String', '  panel: Nat').replace('panel: "main"', 'panel: 0')
        with self.assertRaisesRegex(ValueError, 'view children.*incompatible'):
            translate.translate('objective-bend-object', wrong.encode())



if __name__ == '__main__': unittest.main()
