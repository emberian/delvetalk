"""One retained Bend intention accepts forms and attributed interpretation proposals."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from syntaxes import obend_object
from scene import projection
import source_offers
import resident_store


def fixture_law(protocol, principals=('iris', 'moss')):
    return {'profile': 'delvetalk-scoped-law',
            'invoke': {name: list(principals) for name in protocol['commands']},
            'read': 'public', 'reprogram': list(principals), 'law': list(principals)}


def modules(evening=False):
    paths = [('Abi', 'world/lib/prelude/Abi.obend'),
             ('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'),
             ('Encounter', 'world/lib/prelude/Encounter.obend'),
             ('Document', 'world/lib/document/Document.obend'),
             ('Reflection', 'world/lib/prelude/Reflection.obend'),
             ('Writing', 'protocols/source-desk/Writing.obend'),
             ('Interpretation', 'protocols/interpretation/Interpretation.obend'),
             ('Conversation', 'protocols/conversation/Conversation.obend'),
             ('ModelEncounter', 'protocols/interpretation/Encounter.obend'),
             ('ConversationModel', 'protocols/interpretation/ConversationModel.obend'),
             ('Notebook', 'protocols/conversation/Notebook.obend'),
             ('MothNotebook', 'protocols/conversation/MothNotebook.obend')]
    if evening:
        paths.append(('EveningNotebook', 'protocols/conversation/EveningNotebook.obend'))
    return [{'name': name, 'source': (ROOT / path).read_text()} for name, path in paths]


def plain(value):
    if value['tag'] == 'record':
        return {field['name']: plain(field['value']) for field in value['fields']}
    if value['tag'] == 'variant':
        return {'variant': value['label'], 'payload': plain(value['payload'])}
    if value['tag'] == 'natural': return int(value['value'])
    return value['value']


def rows(value):
    result = []
    while value['variant'] == 'cons':
        result.append(value['payload']['head'])
        value = value['payload']['tail']
    return result


def typed_envelope(value):
    """Test-fixture construction only; production retains native-produced wire."""
    import source_object as source
    def linked(values):
        result = source.variant('nil', source.record({}))
        for item in reversed(values):
            result = source.variant('cons', source.record({'head': item, 'tail': result}))
        return result
    def bindings(items):
        encoded = source.value(items)
        return next(field['value'] for field in encoded['payload']['fields'] if field['name'] == 'fields')
    def observations(items):
        return linked([source.record({name: source.value(item) if name in ('state', 'law') else source.data(item)
                                      for name, item in entry.items()}) for entry in items])
    encoders = {'bindings': bindings, 'context': observations,
                'unresolved': lambda items: linked([source.data(item) for item in items])}
    return source.record({key: encoders.get(key, source.data)(item) for key, item in value.items()})


class DocumentConversation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = obend_object.lower_data_modules(modules())
        cls.evening = obend_object.lower_data_modules(modules(True))
        cls.moth = obend_object.lower_data_modules(modules()[:1] + [modules()[2]] + [{'name': 'Moth', 'source': (ROOT / 'protocols/conversation/Moth.obend').read_text()}])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'conversation.sqlite'
        self.receiver = resident_store.Resident(self.path)
        self.addCleanup(lambda: self.receiver.close())
        self.serial = 0
        self.exchange({'op': 'create', 'object': 'conversation', 'principal': 'iris',
            'intent': 'create', 'protocol': self.protocol, 'law': fixture_law(self.protocol)})
        for identity in ('moth:amber', 'moth:silver'):
            self.exchange({'op': 'create', 'object': identity, 'principal': 'iris', 'intent': 'create-' + identity, 'protocol': self.moth, 'law': fixture_law(self.moth)})

    def exchange(self, request, kind='committed'):
        result = self.receiver.exchange(request)
        self.assertEqual(result['kind'], kind, result)
        return result

    def root(self, identity='conversation'):
        return self.receiver.exchange({'op': 'inspect', 'object': identity, 'principal': 'reader'})

    def state(self):
        return plain(self.root()['state']['model'])['conversation']

    def request(self, method, value, actor='iris', expected=None):
        self.serial += 1
        return {'op': 'invoke', 'object': 'conversation', 'principal': actor,
            'intent': f'contribution-{self.serial}', 'expected': self.root() if expected is None else expected,
            'command': method, 'input': value}

    def answer(self, target='', recipient='', original='a literal field', actor='iris'):
        return self.exchange(self.request('answer', {'original': original, 'target': target, 'recipient': recipient}, actor))

    def interpretation(self, target='', recipient='', original='lend the amber moth', **changes):
        return {'original': original, 'target': target, 'recipient': recipient,
                'token': 'resolve', 'policy': 'lending-policy-v2', **changes}

    def invitation(self):
        root = self.root()
        return {'format': source_offers.FORMAT, 'object': 'conversation', 'root': root,
                'entry': 'prepareResolve',
                'observations': [{'object': name, 'root': self.root(name), 'inspectState': False, 'inspectLaw': False} for name in ('moth:amber', 'moth:silver')], 'title': 'Lending conversation', 'label': 'Finish choosing', 'fields': []}

    def test_literal_and_interpretation_share_partial_state_attributed_history_and_completion(self):
        self.answer(recipient='moss', original='For Moss, please.')
        self.assertEqual(rows(self.state()['unresolved']), ['target'])
        outcome = source_offers.prepare(self.invitation(), 'iris', 'question', {})
        self.assertEqual(outcome['kind'], 'question')
        self.assertEqual(outcome['needs'], ['target'])
        self.exchange(self.request('interpret', self.interpretation(target='moth:amber'), 'moss'))
        state = self.state()
        self.assertEqual(rows(state['unresolved']), [])
        history = rows(state['contributions'])
        self.assertEqual([entry['actor'] for entry in history], ['moss', 'iris'])
        self.assertEqual([entry['proposal']['policy'] for entry in history], ['lending-policy-v2', 'literal'])
        self.assertEqual(history[0]['proposal']['original'], 'lend the amber moth')
        outcome = source_offers.prepare(self.invitation(), 'iris', 'complete', {})
        receipt = self.exchange(outcome['request'])
        self.assertTrue(self.state()['closed'])
        self.assertEqual(plain(self.root('moth:amber')['state']['model'])['borrower'], 'moss')
        self.assertEqual(rows(self.state()['outcomes'])[0]['content']['payload']['value'], 'Lent moth:amber to moss')
        self.receiver.checkpoint()
        self.receiver.close()
        self.receiver = resident_store.Resident(self.path)
        self.assertEqual(self.receiver.exchange(outcome['request']), receipt)
        self.exchange(self.request('answer', {'original': 'again', 'target': '', 'recipient': 'iris'}), 'refused')

    def test_model_unavailable_literal_route_and_stale_capture_refuse_then_retry(self):
        self.answer(target='moth:silver', recipient='iris')
        ready = source_offers.prepare(self.invitation(), 'moss', 'captured-before-contribution', {})
        self.answer(recipient='moss', actor='moss')
        refused = self.exchange(ready['request'], 'refused')
        self.assertFalse(self.state()['closed'])
        self.assertEqual(self.receiver.exchange(ready['request']), refused)
        fresh = source_offers.prepare(self.invitation(), 'moss', 'fresh-capture', {})
        committed = self.exchange(fresh['request'])
        self.assertEqual(self.receiver.exchange(fresh['request']), committed)
        self.assertTrue(self.state()['closed'])

    def test_captured_identity_policy_fields_and_current_authority(self):
        original = self.root()
        for proposal in [self.interpretation(target='moth:amber', token='display label'),
                         self.interpretation(target='moth:amber', policy='old-policy'),
                         self.interpretation(target='secret-object')]:
            self.exchange(self.request('interpret', proposal), 'refused')
            self.assertEqual(self.root(), original)
        self.exchange(self.request('answer', {'original': 'as Iris', 'target': 'moth:amber', 'recipient': ''}, 'stranger'), 'refused')
        self.assertEqual(self.root(), original)
        self.answer(target='moth:amber')
        self.assertEqual(rows(self.state()['contributions'])[0]['actor'], 'iris')

    def test_governed_reprogramming_preserves_intention_and_changes_document(self):
        self.answer(target='moth:amber', original='The amber one.')
        old = self.root()
        before = projection.project(old, 'conversation')
        self.assertIn('Field answers', before['data']['prose'])
        self.exchange({'op': 'reprogram', 'object': 'conversation', 'principal': 'moss',
            'intent': 'evening', 'expected': old, 'protocol': self.evening, 'state': old['state']})
        self.assertEqual(self.root()['state'], old['state'])
        after = projection.project(self.root(), 'conversation')
        self.assertIn('evening desk', after['data']['prose'])
        self.assertIn('document', plain(after['rawData']))
        self.answer(recipient='moss', actor='moss')
        self.assertEqual([entry['actor'] for entry in rows(self.state()['contributions'])], ['moss', 'iris'])

    def test_typed_retained_envelope_and_forged_completion(self):
        envelope = {'original': 'Please lend a moth to Moss.', 'policy': 'lending-policy-v2',
                    'context': [], 'capture': self.state()['capture'],
                    'bindings': {'recipient': 'moss'}, 'unresolved': []}
        self.exchange(self.request('retain', typed_envelope(envelope), 'moss'))
        self.assertEqual(rows(self.state()['unresolved']), ['target'])
        contribution = rows(self.state()['contributions'])[0]
        self.assertEqual(contribution['actor'], 'moss')
        self.assertEqual(contribution['proposal']['original'], envelope['original'])
        self.exchange(self.request('resolve', {'object': 'moth:amber', 'recipient': 'moss'}), 'refused')
        old = self.root()
        for changed in ({**envelope, 'actor': 'iris'},
                        {**envelope, 'original': 'x' * 4097},
                        {**envelope, 'capture': {**envelope['capture'], 'revision': '0'}},
                        {**envelope, 'bindings': {'target': 'unoffered'}},
                        {**envelope, 'context': [{'object': 'moth:amber', 'version': 0, 'program': 'claimed', 'state': None, 'unexpected': 'claimed'}]}):
            self.exchange(self.request('retain', typed_envelope(changed)), 'refused')
            self.assertEqual(self.root(), old)

    def test_target_current_law_refusal_rolls_back_completion(self):
        self.answer(target='moth:amber', recipient='moss')
        target = self.root('moth:amber')
        self.exchange({'op': 'law', 'object': 'moth:amber', 'principal': 'iris',
                       'intent': 'restrict-moth', 'expected': target, 'law': fixture_law(self.moth, ('moss',))})
        before = self.root()
        request = source_offers.prepare(self.invitation(), 'iris', 'cannot-lend', {})['request']
        refusal = self.exchange(request, 'refused')
        self.assertEqual(self.root(), before)
        self.assertEqual(plain(self.root('moth:amber')['state']['model'])['borrower'], '')
        self.assertEqual(self.receiver.exchange(request), refusal)
        allowed = source_offers.prepare(self.invitation(), 'moss', 'allowed-lend', {})['request']
        self.exchange(allowed)
        self.assertTrue(self.state()['closed'])

    def run_source(self, entry, *arguments):
        def call(request):
            done = subprocess.run([ROOT / '.lake/build/bin/delvetalk-obend'],
                input=json.dumps(request) + '\n', text=True, capture_output=True, check=True)
            return json.loads(done.stdout)
        compiled = call({'op': 'compile', 'modules': modules(), 'entry': entry})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': list(arguments)})
        self.assertEqual(result['status'], 'finished', result)
        return result['value']

    def test_source_interpretation_request_and_result_prepare_same_native_retain(self):
        import source_object
        state = self.root()['state']['model']
        job = self.run_source('interpretationRequest', state, source_object.data('The amber moth, please.'),
            source_object.variant('nil', source_object.record({})),
            source_object.data({'object': 'conversation', 'principal': 'iris'}))
        fields = {field['name']: field['value'] for field in job['fields']}
        envelope = fields['envelope']
        self.assertEqual(plain(envelope)['original'], 'The amber moth, please.')
        invitation = {**self.invitation(), 'entry': 'prepareInterpretation', 'contributionCodec': 'data'}
        prepared = source_offers.prepare_value(invitation, 'iris', 'model-result', source_object.record({
            'request': envelope, 'reply': source_object.value({'action': 'resolve', 'fields': {'target': 'moth:amber'}})}))
        self.assertEqual(prepared['request']['calls'][0]['command'], 'retain')
        self.exchange(prepared['request'])
        self.assertEqual(rows(self.state()['unresolved']), ['recipient'])
        self.assertEqual(rows(self.state()['contributions'])[0]['proposal']['original'], plain(envelope)['original'])
        self.assertEqual(plain(self.root('moth:amber')['state']['model'])['borrower'], '')
        self.answer(recipient='moss', actor='moss')
        final = source_offers.prepare(self.invitation(), 'moss', 'finish-model-intention', {})
        self.exchange(final['request'])
        self.assertEqual(plain(self.root('moth:amber')['state']['model'])['borrower'], 'moss')

    def test_pure_document_window_retains_explicit_continuation(self):
        import source_object
        self.answer(recipient='moss', original='First voice.')
        self.answer(target='moth:amber', original='Second voice.', actor='moss')
        before = self.root()
        def nodes(node):
            yield node
            if node.get('variant') == 'sequence':
                for child in rows(node['payload']['items']): yield from nodes(child)
        first = plain(self.run_source('document', before['state']['model'], source_object.data(0),
                                     source_object.data(1), source_object.data('A bounded window.')))
        first_nodes = list(nodes(first))
        self.assertEqual([item['payload']['attribution'] for item in first_nodes if item.get('variant') == 'quote'], ['moss'])
        continuation = next(item['payload'] for item in first_nodes if item.get('variant') == 'continuation')
        self.assertEqual((continuation['after'], continuation['limit']), (1, 1))
        second = plain(self.run_source('document', before['state']['model'], source_object.data(1),
                                      source_object.data(1), source_object.data('A bounded window.')))
        self.assertEqual([item['payload']['attribution'] for item in nodes(second) if item.get('variant') == 'quote'], ['iris'])
        self.assertEqual(self.root(), before)


if __name__ == '__main__': unittest.main()
