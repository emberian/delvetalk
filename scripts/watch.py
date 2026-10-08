#!/usr/bin/env python3
"""Observe the imaginary LiveDelveTalk label; no account, authentication or execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('watch_delve', ROOT / 'scripts/delve.py')
delve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delve)
LABEL = 'livedelvetalk.delve.town'
FEED = 'at://did:plc:qzqct2rrq4u2gmy5g3mjxske/town.delve.feed.generator/town'
ANCHOR = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxen3fdeo224'
DEFAULT_STATE = '~/claude_state/delvetalk/watch'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def scan(state=DEFAULT_STATE, **kwargs):
    with delve.locked(Path(state).expanduser() / '.scan.lock'):
        return scan_locked(state, **kwargs)


def scan_locked(state, *, feed_pages=3, search_pages=1, anchor=ANCHOR, request=None):
    if not 1 <= feed_pages <= 20 or not 1 <= search_pages <= 20:
        raise ValueError('page bounds must be 1..20')
    delve.post_uri(anchor)
    state = Path(state).expanduser()
    path = state / 'index.json'
    index = json.loads(path.read_text()) if path.exists() else {'format': 'delvetalk-watch-index-v1', 'posts': {}}
    if index.get('format') != 'delvetalk-watch-index-v1' or not isinstance(index.get('posts'), dict):
        raise ValueError('unsupported watch index')
    http = request or delve.HTTP()
    report = {'format': 'delvetalk-watch-v1', 'startedAt': stamp(), 'label': LABEL,
              'scope': 'literal text label and anchor context; no account resolution or admission',
              'coverage': {}, 'new': [], 'changed': [], 'conflicts': [], 'errors': []}
    found = {}

    def observe(post, source, context=False):
        if not isinstance(post, dict):
            raise ValueError('post must be an object')
        uri, cid, record = post.get('uri'), post.get('cid'), post.get('record')
        if not isinstance(uri, str) or not isinstance(cid, str) or not cid or not isinstance(record, dict):
            raise ValueError('post requires URI, CID and record')
        delve.post_uri(uri)
        text = record.get('text', '')
        if not isinstance(text, str):
            raise ValueError('post text must be a string')
        matched = LABEL in text.casefold()
        if not matched and not context and uri not in index['posts']:
            return
        key = (uri, cid, digest(record))
        if key not in found:
            found[key] = {'uri': uri, 'cid': cid, 'record': record,
                          'author': post.get('author'), 'contentSha256': key[2],
                          'matchedLabel': matched, 'sources': []}
        if source not in found[key]['sources']:
            found[key]['sources'].append(source)

    def pages(source, nsid, params, field, bound):
        coverage = {'pages': 0, 'posts': 0, 'truncated': False, 'cursor': None}
        report['coverage'][source] = coverage
        seen = set()
        try:
            for _ in range(bound):
                response = http('GET', delve.APPVIEW, nsid, params=params)
                rows = response.get(field)
                if not isinstance(rows, list):
                    raise ValueError('response lacks post list')
                coverage['pages'] += 1
                for row in rows:
                    coverage['posts'] += 1
                    observe(row.get('post') if source == 'feed' and isinstance(row, dict) else row, source)
                cursor = response.get('cursor')
                if cursor is not None and (not isinstance(cursor, str) or not cursor):
                    raise ValueError('invalid pagination cursor')
                coverage['cursor'] = cursor
                if cursor is None:
                    return
                if cursor in seen:
                    raise ValueError('pagination cursor repeated')
                seen.add(cursor)
                params = {**params, 'cursor': cursor}
            coverage['truncated'] = coverage['cursor'] is not None
        except (ValueError, TypeError, AttributeError, OSError, delve.Failure) as error:
            coverage.update(error=str(error), truncated=True)
            report['errors'].append({'source': source, 'error': str(error)})

    # Every run begins at the head: overlapping scans catch late observations.
    pages('feed', 'town.delve.feed.getFeed', {'feed': FEED, 'limit': 50}, 'feed', feed_pages)
    pages('search', 'town.delve.feed.searchPosts', {'q': 'livedelvetalk', 'limit': 50}, 'posts', search_pages)
    coverage = {'uri': anchor, 'requestedDepth': 3, 'nodes': 0, 'posts': 0,
                'truncated': False, 'deeperReplies': 0}
    report['coverage']['thread'] = coverage
    try:
        response = http('GET', delve.APPVIEW, 'town.delve.feed.getPostThread',
                        params={'uri': anchor, 'depth': 3, 'parentHeight': 0})
        if not isinstance(response.get('thread'), dict):
            raise ValueError('response lacks thread')
        queue = [(response['thread'], 0)]
        while queue and coverage['nodes'] < 200:
            node, depth = queue.pop(0)
            if not isinstance(node, dict):
                raise ValueError('thread node must be an object')
            coverage['nodes'] += 1
            if isinstance(node.get('post'), dict):
                observe(node['post'], 'thread', context=True)
                coverage['posts'] += 1
            replies = node.get('replies', [])
            if not isinstance(replies, list):
                raise ValueError('thread replies must be a list')
            count = node.get('post', {}).get('replyCount', 0)
            if type(count) is int and count > len(replies):
                coverage['deeperReplies'] += count - len(replies)
                coverage['truncated'] = True
            if depth < 3:
                queue.extend((reply, depth + 1) for reply in replies)
            elif replies:
                coverage['truncated'] = True
        coverage['truncated'] |= bool(queue)
    except (ValueError, TypeError, AttributeError, OSError, delve.Failure) as error:
        coverage.update(error=str(error), truncated=True)
        report['errors'].append({'source': 'thread', 'error': str(error)})

    with delve.locked(state / '.watch.lock'):
        by_uri = {}
        for item in found.values():
            identity = digest([item['uri'], item['cid'], item['contentSha256']])
            observation = state / 'observations' / (identity + '.json')
            if not observation.exists():
                delve.save(observation, {**item, 'observedAt': report['startedAt']})
            by_uri.setdefault(item['uri'], []).append((item, identity, observation))
        for uri, variants in by_uri.items():
            previous = index['posts'].get(uri)
            selected = variants[0]
            if len(variants) > 1:
                report['conflicts'].append({'uri': uri, 'variants': [
                    {'cid': item['cid'], 'contentSha256': item['contentSha256'], 'sources': item['sources']}
                    for item, _, _ in variants], 'scope': 'simultaneous observations; no version ordering inferred'})
                # Preserve an already-observed alternative instead of oscillating
                # between stale AppView/thread caches on every overlapping scan.
                if previous:
                    selected = next((variant for variant in variants
                                     if variant[1] == previous['observation']), selected)
            item, identity, observation = selected
            summary = {key: item[key] for key in ('uri', 'cid', 'contentSha256', 'sources', 'matchedLabel')}
            summary['text'] = item['record'].get('text', '')
            summary['observation'] = str(observation.resolve())
            if previous is None:
                report['new'].append(summary)
            elif previous['cid'] != item['cid'] or previous['contentSha256'] != item['contentSha256']:
                report['changed'].append({**summary, 'previousCid': previous['cid'],
                                          'previousContentSha256': previous['contentSha256']})
            index['posts'][uri] = {'cid': item['cid'], 'contentSha256': item['contentSha256'],
                                 'observation': identity, 'lastSeenAt': report['startedAt']}
        report.update(finishedAt=stamp(), observations=len(found), retainedPosts=len(index['posts']))
        delve.save(path, index)
        delve.save(state / 'latest-report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default=DEFAULT_STATE)
    parser.add_argument('--feed-pages', type=int, default=3)
    parser.add_argument('--search-pages', type=int, default=1)
    parser.add_argument('--anchor', default=ANCHOR)
    args = parser.parse_args()
    try:
        report = scan(args.state, feed_pages=args.feed_pages, search_pages=args.search_pages, anchor=args.anchor)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if not report['errors'] else 1
    except (ValueError, OSError, delve.Failure) as error:
        print('watch: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
