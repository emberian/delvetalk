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

from transport import interpret, model
from transport.config import Config
from transport.state import State

from deploy.serve import Pipe

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

    def test_a_reply_parses_from_plain_fenced_or_prose_text_and_every_other_answer_is_a_named_failure(self):
        for text in ('{"a": 1}', '```json\n{"a": 1}\n```', 'Sure! Here you go:\n{"a": 1}\nHope that helps'):
            r = self.ask(200, body(text))
            self.assertEqual((r['status'], r['json'], r['raw'], r['model']), ('replied', {'a': 1}, text, 'claude-haiku-5-5'), text)
            self.assertEqual(r['usage'], {'input_tokens': 3, 'output_tokens': 4})
        text_only = self.ask(200, body('no json here'))  # a plain-text reply is a reply; the host fits raw
        self.assertEqual((text_only['status'], text_only['json'], text_only['raw']), ('replied', None, 'no json here'))
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
    if req['op'] == 'world-interpretations':
        out = {'status': 'interpretations', 'pending': state['pending']}
    elif req['op'] == 'world-interpretation':
        open(%r, 'a').write(json.dumps(req) + chr(10))
        reply = req['reply']
        if reply.get('status') == 'failed' and reply.get('reason') in ('transport', 'rate'):  # the host's to retry
            for p in state['pending']:
                if p['id'] == req['id']:
                    p['attempts'], p['next'] = p.get('attempts', 0) + 1, 1
            out = {'status': 'retrying', 'attempt': 1, 'next': 1}
        else:
            state['pending'] = [p for p in state['pending'] if p['id'] != req['id']]
            out = {'status': 'interpreted', 'id': req['id']}
    else:
        out = {'status': 'error', 'message': 'unknown world operation ' + req['op']}
    print(json.dumps(out), flush=True)
'''


def item(n):
    return {'id': f'i{n}', 'object': 'garden', 'policy': {'model': 'claude-haiku-5-5', 'system': 'sys', 'examples': [{'u': 'a'}]},
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
        self.host = Pipe(str(stub))
        self.addCleanup(self.host.close)
        self.state = State(d / 'state')
        self.calls = []

    def ask(self, req):
        self.calls.append(req)
        return {'status': 'replied', 'json': {'form': 'plant', 'n': len(self.calls)}, 'raw': '{}', 'model': req['model'], 'usage': {}}

    def settled(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_each_request_is_asked_once_and_settled_verbatim(self):
        r = interpret.run(self.state, self.host, self.ask)
        self.assertEqual((r['settled'], r['failed']), (['i1', 'i2'], []))
        self.assertEqual(self.calls[0], {'model': 'claude-haiku-5-5', 'system': 'sys',
                                         'user': 'plant 1'})
        self.assertEqual([s['reply']['json']['n'] for s in self.settled()], [1, 2])
        self.assertEqual(self.settled()[0]['reply']['json'], {'form': 'plant', 'n': 1})
        again = interpret.run(self.state, self.host, self.ask)  # a second run does nothing
        self.assertEqual((again['settled'], len(self.calls), len(self.settled())), ([], 2, 2))

    def test_the_utterance_is_sent_once(self):
        d = Path(self.tmp.name)
        it = dict(item(1), policy={'model': 'claude-haiku-5-5', 'system': 'forms...\n\nParticipant: plant 1'})
        (d / 'pending.json').write_text(json.dumps({'pending': [it]}))
        host = Pipe(str(d / 'stub'))
        self.addCleanup(host.close)
        interpret.run(self.state, host, self.ask)
        sent = self.calls[0]
        self.assertEqual((sent['system'], sent['user']), ('forms...', 'plant 1'))  # Policy.prompt's tail is the user turn, once
        self.assertEqual((sent['system'] + sent['user']).count('plant 1'), 1)

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
        self.assertEqual(self.settled()[0]['reply']['json']['n'], 1)

    def test_after_a_restore_a_request_the_host_lists_as_pending_is_settled_again_with_its_saved_reply(self):
        interpret.run(self.state, self.host, self.ask)
        d = Path(self.tmp.name)  # the journal restored from before i1 settled, its receipt file from after
        (d / 'pending.json').write_text(json.dumps({'pending': [item(1)]}))
        restored = Pipe(str(d / 'stub'))
        self.addCleanup(restored.close)
        again = interpret.run(self.state, restored, self.ask)
        self.assertEqual((again['settled'], len(self.calls)), (['i1'], 2))
        self.assertEqual([(s['id'], s['reply']['json']['n']) for s in self.settled()], [('i1', 1), ('i2', 2), ('i1', 1)])

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
