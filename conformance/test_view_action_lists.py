"""Source collection values render directly; no scene control flow in the bridge."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import history
import portal
import town_cards
from scene import projection
from syntaxes import obend_object
from conformance.test_typed_view import wire, sequence

SOURCE = '''edition ObjectiveBend 1
record State:
  started: Bool
record Context:
  object: String
  principal: String
  inputOrigin: {kind: String, object: String, command: String, immediatelyPrevious: Bool}
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: String
sum Children:
  nil: {}
  cons: {head: {key: String, label: String, object: String, panel: String}, tail: Children}
sum Action:
  opening: {key: String, text: String, command: String, input: {}, visible: Bool}
  picking: {key: String, text: String, command: String, input: {choice: Nat}, visible: Bool}
sum Actions:
  nil: {}
  cons: {head: Action, tail: Actions}
record Description:
  name: String
  initial: State
  methods: {start: {label: String, fields: {}}, choose: {label: String, fields: {choice: {type: String, minimum: Nat, maximum: Nat}}}}
  panels: {}
def describe() -> Description:
  {name: "A list of gestures", initial: {started: false}, methods: {start: {label: "Start", fields: {}}, choose: {label: "Choose", fields: {choice: {type: "nat", minimum: 0n, maximum: 99n}}}}, panels: {}}
def start(state: State, input: {}, context: Context) -> Decision:
  {accepted: state.started == false, reason: if state.started then "already started" else "", state: {started: true}, result: "opened"}
def choose(state: State, input: {choice: Nat}, context: Context) -> Decision:
  {accepted: state.started, reason: if state.started then "" else "not started", state: state, result: "chosen"}
def view(state: State, panel: String) -> {title: String, prose: String, actions: Actions, children: Children}:
  {title: "A list of gestures", prose: "Choose a gesture.", actions: Actions.cons({head: Action.opening({key: "z-start", text: "Begin", command: "start", input: {}, visible: state.started == false}), tail: Actions.cons({head: Action.picking({key: "z-first", text: "First offered", command: "choose", input: {choice: 12n}, visible: state.started}), tail: Actions.cons({head: Action.picking({key: "a-second", text: "Second offered", command: "choose", input: {choice: 2n}, visible: state.started}), tail: Actions.nil()})})}), children: Children.nil()}
'''


def action(key, visible=True):
    return {'key': key, 'text': key, 'command': 'choose', 'input': {'choice': 0}, 'visible': visible}


def fixture(entries):
    root = {'protocol': {'commands': {'choose': {}}, 'viewProgram': {'profile': projection.DATA_MENU_PROFILE}},
            'state': {}, 'version': 0, 'law': []}
    raw = wire({'title': 'A list', 'prose': 'Choose.'})
    raw['fields'] += [{'name': 'actions', 'value': sequence(entries)}, {'name': 'children', 'value': sequence([])}]
    data, children = projection._typed_menu(raw, root)
    return {'object': 'list', 'mode': 'projection', 'root': root, 'data': data,
            'actions': copy.deepcopy(data['actions']), 'rawData': raw, 'children': children}


class ActionListFraming(unittest.TestCase):
    def test_source_order_survives_canonical_custody(self):
        view = fixture([action('z-first'), action('hidden', False), action('a-second')])
        canonical = json.loads(json.dumps(view, sort_keys=True))
        self.assertEqual(projection.action_order(canonical), ['z-first', 'a-second'])
        self.assertEqual([item['label'] for item in affordances.card(canonical)['actions']], ['z-first', 'a-second'])
        self.assertEqual(projection.action_order(fixture([])), [])

    def test_all_elements_checked_before_visibility_and_never_truncated(self):
        for entry in [action('same', False), {**action('hidden', False), 'command': 'missing'},
                      {**action('hidden', False), 'visible': 0}, {**action('hidden', False), 'extra': 'bad'}]:
            with self.subTest(entry=entry), self.assertRaises(projection.ProjectionError):
                fixture([action('same'), entry])
        self.assertEqual(len(projection.action_order(fixture([action(str(i)) for i in range(64)]))), 64)
        with self.assertRaisesRegex(projection.ProjectionError, '64'):
            fixture([action(str(i)) for i in range(65)])

    def test_malformed_list_and_normalized_forgery_refuse(self):
        view = fixture([action('offered')])
        view['data']['actions']['offered']['input']['choice'] = 9
        with self.assertRaisesRegex(projection.ProjectionError, 'differs'):
            projection.action_order(view)
        view = fixture([action('offered')])
        raw = view['rawData']['fields'][2]['value']
        raw['label'] = 'not-cons'
        with self.assertRaises(projection.ProjectionError):
            projection.action_order(view)


class NativeActionLists(unittest.TestCase):
    def test_unselected_nonserializable_action_alternative_is_rejected(self):
        source = SOURCE.replace('sum Action:\n',
            'sum Action:\n  executable: {key: String, text: String, command: String, input: {callback: Nat -> Nat}, visible: Bool}\n')
        with self.assertRaises(ValueError):
            obend_object.lower_data(source)

    def test_heterogeneous_source_list_reaches_town_and_portal_without_dummy_input(self):
        protocol = obend_object.lower_data(SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            db = home / 'world.json'
            runtime = history.runtime('compiled')
            reply = projection.world.exchange(db, {'op': 'create', 'object': 'gestures', 'principal': 'actor',
                'intent': 'create', 'protocol': protocol, 'law': ['actor']}, profile='compiled')
            self.assertEqual(reply['kind'], 'committed', reply)
            root = reply['data']['root']
            initial = projection.project(root, 'gestures', expected_runtime=runtime)
            self.assertEqual(projection.action_order(initial), ['z-start'])
            self.assertEqual(initial['data']['actions']['z-start']['input'], {})
            request = projection.request(initial, 'z-start', 'actor', 'start')
            reply = projection.world.exchange(db, request, profile='compiled')
            self.assertEqual(reply['kind'], 'committed', reply)
            view = projection.project(reply['data']['root'], 'gestures', expected_runtime=runtime)
            (home / 'manifest.json').write_text(json.dumps({'runtime': runtime}))
            app = portal.Portal(home)
            browser = app.object('gestures')
            book = town_cards.CardBook.create(home / 'cards', issuer_did='did:plc:' + 'a' * 24,
                world_id='urn:test:action-list', runtime=runtime)
            town = book.capture(view, alias='gestures')
            self.assertEqual([a['label'] for a in browser['actions']], ['First offered', 'Second offered'])
            self.assertEqual([a['label'] for a in town['card']['actions']], ['First offered', 'Second offered'])
            saved = book.card('gestures')
            town_request = affordances.request(saved['view'], 'a1', 'actor', 'first', {})
            browser_request = app.prepare({'card': browser['card'], 'action': 'a1'})['wire']
            self.assertEqual(town_request['input'], {'choice': 12})
            self.assertEqual(browser_request['input'], town_request['input'])
            self.assertEqual(saved['view']['rawData'], view['rawData'])
            self.assertEqual(projection.world.exchange(db, town_request, profile='compiled')['kind'], 'committed')


if __name__ == '__main__':
    unittest.main()
