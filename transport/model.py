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
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from transport.delve import _NoRedirect, canonical

URL = 'https://api.anthropic.com/v1/messages'
DEFAULT_MODEL = 'claude-haiku-5-5'
TOKENS_TOML = '~/.config/tokeman/tokens.toml'
BETA = 'oauth-2025-04-20'
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


def ask(request, mock=None, transport=http, tokeman=None):
    req = normalise(request)
    if len(req['system'].encode()) > MAX_INPUT or len(req['user'].encode()) > MAX_INPUT:
        return failed('refused', 'input too large')
    if mock:
        path = Path(mock) / (request_hash(request) + '.json')
        if not path.exists():
            return failed('transport', 'no fixture ' + path.name)
        return interpret_body(200, path.read_bytes(), req['model'])
    wire = json.dumps({'model': req['model'], 'max_tokens': req['maxTokens'], 'system': req['system'],
                       'messages': [{'role': 'user', 'content': req['user']}]}).encode()
    base = {'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
    if os.environ.get('DELVETALK_MODEL_AUTH', 'key') == 'oauth':
        return ask_oauth(req, wire, base, transport, tokeman)
    secret = key()
    if not secret:
        return failed('refused', 'no key: set DELVETALK_ANTHROPIC_KEY or DELVETALK_ANTHROPIC_KEY_FILE')
    return interpret_body(*transport('POST', URL, {**base, 'x-api-key': secret}, wire), req['model'])


def load_accounts():
    """-> {name: token} from tokeman's toml, or a failed() result. Never copied, never logged."""
    path = Path(os.environ.get('DELVETALK_TOKENS_TOML') or TOKENS_TOML).expanduser()
    try:
        if path.stat().st_mode & 0o077:
            return failed('refused', f'{path.name} is group/other-readable; chmod 600')
        data = tomllib.loads(path.read_text())
    except (OSError, ValueError):
        return failed('refused', f'cannot read {path.name}')
    rows = next((v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
    now_ms = time.time() * 1000
    accounts = {}
    for row in rows:
        token = row.get('key') or (row.get('access_token') if row.get('expires_at', now_ms + 1) > now_ms else '')
        if row.get('name') and token:
            accounts[row['name']] = token
    return accounts or failed('refused', 'no usable account in ' + path.name)


def run_tokeman():
    try:
        out = subprocess.run(['tokeman', '--json'], capture_output=True, text=True, timeout=60).stdout
        data = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])


def headroom(probe, model):
    """Seven-day remaining fraction for the model's bucket; Haiku and unknown models use the general window."""
    usage = (probe.get('quota') or {}).get('weekly') or {}
    for bucket in ((probe.get('model_usage') or {}).get('scoped_weekly') or []):
        label = (bucket.get('key', '') + ' ' + bucket.get('label', '')).lower()
        family = next((f for f in ('opus', 'sonnet', 'fable') if f in model.lower()), None)
        if family and family in label:
            usage = bucket.get('window') or usage
            break
    return 1.0 - usage['utilization'] if 'utilization' in usage else -1.0


def overage_enabled(probe):
    """Extra usage (tokeman's `overage`) is available: a status other than rejected/disabled and no disabled reason."""
    q = probe.get('quota') or {}
    return q.get('overage_status') not in (None, 'rejected', 'disabled') and not q.get('overage_disabled_reason')


def ask_oauth(req, wire, base, transport, tokeman):
    accounts = load_accounts()
    if 'status' in accounts:
        return accounts
    probes = {p['token_name']: p for p in (tokeman or run_tokeman)() if p.get('token_name') in accounts and not p.get('error')}
    exhausted = bool(probes) and all(headroom(p, req['model']) <= 0 for p in probes.values())
    ranked = sorted(probes, key=lambda n: (exhausted and not overage_enabled(probes[n]), -headroom(probes[n], req['model'])))
    ranked += [n for n in accounts if n not in ranked]
    chosen = os.environ.get('DELVETALK_MODEL_ACCOUNT')
    order = ([chosen] + [n for n in ranked if n != chosen]) if chosen in accounts else ranked
    for i, name in enumerate(order[:2]):
        headers = {**base, 'Authorization': 'Bearer ' + accounts[name], 'anthropic-beta': BETA}
        status, raw = transport('POST', URL, headers, wire)
        if status in (429, 529) and i == 0 and len(order) > 1:
            continue
        out = interpret_body(status, raw, req['model'])
        billed = bool(((probes.get(name) or {}).get('quota') or {}).get('overage_in_use'))
        return {**out, 'account': name, 'rotated': i == 1, 'overageInUse': billed}
    return failed('rate', 'no account')


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
