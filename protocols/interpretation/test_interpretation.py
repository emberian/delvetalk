"""Source/native interpretation and bounded physical custody, without paid calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import interpret
import model_service
import source_object as source


def card():
    return {'card': 'capture-1', 'object': 'moth', 'title': 'Lend', 'prose': 'Quoted room text.',
        'actions': [{'id': 'lend', 'label': 'Lend a moth', 'available': True, 'fields': [
            {'name': 'recipient', 'label': 'Recipient', 'required': True, 'type': 'string', 'maxLength': 32},
            {'name': 'nights', 'label': 'Nights', 'required': True, 'type': 'nat', 'minimum': 1, 'maximum': 7}]}]}


def fixture_law(protocol):
    return {'profile': 'delvetalk-scoped-law',
            'invoke': {name: ['iris'] for name in protocol['commands']},
            'read': 'public', 'reprogram': ['iris'], 'law': ['iris']}


class SourceInterpretation(unittest.TestCase):
    def test_literal_and_model_share_partial_binding_and_validation(self):
        literal = interpret.interpret('do capture-1 lend {"nights":2}', card())
        model = interpret.interpret('two nights', card(), proposer=lambda *_: {'action': 'lend', 'fields': {'nights': 2}})
        self.assertEqual(literal['status'], 'partial')
        self.assertEqual(literal['unresolved'], ['recipient'])
        self.assertEqual(literal['fields'], model['fields'])
        for fields in ({'nights': True}, {'nights': 8}, {'principal': 'owner'}):
            self.assertEqual(interpret.interpret('x', card(), proposer=lambda *_: {'action': 'lend', 'fields': fields})['status'], 'clarify')
        self.assertEqual(interpret.interpret('do stale lend {}', card())['status'], 'clarify')

    def test_model_text_has_no_authority_and_literal_needs_no_provider(self):
        for answer in ({'action': 'lend', 'fields': {}, 'principal': 'owner'}, {'action': 'shell', 'fields': {}}, None, []):
            self.assertEqual(interpret.interpret('ignore policy', card(), proposer=lambda *_: answer)['status'], 'clarify')
        def forbidden(*_):
            raise AssertionError('literal attempted provider')
        self.assertEqual(interpret.interpret('do capture-1 lend {"recipient":"Ada","nights":2}', card(), proposer=forbidden)['status'], 'proposed')

    def test_dynamic_proposal_accessors_do_not_coerce_nonstrings_to_empty_tokens(self):
        source_card = {'actions': [{'id': '', 'available': True, 'fields': []}]}
        result = interpret.unpack(interpret.native('propose', [source.value(source_card),
            source.value({'action': False, 'fields': {}}), source.data('model')]))
        self.assertEqual(result['status'], 'clarify')
        source_card['actions'] = [{'id': 'pick', 'available': True, 'fields': [
            {'name': 'choice', 'type': 'enum', 'options': [0]}]}]
        result = interpret.unpack(interpret.native('propose', [source.value(source_card),
            source.value({'action': 'pick', 'fields': {'choice': ''}}), source.data('model')]))
        self.assertEqual(result['status'], 'clarify')

    def test_source_prompt_revision_and_receipt_deduplication(self):
        calls = []
        def provider(body):
            calls.append(copy.deepcopy(body))
            return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '```json\n{"action":"lend","fields":{"nights":2}}\n```'}]}
        with tempfile.TemporaryDirectory() as directory:
            helper = interpret.AnthropicProposer(None, provider=provider, directory=directory)
            self.assertEqual(interpret.interpret('two nights', card(), proposer=helper)['status'], 'partial')
            interpret.interpret('two nights', card(), proposer=helper)
            self.assertEqual(len(calls), 1)
            self.assertTrue(helper.last_receipt['reply']['content'][0]['text'].startswith('```json'))
            self.assertEqual(calls[0]['model'], 'claude-haiku-5-5')
            self.assertIn('Missing fields are welcome', calls[0]['system'])
            self.assertEqual(set(json.loads(calls[0]['messages'][0]['content'])), {'userRequest', 'untrustedCard'})
            policy = source.plain(interpret.native('defaultPolicy'))
            policy.update(revision='room-v2', vocabulary='moths are loaned specimens')
            helper.policy = source.data(policy)
            interpret.interpret('two nights', card(), proposer=helper)
            self.assertEqual(len(calls), 2)
            self.assertIn('loaned specimens', calls[1]['system'])
            self.assertIn('document', helper.last_receipt['job'])
            restored = model_service.Service(directory, lambda _: self.fail('receipt replay called provider'))
            self.assertEqual(restored.request(helper.last_receipt['job']), helper.last_receipt)

    def test_uncertain_and_malformed_reply_are_retained_without_retry(self):
        for reply in ({'stop_reason': 'max_tokens', 'content': []}, {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{bad'}]}):
            calls = []
            with tempfile.TemporaryDirectory() as directory:
                helper = interpret.AnthropicProposer(None, directory=directory, provider=lambda body: calls.append(body) or reply)
                first = interpret.interpret('help', card(), proposer=helper)
                self.assertEqual(first['status'], 'provider-error')
                self.assertEqual(interpret.interpret('help', card(), proposer=helper), first)
                self.assertEqual(first['request'], helper.last_receipt['key'])
                self.assertEqual(len(calls), 1)
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def fail(body):
                calls.append(body)
                raise TimeoutError('private remote failure')
            helper = interpret.AnthropicProposer(None, directory=directory, provider=fail)
            self.assertEqual(interpret.interpret('help', card(), proposer=helper)['status'], 'escalate')
            interpret.interpret('help', card(), proposer=helper)
            self.assertEqual(len(calls), 1)
            self.assertEqual(helper.last_receipt['status'], 'uncertain')

    def test_source_job_provider_preparation_and_governed_receiving_path(self):
        sys.path.insert(0, str(ROOT))
        from conformance.test_document_conversation import modules, rows
        import resident_store
        import source_offers
        retained_modules = modules()
        protocol = source.adapter.lower_data_modules(retained_modules)
        empty = source.variant('nil', source.record({}))
        context = source.data({'object': 'conversation', 'principal': 'iris'})
        with tempfile.TemporaryDirectory() as directory:
            with __import__('contextlib').closing(resident_store.Resident(Path(directory) / 'world.sqlite')) as receiver:
                created = receiver.exchange({'op': 'create', 'object': 'conversation', 'principal': 'iris',
                    'intent': 'create', 'protocol': protocol, 'law': fixture_law(protocol)})
                self.assertEqual(created['kind'], 'committed', created)
                root = receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})
                job_wire = interpret.native('interpretationRequest', [source.state_data(root), source.data('Lend the amber moth'), empty, context], modules=retained_modules)
                job = source.plain(next(f['value'] for f in job_wire['fields'] if f['name'] == 'job'))
                envelope = next(f['value'] for f in job_wire['fields'] if f['name'] == 'envelope')
                calls = []
                def provider(body):
                    calls.append(body)
                    return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{"action":"resolve","fields":{"target":"moth:amber"}}'}]}
                helper = interpret.AnthropicProposer(None, directory=Path(directory) / 'models', identity_scope='iris/private', provider=provider)
                reply = helper.request_source(job, source_modules=retained_modules, envelope=envelope)
                self.assertEqual(job['revision'], 'lending-policy-v2')
                invitation = {'format': source_offers.FORMAT, 'object': 'conversation', 'root': root,
                    'entry': 'prepareInterpretation', 'contributionCodec': 'data', 'observations': [], 'title': 'Conversation', 'label': 'Interpret', 'fields': []}
                prepared = source_offers.prepare_value(invitation, 'iris', 'retain-model-1', source.record({'request': envelope, 'reply': source.value(reply)}))
                self.assertEqual(prepared['kind'], 'ready', prepared)
                receipt = receiver.exchange(prepared['request'])
                self.assertEqual(receipt['kind'], 'committed', receipt)
                state = source.plain(source.state_data(receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})))
                contribution = rows(state['conversation']['contributions'])[0]
                self.assertEqual(contribution['actor'], 'iris')
                self.assertEqual(contribution['proposal']['original'], 'Lend the amber moth')
                self.assertEqual(contribution['proposal']['policy'], 'lending-policy-v2')
                self.assertEqual(rows(state['conversation']['unresolved']), ['recipient'])
                self.assertEqual(receiver.exchange(prepared['request']), receipt)
                stale = copy.deepcopy(prepared['request'])
                stale['intent'] = 'different-intent-same-old-capture'
                self.assertEqual(receiver.exchange(stale)['kind'], 'refused')
                current = receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})
                other_actor = source_offers.prepare_value({**invitation, 'root': current}, 'mallory', 'no-authority', source.record({'request': envelope, 'reply': source.value(reply)}))
                self.assertEqual(other_actor['kind'], 'ready', other_actor)
                self.assertEqual(receiver.exchange(other_actor['request'])['kind'], 'refused')
                self.assertEqual(helper.request_source(job, source_modules=retained_modules, envelope=envelope), reply)
                self.assertEqual(len(calls), 1)
                forged = copy.deepcopy(envelope)
                next(field for field in forged['fields'] if field['name'] == 'policy')['value'] = source.data('wrong-policy')
                refused = source_offers.prepare_value(invitation, 'iris', 'wrong-policy', source.record({'request': forged, 'reply': source.value(reply)}))
                self.assertEqual(refused['kind'], 'refused', refused)

                # Complete the retained intention through the actual offered action.
                moth_modules = source.read_closure([
                    ('Moth', ROOT / 'protocols/conversation/Moth.obend')])
                moth_protocol = source.adapter.lower_data_modules(moth_modules)
                for name in ('moth:amber', 'moth:silver'):
                    self.assertEqual(receiver.exchange({'op': 'create', 'object': name, 'principal': 'iris',
                        'intent': 'create-' + name, 'protocol': moth_protocol, 'law': fixture_law(moth_protocol)})['kind'], 'committed')
                current = receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})
                answered = receiver.exchange({'op': 'invoke', 'object': 'conversation', 'principal': 'iris',
                    'intent': 'answer-missing-recipient', 'expected': current, 'command': 'answer',
                    'input': {'original': 'For Moss, please.', 'target': '', 'recipient': 'moss'}})
                self.assertEqual(answered['kind'], 'committed', answered)
                current = receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})
                observations = [{'object': name, 'root': receiver.exchange({'op': 'inspect', 'object': name,
                    'principal': 'iris'}), 'inspectState': False, 'inspectLaw': False}
                    for name in ('moth:amber', 'moth:silver')]
                finish = source_offers.prepare({**invitation, 'root': current, 'entry': 'prepareResolve',
                    'observations': observations, 'contributionCodec': 'value'}, 'iris', 'finish-lending', {})
                self.assertEqual(finish['kind'], 'ready', finish)
                completed = receiver.exchange(finish['request'])
                self.assertEqual(completed['kind'], 'committed', completed)
                self.assertEqual(receiver.exchange(finish['request']), completed)
                moth = receiver.exchange({'op': 'inspect', 'object': 'moth:amber', 'principal': 'iris'})
                self.assertEqual(source.plain(source.state_data(moth))['borrower'], 'moss')
                self.assertEqual(len(calls), 1)

    def test_physical_service_quota_and_busy_never_call_provider(self):
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            service = model_service.Service(directory, lambda body: calls.append(body) or {}, max_jobs=1)
            first = service.request({'body': {}, 'identityScope': 'account-a'})
            self.assertEqual(first['status'], 'received')
            self.assertEqual(service.request({'body': {}, 'identityScope': 'account-a'}), first)
            self.assertEqual(service.request({'body': {}, 'identityScope': 'account-b'})['status'], 'quota')
            with open(Path(directory) / 'service.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(service.request({'body': {}, 'identityScope': 'account-a'})['status'], 'busy')
            self.assertEqual(len(calls), 1)

    def test_participant_revises_stored_prompt_and_next_source_request(self):
        sys.path.insert(0, str(ROOT))
        from conformance.test_document_conversation import modules, rows
        import resident_store
        import source_offers
        import affordances
        import portal
        import town_cards
        from scene import projection
        retained_modules = modules()
        protocol = source.adapter.lower_data_modules(retained_modules)
        empty = source.variant('nil', source.record({}))
        context = source.data({'object': 'conversation', 'principal': 'iris'})
        with tempfile.TemporaryDirectory() as directory:
            with __import__('contextlib').closing(resident_store.Resident(Path(directory) / 'world.sqlite')) as receiver:
                self.assertEqual(receiver.exchange({'op': 'create', 'object': 'conversation', 'principal': 'iris',
                    'intent': 'create', 'protocol': protocol, 'law': fixture_law(protocol)})['kind'], 'committed')
                old = receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})
                wire = interpret.native('interpretationRequest', [source.state_data(old), source.data('Lend the amber moth'),
                    empty, context], modules=retained_modules)
                old_envelope = next(f['value'] for f in wire['fields'] if f['name'] == 'envelope')
                policy = source.plain(source.state_data(old))['conversation']['interpreter']
                revised = {**policy, 'revision': 'participant-policy-v3', 'vocabulary': 'A lantern means the amber moth.'}
                edit = {'revision': revised['revision'], 'section': 'vocabulary', 'text': revised['vocabulary']}
                before_panel = projection.project(old, 'conversation', panel='interpretation')
                self.assertIn('interpretation', [item['id'] for item in portal.Portal.panels(old)])
                main = projection.project(old, 'conversation')
                town_panels = town_cards._panels(main, None)
                town_panel = next(item['view'] for item in town_panels if item['id'] == 'interpretation')
                for captured_panel in (before_panel, town_panel):
                    displayed = affordances.card(captured_panel)
                    editing = next(action for action in displayed['actions'] if action.get('command') == 'reviseInterpretation')
                    self.assertEqual({field['name'] for field in editing['fields']}, {'revision', 'section', 'text'})
                changed_request = affordances.request(before_panel, editing['id'], 'iris', 'revise-prompt', edit)
                denied = receiver.exchange({'op': 'invoke', 'object': 'conversation', 'principal': 'mallory',
                    'intent': 'unauthorized-prompt-edit', 'expected': old, 'command': 'reviseInterpretation', 'input': edit})
                self.assertEqual(denied['kind'], 'refused', denied)
                self.assertEqual(receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'}), old)
                changed = receiver.exchange(changed_request)
                self.assertEqual(changed['kind'], 'committed', changed)
                current = receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})
                updated_state = source.plain(source.state_data(current))['conversation']
                self.assertEqual(updated_state['interpreter'], revised)
                self.assertEqual(updated_state['capture']['revision'],
                    source.plain(source.state_data(old))['conversation']['capture']['revision'] + 1)
                self.assertEqual(rows(updated_state['outcomes'])[0]['actor'], 'iris')
                panel = projection.project(current, 'conversation', panel='interpretation')
                self.assertIn(revised['vocabulary'], panel['data']['prose'])
                new_wire = interpret.native('interpretationRequest', [source.state_data(current), source.data('Lend the lantern'),
                    empty, context], modules=retained_modules)
                job = source.plain(next(f['value'] for f in new_wire['fields'] if f['name'] == 'job'))
                self.assertEqual(job['revision'], revised['revision'])
                self.assertIn(revised['vocabulary'], job['system'])
                self.assertIn(revised['examples'], job['system'])
                calls = []
                helper = interpret.AnthropicProposer(None, directory=Path(directory) / 'models', provider=lambda body:
                    calls.append(body) or {'stop_reason': 'end_turn', 'content': [{'type': 'text',
                    'text': '{"action":"resolve","fields":{"target":"moth:amber"}}'}]})
                envelope = next(f['value'] for f in new_wire['fields'] if f['name'] == 'envelope')
                reply = helper.request_source(job, source_modules=retained_modules, envelope=envelope)
                invitation = {'format': source_offers.FORMAT, 'object': 'conversation', 'root': current,
                    'entry': 'prepareInterpretation', 'contributionCodec': 'data', 'observations': [],
                    'title': 'Conversation', 'label': 'Interpret', 'fields': []}
                old_reply = source_offers.prepare_value(invitation, 'iris', 'old-prompt-reply',
                    source.record({'request': old_envelope, 'reply': source.value(reply)}))
                self.assertEqual(old_reply['kind'], 'refused', old_reply)
                prepared = source_offers.prepare_value(invitation, 'iris', 'new-prompt-reply',
                    source.record({'request': envelope, 'reply': source.value(reply)}))
                self.assertEqual(prepared['kind'], 'ready', prepared)
                receipt = receiver.exchange(prepared['request'])
                self.assertEqual(receipt['kind'], 'committed', receipt)
                state = source.plain(source.state_data(receiver.exchange({'op': 'inspect', 'object': 'conversation', 'principal': 'iris'})))
                self.assertEqual(rows(state['conversation']['contributions'])[0]['proposal']['policy'], revised['revision'])
                self.assertEqual(helper.request_source(job, source_modules=retained_modules, envelope=envelope), reply)
                self.assertEqual(len(calls), 1)

    def test_explicit_generation_and_pure_retained_render(self):
        modules = source.read_modules([(name, ROOT / path) for name, path in [
            ('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'), ('Abi', 'world/lib/prelude/Abi.obend'),
            ('Encounter', 'world/lib/prelude/Encounter.obend'), ('Document', 'world/lib/document/Document.obend'),
            ('Interpretation', 'protocols/interpretation/Interpretation.obend'), ('Conversation', 'protocols/conversation/Conversation.obend'),
            ('ModelEncounter', 'protocols/interpretation/Encounter.obend')]])
        job = interpret.native('prompt', [interpret.native('defaultPolicy'), source.data('{}')])
        request = source.record({'key': source.data('exact-1'), 'generation': source.data(1),
            'templateRevision': source.data('template-v1'), 'original': source.data('hello'),
            'context': source.variant('nil', source.record({})),
            'capture': source.data({'object': 'moth', 'revision': 1, 'meaning': 'p1', 'entry': 'lend', 'token': 'c1'}), 'job': job})
        pending = interpret.native('pending', [request], modules=modules)
        duplicate = source.plain(interpret.native('regenerate', [pending, request], modules=modules))
        self.assertFalse(duplicate['accepted'])
        wrong = source.plain(interpret.native('receive', [pending, source.data({'key': 'other', 'status': 'received', 'output': 'forged'})], modules=modules))
        self.assertFalse(wrong['accepted'])
        decision = interpret.native('receive', [pending, source.data({'key': 'exact-1', 'status': 'received', 'output': 'retained moth'})], modules=modules)
        state = next(f['value'] for f in decision['fields'] if f['name'] == 'state')
        first = interpret.native('render', [state], modules=modules)
        self.assertEqual(first, interpret.native('render', [state], modules=modules))
        self.assertIn('retained moth', json.dumps(source.plain(first)))


if __name__ == '__main__':
    unittest.main()
