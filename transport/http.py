#!/usr/bin/env python3
"""Run as `python3 -m transport.http` (never as a script: this file would shadow stdlib http).

HTTP front on the world host: /AGENTS.md. Carries bytes and a verified principal;
it validates nothing but size and JSON well-formedness. Host replies pass through.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from transport.delve import Client, canonical, http_transport
from transport.identity import Identity, IdentityError, ORIGIN

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / 'docs' / 'AGENTS-API.md'
BINARY = os.environ.get('DELVETALK_OBEND', '/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend')
MAX_BODY, RATE, WINDOW, HOST_TIMEOUT, DELIVER_LIMIT = 64 * 1024, 32, 60, 120, 16
PREFIX = '/AGENTS.md'


class HostDied(Exception):
    pass


class Host:
    """One host subprocess, one request at a time; respawned and reopened if it dies."""

    def __init__(self, journal, binary=BINARY):
        self.journal, self.binary, self.proc = journal, binary, None
        self.lock = threading.Lock()

    def _spawn(self):
        self.proc = subprocess.Popen([self.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        reply = self._exchange({'op': 'world-open', 'path': self.journal})
        if reply.get('status') != 'opened':
            raise HostDied('world-open refused: ' + json.dumps(reply))

    def _exchange(self, request):
        watchdog = threading.Timer(HOST_TIMEOUT, self.proc.kill)
        watchdog.start()
        try:
            self.proc.stdin.write(json.dumps(request) + '\n')
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        except (BrokenPipeError, OSError, ValueError):
            line = ''
        finally:
            watchdog.cancel()
        if not line:
            raise HostDied('host closed its output')
        return json.loads(line)

    def send(self, request):
        """A turn is retried once after a restart: the host answers a repeated identity with the original receipt."""
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.proc is None or self.proc.poll() is not None:
                        self.close()
                        self._spawn()
                    return self._exchange(request)
                except (HostDied, ValueError):
                    self.close()
                    if attempt:
                        return {'status': 'error', 'message': 'host unavailable'}

    def close(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            for s in (self.proc.stdin, self.proc.stdout):
                s.close()
            self.proc = None


class Front(HTTPServer):
    def __init__(self, address, host, identity, origin=ORIGIN, clock=time.time):
        super().__init__(address, Handler)
        self.host, self.identity, self.origin, self.clock = host, identity, origin, clock
        self.hits = {}

    def limited(self, credential):
        now = self.clock()
        hits = [t for t in self.hits.get(credential, []) if now - t < WINDOW]
        self.hits[credential] = hits + [now]
        return len(hits) >= RATE

    def guide(self):
        return GUIDE.read_text().replace('{{origin}}', self.origin)


class Handler(BaseHTTPRequestHandler):
    server_version = 'DelveTalk'

    def log_message(self, *args):
        pass

    def reply(self, code, body, ctype='application/json'):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)

    def fail(self, code, message):
        self.reply(code, canonical({'status': 'error', 'message': message}))

    def body(self):
        """-> dict, or None after replying with the refusal."""
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self.fail(400, 'bad Content-Length')
        if n > MAX_BODY:
            return self.fail(413, f'body exceeds {MAX_BODY} bytes')
        try:
            data = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self.fail(400, 'body is not valid JSON')
        return data if isinstance(data, dict) else self.fail(400, 'body must be a JSON object')

    def host(self, request):
        reply = self.server.host.send(request)
        self.reply(400 if reply.get('status') == 'error' else 200, canonical(reply))

    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')

    def route(self, method):
        path = urllib.parse.urlsplit(self.path).path
        if method == 'GET' and path == PREFIX:
            return self.reply(200, self.server.guide(), 'text/plain')
        parts = [urllib.parse.unquote(p) for p in path.split('/')[1:]]
        if parts[:1] != ['AGENTS.md']:
            return self.fail(404, f'unknown route; read {self.server.origin}{PREFIX}')
        rest = parts[1:]
        if method == 'POST' and rest in (['challenge'], ['verify']):
            data = self.body()
            if data is None:
                return
            try:
                if rest == ['challenge']:
                    out = self.server.identity.challenge(data.get('handle'))
                else:
                    out = self.server.identity.verify(data.get('handle'), data.get('uri'))
            except IdentityError as e:
                return self.fail(400, e.code)
            return self.reply(200, canonical(out))
        kind = None
        if method == 'GET' and len(rest) == 2 and rest[0] == 'world':
            kind = 'view'
        elif method == 'POST' and len(rest) == 3 and rest[0] == 'world':
            kind = 'turn'
        elif method == 'GET' and len(rest) == 2 and rest[0] == 'receipt':
            kind = 'receipt'
        elif method == 'POST' and rest == ['deliver']:
            kind = 'deliver'
        elif method == 'GET' and rest == ['pending']:
            kind = 'pending'
        if kind is None:
            return self.fail(404, f'unknown route; read {self.server.origin}{PREFIX}')
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else ''
        try:
            principal = self.server.identity.authenticate(credential)['handle']
        except IdentityError:
            return self.fail(401, 'missing, unverified or revoked credential')
        if self.server.limited(credential):
            return self.fail(429, f'more than {RATE} requests per {WINDOW} seconds')
        if kind == 'view':
            return self.host({'op': 'world-view', 'principal': principal, 'object': rest[1]})
        if kind == 'receipt':
            return self.host({'op': 'world-receipt', 'principal': principal, 'identity': rest[1]})
        if kind == 'pending':
            return self.host({'op': 'world-pending'})
        if kind == 'deliver':
            if self.body() is None:
                return
            return self.host({'op': 'world-deliver', 'limit': DELIVER_LIMIT})
        data = self.body()
        if data is None:
            return
        self.host({'op': 'world-turn', 'principal': principal, 'object': rest[1], 'method': rest[2],
                   'argument': data.get('argument', {'tag': 'record', 'fields': []}), 'identity': data.get('intent')})


def main(argv=None):
    ap = argparse.ArgumentParser(prog='http.py')
    ap.add_argument('--state', required=True)
    ap.add_argument('--journal', required=True)
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--bind', default='127.0.0.1')
    ap.add_argument('--origin', default=ORIGIN)
    a = ap.parse_args(argv)
    front = Front((a.bind, a.port), Host(a.journal), Identity(a.state, Client(http_transport), a.origin), a.origin)
    try:
        front.serve_forever()
    finally:
        front.host.close()


if __name__ == '__main__':
    sys.exit(main())
