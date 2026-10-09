#!/usr/bin/env python3
"""Bounded local delivery of native retained events; no network or payload authority."""
import argparse
import hashlib
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk
import runtime_profile
import worker
import process_custody

ROOT = Path(__file__).resolve().parents[1]
canonical, loads, digest, save = desk.canonical, desk.loads, desk.digest, worker.clerk.save


class MessageRelay:
    def __init__(self, state, database, principal, *, profile='compiled', memory_mib=process_custody.NATIVE_MEMORY_MIB):
        if not isinstance(principal, str) or not principal or len(principal.encode()) > 256:
            raise ValueError('explicit local relay principal required')
        if profile != 'compiled' or type(memory_mib) is not int or not 64 <= memory_mib <= 8192:
            raise ValueError('messages require compiled receiving and memory 64..8192 MiB')
        self.state, self.database = Path(state).resolve(), Path(database).resolve()
        self.principal, self.profile, self.memory_mib = principal, profile, memory_mib

    def query(self, operation, deadline, **fields):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('message query deadline reached')
        return desk.world.query(self.database, {'op': operation, 'principal': self.principal, **fields},
                                profile=self.profile, timeout=remaining)

    def pins(self):
        return {**runtime_profile.file_hashes(self.profile),
                'scripts/message_relay.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def bind(self, registry):
        registry = registry.get('messages', registry)
        if registry.get('profile') != 'delvetalk-messages-v1':
            raise ValueError('initialize native messages before starting local relay')
        binding = {'format': 'delvetalk-message-relay-v1', 'database': str(self.database),
                   'principal': self.principal, 'profile': self.profile, 'lineage': registry['lineage']}
        path = self.state / 'relay.json'
        if path.exists():
            saved = loads(path.read_bytes())
            if {key: saved.get(key) for key in binding} != binding:
                raise ValueError('relay custody belongs to another world, principal, or lineage')
            return saved
        return desk.immutable(path, {**binding, 'runtime': self.pins()})

    def event_path(self, identity):
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('invalid native event identity')
        return self.state / 'events' / (identity + '.json')

    def retry(self, identity):
        with worker.bounded_lock(self.state / 'relay.lock', time.monotonic() + 10, time.monotonic) as acquired:
            if not acquired:
                raise TimeoutError('relay custody deadline reached')
            path = self.event_path(identity)
            entry = loads(path.read_bytes())
            entry['retryRequested'] = True
            entry['tries'] = 0
            save(path, entry)
            return {'event': identity, 'status': 'retry-enabled'}

    def run(self, *, limit=16, deadline_seconds=30, max_attempts=3):
        if (type(limit) is not int or not 1 <= limit <= 16 or not math.isfinite(deadline_seconds)
                or not 0 < deadline_seconds <= 300 or type(max_attempts) is not int or not 1 <= max_attempts <= 20):
            raise ValueError('relay bounds: batch 1..16, deadline (0,300], attempts 1..20')
        deadline = time.monotonic() + deadline_seconds
        report = {'format': 'delvetalk-message-relay-run-v1', 'processed': [], 'blocked': [],
                  'errors': [], 'deadlineReached': False, 'publication': 'none'}
        with worker.bounded_lock(self.state / 'relay.lock', deadline, time.monotonic) as acquired:
            if not acquired:
                return {**report, 'deadlineReached': True, 'lockTimedOut': True}
            registry = self.query('messages-pending', deadline)
            config = self.bind(registry)
            progress_path = self.state / 'progress.json'
            progress = loads(progress_path.read_bytes()) if progress_path.exists() else {}
            cursor, active = progress.get('cursor', ''), set(progress.get('active', []))
            # Include locally uncertain consumed events once to reconcile a lost reply.
            pending = registry['pending']
            if len(pending) > 128:
                raise ValueError('native pending message index exceeds capacity')
            identities = sorted(set(pending) | active)
            identities = [x for x in identities if x > cursor] + [x for x in identities if x <= cursor]
            examined = 0
            for identity in identities:
                if time.monotonic() >= deadline:
                    report['deadlineReached'] = True
                    break
                path = self.event_path(identity)
                entry = loads(path.read_bytes()) if path.exists() else {'attempts': [], 'tries': 0}
                if entry.get('status') in ('consumed', 'settled'):
                    active.discard(identity)
                    save(progress_path, {'cursor': identity, 'active': sorted(active)})
                    continue
                if examined >= limit:
                    break
                examined += 1
                active.add(identity)
                save(progress_path, {'cursor': identity, 'active': sorted(active)})
                try:
                    observed = self.query('message-event', deadline, event={'lineage': config['lineage'], 'id': identity})
                    event = observed['event']
                    attempt = entry['attempts'][-1] if entry['attempts'] else None
                    if attempt is not None and attempt.get('receipt') is None:
                        retained = desk.world.retained_reply(self.database, attempt['request'],
                            timeout=max(0.001, deadline - time.monotonic()))
                        if retained is not None:
                            attempt['receipt'] = retained
                    if event['status'] in ('consumed', 'settled'):
                        entry.update(status=event['status'], consumption=event.get('consumption'))
                    else:
                        evidence = event['evidence']
                        root = observed['root']
                        receipt = attempt.get('receipt') if attempt else None
                        if receipt is not None:
                            stale = receipt.get('kind') == 'refused' and receipt.get('data') == 'stale read root'
                            changed = canonical(root) != canonical(attempt['request']['expected'])
                            if entry.pop('retryRequested', False) or (stale and changed):
                                attempt = None
                                entry['tries'] = 0
                            else:
                                entry.update(status='blocked', reason=receipt.get('data'))
                        if attempt is None:
                            if len(entry['attempts']) >= 64:
                                raise ValueError('event attempt custody is full (64 exact requests)')
                            # Native delivery resolves all source, command and payload facts from this ref.
                            request = {'op': 'deliver', 'object': evidence['to'], 'principal': self.principal,
                                       'intent': 'local-message:' + digest([config['lineage'], self.principal, identity,
                                                                          len(entry['attempts'])]),
                                       'event': evidence['ref'], 'expected': root}
                            attempt = {'request': request}
                            entry['attempts'].append(attempt)
                            entry['status'] = 'pending'
                        if attempt.get('receipt') is None:
                            if entry['tries'] >= max_attempts:
                                entry.update(status='blocked', reason='uncertain attempt budget exhausted; retry same event')
                            else:
                                if self.pins() != config['runtime']:
                                    raise ValueError('relay runtime changed; retain exact pending attempts')
                                entry.update(status='uncertain', tries=entry['tries'] + 1)
                                save(path, entry)  # Exact identity is durable before the receiving call.
                                request_path = self.state / 'requests' / (digest(attempt['request']) + '.json')
                                if canonical(desk.immutable(request_path, attempt['request'])) != canonical(attempt['request']):
                                    raise ValueError('retained delivery request identity mismatch')
                                reply = worker.command([str(ROOT / 'scripts/world.py'), '--profile', self.profile,
                                    str(self.database), str(request_path)], max(0.001, deadline - time.monotonic()), self.memory_mib)
                                if reply.get('kind') not in ('committed', 'refused'):
                                    raise ValueError('native delivery returned no terminal receipt')
                                attempt['receipt'] = reply
                                entry.update(status='consumed' if reply['kind'] == 'committed' else 'blocked',
                                             reason=reply.get('data') if reply['kind'] == 'refused' else None)
                    save(path, entry)
                    if entry['status'] in ('consumed', 'settled'):
                        active.discard(identity)
                        save(progress_path, {'cursor': identity, 'active': sorted(active)})
                    report['processed'].append({'event': identity, 'status': entry['status']})
                    if entry['status'] == 'blocked':
                        report['blocked'].append({'event': identity, 'reason': entry.get('reason')})
                except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    entry.update(status='uncertain', reason=str(error)[:1000])
                    save(path, entry)
                    report['errors'].append({'event': identity, 'reason': entry['reason']})
            report['deadlineReached'] |= time.monotonic() >= deadline
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--principal', required=True)
    parser.add_argument('--memory-mib', type=int, default=process_custody.NATIVE_MEMORY_MIB)
    commands = parser.add_subparsers(dest='operation', required=True)
    run = commands.add_parser('run')
    run.add_argument('--limit', type=int, default=16)
    run.add_argument('--deadline-seconds', type=float, default=30)
    run.add_argument('--max-attempts', type=int, default=3)
    commands.add_parser('retry').add_argument('event')
    args = parser.parse_args()
    try:
        relay = MessageRelay(args.state, args.database, args.principal, memory_mib=args.memory_mib)
        result = relay.retry(args.event) if args.operation == 'retry' else relay.run(
            limit=args.limit, deadline_seconds=args.deadline_seconds, max_attempts=args.max_attempts)
        print(canonical(result).decode())
        return 1 if result.get('errors') or result.get('blocked') or result.get('deadlineReached') else 0
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        print('message relay: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
