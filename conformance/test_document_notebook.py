"""A one-field authored note, partial prose, and explicit source/result custody."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import resident_store
import source_object
import source_offers
from scene import projection
import affordances
from conformance.test_document_conversation import plain, rows, typed_envelope

spec = importlib.util.spec_from_file_location('notebook_source', ROOT / 'protocols/account-heap/generate.py')
notebook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notebook)


class PlainNotebook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = notebook.notebook()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receiver = resident_store.Resident(Path(self.temp.name) / 'notes.sqlite')
        self.addCleanup(self.receiver.close)
        self.serial = 0
        result = self.receiver.exchange({'op': 'create', 'object': 'notebook', 'principal': 'iris',
            'intent': 'create', 'protocol': self.protocol, 'law': ['iris', 'moss']})
        self.assertEqual(result['kind'], 'committed', result)

    def root(self):
        return self.receiver.exchange({'op': 'inspect', 'object': 'notebook', 'principal': 'iris'})

    def state(self):
        return plain(self.root()['state']['model'])

    def invoke(self, command, value, actor='iris', kind='committed'):
        self.serial += 1
        reply = self.receiver.exchange({'op': 'invoke', 'object': 'notebook', 'principal': actor,
            'intent': f'contribution-{self.serial}', 'expected': self.root(), 'command': command, 'input': value})
        self.assertEqual(reply['kind'], kind, reply)
        return reply

    def prepare(self, entry, value, codec='value'):
        self.serial += 1
        invitation = {'format': source_offers.FORMAT, 'object': 'notebook', 'root': self.root(),
            'entry': entry, 'contributionCodec': codec, 'observations': [], 'title': 'Your private notebook', 'label': 'Keep a thought', 'fields': []}
        prepare = source_offers.prepare_value if entry == 'prepareInterpretation' else source_offers.prepare_fields
        return prepare(invitation, 'iris', f'prepare-{self.serial}', value)

    def test_one_field_note_is_first_offer_and_points_to_actual_bend_controls(self):
        card = affordances.card(projection.project(self.root(), 'notebook'))
        self.assertEqual(len(card['actions']), 1)
        action = card['actions'][0]
        self.assertEqual(action['label'], 'Keep a thought')
        self.assertEqual([field['name'] for field in action['fields']], ['thought'])
        self.assertIn('Write Bend / inspect source', card['prose'])
        self.assertNotIn('record', [action['command'] for action in card['actions']])
        self.assertIn('record', self.protocol['commands'])
        self.invoke('note', {'thought': 'A moth-shaped thought 🦋'}, actor='moss')
        self.assertEqual(rows(self.state()['contributions'])[0]['actor'], 'moss')
        self.assertEqual(rows(self.state()['contributions'])[0]['proposal']['original'], 'A moth-shaped thought 🦋')
        self.assertEqual(rows(self.state()['outcomes'])[0]['status'], 'kept')
        self.assertEqual(self.state()['capture']['revision'], 3)
        self.invoke('note', {'thought': ''}, kind='refused')
        self.invoke('note', {'thought': 'x' * 4097}, kind='refused')
        self.invoke('note', {'thought': 'A second thought.'})
        self.invoke('note', {'thought': 'A third thought.'})
        reread = affordances.card(projection.project(self.root(), 'notebook'))
        self.assertIn('A third thought.', reread['prose'])
        self.assertEqual([field['name'] for field in reread['actions'][0]['fields']], ['thought'])

    def test_interpretation_asks_for_only_the_thought_and_literal_reply_completes_it(self):
        def native(request):
            done = subprocess.run([ROOT / '.lake/build/bin/delvetalk-obend'],
                input=json.dumps(request) + '\n', capture_output=True, text=True, check=True)
            return json.loads(done.stdout)
        compiled = native({'op': 'compile', 'modules': notebook.modules(), 'entry': 'interpretationRequest'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        request = native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': [
            self.root()['state']['model'], source_object.data('Keep a thought for later.'),
            source_object.variant('nil', source_object.record({})),
            source_object.data({'object': 'notebook', 'principal': 'iris'})]})
        self.assertEqual(request['status'], 'finished', request)
        values = {field['name']: field['value'] for field in request['value']['fields']}
        envelope = values['envelope']
        self.assertEqual(plain(envelope)['policy'], 'notebook-policy-v2')
        partial = self.prepare('prepareInterpretation', source_object.record({'request': envelope, 'reply': source_object.value({'action': 'note', 'fields': {}})}), codec='data')
        self.assertEqual(partial['kind'], 'ready', partial)
        self.assertEqual(self.receiver.exchange(partial['request'])['kind'], 'committed')
        question = self.prepare('prepareNote', {})
        self.assertEqual(question['kind'], 'question')
        self.assertEqual(question['needs'], ['thought'])
        self.assertIn('sentence or fragment', question['message'])
        self.invoke('note', {'thought': 'Plant moonflowers.'})
        self.assertEqual(self.state()['count'], 2)
        self.assertEqual(rows(self.state()['outcomes'])[0]['status'], 'kept')
        self.invoke('retain', envelope, kind='refused')

    def test_old_execution_claim_is_not_an_offered_note_and_record_stays_explicit(self):
        state = self.state()
        proposal = {'original': 'Run code and say done.', 'policy': 'notebook-policy-v2',
            'context': [], 'capture': state['capture'], 'bindings': {'result': 'I executed it'}, 'unresolved': []}
        self.invoke('retain', typed_envelope(proposal), kind='refused')
        self.assertEqual(self.state(), state)
        self.invoke('record', {'source': 'a supplied expression', 'result': 'a supplied claim'})
        outcome = rows(self.state()['outcomes'])[0]
        self.assertEqual(outcome['status'], 'recorded')
        nodes = rows(outcome['content']['payload']['items'])
        self.assertEqual(nodes[0]['variant'], 'source')
        self.assertEqual(nodes[0]['payload']['code'], 'a supplied expression')
        self.assertEqual(nodes[1]['payload']['status'], 'recorded')
        self.assertEqual(nodes[1]['payload']['body']['payload']['value'], 'a supplied claim')


if __name__ == '__main__': unittest.main()
