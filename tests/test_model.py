import io
import json
import os
import socket
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transport import interpret, model
from transport.hostproc import Host

REQ = {'system': 'You interpret utterances.', 'user': 'plant a fern'}


def body(text, **extra):
    return json.dumps({'model': 'claude-haiku-5-5', 'content': [{'type': 'text', 'text': text}],
                       'usage': {'input_tokens': 3, 'output_tokens': 4}, **extra}).encode()


class Model(unittest.TestCase):
    def ask(self, status, raw, request=REQ):
        with mock.patch.dict(os.environ, {'DELVETALK_ANTHROPIC_KEY': 'k'}):
            return model.ask(request, transport=lambda *a: (status, raw))

    def test_plain_fenced_and_prose_replies_all_parse(self):
        for text in ('{"a": 1}', '```json\n{"a": 1}\n```', 'Sure! Here you go:\n{"a": 1}\nHope that helps'):
            r = self.ask(200, body(text))
            self.assertEqual((r['status'], r['json'], r['raw'], r['model']), ('replied', {'a': 1}, text, 'claude-haiku-5-5'), text)
            self.assertEqual(r['usage'], {'input_tokens': 3, 'output_tokens': 4})

    def test_failure_reasons(self):
        text_only = self.ask(200, body('no json here'))  # a plain-text reply is a reply; the host fits raw
        self.assertEqual((text_only['status'], text_only['json'], text_only['raw']), ('replied', None, 'no json here'))
        self.assertEqual(self.ask(200, b'not json')['reason'], 'malformed')
        self.assertEqual(self.ask(429, b'{}')['reason'], 'rate')
        self.assertEqual(self.ask(0, b'')['reason'], 'transport')
        self.assertEqual(self.ask(500, b'{}')['reason'], 'transport')
        self.assertEqual(self.ask(200, body('{}', stop_reason='refusal'))['reason'], 'refused')
        self.assertEqual(self.ask(401, b'{}')['reason'], 'refused')

    def test_request_on_the_wire(self):
        seen = []
        with mock.patch.dict(os.environ, {'DELVETALK_ANTHROPIC_KEY': 'sekret'}):
            model.ask({**REQ, 'maxTokens': 10 ** 6}, transport=lambda *a: seen.append(a) or (200, body('{}')))
        method, url, headers, wire = seen[0]
        wire = json.loads(wire)
        self.assertEqual((method, url, headers['x-api-key']), ('POST', model.URL, 'sekret'))
        self.assertEqual((wire['model'], wire['max_tokens'], wire['system'], wire['messages']),
                         ('claude-haiku-5-5', 4096, REQ['system'], [{'role': 'user', 'content': REQ['user']}]))

    def test_no_key_opens_no_socket(self):
        with mock.patch.dict(os.environ, clear=True), \
                mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('socket')) as c, \
                mock.patch.object(socket, 'create_connection', side_effect=AssertionError('socket')) as cc:
            r = model.ask(REQ)
        self.assertEqual((r['status'], r['reason']), ('failed', 'refused'))
        self.assertEqual((c.call_count, cc.call_count), (0, 0))

    def test_key_file_is_read_from_the_named_path_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'k').write_text('filekey\n')
            with mock.patch.dict(os.environ, {'DELVETALK_ANTHROPIC_KEY_FILE': str(Path(d) / 'k')}, clear=True):
                self.assertEqual(model.key(), 'filekey')

    def test_mock_fixtures_are_keyed_by_request_hash(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / (model.request_hash(REQ) + '.json')).write_bytes(body('```json\n{"form": "plant"}\n```'))
            with mock.patch.dict(os.environ, clear=True):
                self.assertEqual(model.ask(REQ, mock=d)['json'], {'form': 'plant'})
                self.assertEqual(model.ask({**REQ, 'user': 'other'}, mock=d)['reason'], 'transport')

    def test_oversized_input_is_refused(self):
        self.assertEqual(model.ask({'system': 'x' * (model.MAX_INPUT + 1), 'user': ''})['reason'], 'refused')


STUB = '''#!%s
import json, sys
state = json.load(open(%r))
for line in sys.stdin:
    req = json.loads(line)
    if req['op'] == 'world-interpretations':
        out = {'status': 'interpretations', 'pending': state['pending']}
    elif req['op'] == 'world-interpretation':
        state['pending'] = [p for p in state['pending'] if p['id'] != req['id']]
        open(%r, 'a').write(json.dumps(req) + chr(10))
        out = {'status': 'settled', 'id': req['id']}
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
        self.host = Host(None, str(stub))
        self.addCleanup(self.host.close)
        self.state = d / 'state'
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
                                         'user': '{"examples":[{"u":"a"}],"offers":[{"form":"plant"}],"utterance":"plant 1"}'})
        self.assertEqual([s['reply']['json']['n'] for s in self.settled()], [1, 2])
        self.assertEqual(self.settled()[0]['reply']['json'], {'form': 'plant', 'n': 1})

    def test_a_second_run_does_nothing(self):
        interpret.run(self.state, self.host, self.ask)
        n = len(self.calls)
        again = interpret.run(self.state, self.host, self.ask)
        self.assertEqual((again['settled'], len(self.calls), len(self.settled())), ([], n, 2))

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

    def test_a_refused_model_call_is_settled_as_the_failure_reply(self):
        interpret.run(self.state, self.host, lambda req: model.failed('refused'))
        self.assertEqual(self.settled()[0]['reply'], {'status': 'failed', 'reason': 'refused', 'detail': ''})

    def test_transient_failures_retry_with_backoff_and_settle_failed_after_eight(self):
        clock = [1000.0]
        flaky = lambda req: model.failed('transport')
        r = interpret.run(self.state, self.host, flaky, lambda: clock[0])
        self.assertEqual((r['settled'], r['retrying']), ([], ['i1', 'i2']))
        self.assertEqual(self.settled(), [])
        saved = json.loads(interpret.receipt_path(self.state, 'i1').read_text())
        self.assertEqual((saved['attempts'], saved['next']), (1, 1060.0))
        calls = []
        interpret.run(self.state, self.host, lambda req: calls.append(1) or model.failed('rate'), lambda: clock[0])
        self.assertEqual(calls, [])  # still backing off
        for n in range(2, 8):
            clock[0] += 10 ** 5
            interpret.run(self.state, self.host, flaky, lambda: clock[0])
        self.assertEqual(self.settled(), [])
        clock[0] += 10 ** 5
        r = interpret.run(self.state, self.host, flaky, lambda: clock[0])
        self.assertEqual(r['settled'], ['i1', 'i2'])
        self.assertEqual(self.settled()[0]['reply']['reason'], 'transport')
        self.assertEqual(json.loads(interpret.receipt_path(self.state, 'i1').read_text())['attempts'], 8)

    def test_a_retry_that_replies_settles_with_the_reply(self):
        clock = [1000.0]
        interpret.run(self.state, self.host, lambda req: model.failed('rate'), lambda: clock[0])
        clock[0] += 10 ** 5
        r = interpret.run(self.state, self.host, self.ask, lambda: clock[0])
        self.assertEqual(r['settled'], ['i1', 'i2'])
        self.assertEqual(self.settled()[0]['reply']['status'], 'replied')

    def test_malformed_settles_without_retry(self):
        r = interpret.run(self.state, self.host, lambda req: model.failed('malformed'))
        self.assertEqual((r['settled'], r.get('retrying')), (['i1', 'i2'], None))

    def test_end_to_end_against_the_real_host(self):
        from tests.host import Host as RealHost, binary
        host = Host(str(Path(self.tmp.name) / 'real.journal'), binary())
        self.addCleanup(host.close)
        r = interpret.run(self.state, host, self.ask)
        self.assertEqual(r['failed'], [])



class OAuth(unittest.TestCase):
    TOKENS = {'main': 'sk-ant-oat01-AAAAAAAA', 'spare': 'sk-ant-oat01-BBBBBBBB'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.toml = Path(self.tmp.name) / 'tokens.toml'
        self.toml.write_text(''.join(f'[[tokens]]\nname = "{n}"\nkey = "{t}"\n' for n, t in self.TOKENS.items()))
        self.toml.chmod(0o600)
        env = {'DELVETALK_MODEL_AUTH': 'oauth', 'DELVETALK_TOKENS_TOML': str(self.toml)}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
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

    def test_headers_and_most_headroom_account(self):
        r = model.ask(REQ, transport=self.transport(200), tokeman=self.probes(0.9, 0.2))
        h = self.sent[0]
        self.assertEqual((h['Authorization'], h['anthropic-beta']), ('Bearer ' + self.TOKENS['spare'], 'oauth-2025-04-20'))
        self.assertNotIn('x-api-key', h)
        self.assertEqual((r['status'], r['account'], r['rotated']), ('replied', 'spare', False))

    def test_model_bucket_headroom_and_haiku_uses_the_general_window(self):
        opus = [{'key': 'opus_5', 'label': 'Opus 5', 'window': {'utilization': 0.95, 'reset': 0}}]
        r = model.ask({**REQ, 'model': 'claude-opus-5'}, transport=self.transport(200), tokeman=self.probes(0.1, 0.5, opus))
        self.assertEqual(r['account'], 'spare')  # main's Opus bucket is nearly spent
        r = model.ask(REQ, transport=self.transport(200), tokeman=self.probes(0.1, 0.5, opus))
        self.assertEqual(r['account'], 'main')  # haiku ignores the Opus bucket

    def test_named_account_wins(self):
        os.environ['DELVETALK_MODEL_ACCOUNT'] = 'main'
        r = model.ask(REQ, transport=self.transport(200), tokeman=self.probes(0.9, 0.0))
        self.assertEqual(r['account'], 'main')

    def test_429_rotates_once_then_stops(self):
        r = model.ask(REQ, transport=self.transport(429, 200), tokeman=self.probes(0.1, 0.5))
        self.assertEqual((r['status'], r['account'], r['rotated']), ('replied', 'spare', True))
        self.assertEqual([h['Authorization'][-8:] for h in self.sent], ['AAAAAAAA', 'BBBBBBBB'])
        self.sent.clear()
        r = model.ask(REQ, transport=self.transport(529, 429), tokeman=self.probes(0.1, 0.5))
        self.assertEqual((r['status'], r['reason'], r['rotated']), ('failed', 'rate', True))
        self.assertEqual(len(self.sent), 2)

    def test_world_readable_toml_is_refused_by_name_and_nothing_is_sent(self):
        self.toml.chmod(0o644)
        r = model.ask(REQ, transport=self.transport(), tokeman=self.probes(0, 0))
        self.assertEqual((r['status'], r['reason']), ('failed', 'refused'))
        self.assertIn('tokens.toml', r['detail'])
        self.assertEqual(self.sent, [])

    def test_no_token_string_appears_in_any_result(self):
        outs = [model.ask(REQ, transport=self.transport(429, 200), tokeman=self.probes(0.1, 0.5)),
                model.ask(REQ, transport=self.transport(401, 401), tokeman=self.probes(0.1, 0.5))]
        self.toml.chmod(0o666)
        outs.append(model.ask(REQ, transport=self.transport(), tokeman=self.probes(0, 0)))
        for token in self.TOKENS.values():
            self.assertNotIn(token, json.dumps(outs))

    def test_when_every_account_is_spent_prefer_one_with_extra_usage_and_surface_billing(self):
        def probe(name, enabled, in_use=False):
            return {'token_name': name, 'quota': {'weekly': {'utilization': 1.0, 'reset': 0},
                                                  'overage_status': 'allowed' if enabled else 'rejected',
                                                  'overage_disabled_reason': None if enabled else 'out_of_credits',
                                                  'overage_in_use': in_use}}
        r = model.ask(REQ, transport=self.transport(200), tokeman=lambda: [probe('main', False), probe('spare', True, True)])
        self.assertEqual((r['account'], r['overageInUse']), ('spare', True))
        r = model.ask(REQ, transport=self.transport(200), tokeman=lambda: [probe('main', True), probe('spare', False)])
        self.assertEqual((r['account'], r['overageInUse']), ('main', False))

    def test_headroom_still_beats_overage_while_any_account_has_some(self):
        probes = [{'token_name': 'main', 'quota': {'weekly': {'utilization': 0.4}, 'overage_status': 'rejected'}},
                  {'token_name': 'spare', 'quota': {'weekly': {'utilization': 1.0}, 'overage_status': 'allowed'}}]
        self.assertEqual(model.ask(REQ, transport=self.transport(200), tokeman=lambda: probes)['account'], 'main')

    def test_key_mode_still_uses_x_api_key(self):
        os.environ.update({'DELVETALK_MODEL_AUTH': 'key', 'DELVETALK_ANTHROPIC_KEY': 'k'})
        model.ask(REQ, transport=self.transport(200))
        self.assertEqual(self.sent[0]['x-api-key'], 'k')
        self.assertNotIn('Authorization', self.sent[0])


class Spend(unittest.TestCase):
    def test_wire_never_carries_sampling_fields_and_thinking_is_opt_in(self):
        seen = []
        t = lambda *a: seen.append(json.loads(a[3])) or (200, body('{}'))
        with mock.patch.dict(os.environ, {'DELVETALK_ANTHROPIC_KEY': 'k'}, clear=True):
            model.ask({**REQ, 'temperature': 0.2, 'top_p': 0.9, 'top_k': 3}, transport=t)
            self.assertNotIn('thinking', seen[0])
            os.environ['DELVETALK_MODEL_THINKING'] = 'off'
            model.ask(REQ, transport=t)
        self.assertEqual(seen[1]['thinking'], {'type': 'disabled'})
        for wire in seen:
            self.assertEqual(set(wire) - {'thinking'}, {'model', 'max_tokens', 'system', 'messages'})

    def test_spend_log_and_ratelimit_headers(self):
        t = lambda *a: (200, body('{}'), {'Anthropic-RateLimit-Requests-Remaining': '7', 'x-other': '1'})
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'DELVETALK_ANTHROPIC_KEY': 'sekret', 'DELVETALK_KEY_NAME': 'max-grant'}, clear=True):
            r = model.ask(REQ, transport=t, state=d)
            model.ask(REQ, transport=lambda *a: (429, b'{}'), state=d)  # failures are not logged
            lines = [json.loads(x) for x in (Path(d) / 'model-spend.jsonl').read_text().splitlines()]
            self.assertNotIn('sekret', (Path(d) / 'model-spend.jsonl').read_text())
        self.assertEqual(r['rateLimits'], {'anthropic-ratelimit-requests-remaining': '7'})
        self.assertEqual(len(lines), 1)
        self.assertEqual({k: lines[0][k] for k in ('model', 'inputTokens', 'outputTokens', 'account')},
                         {'model': 'claude-haiku-5-5', 'inputTokens': 3, 'outputTokens': 4, 'account': 'max-grant'})


if __name__ == '__main__':
    unittest.main()
