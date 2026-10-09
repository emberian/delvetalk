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


def job(snapshot, request):
    process = subprocess.run([BINARY], input=(world.wire_dumps({'world': snapshot, 'request': request}) + '\n').encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return world.wire_loads(process.stdout.decode())


class NativePreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = [{'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
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
            'entry': 'prepareGesture', 'observations': [{'object': 'peer', 'root': self.peer}],
            'title': 'Gallery', 'label': 'Offer a gesture', 'fields': []}

    def prepare(self, contribution, principal='actor', entry='prepareGesture'):
        invitation = {**self.invitation, 'entry': entry}
        return source_offers.prepare(invitation, principal, 'gesture:1', contribution, binary=BINARY)

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
                   'observations': [{'object': 'peer', 'root': {**self.peer, 'version': 8}}]}
        frame = job(self.snapshot, request)
        self.assertIn('differs', frame['error'])

    def test_generic_value_preserves_decimal_null_and_array_without_recipes(self):
        from decimal import Decimal
        observed = {**self.peer, 'state': {'gesture': 'wave', 'decimal': Decimal('1.00'), 'missing': None,
                                          'list': [True, Decimal('-0.250'), 'x']}}
        invitation = {**self.invitation, 'entry': 'prepareData', 'observations': [{'object': 'peer', 'root': observed}]}
        outcome = source_offers.prepare(invitation, 'actor', 'exactdata', {}, binary=BINARY)
        actual = outcome['request']['calls'][0]['input']
        self.assertEqual(actual, observed['state'])
        self.assertEqual(actual['decimal'].as_tuple(), observed['state']['decimal'].as_tuple())
        self.assertEqual(actual['list'][1].as_tuple(), observed['state']['list'][1].as_tuple())


if __name__ == '__main__':
    unittest.main()
