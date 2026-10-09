#!/usr/bin/env python3
"""Bounded local receiving queue; ordinary runs prepare receipts without publishing."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clerk
import receipts
import process_custody

ROOT = Path(__file__).resolve().parents[1]


def key(uri):
    return hashlib.sha256(uri.encode()).hexdigest()


def command(arguments, remaining, memory_mib=2048):
    if os.name != 'posix':
        raise RuntimeError('worker process custody requires POSIX process groups')
    if not 64 <= memory_mib <= 8192:
        raise ValueError('memory bound must be 64..8192 MiB')
    # This caps reply transport, not the world snapshots/history a child writes.
    process = process_custody.run([sys.executable, *arguments], timeout=remaining,
        cpu_seconds=max(1, math.ceil(remaining)), memory_bytes=memory_mib * 1024 * 1024,
        stdout_limit=64 * 1024 * 1024, stderr_limit=1024 * 1024, cwd=ROOT)
    output, errors = process.stdout.decode('utf-8'), process.stderr.decode('utf-8')
    if process.returncode:
        raise RuntimeError((errors or output or f'worker subprocess exited {process.returncode}').strip()[:2000])
    return clerk.loads(output)


@contextmanager
def bounded_lock(path, deadline, now):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a') as stream:
        while True:
            remaining = deadline - now()
            if remaining <= 0:
                yield False
                return
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(min(0.02, remaining))
        try:
            yield True
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def publication_artifacts(receipt):
    """Prepare immutable records at this admission boundary, never current pointers."""
    if receipt['reply']['kind'] != 'committed':
        return []
    data, request = receipt['reply']['data'], receipt['request']
    roots = (data['roots'] if request['op'] == 'transaction' else
             {request['object']: data['root'], **data.get('allocated', {})})
    artifacts, references = [], {}
    for object_id, root in sorted(roots.items()):
        if root is None:
            references[object_id] = None
            continue
        snapshot = {'format': 'delvetalk-clerk-root-v1', 'object': object_id,
                    'root': root, 'profile': receipt['profile']}
        snapshot['id'] = clerk.digest(snapshot)
        raw = clerk.canonical(snapshot).decode('utf-8')
        record = {'$type': 'org.delvetalk.rootSnapshot', 'profile': 'delvetalk-live-v1',
                  'object': object_id, 'version': str(root['version']), 'snapshotJson': raw,
                  'sha256': hashlib.sha256(raw.encode()).hexdigest()}
        references[object_id] = {'snapshotId': snapshot['id'], 'recordSha256': clerk.digest(record)}
        artifacts.append({'kind': 'root-snapshot', 'id': snapshot['id'], 'record': record,
                          'intent': 'worker-root:' + snapshot['id']})
    head = {'format': 'delvetalk-admission-head-v1', 'receiptId': receipt['id'],
            'source': receipt['source'], 'roots': references, 'profile': receipt['profile']}
    head['id'] = clerk.digest(head)
    raw = clerk.canonical(head).decode('utf-8')
    artifacts.append({'kind': 'admission-head', 'id': head['id'], 'intent': 'worker-head:' + head['id'],
                      'record': {'$type': 'org.delvetalk.admissionHead', 'profile': 'delvetalk-live-v1',
                                 'headJson': raw, 'sha256': hashlib.sha256(raw.encode()).hexdigest()}})
    return artifacts


class Worker:
    def __init__(self, state, clerk_state, *, receiver=None, publisher=None, now=None, memory_mib=2048):
        self.state = Path(state).expanduser().resolve()
        self.clerk_state = Path(clerk_state).expanduser().resolve()
        self.receiver = receiver
        self.publisher = publisher
        self.now = now or time.monotonic
        if not 64 <= memory_mib <= 8192:
            raise ValueError('memory bound must be 64..8192 MiB')
        self.memory_mib = memory_mib

    def path(self, uri):
        return self.state / 'queue' / (key(uri) + '.json')

    def bind(self):
        """A queue cannot be pointed at a different world after discovery."""
        path = self.state / 'worker.json'
        configuration = {'format': 'delvetalk-worker-v1', 'clerkState': str(self.clerk_state)}
        if path.exists():
            if clerk.loads(path.read_text()) != configuration:
                raise ValueError('worker queue belongs to a different clerk state')
        else:
            clerk.save(path, configuration)

    def enqueue(self, uri, cid, observation=None):
        clerk.parse_uri(uri)
        if not isinstance(cid, str) or not cid or len(cid) > 200:
            raise ValueError('nonempty source CID of at most 200 characters required')
        with clerk.delve.locked(self.state / '.worker.lock'):
            self.bind()
            path = self.path(uri)
            if path.exists():
                entry = clerk.loads(path.read_text())
                if entry['uri'] != uri or entry['cid'] != cid:
                    raise ValueError('queued request URI already bound to another CID')
                return {'uri': uri, 'cid': cid, 'status': 'already-queued', 'phase': entry['phase']}
            if sum(1 for _ in (self.state / 'queue').glob('*.json')) >= 10000:
                raise ValueError('worker queue retention bound reached (10000 requests)')
            entry = {'uri': uri, 'cid': cid, 'phase': 'queued', 'receiveAttempts': 0,
                     'publishAttempts': 0, 'observation': observation}
            clerk.save(path, entry)
            return {'uri': uri, 'cid': cid, 'status': 'queued'}

    def discover(self, watch_state, limit=1000):
        if not 1 <= limit <= 10000:
            raise ValueError('discovery limit must be 1..10000')
        watch_state = Path(watch_state).expanduser()
        index = clerk.loads((watch_state / 'index.json').read_text())
        if index.get('format') != 'delvetalk-watch-index-v1' or not isinstance(index.get('posts'), dict):
            raise ValueError('unsupported observation index')
        rows = sorted(index['posts'].items(), key=lambda pair: (pair[1].get('lastSeenAt', ''), pair[0]), reverse=True)
        report = {'format': 'delvetalk-worker-discovery-v1', 'examined': 0, 'queued': [],
                  'skipped': 0, 'errors': [], 'truncated': len(rows) > limit}
        cardbook_enabled = 'townCards' in clerk.Clerk(self.clerk_state).config()['profile']
        for uri, metadata in rows[:limit]:
            report['examined'] += 1
            try:
                identity = metadata['observation']
                if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
                    raise ValueError('invalid observation file identity')
                observation = clerk.loads((watch_state / 'observations' / (identity + '.json')).read_text())
                if observation['uri'] != uri or observation['cid'] != metadata['cid']:
                    raise ValueError('observation/index source mismatch')
                record = observation['record']
                # Discovery only recognizes explicit grammar. Receiving re-fetches
                # and authenticates the author, parent publication and captured card.
                text = record.get('text')
                if isinstance(text, str) and text.startswith('delvetalk-request v1\n'):
                    receipts.encode('request', clerk.feed_request(record))
                elif cardbook_enabled and isinstance(text, str) and text.strip().startswith('delvetalk '):
                    cards = clerk.module('worker_town_cards', 'scripts/town_cards.py')
                    cards.parse_reply(text)
                else:
                    report['skipped'] += 1
                    continue
                result = self.enqueue(uri, observation['cid'], observation)
                if result['status'] == 'queued':
                    report['queued'].append(result)
            except (ValueError, KeyError, TypeError, OSError, receipts.Failure) as error:
                report['errors'].append({'uri': uri, 'error': str(error)})
        return report

    def receive(self, entry, remaining):
        if self.receiver is not None:
            return self.receiver(entry['uri'], entry['cid'])
        return command([str(ROOT / 'scripts/clerk.py'), '--state', str(self.clerk_state),
                        'receive', entry['uri'], '--cid', entry['cid']], remaining, self.memory_mib)

    def publish(self, entry, remaining):
        outbox = entry['outbox']
        if self.publisher is not None:
            return self.publisher(outbox['kind'], outbox['text'], outbox['intent'])
        path = self.state / 'publication-inputs' / (key(entry['uri']) + '.json')
        # Publisher consumes this exact selected envelope, not a directory scan.
        clerk.save(path, clerk.loads(outbox['text']))
        # save emits canonical JSON plus newline, the exact prepared text below.
        if path.read_text() != outbox['text']:
            raise ValueError('prepared publication text mismatch')
        return command([str(ROOT / 'scripts/receipts.py'), outbox['kind'], str(path),
                        '--intent', outbox['intent'], '--state', str(self.state / 'publications')], remaining, self.memory_mib)

    def run(self, *, limit=10, deadline_seconds=60, max_attempts=3, allow_publication=False):
        if not 1 <= limit <= 100 or not 0 < deadline_seconds <= 300 or not 1 <= max_attempts <= 20:
            raise ValueError('bounds: limit 1..100, deadline (0,300], attempts 1..20')
        started = self.now()
        report = {'format': 'delvetalk-worker-run-v1', 'mode': 'publish' if allow_publication else 'prepare',
                  'processed': [], 'errors': [], 'blocked': [], 'deadlineReached': False,
                  'resourceProfile': {'wall': 'per-call remaining deadline; POSIX process-group kill',
                                      'cpu': 'per-process inherited ceil(remaining seconds)',
                                      'memory': f'per-process RLIMIT_AS {self.memory_mib} MiB'
                                      if sys.platform.startswith('linux') else 'no memory limit on this platform'}}
        with bounded_lock(self.state / '.worker.lock', started + deadline_seconds, self.now) as acquired:
            if not acquired:
                report.update(deadlineReached=True, lockTimedOut=True, elapsedSeconds=self.now() - started)
                return report
            self.bind()
            for path in sorted((self.state / 'queue').glob('*.json')):
                if self.now() - started >= deadline_seconds:
                    report['deadlineReached'] = True
                    break
                entry = clerk.loads(path.read_text())
                phase = entry['phase']
                if phase == 'published' or (phase == 'prepared' and not allow_publication):
                    continue
                if len(report['processed']) >= limit:
                    break
                if self.now() - started >= deadline_seconds:
                    report['deadlineReached'] = True
                    break
                counter = 'receiveAttempts' if phase == 'queued' else 'publishAttempts'
                if entry[counter] >= max_attempts:
                    report['blocked'].append({'uri': entry['uri'], 'phase': phase, 'error': entry.get('lastError')})
                    continue
                entry[counter] += 1
                clerk.save(path, entry)
                try:
                    remaining = max(0.001, deadline_seconds - (self.now() - started))
                    if phase == 'queued':
                        receipt = self.receive(entry, remaining)
                        if (receipt.get('format') != 'delvetalk-clerk-receipt-v1'
                                or receipt['source']['uri'] != entry['uri'] or receipt['source']['cid'] != entry['cid']):
                            raise ValueError('receiving result does not match queued source')
                        text = clerk.canonical(receipt).decode('utf-8') + '\n'
                        entry.update(phase='prepared', receipt=receipt, publicationArtifacts=publication_artifacts(receipt),
                                     outbox={'kind': 'receipt', 'intent': 'worker-receipt:' + key(entry['uri']), 'text': text})
                    else:
                        entry.update(phase='published', publication=self.publish(entry, remaining))
                    entry.pop('lastError', None)
                    clerk.save(path, entry)
                except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired, clerk.delve.Failure, receipts.Failure) as error:
                    entry['lastError'] = str(error)[:2000]
                    clerk.save(path, entry)
                    report['errors'].append({'uri': entry['uri'], 'phase': phase, 'error': entry['lastError']})
                report['processed'].append({'uri': entry['uri'], 'cid': entry['cid'], 'phase': entry['phase']})
        report['elapsedSeconds'] = self.now() - started
        return report

    def retry(self, uri):
        with clerk.delve.locked(self.state / '.worker.lock'):
            self.bind()
            path = self.path(uri)
            entry = clerk.loads(path.read_text())
            counter = 'receiveAttempts' if entry['phase'] == 'queued' else 'publishAttempts'
            entry[counter] = 0
            clerk.save(path, entry)
            return {'uri': uri, 'phase': entry['phase'], 'status': 'retry-enabled'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--clerk-state', required=True, type=Path)
    parser.add_argument('--memory-mib', type=int, default=2048)
    commands = parser.add_subparsers(dest='op', required=True)
    discover = commands.add_parser('discover')
    discover.add_argument('--watch-state', default='~/claude_state/delvetalk/watch')
    discover.add_argument('--limit', type=int, default=1000)
    enqueue = commands.add_parser('enqueue')
    enqueue.add_argument('uri')
    enqueue.add_argument('--cid', required=True)
    retry = commands.add_parser('retry')
    retry.add_argument('uri')
    run = commands.add_parser('run')
    run.add_argument('--limit', type=int, default=10)
    run.add_argument('--deadline-seconds', type=float, default=60)
    run.add_argument('--max-attempts', type=int, default=3)
    run.add_argument('--allow-publication', action='store_true', help='explicit future publication; omitted prepares only')
    args = parser.parse_args()
    try:
        worker = Worker(args.state, args.clerk_state, memory_mib=args.memory_mib)
        if args.op == 'discover':
            result = worker.discover(args.watch_state, args.limit)
        elif args.op == 'enqueue':
            result = worker.enqueue(args.uri, args.cid)
        elif args.op == 'retry':
            result = worker.retry(args.uri)
        else:
            result = worker.run(limit=args.limit, deadline_seconds=args.deadline_seconds,
                                max_attempts=args.max_attempts, allow_publication=args.allow_publication)
        print(clerk.world.wire_dumps(result))
        return 1 if result.get('errors') else 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('worker: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
