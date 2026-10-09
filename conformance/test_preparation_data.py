"""Typed source contributions cross native preparation and receiving unchanged."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_offers
from syntaxes import obend_object
from conformance.test_preparation import job, PACKAGE, BINARY
from conformance.test_view_action_lists import SOURCE as BASE
from conformance.test_typed_view import wire

SOURCE = BASE.replace('edition ObjectiveBend 1\n', 'edition ObjectiveBend 1\nimport ./Preparation.obend as P\n', 1) + '''record Contribution:
  choice: Nat
sum TypedEffect:
  invokeData: {object: String, command: String, input: Contribution}
sum TypedEffects:
  nil: {}
  cons: {head: TypedEffect, tail: TypedEffects}
record TypedTurn:
  summary: String
  reads: P.Reads
  calls: TypedEffects
sum TypedPreparation:
  ready: TypedTurn
  question: {message: String, needs: P.Names}
  refused: {message: String}
def prepareTyped(state: State, input: Contribution, observations: P.Observations, context: P.Context) -> TypedPreparation:
  if input.choice == 99n then TypedPreparation.question({message: "Choose a smaller gesture.", needs: P.Names.cons({head: "choice", tail: P.Names.nil()})}) else TypedPreparation.ready({summary: "Choose a typed gesture", reads: P.Reads.cons({head: P.Read.existing({object: "peer"}), tail: P.Reads.nil()}), calls: TypedEffects.cons({head: TypedEffect.invokeData({object: "peer", command: "choose", input: input}), tail: TypedEffects.nil()})})
def prepareForeign(state: State, input: Contribution, observations: P.Observations, context: P.Context) -> TypedPreparation:
  TypedPreparation.ready({summary: "Attempt unobserved access", reads: P.Reads.cons({head: P.Read.existing({object: "secret"}), tail: P.Reads.nil()}), calls: TypedEffects.cons({head: TypedEffect.invokeData({object: "secret", command: "choose", input: input}), tail: TypedEffects.nil()})})
'''


class TypedPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = [{'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
                   {'name': 'Gesture', 'source': SOURCE}]
        with patch.object(obend_object, 'RUNNER', PACKAGE):
            cls.protocol = obend_object.lower_data_modules(modules)
        cls.protocol['preparation'] = {'profile': 'delvetalk-source-preparation-v1', 'sourcePackage': 'resident'}

    def setUp(self):
        self.snapshot = {'objects': {}, 'receipts': []}
        for identity in ('owner', 'peer'):
            protocol = copy.deepcopy(self.protocol)
            if identity == 'peer':
                protocol['commands']['choose']['transition']['inputCodec'] = 'data'
            frame = job(self.snapshot, {'op': 'create', 'object': identity, 'principal': 'actor',
                'intent': 'create:' + identity, 'protocol': protocol, 'law': ['actor']})
            self.assertEqual(frame['reply']['kind'], 'committed', frame)
            self.snapshot = frame['world']
        frame = job(self.snapshot, {'op': 'invoke', 'object': 'peer', 'command': 'start', 'input': {},
            'principal': 'actor', 'intent': 'start:peer', 'expected': self.snapshot['objects']['peer']})
        self.assertEqual(frame['reply']['kind'], 'committed', frame)
        self.snapshot = frame['world']
        self.invitation = {'format': source_offers.FORMAT, 'object': 'owner', 'root': self.snapshot['objects']['owner'],
            'entry': 'prepareTyped', 'contributionCodec': 'data', 'observations': [{'object': 'peer',
                'root': self.snapshot['objects']['peer'], 'inspectState': False, 'inspectLaw': False}],
            'title': 'Typed gestures', 'label': 'Choose', 'fields': []}

    def prepare(self, data, **changes):
        return source_offers.prepare_value({**self.invitation, **changes}, 'actor', 'typed:choice', data, binary=BINARY)

    def test_typed_contribution_and_effect_are_checked_and_admitted(self):
        data = wire({'choice': 12})
        outcome = self.prepare(data)
        self.assertEqual(outcome['request']['calls'][0]['input'], data)
        frame = job(self.snapshot, outcome['request'])
        self.assertEqual(frame['reply']['kind'], 'committed', frame)
        self.assertEqual(job(frame['world'], outcome['request']), frame)
        unauthorized = {**outcome['request'], 'principal': 'outsider', 'intent': 'typed:unauthorized'}
        refusal = job(self.snapshot, unauthorized)
        self.assertEqual(refusal['reply']['kind'], 'refused')
        self.assertEqual(refusal['world']['objects'], self.snapshot['objects'])
        denied = copy.deepcopy(self.snapshot)
        denied['objects']['peer']['law'] = []
        refused = job(denied, outcome['request'])
        self.assertEqual(refused['reply']['kind'], 'refused')
        self.assertEqual(refused['world']['objects'], denied['objects'])

    def test_source_question_and_type_mismatches_have_no_effect(self):
        self.assertEqual(self.prepare(wire({'choice': 99})), {'kind': 'question',
            'message': 'Choose a smaller gesture.', 'needs': ['choice']})
        for data in (wire({'choice': 'twelve'}), {'choice': 12}, wire({'choice': 12, 'extra': True})):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.prepare(data)
        with self.assertRaises(ValueError):
            self.prepare(wire({'choice': 12}), contributionCodec='value')

    def test_typed_mode_does_not_authorize_unobserved_roots_or_public_form_data(self):
        with self.assertRaisesRegex(ValueError, 'not observed'):
            self.prepare(wire({'choice': 12}), entry='prepareForeign')
        with self.assertRaisesRegex(ValueError, 'explicit DataWire'):
            source_offers.prepare_fields(self.invitation, 'actor', 'typed:form', {})


if __name__ == '__main__':
    unittest.main()
