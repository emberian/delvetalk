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
from transport.http import Host

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
        self.assertEqual(self.ask(200, body('no json here'))['reason'], 'malformed')
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

    def test_a_failed_model_call_is_settled_as_the_failure_reply(self):
        interpret.run(self.state, self.host, lambda req: model.failed('rate'))
        self.assertEqual(self.settled()[0]['reply'], {'status': 'failed', 'reason': 'rate', 'detail': ''})

    def test_end_to_end_against_the_real_host(self):
        from tests.host import Host as RealHost, binary
        host = Host(str(Path(self.tmp.name) / 'real.journal'), binary())
        self.addCleanup(host.close)
        r = interpret.run(self.state, host, self.ask)
        self.assertEqual(r['failed'], [])


if __name__ == '__main__':
    unittest.main()
