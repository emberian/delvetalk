#!/usr/bin/env python3
"""Private two-player custody and portable typed cards; Lean admits every action."""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


desk = module('participant_desk', 'scripts/desk.py')
client = module('participant_client', 'game/table/client.py')
table = module('participant_table', 'game/table/protocol.py')
affordances = module('participant_affordances', 'scripts/affordances.py')
interpret = module('participant_interpret', 'scripts/interpret.py')
canonical, loads = desk.canonical, desk.loads
TOKEN = re.compile(r'[0-9a-f]{24}\Z')


def retained(path, value):
    stored = desk.immutable(path, value)
    if canonical(stored) != canonical(value):
        raise ValueError('Retained custody differs; choose a new intent or restore its original inputs')
    return stored


class Participant:
    def __init__(self, database, custody, object_id, principal, seat):
        if type(seat) is not int or seat not in (0, 1):
            raise ValueError('Two-player seat must be 0 or 1')
        if not all(isinstance(x, str) and x for x in (object_id, principal)):
            raise ValueError('Table and principal must be nonempty strings')
        self.database = Path(database).resolve()
        self.custody = Path(custody).resolve()
        self.custody.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.custody.stat().st_mode & 0o077:
            raise ValueError('Participant custody directory must be private (mode 0700)')
        self.object, self.principal, self.seat = object_id, principal, seat
        binding = {'format': 'delvetalk-table-participant-v1',
            'database': str(self.database), 'object': object_id, 'principal': principal,
            'seat': seat}
        binding_path = self.custody / 'binding.json'
        if binding_path.exists():
            saved = loads(binding_path.read_bytes())
            if ({key: value for key, value in saved.items() if key != 'runtime'} != binding
                    or not isinstance(saved.get('runtime'), dict)
                    or saved['runtime'].get('profile') != 'compiled'):
                raise ValueError('Retained custody differs from this database, table, principal or seat')
            self.runtime = saved['runtime']
        else:
            self.runtime = desk.execution_profile('compiled')
            retained(binding_path, {**binding, 'runtime': self.runtime})
        for name in ('cards', 'openings', 'requests', 'receipts'):
            path = self.custody / name
            path.mkdir(exist_ok=True, mode=0o700)
            if path.stat().st_mode & 0o077:
                raise ValueError('Participant custody subdirectories must be private (mode 0700)')

    def _runtime(self):
        if canonical(desk.execution_profile('compiled')) != canonical(self.runtime):
            raise ValueError('Compiled runtime changed; restore the pinned runtime before continuing')

    def _read(self, category, token):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise ValueError('Invalid custody token')
        return loads((self.custody / category / (token + '.json')).read_bytes())

    def _opening(self, number):
        return self.custody / 'openings' / (str(number) + '.json')

    def observe(self):
        self._runtime()
        root = desk.world.exchange(self.database,
            {'op': 'inspect', 'object': self.object, 'principal': self.principal}, profile='compiled')
        # This specialized renderer must not assign game meaning to arbitrary code.
        if not client.same_game(root.get('protocol'), table.protocol(self.object)):
            raise ValueError('This table does not use the supported two-player protocol')
        public = client.public_view(root)
        token = secrets.token_hex(12)
        fields = [{'name': name, 'label': name.capitalize() + ' cell index', 'type': 'nat',
                   'required': True, 'minimum': 0, 'maximum': len(public['cells']) - 1}
                  for name in ('source', 'target')]
        actions = []
        next_hint = 'The game has finished.'
        if not public['winner']:
            if not public['committed'][self.seat]:
                actions.append({'id': 'commit', 'label': 'Seal my move', 'available': True, 'fields': fields})
                next_hint = 'Seal your move; its opening stays in your private custody.'
            elif all(public['committed']) and not public['revealed'][self.seat]:
                next_hint = 'Your opening is unavailable here. Recover the original participant custody to reveal.'
                opening_path = self._opening(public['round'])
                if opening_path.exists():
                    opening = loads(opening_path.read_bytes())
                    if opening['commit']['digest'] == root['state']['commit' + str(self.seat)]:
                        actions.append({'id': 'reveal', 'label': 'Open my sealed move', 'available': True, 'fields': []})
                        next_hint = 'Both moves are sealed. You can now open yours.'
            else:
                next_hint = ('Waiting for the other seat to open its move.' if public['revealed'][self.seat]
                             else 'Waiting for the other seat to seal its move.')
            if all(public['revealed']):
                actions.append({'id': 'resolve', 'label': 'Resolve both moves', 'available': True, 'fields': []})
                next_hint = 'Both moves are open. Either seat can resolve the round.'
        # Distinct glyphs: attractor +, repulsor -, automaton @.
        glyphs = '.+-@'
        width = public['width']
        rows = [' '.join(f'{i:02d}{glyphs[public["cells"][i]]}' for i in range(start, start + width))
                for start in range(0, len(public['cells']), width)]
        status = {0: 'completed', 1: 'conflict', 2: 'illegal input or move', 3: 'already terminal'}
        marked = [i for i in range(len(public['cells'])) if public['marks'] & (1 << i)]
        prose = '\n'.join([f'Round {public["round"]}; seat {self.seat}; version {public["version"]}.',
            f'Last result: {status[public["status"]]}; winner: {public["winner"]} (0 none, 1 top, 2 bottom).',
            f'Sealed: {public["committed"]}; opened: {public["revealed"]}.',
            'Row-major indices: . empty, + attractor, - repulsor, @ automaton.', *rows,
            f'Marked cells: {marked}. Your goal: guide @ to a {"top" if self.seat == 0 else "bottom"} corner.',
            'Choose distinct cells in one row or column, excluding @ and marked cells.',
            'Choose source and target indices. The game checks movement when both moves resolve.',
            next_hint, 'Copy do CARD ACTION with the displayed fields.'])
        card = {'card': token, 'object': self.object, 'title': 'Two-player Automatafl', 'prose': prose, 'actions': actions}
        interpret.validate_card(card)
        retained(self.custody / 'cards' / (token + '.json'), {'root': root, 'card': card})
        return card

    def prepare(self, token, action_id, fields, intent):
        if not isinstance(intent, str) or not intent or len(intent) > 256:
            raise ValueError('Intent must be a nonempty string of at most 256 characters')
        saved = self._read('cards', token)
        action = next((a for a in saved['card']['actions'] if a['id'] == action_id), None)
        if action is None:
            raise ValueError('Action was not offered on this captured card')
        fields = affordances.validate_fields(action, fields)
        identity = hashlib.sha256(canonical([self.principal, intent])).hexdigest()[:24]
        choice = {'card': token, 'action': action_id, 'fields': fields, 'intent': intent}
        path = self.custody / 'requests' / (identity + '.json')
        with (self.custody / 'prepare.lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Participant custody busy; retry the same choice') from None
            if path.exists():
                if self._read('requests', identity)['choice'] != choice:
                    raise ValueError('Intent already retains a different choice')
                return {'prepared': identity, 'action': action_id, 'status': 'retained'}
            self._runtime()
            state = saved['root']['state']
            number = state['round']
            if action_id == 'commit':
                opening_path = self._opening(number)
                if opening_path.exists():
                    opening = loads(opening_path.read_bytes())
                    if any(opening['reveal'][key] != fields[key] for key in ('source', 'target')):
                        raise ValueError('Round already has a sealed move; retain its original source and target')
                else:
                    opening = retained(opening_path, client.prepare(self.object, number, self.seat,
                        fields['source'], fields['target']))
                payload = opening['commit']
            elif action_id == 'reveal':
                opening = loads(self._opening(number).read_bytes())
                if not all(state['commit' + str(i)] for i in (0, 1)):
                    raise ValueError('Both observed commitments must precede an opening')
                if opening['commit']['digest'] != state['commit' + str(self.seat)]:
                    raise ValueError('Retained opening does not match observed commitment')
                payload = opening['reveal']
            else:
                payload = {'round': number}
            command = action_id if action_id == 'resolve' else action_id + str(self.seat)
            request = {'op': 'invoke', 'object': self.object, 'principal': self.principal,
                       'intent': intent, 'expected': copy.deepcopy(saved['root']), 'command': command,
                       'input': copy.deepcopy(payload)}
            retained(path, {'choice': choice, 'request': request})
        return {'prepared': identity, 'action': action_id, 'status': 'retained'}

    def _world_receipt(self, request):
        """Read an exact historical request without selecting or executing a runtime."""
        with Path(str(self.database) + '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('World receipt custody busy; retry the same prepared request') from None
            if self.database.exists():
                for entry in loads(self.database.read_bytes())['receipts']:
                    if canonical(entry['request']) == canonical(request):
                        return entry['receipt']
        return None

    def send(self, identity):
        """Recover an admitted outcome first; pending execution requires original pins."""
        request = self._read('requests', identity)['request']
        receipt_path = self.custody / 'receipts' / (identity + '.json')
        if receipt_path.exists():
            reply = self._read('receipts', identity)
        else:
            reply = self._world_receipt(request)
            if reply is None:
                self._runtime()
                reply = desk.world.exchange(self.database, request, profile='compiled')
            retained(receipt_path, reply)
        # Full roots and openings stay in custody, never in the default display.
        result = {'prepared': identity, 'kind': reply['kind']}
        if reply['kind'] == 'refused':
            result['reason'] = reply['data'] if isinstance(reply['data'], str) else 'Host refused this request'
        elif reply['kind'] == 'committed':
            result['receiptView'] = client.public_view(reply['data']['root'])
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--custody', type=Path, required=True)
    parser.add_argument('--table', required=True)
    parser.add_argument('--principal', required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('observe')
    prepare = commands.add_parser('prepare')
    prepare.add_argument('card')
    prepare.add_argument('action', choices=('commit', 'reveal', 'resolve'))
    prepare.add_argument('--fields', default='{}')
    prepare.add_argument('--intent', required=True)
    send = commands.add_parser('send')
    send.add_argument('prepared')
    args = parser.parse_args()
    participant = Participant(args.database, args.custody, args.table, args.principal, args.seat)
    if args.command == 'observe':
        result = participant.observe()
    elif args.command == 'prepare':
        result = participant.prepare(args.card, args.action, loads(args.fields), args.intent)
    else:
        result = participant.send(args.prepared)
    print(desk.world.wire_dumps(result))


if __name__ == '__main__':
    main()
