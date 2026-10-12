"""One request to the Anthropic Messages API; the model's text back as `raw`, returned verbatim to the host.

The key comes from the file the config's `anthropic_key_file` names, never from the repo; without a key nothing is
sent. With `model_mock` the answer is the fixture <sha256 of the canonical request>.json (a raw Messages API response
body). Every replied call is a line of <state>/model-spend.jsonl, which `spent` totals.
"""
import hashlib
import json
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from transport.delve import _NoRedirect, canonical

URL = 'https://api.anthropic.com/v1/messages'
DEFAULT_MODEL = 'claude-haiku-5-5'
BETA = 'oauth-2025-04-20'
TIMEOUT, DEFAULT_TOKENS, MAX_TOKENS, MAX_INPUT, MAX_RESPONSE = 30, 1024, 4096, 256 * 1024, 4 * 1024 * 1024
RATES = {'input': 0.10, 'output': 0.50}  # dollars per million tokens, Haiku 5.5's published rates


def failed(reason, detail=''):
    return {'status': 'failed', 'reason': reason, 'detail': detail}


def key(path):
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
            return resp.status, resp.read(MAX_RESPONSE + 1), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read(MAX_RESPONSE + 1), dict(err.headers)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b'', {}


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
    except (ValueError, KeyError, TypeError, AttributeError):
        return failed('malformed')
    return {'status': 'replied', 'raw': text, 'model': body.get('model', model), 'usage': body.get('usage', {})}  # the host reads `raw`


def call(transport, headers, wire, model_id):
    """One wire call -> (status, result with any anthropic-ratelimit-* headers attached)."""
    status, raw, *rest = transport('POST', URL, headers, wire)
    out = interpret_body(status, raw, model_id)
    limits = {k.lower(): v for k, v in (rest[0] if rest else {}).items() if k.lower().startswith('anthropic-ratelimit-')}
    return status, ({**out, 'rateLimits': limits} if limits else out)


def spend(st, out, who, use=None):
    """Append one line per replied call so the operator can total spend against the monthly grant; `use` names what the
    call was for (`paint`; none for an interpretation)."""
    if out.get('status') == 'replied':
        usage = out.get('usage') or {}
        st.append(st.spend, canonical({'at': time.time(), 'world': st.world, 'model': out.get('model'), 'inputTokens': usage.get('input_tokens'),
                                       'outputTokens': usage.get('output_tokens'), 'account': who, **({'use': use} if use else {})}))
    return out


def spent(st, start=0):
    """{UTC month: {calls, inputTokens, outputTokens, dollars}} of the replied calls at or after unix time `start`, every
    world's, with `all` their sum."""
    out = {}
    for row in st.lines(st.spend):
        for k in ('all', time.strftime('%Y-%m', time.gmtime(row['at']))) if row['at'] >= start else ():
            t = out.setdefault(k, {'calls': 0, 'inputTokens': 0, 'outputTokens': 0})
            t['calls'] += 1
            t['inputTokens'] += row.get('inputTokens') or 0
            t['outputTokens'] += row.get('outputTokens') or 0
    out.setdefault('all', {'calls': 0, 'inputTokens': 0, 'outputTokens': 0})
    for t in out.values():
        t['dollars'] = round((t['inputTokens'] * RATES['input'] + t['outputTokens'] * RATES['output']) / 1e6, 4)
    return out


def ask(request, st, transport=http, tokeman=None):
    req, c = normalise(request), st.config
    if len(req['system'].encode()) > MAX_INPUT or len(req['user'].encode()) > MAX_INPUT:
        return failed('refused', 'input too large')
    if c.model_mock:
        path = Path(c.model_mock) / (request_hash(request) + '.json')
        if not path.exists():
            return failed('transport', 'no fixture ' + path.name)
        return interpret_body(200, path.read_bytes(), req['model'])
    # Only these fields are ever sent: never temperature, top_p or top_k (Haiku 5.5 answers 400 for some values).
    body = {'model': req['model'], 'max_tokens': req['maxTokens'], 'system': req['system'],
            'messages': [{'role': 'user', 'content': req['user']}]}
    if not c.model_thinking:  # adaptive thinking spent 0 to 337 output tokens on `unclear:` lines
        body['thinking'] = {'type': 'disabled'}
    wire = json.dumps(body).encode()
    base = {'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
    if c.model_auth == 'oauth':
        return ask_oauth(req, wire, base, transport, tokeman, st, request.get('use'))
    secret = key(c.anthropic_key_file)
    if not secret:
        return failed('refused', 'no key: anthropic_key_file names none')
    return spend(st, call(transport, {**base, 'x-api-key': secret}, wire, req['model'])[1], c.key_name, request.get('use'))


def load_accounts(path):
    """-> {name: token} from tokeman's toml, or a failed() result. Never copied, never logged."""
    path = Path(path).expanduser()
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


def ask_oauth(req, wire, base, transport, tokeman, st, use=None):
    accounts = load_accounts(st.config.tokens_toml)
    if 'status' in accounts:
        return accounts
    probes = {p['token_name']: p for p in (tokeman or run_tokeman)() if p.get('token_name') in accounts and not p.get('error')}
    exhausted = bool(probes) and all(headroom(p, req['model']) <= 0 for p in probes.values())
    ranked = sorted(probes, key=lambda n: (exhausted and not overage_enabled(probes[n]), -headroom(probes[n], req['model'])))
    ranked += [n for n in accounts if n not in ranked]
    chosen = st.config.model_account
    order = ([chosen] + [n for n in ranked if n != chosen]) if chosen in accounts else ranked
    for i, name in enumerate(order[:2]):
        headers = {**base, 'Authorization': 'Bearer ' + accounts[name], 'anthropic-beta': BETA}
        status, out = call(transport, headers, wire, req['model'])
        if status in (429, 529) and i == 0 and len(order) > 1:
            continue
        billed = bool(((probes.get(name) or {}).get('quota') or {}).get('overage_in_use'))
        return spend(st, {**out, 'account': name, 'rotated': i == 1, 'overageInUse': billed}, name, use)
    return failed('rate', 'no account')

