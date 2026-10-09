"""Saved source references bind their original root rather than current observations."""
import copy
from pathlib import Path
import tempfile
import unittest
from conformance import test_containment as containment
from scripts import source_object
from syntaxes import obend_object

ROOT = Path(__file__).resolve().parents[1]

class ExactReferenceReads(unittest.TestCase):
    send = containment.Containment.send
    root = containment.Containment.root
    create = containment.Containment.create
    invoke = containment.Containment.invoke

    @classmethod
    def setUpClass(cls):
        cls.lamp = containment.compile_source('Lamp')
        cls.book = obend_object.lower_data_modules(source_object.read_closure([
            ('ReferenceBook', ROOT / 'conformance/fixtures/preparation/ReferenceBook.obend')]))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.database = self.base / 'world.json'
        self.serial = 0
        self.create('book', self.book, {'profile': 'delvetalk-scoped-law',
            'invoke': {'remember': ['alice']}, 'reprogram': ['curator'], 'law': ['curator']})
        self.create('lamp', self.lamp, {'profile': 'delvetalk-scoped-law',
            'invoke': {'shine': ['alice']}, 'reprogram': ['curator'], 'law': ['curator']})

    def prepare(self, entry):
        self.serial += 1
        return containment.world.query(self.database, {'op': 'prepare-retained',
            'object': 'book', 'root': self.root('book'), 'entry': entry,
            'contribution': {}, 'observations': [{'object': 'lamp', 'root': self.root('lamp'),
                'inspectState': False, 'inspectLaw': False}], 'principal': 'alice',
            'intent': 'prepare-' + str(self.serial)}, profile='compiled')

    def capture(self):
        ready = self.prepare('prepareCapture')
        self.assertEqual(ready['kind'], 'ready', ready)
        self.send(ready['request'], 'alice')

    def test_saved_and_tampered_reference_refuse_fresh_observation_but_current_reference_retries(self):
        self.capture()
        saved = source_object.plain(source_object.state_data(self.root('book')))['saved']
        valid = self.prepare('prepareUse')
        self.assertEqual(valid['kind'], 'ready', valid)
        self.invoke('lamp', 'shine', {})
        with self.assertRaisesRegex(ValueError, 'exact read differs'):
            self.prepare('prepareUse')
        self.assertEqual(source_object.plain(source_object.state_data(self.root('book')))['saved'], saved)
        self.capture()
        actual = source_object.plain(source_object.state_data(self.root('book')))['saved']
        self.invoke('book', 'remember', {**actual, 'key': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'exact read differs'):
            self.prepare('prepareUse')
        self.capture()
        ready = self.prepare('prepareUse')
        self.assertEqual(ready['kind'], 'ready', ready)
        reply = self.send(ready['request'], 'alice')
        self.assertEqual(containment.world.exchange(self.database, ready['request'], profile='compiled'), reply)
        # A retained current root does not carry its old invocation grant.
        current = self.root('lamp')
        law = copy.deepcopy(current['law'])
        law['invoke']['shine'] = []
        self.send({'op': 'law', 'object': 'lamp', 'expected': current, 'law': law})
        self.capture()
        refused = self.prepare('prepareUse')
        self.assertEqual(refused['kind'], 'ready', refused)
        before = self.root('lamp')
        self.send(refused['request'], 'alice', 'refused')
        self.assertEqual(self.root('lamp'), before)
