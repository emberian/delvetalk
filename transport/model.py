#!/usr/bin/env python3
"""One request to the Anthropic Messages API; strict JSON back, returned verbatim to the host.

The key comes from DELVETALK_ANTHROPIC_KEY or the file named by DELVETALK_ANTHROPIC_KEY_FILE,
never from the repo. Without a key nothing is sent. --mock DIR answers from fixtures named
<sha256 of the canonical request>.json (the raw Messages API response body).
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from transport.delve import _NoRedirect, canonical

URL = 'https://api.anthropic.com/v1/messages'
DEFAULT_MODEL = 'claude-haiku-5-5'
TIMEOUT, DEFAULT_TOKENS, MAX_TOKENS, MAX_INPUT, MAX_RESPONSE = 30, 1024, 4096, 256 * 1024, 4 * 1024 * 1024


def failed(reason, detail=''):
    return {'status': 'failed', 'reason': reason, 'detail': detail}


def key():
    if os.environ.get('DELVETALK_ANTHROPIC_KEY'):
        return os.environ['DELVETALK_ANTHROPIC_KEY'].strip()
    path = os.environ.get('DELVETALK_ANTHROPIC_KEY_FILE')
    try:
        return Path(path).expanduser().read_text().strip() if path else ''
    except OSError:
        return ''


def normalise(request):
    """-> the exact request that is hashed for mocks and sent on the wire."""
    return {'model': request.get('model') or DEFAULT_MODEL, 'system': request.get('system', ''),
            'user': request.get('user', ''), 'maxTokens': min(int(request.get('maxTokens') or DEFAULT_TOKENS), MAX_TOKENS)}


def request_hash(request):
    return hashlib.sha256(canonical(normalise(request)).encode()).hexdigest()


def http(method, url, headers, body):
    req = urllib.request.Request(url, body, headers, method=method)
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as err:
        return err.code, err.read(MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b''


def extract(text):
    """The first JSON value in text: whole, inside a fence, or after leading prose."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in '{[':
            try:
                return decoder.raw_decode(text[i:])[0]
            except ValueError:
                continue
    raise ValueError('no JSON')


def interpret_body(status, raw, model):
    if status == 0:
        return failed('transport')
    if status in (429, 529):
        return failed('rate', str(status))
    if status in (401, 403):
        return failed('refused', f'http {status}')
    if status != 200 or len(raw) > MAX_RESPONSE:
        return failed('transport', f'http {status}')
    try:
        body = json.loads(raw)
        if body.get('stop_reason') == 'refusal':
            return failed('refused', 'model refusal')
        text = ''.join(b.get('text', '') for b in body['content'] if b.get('type') == 'text')
        return {'status': 'replied', 'json': extract(text), 'raw': text, 'model': body.get('model', model),
                'usage': body.get('usage', {})}
    except (ValueError, KeyError, TypeError, AttributeError):
        return failed('malformed')


def ask(request, mock=None, transport=http):
    req = normalise(request)
    if len(req['system'].encode()) > MAX_INPUT or len(req['user'].encode()) > MAX_INPUT:
        return failed('refused', 'input too large')
    if mock:
        path = Path(mock) / (request_hash(request) + '.json')
        if not path.exists():
            return failed('transport', 'no fixture ' + path.name)
        return interpret_body(200, path.read_bytes(), req['model'])
    secret = key()
    if not secret:
        return failed('refused', 'no key: set DELVETALK_ANTHROPIC_KEY or DELVETALK_ANTHROPIC_KEY_FILE')
    wire = {'model': req['model'], 'max_tokens': req['maxTokens'], 'system': req['system'],
            'messages': [{'role': 'user', 'content': req['user']}]}
    headers = {'x-api-key': secret, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
    return interpret_body(*transport('POST', URL, headers, json.dumps(wire).encode()), req['model'])


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='model.py')
    ap.add_argument('--request-file', required=True, help='JSON {model?, system, user, maxTokens?}')
    ap.add_argument('--mock', metavar='DIR')
    a = ap.parse_args(argv)
    out.write(canonical(ask(json.loads(Path(a.request_file).read_text()), a.mock)) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
