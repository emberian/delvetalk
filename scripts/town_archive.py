#!/usr/bin/env python3
"""Bounded private AppView observations; no writes, credentials or signed proof."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('archive_delve', ROOT / 'scripts/delve.py')
delve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delve)
FEED = 'at://did:plc:qzqct2rrq4u2gmy5g3mjxske/town.delve.feed.generator/town'
DEFAULT_STATE = '~/claude_state/delvetalk/watch/archive'
ALLOWED = {
    'town.delve.feed.getFeed': {'feed', 'limit', 'cursor'},
    'town.delve.feed.searchPosts': {'q', 'limit', 'cursor'},
    'town.delve.feed.getPostThread': {'uri', 'depth', 'parentHeight'},
}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def identities(response):
    """Record pins are observed claims, not independently validated CIDs."""
    found = {}
    queue = [response]
    while queue:
        value = queue.pop()
        if isinstance(value, dict):
            if isinstance(value.get('uri'), str) and isinstance(value.get('cid'), str) and isinstance(value.get('record'), dict):
                pin = {'uri': value['uri'], 'cid': value['cid'], 'contentSha256': digest(value['record'])}
                found[digest(pin)] = pin
            queue.extend(value.values())
        elif isinstance(value, list):
            queue.extend(value)
    return list(found.values())


class Archive:
    """Public-GET-only transport decorator with immutable captures and progress."""
    def __init__(self, state=DEFAULT_STATE, request=None, *, max_requests=45, max_bytes=64 * 1024 * 1024):
        if type(max_requests) is not int or max_requests < 1 or type(max_bytes) is not int or max_bytes < 1:
            raise ValueError('archive bounds must be positive integers')
        self.state = Path(state).expanduser()
        self.request = request or delve.HTTP()
        self.max_requests, self.max_bytes = max_requests, max_bytes
        self.path = self.state / 'manifests' / (uuid.uuid4().hex + '.json')
        self.manifest = {'format': 'delvetalk-town-archive-v1', 'startedAt': stamp(),
                         'evidence': 'AppView observations; no CID/signature verification',
                         'status': 'running', 'requests': [], 'retainedBytes': 0,
                         'bounds': {'requests': max_requests, 'bytes': max_bytes}}
        self._save()

    def _save(self):
        delve.save(self.path, self.manifest)

    def __call__(self, method, base, nsid, *, params=None):
        params = params or {}
        if method != 'GET' or base != delve.APPVIEW or nsid not in ALLOWED or set(params) - ALLOWED[nsid]:
            raise ValueError('archive accepts only whitelisted public AppView GET requests')
        if len(self.manifest['requests']) >= self.max_requests:
            raise delve.Failure('archive request bound reached')
        entry = {'nsid': nsid, 'params': dict(params), 'startedAt': stamp(), 'status': 'pending'}
        self.manifest['requests'].append(entry)
        self._save()  # A crash leaves an explicit pending request, not invented success.
        try:
            response = self.request(method, base, nsid, params=params)
        except (ValueError, TypeError, AttributeError, OSError, delve.Failure) as error:
            entry.update(status='failed', finishedAt=stamp(), error=type(error).__name__)
            self._save()  # Never persist transport messages, tokens or headers.
            raise delve.Failure('public archive request failed') from None
        capture = {'format': 'delvetalk-appview-capture-v1', 'nsid': nsid,
                   'params': dict(params), 'response': response}
        size = len(encoded(capture))
        if self.manifest['retainedBytes'] + size > self.max_bytes:
            entry.update(status='unretained', finishedAt=stamp(), error='capture byte bound reached')
            self._save()
            raise delve.Failure('archive byte bound reached')
        identity = digest(capture)
        path = self.state / 'captures' / (identity + '.json')
        with delve.locked(self.state / '.archive.lock'):
            if not path.exists():
                delve.save(path, capture)
        entry.update(status='captured', finishedAt=stamp(), capture=identity,
                     records=identities(response), bytes=size)
        self.manifest['retainedBytes'] += size
        self._save()
        return response

    def finish(self, coverage=None, errors=None):
        partial = bool(errors) or any(entry['status'] != 'captured' for entry in self.manifest['requests'])
        self.manifest.update(status='partial' if partial else 'complete', finishedAt=stamp(),
                             coverage=coverage or {}, errors=errors or [])
        self._save()
        return str(self.path.resolve())


def backfill(state=DEFAULT_STATE, *, pages=3, request=None):
    if not 1 <= pages <= 20:
        raise ValueError('page bounds must be 1..20')
    state = Path(state).expanduser()
    with delve.locked(state / '.backfill.lock'):
        progress_path = state / 'backfill.json'
        progress = json.loads(progress_path.read_text()) if progress_path.exists() else {
            'format': 'delvetalk-town-backfill-v1', 'feed': FEED, 'cursor': None,
            'complete': False, 'pages': 0, 'captures': []}
        if progress.get('format') != 'delvetalk-town-backfill-v1' or progress.get('feed') != FEED:
            raise ValueError('unsupported backfill state')
        if progress['complete']:
            return {'complete': True, 'pages': 0, 'cursor': None}
        archive = Archive(state, request, max_requests=pages)
        coverage = {'pages': 0, 'posts': 0, 'cursor': progress['cursor'], 'truncated': True}
        errors = []
        seen = set()
        try:
            for _ in range(pages):
                params = {'feed': FEED, 'limit': 50}
                if progress['cursor']:
                    params['cursor'] = progress['cursor']
                response = archive('GET', delve.APPVIEW, 'town.delve.feed.getFeed', params=params)
                rows, cursor = response.get('feed'), response.get('cursor')
                if not isinstance(rows, list) or (cursor is not None and (not isinstance(cursor, str) or not cursor)):
                    raise ValueError('invalid feed page')
                if cursor is not None and (cursor == progress['cursor'] or cursor in seen):
                    raise ValueError('repeated feed cursor')
                seen.add(cursor)
                progress['cursor'] = cursor
                progress['complete'] = cursor is None
                progress['pages'] += 1
                progress['captures'].append(archive.manifest['requests'][-1]['capture'])
                progress['manifest'] = str(archive.path.resolve())
                delve.save(progress_path, progress)  # Cursor advances only after capture is durable.
                coverage.update(pages=coverage['pages'] + 1, posts=coverage['posts'] + len(rows),
                                cursor=cursor, truncated=cursor is not None)
                if cursor is None:
                    break
        except (ValueError, TypeError, AttributeError, OSError, delve.Failure) as error:
            errors.append({'source': 'feed', 'error': type(error).__name__})
        manifest = archive.finish(coverage, errors)
        return {'complete': progress['complete'], 'coverage': coverage, 'errors': errors, 'manifest': manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default=DEFAULT_STATE)
    parser.add_argument('--pages', type=int, default=3)
    args = parser.parse_args()
    try:
        result = backfill(args.state, pages=args.pages)
        print(json.dumps(result))
        return 1 if result.get('errors') else 0
    except (ValueError, OSError, delve.Failure):
        print('archive: local/configuration failure')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
