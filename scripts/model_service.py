"""Bounded physical Messages transport and exact job/receipt custody.

No prompts, schemas, offer selection or escalation policy are authored here.
An attempted job with no receipt stays uncertain: replay never spends again.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import ssl
import urllib.request

ENDPOINT = 'https://api.anthropic.com/v1/messages'
MAX_REQUEST = 65536
MAX_REPLY = 16384
MAX_JOB = 512 * 1024


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON member')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('nonfinite number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def encoded(value, maximum=MAX_REQUEST):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True).encode()
    if len(raw) > maximum:
        raise ValueError('physical frame too large')
    return raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('provider redirects are forbidden')


class AnthropicMessages:
    def __init__(self, api_key):
        if not isinstance(api_key, str) or not api_key or len(api_key) > 4096 or '\n' in api_key or '\r' in api_key:
            raise ValueError('an explicitly configured API key is required')
        self.api_key = api_key

    def __call__(self, body):
        if (set(body) != {'model', 'max_tokens', 'stream', 'system', 'messages'}
                or type(body['max_tokens']) is not int or not 1 <= body['max_tokens'] <= 1024
                or body['stream'] is not False):
            raise ValueError('bounded Messages frame required')
        request = urllib.request.Request(ENDPOINT, data=encoded(body), headers={
            'Content-Type': 'application/json', 'anthropic-version': '2023-06-01',
            'x-api-key': self.api_key}, method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        with opener.open(request, timeout=15) as response:
            raw = response.read(MAX_REPLY + 1)
        if len(raw) > MAX_REPLY:
            raise ValueError('provider response exceeds bound')
        return loads(raw)


def save(path, value):
    raw = encoded(value, MAX_JOB + MAX_REPLY + 4096)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class Service:
    def __init__(self, directory, provider, *, max_jobs=32, max_bytes=4 * 1024 * 1024):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.provider = provider
        if type(max_jobs) is not int or not 1 <= max_jobs <= 1024 or type(max_bytes) is not int or not 262144 <= max_bytes <= 268435456:
            raise ValueError('explicit bounded model service quota required')
        self.max_jobs = max_jobs
        self.max_bytes = max_bytes

    def request(self, job):
        """Explicit activity only; exact repeats return custody, never a new call."""
        raw = encoded(job, MAX_JOB)
        key = hashlib.sha256(raw).hexdigest()
        path = self.directory / (key + '.json')
        fd = os.open(self.directory / 'service.lock', os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'key': key, 'job': job, 'status': 'busy', 'reply': None}
            if path.exists():
                saved = loads(path.read_bytes())
                if encoded(saved['job'], MAX_JOB) != raw:
                    raise ValueError('job custody mismatch')
                return saved
            retained = list(self.directory.glob('*.json'))
            interrupted = list(self.directory.glob('*.tmp'))
            # Reserve one bounded receipt per job, so future completion cannot
            # exceed the explicitly configured physical custody budget.
            reserved = sum(item.stat().st_size + MAX_REPLY + 1024 for item in retained) + sum(item.stat().st_size for item in interrupted)
            if len({item.stem for item in retained + interrupted}) >= self.max_jobs or reserved + len(raw) + MAX_REPLY + 1024 > self.max_bytes:
                return {'key': key, 'job': job, 'status': 'quota', 'reply': None}
            saved = {'key': key, 'job': job, 'status': 'pending', 'reply': None}
            save(path, saved)  # Durable before crossing the physical boundary.
            try:
                reply = self.provider(job['body'])
                encoded(reply, MAX_REPLY)
                saved.update(status='received', reply=reply)
            except Exception:
                # No response body, key, or remote diagnostic is reflected.
                saved.update(status='uncertain')
            save(path, saved)
            return saved
