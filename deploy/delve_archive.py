#!/usr/bin/env python3
"""Read-only, resumable archive of every public `town.delve.feed.post` on pds.delve.town.

Reads only public, unauthenticated endpoints: the PDS's `com.atproto.sync.listRepos`,
`com.atproto.repo.describeRepo` (handle) and `com.atproto.repo.listRecords`, and the AppView's
`town.delve.actor.getProfile` (labels; delve.town/llms.txt asks readers to honour an author's
`!no-unauthenticated`). It never authenticates, posts, likes or follows.

Town members whose repos live on another PDS (penny.hailey.at, trinity.automata.garden, ...) are
not in listRepos. After the PDS's own repos, every DID that a crawled post replies to, quotes or
mentions and that the PDS does not list is resolved through plc.directory (or did:web) and its
own PDS is read the same way, for `town.delve.feed.post` only, until no new DID appears
(--no-foreign skips this; repos.jsonl marks them `foreign`).

  python3 deploy/delve_archive.py                  # full crawl, resumes where it stopped
  python3 deploy/delve_archive.py --since 2026-10-11T00:00:00Z   # incremental: newer posts only

Output (outside Git: the posts of real people are not committed), under --out
(default ~/dev/delvetalk2-archive):
  posts.jsonl   one line per post: uri, cid, did, handle, createdAt, text, root, parent, quote,
                tags, mentions (DIDs), links, langs
  repos.jsonl   one line per repo: did, handle, active, labels, noUnauthenticated, posts
  state.json    per-repo progress (cursor, done), so an interrupted crawl resumes
                (state.since.json for an interrupted --since pass)
  cache/        every page fetched, by URL hash; a full crawl reuses cached pages, --since
                refetches the first pages and stops at the first record older than its cut

Gentle by construction: at most 2 requests a second (--rate), Retry-After / RateLimit-Reset on
429 and 5xx, exponential backoff, one process.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PDS = 'https://pds.delve.town'
APPVIEW = 'https://api.delve.town'
COLLECTION = 'town.delve.feed.post'
AGENT = 'delvetalk-archive/1 (read-only; ember.delve.town)'


class Client:
    def __init__(self, cache, rate):
        self.cache, self.gap, self.last, self.requests = cache, 1.0 / rate, 0.0, 0
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, base, method, params, fresh=False):
        return self.fetch(f'{base}/xrpc/{method}?{urllib.parse.urlencode(params)}', method, fresh)

    def fetch(self, url, method, fresh=False):
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if path.exists() and not fresh:
            return json.loads(path.read_text())['body']
        for attempt in range(8):
            wait = self.last + self.gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            self.requests += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': AGENT}), timeout=60) as r:
                    body = json.loads(r.read())
                tmp = path.with_suffix('.tmp')
                tmp.write_text(json.dumps({'url': url, 'fetched': time.time(), 'body': body}))
                os.replace(tmp, path)
                return body
            except urllib.error.HTTPError as e:
                if e.code in (400, 404, 410):   # RepoNotFound, a tombstoned DID: an answer, not a failure
                    try:
                        return {'error': json.loads(e.read()).get('error', 'HTTP 400')}
                    except ValueError:
                        return {'error': 'HTTP 400'}
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                delay = backoff(e.headers, attempt)
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                delay = min(300, 2 ** attempt * 2)
            print(f'backing off {delay:.0f}s: {method}', file=sys.stderr)
            time.sleep(delay)
        raise RuntimeError(f'gave up on {url}')


def backoff(headers, attempt):
    if headers.get('Retry-After', '').isdigit():
        return int(headers['Retry-After'])
    reset = headers.get('RateLimit-Reset', '')
    if reset.isdigit() and int(reset) > time.time():
        return min(600, int(reset) - time.time() + 1)
    return min(300, 2 ** attempt * 2)


def row(record, did, handle):
    v = record['value']
    tags, mentions, links = [], [], []
    for facet in v.get('facets') or []:
        for f in facet.get('features') or []:
            kind = f.get('$type', '').rsplit('#', 1)[-1]
            if kind == 'tag':
                tags.append(f.get('tag'))
            elif kind == 'mention':
                mentions.append(f.get('did'))
            elif kind == 'link':
                links.append(f.get('uri'))
    reply = v.get('reply') or {}
    embed = v.get('embed') or {}
    quote = (embed.get('record') or {}).get('uri') or ((embed.get('record') or {}).get('record') or {}).get('uri')
    return {'uri': record['uri'], 'cid': record['cid'], 'did': did, 'handle': handle,
            'createdAt': v.get('createdAt'), 'text': v.get('text', ''),
            'root': (reply.get('root') or {}).get('uri'), 'parent': (reply.get('parent') or {}).get('uri'),
            'quote': quote, 'tags': tags, 'mentions': mentions, 'links': links, 'langs': v.get('langs')}


def list_repos(client, fresh):
    repos, cursor = [], None
    while True:
        params = {'limit': 500} | ({'cursor': cursor} if cursor else {})
        page = client.get(PDS, 'com.atproto.sync.listRepos', params, fresh=fresh)
        repos += page.get('repos', [])
        cursor = page.get('cursor')
        if not cursor or not page.get('repos'):
            return repos


def foreign(client, posts_path, known):
    """DIDs the crawl's posts reply to, quote or mention that no crawled repo holds, with their PDS."""
    dids = set()
    with posts_path.open() as f:
        for line in f:
            p = json.loads(line)
            for uri in (p['root'], p['parent'], p['quote']):
                if uri and uri.startswith('at://did:'):
                    dids.add(uri[5:].split('/')[0])
            dids.update(m for m in p['mentions'] if m and m.startswith('did:'))
    out = []
    for did in sorted(dids - known):
        if did.startswith('did:plc:'):
            doc = client.fetch(f'https://plc.directory/{did}', 'plc.directory')
        elif did.startswith('did:web:'):
            doc = client.fetch(f'https://{did[8:]}/.well-known/did.json', 'did:web')
        else:
            continue
        pds = next((s.get('serviceEndpoint') for s in doc.get('service') or []
                    if s.get('id', '').endswith('#atproto_pds')), None)
        if pds:
            out.append({'did': did, 'pds': pds.rstrip('/'), 'active': True})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', type=Path, default=Path.home() / 'dev' / 'delvetalk2-archive')
    ap.add_argument('--since', help='ISO time; fetch only posts created at or after it (fresh pages)')
    ap.add_argument('--rate', type=float, default=2.0, help='requests per second, at most')
    ap.add_argument('--no-foreign', action='store_true', help='only the repos pds.delve.town lists')
    a = ap.parse_args()
    out = a.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    client = Client(out / 'cache', min(a.rate, 2.0))
    fresh = a.since is not None
    posts_path = out / 'posts.jsonl'
    state_path = out / ('state.since.json' if fresh else 'state.json')   # never clobbers a full crawl's progress
    seen = set()
    if posts_path.exists():
        with posts_path.open() as f:
            seen = {json.loads(line)['uri'] for line in f if line.strip()}
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    def save():
        tmp = state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state, indent=1))
        os.replace(tmp, state_path)

    repos = [r | {'pds': PDS} for r in list_repos(client, fresh)]
    meta = {}
    with posts_path.open('a') as sink:
        n = 0
        while repos:
            for repo in repos:
                n += 1
                did, pds = repo['did'], repo['pds']
                desc = client.get(pds, 'com.atproto.repo.describeRepo', {'repo': did})
                profile = client.get(APPVIEW, 'town.delve.actor.getProfile', {'actor': did}, fresh=fresh)
                handle = desc.get('handle')
                labels = [l.get('val') for l in profile.get('labels') or []]
                meta[did] = {'did': did, 'handle': handle, 'active': repo.get('active', True),
                             'status': repo.get('status'), 'labels': labels,
                             'noUnauthenticated': '!no-unauthenticated' in labels,
                             'displayName': profile.get('displayName'), 'pds': pds, 'foreign': pds != PDS}
                s = state.setdefault(did, {'cursor': None, 'done': False, 'posts': 0})
                if s['done'] or 'error' in desc or COLLECTION not in (desc.get('collections') or []):
                    s['done'] = True
                    continue
                while True:
                    params = {'repo': did, 'collection': COLLECTION, 'limit': 100}
                    if s['cursor']:
                        params['cursor'] = s['cursor']
                    page = client.get(pds, 'com.atproto.repo.listRecords', params, fresh=fresh)
                    records = page.get('records', [])
                    stop = False
                    for record in records:
                        r = row(record, did, handle)
                        if a.since and (r['createdAt'] or '') < a.since:
                            stop = True
                            continue
                        if r['uri'] not in seen:
                            seen.add(r['uri'])
                            sink.write(json.dumps(r, ensure_ascii=False) + '\n')
                            s['posts'] += 1
                    sink.flush()
                    s['cursor'] = page.get('cursor')
                    if stop or not s['cursor'] or not records:
                        s['done'] = True
                        break
                    save()
                save()
                print(f'[{n}] {handle or did}: {s["posts"]} new', file=sys.stderr)
            repos = [] if a.no_foreign else foreign(client, posts_path, set(meta))
    counts = {}
    with posts_path.open() as f:
        for line in f:
            d = json.loads(line)['did']
            counts[d] = counts.get(d, 0) + 1
    with (out / 'repos.jsonl').open('w') as f:
        for m in meta.values():
            f.write(json.dumps(m | {'posts': counts.get(m['did'], 0)}, ensure_ascii=False) + '\n')
    if fresh:
        state_path.unlink(missing_ok=True)   # the pass finished; the next --since starts fresh
    print(f'{len(meta)} repos ({sum(m["foreign"] for m in meta.values())} foreign), {len(seen)} posts, '
          f'{client.requests} requests', file=sys.stderr)


if __name__ == '__main__':
    main()
