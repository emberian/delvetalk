"""Source custody retains exact UTF-8 without a second world authoring workflow."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from authoring import SourceCustody
import portal


class SourceCustodyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        def forbidden(*args, **kwargs):
            raise AssertionError('Source custody cannot prepare or admit a world turn')
        self.app = SimpleNamespace(directory=Path(tmp.name), public=False, public_origin=None,
                                   csrf='custody-test', prepare=forbidden, interpretation=forbidden,
                                   execute=forbidden, repository_prepare=forbidden)
        self.app.authoring = SourceCustody(self.app)

    def test_exact_bytes_and_content_identity(self):
        for kind in ['source', 'scenarios']:
            text = '\ufeff雪\r\n\r\n' + 'e\u0301' + '\n'
            saved = self.app.authoring.source({'text': text, 'kind': kind})
            self.assertEqual(saved, self.app.authoring.source({'text': text, 'kind': kind}))
            read = self.app.authoring.read_source(saved['source'], kind)
            self.assertEqual(read['text'], text)
            self.assertEqual(read['bytes'], len(text.encode()))
            self.assertEqual(read['ref'], saved['ref'])
        self.assertFalse((self.app.directory / 'world.json').exists())
        self.assertFalse((self.app.directory / 'portal-custody').exists())

    def test_bounded_exact_source_identity_refuses_bad_input(self):
        for payload in [{'text': 'x' * 524289}, {'text': 1}, {'text': 'x', 'operation': 'compile'},
                        {'text': 'x', 'kind': 'program'}, {'text': '\ud800'}]:
            with self.subTest(payload=repr(payload)[:80]), self.assertRaises((ValueError, UnicodeError)):
                self.app.authoring.source(payload)
        with self.assertRaises(ValueError):
            self.app.authoring.read_source('../escape')

    def test_http_upload_read_and_retired_workflow_routes(self):
        server = portal.make_server(self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        self.addCleanup(conn.close)
        conn.request('POST', '/api/authoring/source', json.dumps({'text': '雪' * 30000}),
                     {'Content-Type': 'application/json', 'X-Delvetalk-CSRF': self.app.csrf})
        reply = conn.getresponse(); saved = json.loads(reply.read())
        self.assertEqual(reply.status, 200, saved)
        conn.request('GET', '/api/authoring/source?source=' + saved['source'])
        reply = conn.getresponse(); read = json.loads(reply.read())
        self.assertEqual(reply.status, 200, read)
        self.assertEqual(read['text'], '雪' * 30000)
        for route in ['prepare', 'execute', 'run', 'draft', 'status']:
            method = 'GET' if route in ['draft', 'status'] else 'POST'
            conn.request(method, '/api/authoring/' + route, '{}' if method == 'POST' else None,
                         {'Content-Type': 'application/json', 'X-Delvetalk-CSRF': self.app.csrf})
            reply = conn.getresponse(); reply.read()
            self.assertEqual(reply.status, 404, route)


if __name__ == '__main__':
    unittest.main()
