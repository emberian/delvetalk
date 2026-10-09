"""Actual pure source preparation, exact captured reads, and later admission."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import source_offers
import world
from syntaxes import obend_object
from conformance.test_view_invitations import SOURCE as BASE

BINARY = Path(os.environ.get('DELVETALK_PREPARATION_BINARY', ROOT / '.lake/build/bin/delvetalk-compiled'))
PACKAGE = Path(os.environ.get('DELVETALK_PACKAGE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
SOURCE = BASE[:BASE.index('def prepareGesture(')] + '''def prepareGesture(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  let gesture: String = P.text(P.get(contribution, "gesture"))
  if gesture == "" then P.Preparation.question({message: "Which gesture would you like?", needs: P.Names.cons({head: "gesture", tail: P.Names.nil()})}) else if gesture == "refuse" then P.Preparation.refused({message: "Choose another gesture."}) else P.Preparation.ready({summary: textConcat("Offer ", gesture), reads: P.Reads.cons({head: P.Read.existing({object: "peer"}), tail: P.Reads.nil()}), calls: P.Effects.cons({head: P.Effect.invoke({object: "peer", command: "touch", input: P.oneField("gesture", P.Value.text({value: gesture}))}), tail: P.Effects.nil()})})
def prepareUnobserved(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  P.Preparation.ready({summary: "Unobserved", reads: P.Reads.cons({head: P.Read.existing({object: "secret"}), tail: P.Reads.nil()}), calls: P.Effects.cons({head: P.Effect.observe({object: "secret"}), tail: P.Effects.nil()})})
def prepareData(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  P.Preparation.ready({summary: "Pass exact observed data", reads: P.Reads.cons({head: P.Read.existing({object: "peer"}), tail: P.Reads.nil()}), calls: P.Effects.cons({head: P.Effect.invoke({object: "peer", command: "touch", input: P.observation(observations, "peer").state}), tail: P.Effects.nil()})})
'''


SOURCE += """def prepareOwnerArgument(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  if P.observation(observations, context.object).object == "" then P.Preparation.question({message: "Owner state is already an explicit argument.", needs: P.Names.nil()}) else P.Preparation.refused({message: "Owner was explicitly observed."})
"""


SOURCE += """def prepareManufactured(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  P.Preparation.ready({summary: "Attempt a manufactured retained value", reads: P.Reads.cons({head: P.Read.existing({object: "peer"}), tail: P.Reads.nil()}), calls: P.Effects.cons({head: P.Effect.invoke({object: "peer", command: "touch", input: P.oneField("migration", P.Value.retained({object: P.text(P.get(contribution, "object")), key: P.text(P.get(contribution, "key"))}))}), tail: P.Effects.nil()})})
"""


def job(snapshot, request):
    process = subprocess.run([BINARY], input=(world.wire_dumps({'world': snapshot, 'request': request}) + '\n').encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return world.wire_loads(process.stdout.decode())


class NativePreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = [{'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
                   {'name': 'Gallery', 'source': SOURCE}]
        with patch.object(obend_object, 'RUNNER', PACKAGE):
            cls.protocol = obend_object.lower_data_modules(modules)

    def setUp(self):
        self.snapshot = {'objects': {}, 'receipts': []}
        peer = {'profile': 'delvetalk-local-v1', 'initial': {'touched': ''},
                'commands': {'touch': {'require': [], 'set': {'touched': ['input', 'gesture']},
                                       'result': ['input', 'gesture'], 'outbox': []}}}
        for identity, protocol, law in [('gallery', self.protocol, ['actor']), ('peer', peer, ['actor'])]:
            frame = job(self.snapshot, {'op': 'create', 'object': identity, 'principal': 'actor',
                'intent': 'create:' + identity, 'protocol': protocol, 'law': law})
            self.assertEqual(frame['reply']['kind'], 'committed', frame)
            self.snapshot = frame['world']
        self.root = self.snapshot['objects']['gallery']
        self.peer = self.snapshot['objects']['peer']
        self.invitation = {'format': source_offers.FORMAT, 'object': 'gallery', 'root': self.root,
            'entry': 'prepareGesture', 'observations': [{'object': 'peer', 'root': self.peer, 'inspectState': False, 'inspectLaw': False}],
            'title': 'Gallery', 'label': 'Offer a gesture', 'fields': []}

    def prepare(self, contribution, principal='actor', entry='prepareGesture'):
        invitation = {**self.invitation, 'entry': entry}
        return source_offers.prepare_value(invitation, principal, 'gesture:1', contribution, binary=BINARY)

    def test_source_questions_and_refusals_are_read_only(self):
        before = copy.deepcopy(self.snapshot)
        self.assertEqual(self.prepare({}), {'kind': 'question', 'message': 'Which gesture would you like?', 'needs': ['gesture']})
        self.assertEqual(self.prepare({'gesture': 'refuse'}), {'kind': 'refused', 'message': 'Choose another gesture.'})
        self.assertEqual(self.snapshot, before)

    def test_ready_anchors_owner_and_peer_then_current_authority_decides(self):
        outcome = self.prepare({'gesture': 'wave'})
        self.assertEqual(outcome['summary'], 'Offer wave')
        request = outcome['request']
        self.assertEqual(request['reads'], {'gallery': self.root, 'peer': self.peer})
        self.assertEqual(request['calls'], [{'object': 'peer', 'command': 'touch', 'input': {'gesture': 'wave'}}])
        admitted = job(self.snapshot, request)
        self.assertEqual(admitted['reply']['kind'], 'committed', admitted)
        self.assertEqual(admitted['world']['objects']['peer']['state']['touched'], 'wave')
        denied = job(self.snapshot, self.prepare({'gesture': 'wave'}, principal='intruder')['request'])
        self.assertEqual(denied['reply']['kind'], 'refused')
        self.assertEqual(denied['world']['objects'], self.snapshot['objects'])
        changed = copy.deepcopy(self.snapshot)
        changed['objects']['gallery']['version'] += 1
        stale = job(changed, request)
        self.assertEqual(stale['reply']['kind'], 'refused')
        retry = job(admitted['world'], request)
        self.assertEqual(retry['reply'], admitted['reply'])
        self.assertEqual(retry['world'], admitted['world'])

    def test_unobserved_read_and_tampered_capture_refuse(self):
        with self.assertRaisesRegex(ValueError, 'not observed'):
            self.prepare({}, entry='prepareUnobserved')
        request = {'op': 'prepare', 'object': 'gallery', 'root': self.root, 'entry': 'prepareGesture',
                   'principal': 'actor', 'intent': 'tampered', 'contribution': {},
                   'observations': [{'object': 'peer', 'root': {**self.peer, 'version': 8}, 'inspectState': False, 'inspectLaw': False}]}
        frame = job(self.snapshot, request)
        self.assertIn('differs', frame['error'])

    def test_owner_binding_does_not_invent_a_source_observation(self):
        outcome = self.prepare({}, entry='prepareOwnerArgument')
        self.assertEqual(outcome['kind'], 'question')
        invitation = {**self.invitation, 'entry': 'prepareOwnerArgument',
                      'observations': [{'object': 'gallery', 'root': self.root, 'inspectState': False, 'inspectLaw': False}]}
        outcome = source_offers.prepare_value(invitation, 'actor', 'explicit-owner', {}, binary=BINARY)
        self.assertEqual(outcome['kind'], 'refused')
        invitation['observations'].append({'object': 'gallery', 'root': self.root, 'inspectState': False, 'inspectLaw': False})
        with self.assertRaisesRegex(ValueError, 'duplicate preparation observation'):
            source_offers.prepare_value(invitation, 'actor', 'duplicate-owner', {}, binary=BINARY)

    def test_retained_wire_depth_uses_admitted_ceiling_not_contribution_depth(self):
        value = {'leaf': 'exact retained data'}
        for _ in range(80):
            value = {'wrapper': value}
        observed = {**self.peer, 'state': value}
        invitation = {**self.invitation, 'entry': 'prepareData',
                      'observations': [{'object': 'peer', 'root': observed, 'inspectState': False, 'inspectLaw': False}]}
        outcome = source_offers.prepare_value(invitation, 'actor', 'retained-wire', {}, binary=BINARY)
        self.assertEqual(outcome['request']['calls'][0]['input'], value)
        with self.assertRaisesRegex(ValueError, 'nesting capacity'):
            source_offers.prepare_value(self.invitation, 'actor', 'authored-too-deep', value, binary=BINARY)
        invitation['observations'][0]['inspectState'] = True
        with self.assertRaisesRegex(ValueError, 'typed data nesting capacity'):
            source_offers.prepare_value(invitation, 'actor', 'inspect-too-deep', {}, binary=BINARY)

    def test_manufactured_and_foreign_retained_values_refuse(self):
        with self.assertRaisesRegex(ValueError, 'differs from captured root'):
            self.prepare({'object': 'peer', 'key': 'manufactured'}, entry='prepareManufactured')
        with self.assertRaisesRegex(ValueError, 'not held'):
            self.prepare({'object': 'foreign', 'key': 'even-a-valid-global-locator'}, entry='prepareManufactured')
        # Physical standalone conversion supplies no captured authority/table.
        value = {'tag': 'variant', 'label': 'retained', 'payload': {'tag': 'record', 'fields': [
            {'name': 'object', 'value': {'tag': 'label', 'value': 'peer'}},
            {'name': 'key', 'value': {'tag': 'label', 'value': 'manufactured'}}]}}
        reply = job({'objects': {}, 'receipts': []},
                    {'op': 'value-codec', 'direction': 'decode', 'values': [value]})
        self.assertIn('not held', reply['error'])

    def test_generic_value_preserves_decimal_null_and_array_without_recipes(self):
        from decimal import Decimal
        observed = {**self.peer, 'state': {'gesture': 'wave', 'decimal': Decimal('1.00'), 'missing': None,
                                          'list': [True, Decimal('-0.250'), 'x']}}
        invitation = {**self.invitation, 'entry': 'prepareData', 'observations': [{'object': 'peer', 'root': observed, 'inspectState': False, 'inspectLaw': False}]}
        outcome = source_offers.prepare_value(invitation, 'actor', 'exactdata', {}, binary=BINARY)
        actual = outcome['request']['calls'][0]['input']
        self.assertEqual(actual, observed['state'])
        self.assertEqual(actual['decimal'].as_tuple(), observed['state']['decimal'].as_tuple())
        self.assertEqual(actual['list'][1].as_tuple(), observed['state']['list'][1].as_tuple())


if __name__ == '__main__':
    unittest.main()
