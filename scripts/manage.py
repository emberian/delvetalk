#!/usr/bin/env python3
"""Explicit local clerk enrollment and Lean law management; no network writes."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('management_clerk', ROOT / 'scripts/clerk.py')
clerk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clerk)
translation = clerk.module('management_translation', 'scripts/translate.py')


def did(value):
    if not isinstance(value, str) or not clerk.DID.fullmatch(value):
        raise ValueError('principal and repository must be did:plc identifiers')
    return value


def management_profile():
    return {'name': 'delvetalk-local-management-v1', 'pins': {
        'scripts/manage.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}


def translation_current(artifact):
    """Check recorded adapter custody without rerunning any translation."""
    pins = artifact['translation']
    paths = {**pins['files'], 'syntaxes/registry.json': pins['registry_sha256']}
    if artifact['target'] == 'spween-protocol-bundle-v1':
        paths['scene/spween-bridge/target/debug/delvetalk-spween'] = artifact['lowered']['bridge_binary_sha256']
    for name, expected in paths.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('pending management translation pins changed: ' + name)


def expected_root(value, object_id):
    """Accept an exact root or the clerk's checksummed snapshot envelope."""
    if isinstance(value, dict) and value.get('format') == 'delvetalk-clerk-root-v1':
        clerk.exact(value, ['format', 'object', 'root', 'profile', 'id'], 'root envelope')
        if value['object'] != object_id or value['id'] != clerk.digest({
                key: item for key, item in value.items() if key != 'id'}):
            raise ValueError('root envelope object or ID mismatch')
        value = value['root']
    if not isinstance(value, dict):
        raise ValueError('expected root must be a JSON object')
    return value


class Management:
    def __init__(self, state):
        self.clerk = clerk.Clerk(state)
        self.state = self.clerk.state

    def enrollment(self, repository, register):
        """Transport-only change. Does not touch the world or request journals."""
        did(repository)
        with clerk.delve.locked(self.state / 'clerk.lock'):
            config = self.clerk.config()
            before = config['repositories']
            after = sorted((set(before) | {repository}) if register else (set(before) - {repository}))
            if before != after:
                config['repositories'] = after
                clerk.save(self.state / 'clerk.json', config)
            return {'format': 'delvetalk-enrollment-v1',
                    'status': 'changed' if before != after else 'unchanged',
                    'repository': repository, 'registered': register,
                    'repositories': after}

    def path(self, principal, intent):
        did(principal)
        if not isinstance(intent, str) or not intent or len(intent.encode()) > 1024:
            raise ValueError('intent must be a nonempty string of at most 1024 bytes')
        # Share the request directory so clerk.upgrade also refuses pending law work.
        return self.state / 'requests' / ('management-' + clerk.digest([principal, intent]) + '.json')

    def finish(self, path, entry):
        if 'receipt' in entry:
            return entry['receipt']
        config = self.clerk.config()
        selected = self.clerk.execution_profile(entry['request'], config)
        if entry.get('admissionProfile', 'compiled') != selected:
            raise ValueError('pending management admission profile changed')
        if entry['profile']['pins'] != clerk.pins(config.get('runtimeProfile', 'compiled')):
            raise ValueError('pending management clerk implementation pins changed')
        if entry['managementProfile'] != management_profile():
            raise ValueError('pending management implementation pins changed')
        if 'artifact' in entry:
            translation_current(entry['artifact'])
        # Never take world.lock first or hold it across exchange (which acquires it).
        reply = clerk.world.exchange(self.clerk.database, entry['request'], profile=selected)
        receipt = {'format': 'delvetalk-management-receipt-v1',
                   'request': entry['request'], 'reply': reply, 'profile': entry['profile'],
                   'managementProfile': entry['managementProfile'],
                   'admissionProfile': selected,
                   'principalSource': 'local-operator-assertion'}
        if 'artifact' in entry:
            receipt['program'] = {'artifact': entry['artifact']}
            if 'stateSource' in entry['inputs']:
                receipt['program']['stateSource'] = entry['inputs']['stateSource']
        if entry['request']['op'] == 'create':
            registered = reply['kind'] == 'committed'
            if registered:
                config = self.clerk.config()
                config['objects'] = sorted(set(config['objects']) | {entry['request']['object']})
                # Before terminal journal receipt: interruption remains pending,
                # and replay of Lean's create receipt can complete registration.
                clerk.save(self.state / 'clerk.json', config)
            receipt['registration'] = {'object': entry['request']['object'], 'registered': registered}
        receipt['id'] = clerk.digest(receipt)
        entry['receipt'] = receipt
        clerk.save(path, entry)
        return receipt

    def submit(self, path, request, extra=None):
        """Caller holds clerk.lock; retain the whole attempt before Lean admission."""
        config = self.clerk.config()
        if path.exists():
            entry = clerk.loads(path.read_text())
            if clerk.canonical(entry['request']) != clerk.canonical(request):
                raise ValueError('management intent already bound to a different request')
        else:
            if request['op'] != 'create' and request['object'] not in config['objects']:
                raise ValueError('object is not configured for this clerk')
            if config['profile']['pins'] != clerk.pins(config.get('runtimeProfile', 'compiled')):
                raise ValueError('clerk implementation pins changed')
            # Reject oversized transport before reserving an intent: the host's
            # request envelope errors have no retained semantic receipt to recover.
            if len(clerk.canonical(request)) > 65536:
                raise ValueError('management request exceeds 64 KiB')
            entry = {'request': request, 'profile': config['profile'],
                     'admissionProfile': self.clerk.execution_profile(request, config),
                     'managementProfile': management_profile(), **(extra or {})}
            clerk.save(path, entry)
        return self.finish(path, entry)

    def law(self, object_id, principal, intent, expected, law):
        path = self.path(principal, intent)
        request = {'op': 'law', 'object': object_id, 'principal': principal,
                   'intent': 'operator-law:' + intent,
                   'expected': expected_root(expected, object_id), 'law': law}
        with clerk.delve.locked(self.state / 'clerk.lock'):
            return self.submit(path, request)

    def reprogram(self, object_id, principal, intent, expected, syntax, source, state_source):
        path = self.path(principal, intent)
        if len(source) > 512 * 1024 or len(state_source) > 64 * 1024:
            raise ValueError('program source exceeds 512 KiB or state exceeds 64 KiB')
        inputs = {'syntax': syntax, 'source': source.decode('utf-8'),
                  'stateSource': {'encoding': 'utf-8', 'text': state_source.decode('utf-8'),
                                  'sha256': hashlib.sha256(state_source).hexdigest()}}
        request = {'op': 'reprogram', 'object': object_id, 'principal': principal,
                   'intent': 'operator-reprogram:' + intent,
                   'expected': expected_root(expected, object_id)}
        return self.translated(path, request, inputs, source, state_source)

    def add_object(self, object_id, principal, intent, syntax, source, law):
        path = self.path(principal, intent)
        if len(source) > 512 * 1024:
            raise ValueError('program source exceeds 512 KiB')
        request = {'op': 'create', 'object': object_id, 'principal': principal,
                   'intent': 'operator-create:' + intent, 'law': law}
        inputs = {'syntax': syntax, 'source': source.decode('utf-8')}
        return self.translated(path, request, inputs, source)

    def translated(self, path, request, inputs, source, state_source=None):
        with clerk.delve.locked(self.state / 'clerk.lock'):
            self.clerk.config()
            if path.exists():
                entry = clerk.loads(path.read_text())
                retained = {key: entry['request'].get(key) for key in request}
                if (clerk.canonical(retained) != clerk.canonical(request)
                        or clerk.canonical(entry.get('inputs')) != clerk.canonical(inputs)):
                    raise ValueError('management intent already bound to a different request or source')
                return self.finish(path, entry)
            artifact = translation.translate(inputs['syntax'], source)
            if artifact['target'] == 'local-protocol-v1':
                protocol = artifact['lowered']
            elif artifact['target'] == 'spween-protocol-bundle-v1':
                protocol = artifact['lowered']['protocol']
            else:
                raise ValueError('program syntax must target a local protocol or Spween protocol bundle')
            translation_current(artifact)
            request['protocol'] = protocol
            if state_source is not None:
                request['state'] = clerk.loads(state_source)
            return self.submit(path, request, {'inputs': inputs, 'artifact': artifact})

    def resume(self, principal, intent):
        """Recover the exact retained attempt without reconstructing its arguments."""
        path = self.path(principal, intent)
        with clerk.delve.locked(self.state / 'clerk.lock'):
            self.clerk.config()
            entry = clerk.loads(path.read_text())
            return self.finish(path, entry)

    def status(self):
        with clerk.delve.locked(self.state / 'clerk.lock'):
            config = self.clerk.config()
            attempts = []
            for path in sorted((self.state / 'requests').glob('management-*.json')):
                entry = clerk.loads(path.read_text())
                request = entry['request']
                attempts.append({'principal': request['principal'],
                                 'intent': request['intent'].split(':', 1)[1],
                                 'operation': request['op'],
                                 'object': request['object'],
                                 'status': entry.get('receipt', {}).get('reply', {}).get('kind', 'pending')})
            return {'format': 'delvetalk-management-status-v1',
                    'repositories': config['repositories'], 'objects': config['objects'],
                    'attempts': attempts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path, dest='custody_state')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='show transport enrollment and retained management attempts')
    for action in ('register', 'unregister'):
        command = commands.add_parser(action, help='change transport enrollment only')
        command.add_argument('repository')
    revise = commands.add_parser('law', help='submit an exact-preimage law replacement to Lean')
    revise.add_argument('--object', required=True)
    revise.add_argument('--principal', required=True, help='local operator assertion of a current authority DID')
    revise.add_argument('--intent', required=True, help='stable identity for this attempt; retain across retries')
    revise.add_argument('--expected-root', required=True, type=Path, help='exact root JSON or clerk snapshot envelope')
    authority = revise.add_mutually_exclusive_group(required=True)
    authority.add_argument('--empty-law', action='store_true', help='deliberately remove all authority, including management')
    authority.add_argument('--law-file', type=Path, help='complete law JSON; Lean validates its structure and authority')
    create = commands.add_parser('add-object', help='create a local object and recoverably register clerk custody')
    create.add_argument('--object', required=True)
    create.add_argument('--principal', required=True)
    create.add_argument('--intent', required=True)
    create.add_argument('--source', required=True, type=Path)
    create.add_argument('--syntax', required=True)
    initial_law = create.add_mutually_exclusive_group(required=True)
    initial_law.add_argument('--empty-law', action='store_true')
    initial_law.add_argument('--law-file', type=Path)
    program = commands.add_parser('reprogram', help='submit a translated program and complete state to Lean')
    program.add_argument('--object', required=True)
    program.add_argument('--principal', required=True)
    program.add_argument('--intent', required=True)
    program.add_argument('--expected-root', required=True, type=Path)
    program.add_argument('--source', required=True, type=Path)
    program.add_argument('--syntax', required=True, help='explicit reviewed syntax ID/version')
    program.add_argument('--state', required=True, type=Path, dest='program_state', help='complete replacement state JSON file')
    recover = commands.add_parser('resume', help='recover pending or read completed management receipt')
    recover.add_argument('--principal', required=True)
    recover.add_argument('--intent', required=True)
    args = parser.parse_args()
    manager = Management(args.custody_state)
    try:
        if args.command == 'status':
            result = manager.status()
        elif args.command in ('register', 'unregister'):
            result = manager.enrollment(args.repository, args.command == 'register')
        elif args.command == 'resume':
            result = manager.resume(args.principal, args.intent)
        elif args.command == 'add-object':
            result = manager.add_object(args.object, args.principal, args.intent, args.syntax,
                                        args.source.read_bytes(),
                                        clerk.loads(args.law_file.read_bytes()) if args.law_file else {'profile': 'delvetalk-scoped-law', 'invoke': {}, 'reprogram': [], 'law': []})
        elif args.command == 'reprogram':
            result = manager.reprogram(args.object, args.principal, args.intent,
                                       clerk.loads(args.expected_root.read_text()), args.syntax,
                                       args.source.read_bytes(), args.program_state.read_bytes())
        else:
            result = manager.law(args.object, args.principal, args.intent,
                                 clerk.loads(args.expected_root.read_text()),
                                 clerk.loads(args.law_file.read_bytes()) if args.law_file else {'profile': 'delvetalk-scoped-law', 'invoke': {}, 'reprogram': [], 'law': []})
        print(clerk.world.wire_dumps(result))
    except (ValueError, RuntimeError, OSError) as exc:
        print(clerk.world.wire_dumps({'management_error': str(exc)}), file=sys.stderr)
        return 1
    # A retained semantic refusal is a completed attempt, but not a successful revision.
    return 2 if result.get('reply', {}).get('kind') == 'refused' else 0


if __name__ == '__main__':
    raise SystemExit(main())
