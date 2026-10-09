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
import stat
import time
import tomllib
import urllib.request
import urllib.error

ENDPOINT = 'https://api.anthropic.com/v1/messages'
MAX_REQUEST = 65536
MAX_REPLY = 16384
MAX_JOB = 512 * 1024


def configured_credential(account=None, *, path=None):
    """Read one explicitly selected credential; never rotate or copy secrets.

    Without an account, preserve the explicit environment configuration. Tokeman
    remains the credential owner: this reader performs no refresh exchange or write.
    """
    if account is None:
        return os.environ.get('ANTHROPIC_API_KEY')
    if not isinstance(account, str) or not account:
        raise ValueError('select a nonempty tokeman account')
    path = Path(path) if path is not None else Path.home() / '.config/tokeman/tokens.toml'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ValueError('tokeman credentials require a private owner-controlled file')
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('tokeman configuration exceeds physical bound')
    try:
        configuration = tomllib.loads(raw.decode())
        if not isinstance(configuration, dict):
            raise ValueError('invalid tokeman credential configuration')
        tokens = configuration.get('tokens', [])
        if not isinstance(tokens, list) or any(not isinstance(entry, dict) for entry in tokens):
            raise ValueError('invalid tokeman credential configuration')
        selected = [entry for entry in tokens if entry.get('name') == account]
        if len(selected) != 1:
            raise ValueError('select exactly one configured tokeman account')
        entry = selected[0]
        expiry = entry.get('expires_at')
        if expiry is not None and type(expiry) is not int:
            raise ValueError('invalid tokeman credential expiry')
        if (entry.get('refresh_token') and not entry.get('login_error')
                and isinstance(entry.get('access_token'), str)
                and (expiry is None or expiry > int(time.time() * 1000) + 120000)):
            return entry['access_token']
        if isinstance(entry.get('key'), str) and entry['key']:
            return entry['key']
    except (TypeError, UnicodeError, tomllib.TOMLDecodeError):
        raise ValueError('invalid tokeman credential configuration') from None
    raise ValueError('selected tokeman account has no usable inference credential')


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


class ProviderHTTPError(Exception):
    """Confirmed HTTP refusal; retain physical status without remote text."""
    def __init__(self, code, *, error_type=None):
        self.code = code
        self.error_type = error_type
        super().__init__('provider returned HTTP ' + str(code))


class ProviderInputError(ValueError):
    """The bounded physical frame was refused before any HTTP request."""


class AnthropicMessages:
    def __init__(self, api_key):
        if not isinstance(api_key, str) or not api_key or len(api_key) > 4096 or '\n' in api_key or '\r' in api_key:
            raise ValueError('an explicitly configured API key is required')
        self.api_key = api_key

    def __call__(self, body):
        if (not isinstance(body, dict)
                or set(body) != {'model', 'max_tokens', 'stream', 'system', 'messages'}
                or type(body['max_tokens']) is not int or not 1 <= body['max_tokens'] <= 1024
                or body['stream'] is not False):
            raise ProviderInputError('bounded Messages frame required')
        try:
            raw_request = encoded(body)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise ProviderInputError('Messages frame exceeds physical encoding bounds') from None
        headers = {'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'}
        if self.api_key.startswith('sk-ant-oat01-'):
            headers.update({'Authorization': 'Bearer ' + self.api_key, 'anthropic-beta': 'oauth-2025-04-20'})
        else:
            headers['x-api-key'] = self.api_key
        request = urllib.request.Request(ENDPOINT, data=raw_request, headers=headers, method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        try:
            with opener.open(request, timeout=15) as response:
                raw = response.read(MAX_REPLY + 1)
        except urllib.error.HTTPError as error:
            error_type = None
            try:
                diagnostic = loads(error.read(MAX_REPLY + 1))
                category = diagnostic.get('error', {}).get('type')
                if category in ('authentication_error', 'permission_error', 'rate_limit_error',
                                'invalid_request_error', 'not_found_error', 'overloaded_error', 'api_error'):
                    error_type = category
            except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError, OSError):
                pass
            error.close()
            raise ProviderHTTPError(error.code, error_type=error_type) from None
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
            except ProviderHTTPError as error:
                saved.update(status='rejected', httpStatus=error.code)
                if error.error_type is not None:
                    saved['errorType'] = error.error_type
            except ProviderInputError:
                saved.update(status='unsupported')
            except Exception:
                # No response body, key, or remote diagnostic is reflected.
                saved.update(status='uncertain')
            save(path, saved)
            return saved
