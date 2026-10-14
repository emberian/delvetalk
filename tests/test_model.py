"""The model client and interpreter: replies parsed, each pending interpretation asked once and
submitted verbatim, failures included (the host retries them), credentials never shown.

Evidence for FOUNDATION §6 (layer: transport).
"""
import json
import socket
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transport import bridge, interpret, model
from transport.config import Config
from transport.state import State

from transport.host import HostProcess, plain, typed

REQ = {'system': 'You interpret utterances.', 'user': 'plant a fern'}


def body(text, **extra):
    return json.dumps({'model': 'claude-haiku-5-5', 'content': [{'type': 'text', 'text': text}],
                       'usage': {'input_tokens': 3, 'output_tokens': 4}, **extra}).encode()


PLACES = tempfile.TemporaryDirectory(prefix='dt-model-')  # removed when the run ends


def place(key='k', **settings):
    """A state in a fresh directory whose config names an API key file holding `key` (none for '')."""
    d = tempfile.mkdtemp(dir=PLACES.name)
    if key:
        (Path(d) / 'key').write_text(key + '\n')
    return State(d, config=Config(anthropic_key_file=str(Path(d) / 'key') if key else '', **settings))


class Model(unittest.TestCase):
    def ask(self, status, raw, request=REQ):
        return model.ask(request, place(), transport=lambda *a: (status, raw))

    def test_a_reply_is_the_models_text_whole_and_every_other_answer_is_a_named_failure(self):
        for text in ('delvetalk garden plant\nseed: a fern', 'none', '{"a": 1}'):
            r = self.ask(200, body(text))
            self.assertEqual(r, {'status': 'replied', 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 3, 'output_tokens': 4}}, text)
        for status, raw, reason in ((200, b'not json', 'malformed'), (429, b'{}', 'rate'), (0, b'', 'transport'), (500, b'{}', 'transport'),
                                    (200, body('{}', stop_reason='refusal'), 'refused'), (401, b'{}', 'refused')):
            self.assertEqual(self.ask(status, raw)['reason'], reason, (status, raw))
        self.assertEqual(model.ask({'system': 'x' * (model.MAX_INPUT + 1), 'user': ''}, place())['reason'], 'refused')  # oversized input

    def test_no_key_opens_no_socket_and_a_key_file_is_read_from_the_named_path_only(self):
        with mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('socket')) as c, \
                mock.patch.object(socket, 'create_connection', side_effect=AssertionError('socket')) as cc:
            r = model.ask(REQ, place(key=''))
        self.assertEqual((r['status'], r['reason']), ('failed', 'refused'))
        self.assertEqual((c.call_count, cc.call_count), (0, 0))
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'k').write_text('filekey\n')
            self.assertEqual(model.key(str(Path(d) / 'k')), 'filekey')


STUB = '''#!%s
import json, sys
state = json.load(open(%r))
for line in sys.stdin:
    req = json.loads(line)
    if req['op'] != 'world-test':
        open(%r, 'a').write(json.dumps(req) + chr(10))
    if req['op'] == 'world-interpretations':
        out = {'status': 'interpretations', 'pending': state['pending']}
    elif req['op'] == 'world-interpretation':
        reply = req['reply']
        if reply.get('status') == 'failed' and reply.get('reason') in ('transport', 'rate'):  # the host's to retry
            for p in state['pending']:
                if p['id'] == req['id']:
                    p['attempts'], p['next'] = p.get('attempts', 0) + 1, 1
            out = {'status': 'retrying', 'attempt': 1, 'next': 1}
        else:
            state['pending'] = [p for p in state['pending'] if p['id'] != req['id']]
            out = {'status': 'interpreted', 'id': req['id']}
    elif req['op'] == 'world-receipt':
        out = next((r for r in state.get('receipts', []) if r['receipt']['identity'] == {'principal': req['principal'], 'intent': req['identity']}),
                   {'status': 'unknown'})
    elif req['op'] == 'world-turn' and req['method'] == 'mentions':
        if req['object'] in state.get('missing', []):
            out = {'status': 'error', 'message': 'missing avatar'}
        else:
            notes = state.setdefault('notes', {})
            notes.setdefault(req['identity'], req)
            out = {'status': 'admitted', 'receipt': {'identity': req['identity']}}
    elif req['op'] == 'world-test':
        state.update(req.get('state', {}))
        out = {'status': 'configured', 'notes': list(state.get('notes', {}).values())}
    else:
        out = {'status': 'error', 'message': 'unknown world operation ' + req['op']}
    print(json.dumps(out), flush=True)
'''


def item(n):
    return {'id': f'i{n}', 'object': 'garden', 'policy': {'model': 'claude-haiku-5-5', 'system': 'sys', 'examples': [{'u': 'a'}]},
            'identity': {'principal': 'did:plc:resident', 'intent': f'plant-{n}'},
            'utterance': f'plant {n}', 'offers': [{'form': 'plant'}]}


class Interpret(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / 'pending.json').write_text(json.dumps({'pending': [item(1), item(2)]}))
        self.log = d / 'settled.jsonl'
        stub = d / 'stub'
        stub.write_text(STUB % (sys.executable, str(d / 'pending.json'), str(self.log)))
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.host = HostProcess(stub)
        self.addCleanup(self.host.close)
        self.state = State(d / 'state')
        self.calls = []

    def ask(self, req):
        self.calls.append(req)
        return {'status': 'replied', 'raw': f'delvetalk garden plant\nseed: {len(self.calls)}', 'model': req['model'], 'usage': {}}

    def settled(self):
        return [r for r in self.operations() if r['op'] == 'world-interpretation']

    def operations(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def refusal(self, principal='did:plc:resident', intent='make-pianist-2'):
        return {'status': 'receipt', 'inPublic': False,
                'receipt': {'identity': {'principal': principal, 'intent': intent}, 'slug': 'famaj-rumij', 'height': 1352,
                            'outcome': {'tag': 'refused', 'class': 'badSpell', 'clause': 'unknownField',
                                        'reason': 'place is not a field of kind/inhabitant make'}},
                'public': {'class': 'badSpell', 'hint': 'delvetalk kind/inhabitant make / name: pianist'}}

    def resume(self, *receipts, **extra):
        pending = [{**item(n), 'identity': r['receipt']['identity']} for n, r in enumerate(receipts, 1)]
        self.host.send({'op': 'world-test', 'state': {'pending': pending, 'receipts': list(receipts), **extra}})

    def notes(self):
        return self.host.send({'op': 'world-test'})['notes']

    def test_a_resumed_refusal_tells_the_avatar_its_intent_clause_hint_and_receipt_once(self):
        got = self.refusal()
        self.resume(got)
        interpret.run(self.state, self.host, self.ask)
        [turn] = self.notes()
        text = ('receipt famaj-rumij; intent make-pianist-2; refused unknownField: '
                'place is not a field of kind/inhabitant make; hint: delvetalk kind/inhabitant make / name: pianist')
        self.assertEqual(turn, {'op': 'world-turn', 'principal': self.state.config.opener, 'object': 'did:plc:resident',
                               'method': 'mentions', 'identity': turn['identity'],
                               'argument': typed({'notes': [{'from': self.state.config.opener, 'handle': 'the town',
                                                            'text': text, 'post': 'make-pianist-2'}]})})
        self.assertIn({'op': 'world-receipt', 'principal': 'did:plc:resident', 'identity': 'make-pianist-2'}, self.operations())
        self.resume(got)  # the same settlement after a restored journal
        interpret.run(self.state, self.host, self.ask)
        self.assertEqual(self.notes(), [turn])  # host idempotency, not a local sent marker
        sent = [r for r in self.operations() if r['op'] == 'world-turn']
        self.assertEqual(sent, [turn, turn])

    def test_bridge_owned_turns_the_town_and_hobs_none_leave_no_note(self):
        waiting, town, quiet = self.refusal(intent='post'), self.refusal(self.state.config.opener), self.refusal(intent='quiet')
        quiet['receipt']['outcome'] = {'tag': 'admitted', 'writes': []}
        self.state.write(bridge.awaiting_path(self.state, 'post'), {'principal': 'did:plc:resident', 'settled': True})
        self.resume(waiting, town, quiet)
        interpret.run(self.state, self.host, self.ask)
        self.assertEqual(self.notes(), [])

    def test_a_missing_avatar_does_not_stop_other_notes_or_interpretations(self):
        self.resume(self.refusal('missing'), self.refusal(), missing=['missing'])
        done = interpret.run(self.state, self.host, self.ask)
        self.assertEqual(done['settled'], ['i1', 'i2'])
        self.assertEqual([t['object'] for t in self.notes()], ['did:plc:resident'])

    def test_long_refusals_keep_the_slug_outcome_clause_and_hint_inside_280_characters(self):
        got = self.refusal(intent='😀' * 256)
        got['receipt']['outcome']['reason'] += 'é' * 4000
        got['public']['hint'] = 'corrected spell ' + '☃' * 4000
        self.resume(got)
        interpret.run(self.state, self.host, self.ask)
        [turn] = self.notes()
        [note] = plain(turn['argument'])['notes']
        self.assertLessEqual(len(note['text']), bridge.NOTE_TEXT)
        for words in ('receipt famaj-rumij', 'intent 😀', 'refused unknownField', 'hint: corrected spell'):
            self.assertIn(words, note['text'])
        self.assertFalse(note['text'].endswith('famaj-rumij'))
        self.assertEqual(note['post'], '😀' * 256)

    def test_equal_intents_from_two_principals_have_distinct_note_identities(self):
        self.resume(self.refusal('one'), self.refusal('two'))
        interpret.run(self.state, self.host, self.ask)
        self.assertEqual(len(self.notes()), 2)

    def test_admitted_turns_with_an_offer_or_a_write_tell_the_sender(self):
        offered, written = self.refusal(intent='offered'), self.refusal(intent='written')
        offered['receipt']['outcome'] = {'tag': 'admitted', 'writes': []}
        offered['receipt']['offers'] = [{'text': 'hob: that still needs a name'}]
        written['receipt']['outcome'] = {'tag': 'admitted', 'writes': [{'object': 'bell', 'version': 2}]}
        self.resume(offered, written)
        interpret.run(self.state, self.host, self.ask)
        notes = [plain(t['argument'])['notes'][0] for t in self.notes()]
        self.assertEqual([n['post'] for n in notes], ['offered', 'written'])
        self.assertTrue(all('admitted' in n['text'] and 'famaj-rumij' in n['text'] for n in notes))

    def test_a_still_suspended_or_absent_receipt_leaves_no_note(self):
        waiting = self.refusal(intent='still-reading')
        waiting['receipt']['outcome'] = {'tag': 'suspended'}
        self.resume(waiting)
        self.host.send({'op': 'world-test', 'state': {'pending': [
            {**item(1), 'identity': waiting['receipt']['identity']}, item(2)]}})
        done = interpret.run(self.state, self.host, self.ask)
        self.assertEqual(done['settled'], ['i1', 'i2'])
        self.assertEqual(self.notes(), [])

    def test_a_cached_reply_tells_the_identity_from_the_current_pending_listing(self):
        got = self.refusal('did:plc:current', 'current-intent')
        self.state.write(interpret.cache_path(self.state, 'i1'), {
            'id': 'i1', 'object': 'garden', 'identity': {'principal': 'old', 'intent': 'old'},
            'reply': {'status': 'replied', 'raw': 'none', 'model': 'm'}})
        self.resume(got)
        interpret.run(self.state, self.host, self.ask)
        [turn] = self.notes()
        self.assertEqual(self.calls, [])
        self.assertEqual(turn['object'], 'did:plc:current')
        self.assertEqual(plain(turn['argument'])['notes'][0]['post'], 'current-intent')

    def test_each_request_is_asked_once_and_settled_verbatim(self):
        r = interpret.run(self.state, self.host, self.ask)
        self.assertEqual((r['settled'], r['failed']), (['i1', 'i2'], []))
        self.assertEqual(self.calls[0], {'model': 'claude-haiku-5-5', 'system': 'sys',
                                         'user': 'plant 1'})
        self.assertEqual([s['reply']['raw'] for s in self.settled()], ['delvetalk garden plant\nseed: 1', 'delvetalk garden plant\nseed: 2'])
        again = interpret.run(self.state, self.host, self.ask)  # a second run does nothing
        self.assertEqual((again['settled'], len(self.calls), len(self.settled())), ([], 2, 2))

    def test_crash_after_the_model_call_never_asks_or_settles_twice(self):
        real = self.host.send

        def die_on_first_settle(req):
            if req['op'] == 'world-interpretation' and not self.calls[1:]:
                raise RuntimeError('crash')
            return real(req)
        with mock.patch.object(self.host, 'send', side_effect=die_on_first_settle):
            with self.assertRaises(RuntimeError):
                interpret.run(self.state, self.host, self.ask)
        self.assertEqual((len(self.calls), self.settled()), (1, []))
        interpret.run(self.state, self.host, self.ask)
        self.assertEqual(len(self.calls), 2)  # i1 was not asked again
        self.assertEqual([s['id'] for s in self.settled()], ['i1', 'i2'])
        self.assertEqual(self.settled()[0]['reply']['raw'], 'delvetalk garden plant\nseed: 1')

    def test_after_a_restore_a_request_the_host_lists_as_pending_is_settled_again_with_its_saved_reply(self):
        interpret.run(self.state, self.host, self.ask)
        d = Path(self.tmp.name)  # the journal restored from before i1 settled, its receipt file from after
        (d / 'pending.json').write_text(json.dumps({'pending': [item(1)]}))
        restored = HostProcess(d / 'stub')
        self.addCleanup(restored.close)
        again = interpret.run(self.state, restored, self.ask)
        self.assertEqual((again['settled'], len(self.calls)), (['i1'], 2))
        self.assertEqual([(s['id'], s['reply']['raw'][-1]) for s in self.settled()], [('i1', '1'), ('i2', '2'), ('i1', '1')])

    def test_a_refused_or_malformed_model_call_is_settled_as_the_failure_reply_without_retry(self):
        r = interpret.run(self.state, self.host, lambda req: model.failed('refused') if req['user'] == 'plant 1' else model.failed('malformed'))
        self.assertEqual([s['reply'] for s in self.settled()], [{'status': 'failed', 'reason': 'refused', 'detail': ''}, model.failed('malformed')])
        self.assertEqual((r['settled'], r.get('retrying')), (['i1', 'i2'], None))

    def test_every_result_goes_to_the_host_verbatim_and_an_item_waiting_for_its_next_is_not_asked(self):
        r = interpret.run(self.state, self.host, lambda req: model.failed('transport'))
        self.assertEqual((r['settled'], r['retrying']), ([], ['i1', 'i2']))  # the host said retrying
        self.assertEqual([s['reply'] for s in self.settled()], [model.failed('transport')] * 2)  # submitted, failure and all
        calls = []
        again = interpret.run(self.state, self.host, lambda req: calls.append(1) or self.ask(req))
        self.assertEqual((calls, again['retrying'], len(self.settled())), ([], ['i1', 'i2'], 2))  # `next` has not passed


class OAuth(unittest.TestCase):
    TOKENS = {'main': 'sk-ant-oat01-AAAAAAAA', 'spare': 'sk-ant-oat01-BBBBBBBB'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.toml = Path(self.tmp.name) / 'tokens.toml'
        self.toml.write_text(''.join(f'[[tokens]]\nname = "{n}"\nkey = "{t}"\n' for n, t in self.TOKENS.items()))
        self.toml.chmod(0o600)
        self.st = place(model_auth='oauth', tokens_toml=str(self.toml))
        self.sent = []

    def probes(self, main, spare, scoped=()):
        mk = lambda n, u: {'token_name': n, 'quota': {'weekly': {'utilization': u, 'reset': 0}},
                           'model_usage': {'scoped_weekly': list(scoped) if n == 'main' else []}}
        return lambda: [mk('main', main), mk('spare', spare)]

    def transport(self, *statuses):
        queue = list(statuses)

        def t(method, url, headers, wire):
            self.sent.append(headers)
            return queue.pop(0), body('{"ok": 1}')
        return t


    def test_model_bucket_headroom_and_haiku_uses_the_general_window(self):
        opus = [{'key': 'opus_5', 'label': 'Opus 5', 'window': {'utilization': 0.95, 'reset': 0}}]
        r = model.ask({**REQ, 'model': 'claude-opus-5'}, self.st, transport=self.transport(200), tokeman=self.probes(0.1, 0.5, opus))
        self.assertEqual(r['account'], 'spare')  # main's Opus bucket is nearly spent
        r = model.ask(REQ, self.st, transport=self.transport(200), tokeman=self.probes(0.1, 0.5, opus))
        self.assertEqual(r['account'], 'main')  # haiku ignores the Opus bucket


    def test_429_rotates_once_then_stops(self):
        r = model.ask(REQ, self.st, transport=self.transport(429, 200), tokeman=self.probes(0.1, 0.5))
        self.assertEqual((r['status'], r['account'], r['rotated']), ('replied', 'spare', True))
        self.assertEqual([h['Authorization'][-8:] for h in self.sent], ['AAAAAAAA', 'BBBBBBBB'])
        self.sent.clear()
        r = model.ask(REQ, self.st, transport=self.transport(529, 429), tokeman=self.probes(0.1, 0.5))
        self.assertEqual((r['status'], r['reason'], r['rotated']), ('failed', 'rate', True))
        self.assertEqual(len(self.sent), 2)

    def test_world_readable_toml_is_refused_by_name_and_nothing_is_sent(self):
        self.toml.chmod(0o644)
        r = model.ask(REQ, self.st, transport=self.transport(), tokeman=self.probes(0, 0))
        self.assertEqual((r['status'], r['reason']), ('failed', 'refused'))
        self.assertIn('tokens.toml', r['detail'])
        self.assertEqual(self.sent, [])

    def test_no_token_string_appears_in_any_result(self):
        outs = [model.ask(REQ, self.st, transport=self.transport(429, 200), tokeman=self.probes(0.1, 0.5)),
                model.ask(REQ, self.st, transport=self.transport(401, 401), tokeman=self.probes(0.1, 0.5))]
        self.toml.chmod(0o666)
        outs.append(model.ask(REQ, self.st, transport=self.transport(), tokeman=self.probes(0, 0)))
        for token in self.TOKENS.values():
            self.assertNotIn(token, json.dumps(outs))

    def test_when_every_account_is_spent_prefer_one_with_extra_usage_and_surface_billing(self):
        def probe(name, enabled, in_use=False):
            return {'token_name': name, 'quota': {'weekly': {'utilization': 1.0, 'reset': 0},
                                                  'overage_status': 'allowed' if enabled else 'rejected',
                                                  'overage_disabled_reason': None if enabled else 'out_of_credits',
                                                  'overage_in_use': in_use}}
        r = model.ask(REQ, self.st, transport=self.transport(200), tokeman=lambda: [probe('main', False), probe('spare', True, True)])
        self.assertEqual((r['account'], r['overageInUse']), ('spare', True))
        r = model.ask(REQ, self.st, transport=self.transport(200), tokeman=lambda: [probe('main', True), probe('spare', False)])
        self.assertEqual((r['account'], r['overageInUse']), ('main', False))
        # headroom still beats overage while any account has some
        probes = [{'token_name': 'main', 'quota': {'weekly': {'utilization': 0.4}, 'overage_status': 'rejected'}},
                  {'token_name': 'spare', 'quota': {'weekly': {'utilization': 1.0}, 'overage_status': 'allowed'}}]
        self.assertEqual(model.ask(REQ, self.st, transport=self.transport(200), tokeman=lambda: probes)['account'], 'main')


class Spend(unittest.TestCase):
    def test_wire_never_carries_sampling_fields_and_thinking_is_off_unless_asked_for(self):
        seen = []
        t = lambda *a: seen.append(json.loads(a[3])) or (200, body('{}'))
        model.ask({**REQ, 'temperature': 0.2, 'top_p': 0.9, 'top_k': 3}, place(), transport=t)
        self.assertEqual(seen[0]['thinking'], {'type': 'disabled'})  # an interpretation spends no output on thinking
        model.ask(REQ, place(model_thinking=True), transport=t)
        self.assertNotIn('thinking', seen[1])
        for wire in seen:
            self.assertEqual(set(wire) - {'thinking'}, {'model', 'max_tokens', 'system', 'messages'})

    def test_spend_log_and_ratelimit_headers(self):
        t = lambda *a: (200, body('{}'), {'Anthropic-RateLimit-Requests-Remaining': '7', 'x-other': '1'})
        st = place(key='sekret', key_name='max-grant')
        r = model.ask(REQ, st, transport=t)
        model.ask(REQ, st, transport=lambda *a: (429, b'{}'))  # failures are not logged
        lines = [json.loads(x) for x in st.spend.read_text().splitlines()]
        self.assertNotIn('sekret', st.spend.read_text())
        self.assertEqual(r['rateLimits'], {'anthropic-ratelimit-requests-remaining': '7'})
        self.assertEqual(len(lines), 1)
        self.assertEqual({k: lines[0][k] for k in ('world', 'model', 'inputTokens', 'outputTokens', 'account')},
                         {'world': 'town', 'model': 'claude-haiku-5-5', 'inputTokens': 3, 'outputTokens': 4, 'account': 'max-grant'})


if __name__ == '__main__':
    unittest.main()
