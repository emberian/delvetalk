#!/usr/bin/env python3
"""Operator custody for posts-only play; capture/bind/receive, never publish."""
import argparse
from pathlib import Path
import sys
import time
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
import clerk
import town_cards
import opaque_offers
import source_offers
import worker
import world

FORMAT = 'delvetalk-town-operator-v1'
canonical, loads, digest, save = clerk.canonical, clerk.loads, clerk.digest, clerk.save


class Town:
    def __init__(self, clerk_state, *, state=None, request=None):
        self.clerk = clerk.Clerk(clerk_state, request=request)
        self.state = Path(state).expanduser().resolve() if state else self.clerk.state / 'town'
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.state / 'requests').mkdir(exist_ok=True, mode=0o700)
        binding = {'format': FORMAT, 'clerkState': str(self.clerk.state)}
        with self.lock():
            path = self.state / 'binding.json'
            if path.exists():
                if canonical(loads(path.read_bytes())) != canonical(binding):
                    raise ValueError('town custody belongs to another clerk')
            else:
                save(path, binding)

    def lock(self):
        return _lock(self.state / 'operator.lock')

    def _configuration(self):
        config = self.clerk.config()
        if config['profile']['pins'] != clerk.pins(config.get('runtimeProfile', 'compiled')):
            raise ValueError('clerk runtime pins changed')
        selection = config.get('townCards')
        if selection is None or config['profile'].get('townCards') != digest(selection):
            raise ValueError('operator requires the clerk’s explicitly configured cardbook')
        self.clerk.card_configuration(selection, config.get('runtimeProfile', 'compiled'))
        book = town_cards.CardBook(selection['path'])
        owner = {'format': FORMAT, 'clerkState': str(self.clerk.state), 'state': str(self.state)}
        stored = bootstrap.desk_module.immutable(book.path / 'operator.json', owner)
        if canonical(stored) != canonical(owner):
            raise ValueError('cardbook already belongs to another operator custody directory')
        return config, book

    def _capture_roots(self, objects, profile, *, expected=None, principal='reader'):
        return world.capture_roots(self.clerk.database, objects, principal=principal, profile=profile, expected=expected)

    def _public_view(self, object_id, profile, *, principal='reader', panel='main', expected=None):
        return world.opaque_view(self.clerk.database, object_id, principal=principal,
            panel=panel, audience='public', expected=expected, profile=profile)

    def check_public(self, alias):
        """Recheck current audience and exact source preimage before draft use."""
        config, book = self._configuration()
        return book.check_public(alias, self.clerk.database, profile=config.get('runtimeProfile', 'compiled'))

    def public_response(self, response):
        """Keep exact receipt recovery separate from current draft availability."""
        try:
            if response.get('audience') != 'public':
                raise ValueError('saved response has no public projection provenance')
            selection = response.get('preparation', {}).get('publicSelection')
            if 'preparation' in response:
                if not isinstance(selection, dict) or selection.get('audience') != 'public':
                    raise ValueError('preparation lacks a public source selection')
                config, _ = self._configuration()
                checked = world.query(self.clerk.database, {
                    'op': 'opaque-invitation', 'object': selection['object'],
                    'principal': response['receipt']['source']['author'],
                    'panel': selection['panel'], 'expected': selection['expected'],
                    'key': selection['key'], 'audience': 'public'},
                    profile=config.get('runtimeProfile', 'compiled'))
                if canonical(checked['selection']) != canonical(selection):
                    raise ValueError('public question observations changed')
            for card in response.get('cards', []):
                self.check_public(card['alias'])
        except (ValueError, KeyError, TypeError, OSError, RuntimeError):
            body = 'Turn outcome is retained. Current public cards are unavailable; check the original reply.'
            return {**response, 'cards': [], 'body': body, 'textSha256': town_cards.sha(body),
                'presentation': {'status': 'unavailable'}, 'publication': 'paused'}
        return response

    def _capture_view(self, object_id, expected_runtime, profile, *, principal='reader'):
        capture = self._capture_roots([object_id], profile, principal=principal)
        pair = capture['roots'][object_id]
        if pair is None:
            return None, capture
        root = pair['root']
        artifact = bootstrap.bound_room_artifact(self.clerk.database.parent, root)
        view = bootstrap.room.inspect_object(root, object_id, artifact, expected_runtime=expected_runtime)
        return view, self._capture_observations(view, capture, profile, principal=principal)

    def _capture_observations(self, view, capture, profile, *, principal='reader'):
        return source_offers.capture_observations(view, capture,
            capture_roots=lambda objects, expected=None: self._capture_roots(objects, profile, expected=expected, principal=principal))

    @staticmethod
    def _capture_parts(capture):
        return {'roots': {name: pair['root'] for name, pair in capture['roots'].items() if pair is not None},
                'references': {name: pair['reference'] for name, pair in capture['roots'].items() if pair is not None}}

    def capture(self, object_id, *, alias=None, principal='reader', panel='main'):
        with self.lock():
            config, book = self._configuration()
            if object_id not in config['objects']:
                raise ValueError('object is not enrolled in this clerk')
            projection = self._public_view(object_id, config.get('runtimeProfile', 'compiled'), principal=principal, panel=panel)
            captured = book.capture_public(object_id, projection, alias=alias, invitations=opaque_offers.capture(
                self.clerk.database, object_id, projection, principal, config.get('runtimeProfile', 'compiled')))
            return {'status': 'prepared', **captured}

    def capture_offer(self, object_id, key, *, alias=None, principal='reader', panel='main', expected=None, expected_observations=None):
        """Capture one source-authored transaction using one current snapshot."""
        with self.lock():
            config, book = self._configuration()
            if object_id not in config['objects']:
                raise ValueError('object is not enrolled in this clerk')
            profile = config.get('runtimeProfile', 'compiled')
            reference = None
            guards = dict(expected_observations or {})
            if expected is not None:
                guards[object_id] = expected
            held = self._capture_roots(list(guards), profile, expected=guards, principal=principal) if guards else None
            if expected is not None:
                reference = held['roots'][object_id]['reference']
            projected = self._public_view(object_id, profile, principal=principal, panel=panel, expected=reference)
            invitations = opaque_offers.capture(self.clerk.database, object_id, projected, principal,
                config.get('runtimeProfile', 'compiled'))
            action = projected['result']['actions'].get(key)
            invitation = invitations.get(key)
            if expected_observations:
                selected = {item['object']: item['root'] for item in (invitation or {}).get('selection', {}).get('observations', [])}
                if any(selected.get(name) != held['roots'][name]['reference'] for name in expected_observations):
                    raise ValueError('public source invitation dependencies changed')
            if not ((isinstance(action, dict) and action.get('visible') is True)
                    or (invitation is not None and invitation.get('available', True))):
                raise ValueError('public source projection does not offer this action')
            captured = book.capture_public(object_id, projected, alias=alias, action_key=key, invitations=invitations)
            return {'status': 'prepared', **captured}

    def capture_child(self, parent_alias, child_key, *, alias=None, principal='reader'):
        """Select one retained catalogue entry, then capture that object's fresh view."""
        with self.lock():
            config, book = self._configuration()
            parent = self.check_public(parent_alias)
            if parent['format'] != 'delvetalk-town-public-card-v1':
                raise ValueError('parent card lacks a public source projection')
            children = parent['projection']['result'].get('children', {'variant': 'nil', 'payload': {}})
            entries = []
            while children.get('variant') == 'cons' and len(entries) < 32:
                entries.append(children['payload']['head'])
                children = children['payload']['tail']
            descriptor = next((child for child in entries if child['key'] == child_key), None)
            if descriptor is None:
                raise ValueError('child is not offered by this public source projection')
            if alias == parent_alias:
                raise ValueError('child card requires a distinct alias')
            object_id, panel = descriptor['object'], descriptor['panel']
            selected = {'parent': parent_alias, 'key': child_key}
            if object_id not in config['objects']:
                return {'status': 'unavailable', **selected, 'object': object_id,
                    'panel': panel, 'reason': 'unenrolled'}
            projected = self._public_view(object_id, config.get('runtimeProfile', 'compiled'),
                principal=principal, panel=panel)
            captured = book.capture_public(object_id, projected, alias=alias, invitations=opaque_offers.capture(
                self.clerk.database, object_id, projected, principal, config.get('runtimeProfile', 'compiled')))
            return {'status': 'prepared', **selected, 'card': captured}

    def bind(self, alias, uri, cid):
        with self.lock():
            config, book = self._configuration()
            issuers = config['townCards']['issuers']
            def verified(source_uri, source_cid):
                author, _, _ = clerk.parse_uri(source_uri, (clerk.FEED,))
                if author not in issuers:
                    raise ValueError('publication issuer is not configured')
                self.clerk.verify_repository(author)
                return self.clerk.fetch_record(source_uri, source_cid, (clerk.FEED,))
            return book.bind(alias, {'uri': uri, 'cid': cid}, verified, database=self.clerk.database,
                profile=config.get('runtimeProfile', 'compiled'))

    def receive(self, uri, cid, *, interpretation=None):
        if interpretation is not None:
            interpretation = clerk.manual_intake.validate(interpretation)
            if interpretation['status'] != 'act':
                review = self.clerk.receive_interpreted(uri, cid, interpretation)
                return {**review, 'body': interpretation['message'], 'publication': 'paused'}
        source = town_cards.publication_source({'uri': uri, 'cid': cid})
        path = self.state / 'requests' / (worker.key(uri) + '.json')
        with self.lock():
            entry = loads(path.read_bytes()) if path.exists() else None
            if entry is not None:
                if entry['source'] != source:
                    raise ValueError('original reply URI is already retained with a different CID')
                if interpretation is not None and 'receipt' in entry:
                    retained = entry['receipt'].get('interpretation', {}).get('decision')
                    if canonical(retained) != canonical(interpretation):
                        raise ValueError('town response already binds a different interpretation')
                if 'response' in entry:
                    return self.public_response(entry['response'])
            config, book = self._configuration()
            if entry is None:
                sequence = len(list((self.state / 'requests').glob('*.json'))) + 1
                if sequence > 10000:
                    raise ValueError('town response retention bound reached')
                entry = {'format': 'delvetalk-town-attempt-v1', 'source': source, 'sequence': sequence,
                         'clerkProfile': config['profile'], 'cardbook': config['townCards']}
                save(path, entry)  # Original source and human alias sequence survive uncertainty.
            elif canonical(entry['clerkProfile']) != canonical(config['profile']) or canonical(entry['cardbook']) != canonical(config['townCards']):
                raise ValueError('pending town response belongs to a different configured runtime/cardbook')
            if 'receipt' not in entry:
                try:
                    receipt = (self.clerk.receive_interpreted(uri, cid, interpretation)
                               if interpretation is not None else self.clerk.receive(uri, cid))
                    if receipt.get('format') not in ('delvetalk-clerk-receipt-v1', 'delvetalk-clerk-preparation-v1') or any(receipt['source'][k] != source[k] for k in source):
                        raise ValueError('clerk receipt differs from the selected original reply')
                    entry['receipt'] = receipt
                    save(path, entry)
                except (OSError, RuntimeError, clerk.delve.Failure) as error:
                    # Pending source identity is already durable. This is not a
                    # terminal refusal and must never allocate fresh cards/attempts.
                    return {'status': 'uncertain', 'source': source, 'publication': 'paused',
                            'body': 'No confirmed outcome. Ask us to check your original reply. Do not repost the command.',
                            'detail': type(error).__name__}
            receipt = entry['receipt']
            if receipt['format'] == 'delvetalk-clerk-preparation-v1':
                outcome = receipt['outcome']
                response = {'status': outcome['kind'], 'source': source, 'publication': 'paused',
                            'body': outcome['message'], 'preparation': outcome, 'receipt': receipt, 'audience': 'public'}
                entry['response'] = response
                save(path, entry)
                return self.public_response(response)
            if 'publicViews' not in entry:
                request = receipt['request']
                targets = [request['object']] if 'object' in request else sorted(request['reads'])
                entry['publicViews'], entry['notices'] = [], []
                for target in targets:
                    try:
                        data = receipt['reply'].get('data', {})
                        if not isinstance(data, dict):
                            data = {}
                        expected = (data.get('reference') if request['op'] == 'opaque-invoke'
                            else data.get('references', {}).get(target) if request['op'] == 'opaque-transaction' else None)
                        projected = self._public_view(target, config.get('runtimeProfile', 'compiled'),
                            principal=request['principal'], expected=expected)
                        entry['publicViews'].append({'object': target, 'projection': projected,
                            'invitations': opaque_offers.capture(self.clerk.database, target, projected,
                                request['principal'], config.get('runtimeProfile', 'compiled'))})
                    except (ValueError, KeyError, TypeError, OSError, RuntimeError):
                        entry['notices'].append({'object': target, 'reason': 'public-view-unavailable'})
                entry['aliases'] = ['reply-' + str(entry['sequence']) + '-' + str(n + 1)
                    for n in range(len(entry['publicViews']))]
                save(path, entry)
            cards = []
            notices = list(entry.get('notices', []))
            for retained, alias in zip(entry['publicViews'], entry['aliases']):
                try:
                    cards.append(book.capture_public(retained['object'], retained['projection'], alias=alias,
                        invitations=retained.get('invitations', {})))
                except (ValueError, KeyError, TypeError, OSError, RuntimeError):
                    notices.append({'object': retained['object'], 'reason': 'public-card-unavailable'})
            # Private invocation results and admission diagnostics are not public
            # projections. The next source-authored public panel supplies detail.
            kind = receipt['reply']['kind']
            prepared = {'body': 'Turn: ' + kind + '.'}
            author = receipt['source']['author']
            name = book.metadata()['displayNames'].get(author, 'the participant')
            key = uri.rsplit('/', 1)[1]
            link = 'https://delve.town/profile/' + quote(author, safe=':') + '/post/' + quote(key, safe='')
            body = 'For ' + town_cards.canonical(name) + ' · [original reply](' + link + ')\n' + prepared['body']
            for notice in notices:
                body += '\nNo next card for ' + town_cards.canonical(notice['object']) + (': object is currently absent.' if notice['reason'] == 'absent' else ': its view could not be prepared; ask the operator to inspect it.')
            if cards:
                body += '\n\nCurrent captured views and next actions:\n' + '\n\n'.join(card['body'] for card in cards)
            response = {'format': 'delvetalk-town-response-v1', 'status': 'prepared', 'source': source,
                        'replyTo': source, 'receipt': receipt, 'cards': cards, 'notices': notices,
                        'body': body, 'textSha256': town_cards.sha(body), 'publication': 'paused', 'audience': 'public'}
            entry['response'] = response
            save(path, entry)
            return self.public_response(response)


from contextlib import contextmanager


@contextmanager
def _lock(path):
    with worker.bounded_lock(path, time.monotonic() + 10, time.monotonic) as acquired:
        if not acquired:
            raise TimeoutError('town custody is busy; check the same original reply later')
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clerk-state', type=Path, required=True)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--text', action='store_true', help='print only the retained draft body')
    commands = parser.add_subparsers(dest='operation', required=True)
    capture = commands.add_parser('capture')
    capture.add_argument('object')
    capture.add_argument('--alias')
    capture.add_argument('--principal', default='reader', help='explicit local custody identity for current read law')
    capture.add_argument('--panel', default='main', help='explicit source-selected public panel')
    draft = commands.add_parser('draft', help='recheck current native audience and exact pins for a saved draft')
    draft.add_argument('card')
    capture.add_argument('--offer', help='visible source-authored composite action key')
    child = commands.add_parser('capture-child')
    child.add_argument('parent')
    child.add_argument('key')
    child.add_argument('--alias')
    child.add_argument('--principal', default='reader', help='explicit local custody identity for current read law')
    bind = commands.add_parser('bind')
    bind.add_argument('card')
    bind.add_argument('uri')
    bind.add_argument('--cid', required=True)
    receive = commands.add_parser('receive')
    receive.add_argument('uri')
    receive.add_argument('--cid', required=True)
    receive.add_argument('--interpretation', type=Path, help='explicit local interpretation of the original post')
    configure_summon = commands.add_parser('configure-summon', help='bind an explicit source session factory/service')
    configure_summon.add_argument('--factory', required=True)
    configure_summon.add_argument('--offer', default='make')
    configure_summon.add_argument('--principal', required=True)
    configure_summon.add_argument('--followup', nargs=2, action='append', default=[], metavar=('OBJECT', 'OFFER'))
    summon = commands.add_parser('summon', help='interpret one verified original post as a fresh source-owned session')
    summon.add_argument('uri')
    summon.add_argument('--cid', required=True)
    summon.add_argument('--interpreter', required=True)
    summon.add_argument('--basis', required=True)
    args = parser.parse_args()
    try:
        operator = Town(args.clerk_state, state=args.state)
        if args.operation in ('configure-summon', 'summon'):
            from town_summon import Summoner
            service = Summoner(operator)
            result = (service.configure(factory=args.factory, offer=args.offer, principal=args.principal,
                                        followups=[{'object': object_id, 'offer': offer} for object_id, offer in args.followup])
                      if args.operation == 'configure-summon' else
                      service.summon(args.uri, args.cid, interpreter=args.interpreter, basis=args.basis))
        elif args.operation == 'capture':
            result = (operator.capture_offer(args.object, args.offer, alias=args.alias, principal=args.principal, panel=args.panel) if args.offer
                      else operator.capture(args.object, alias=args.alias, principal=args.principal, panel=args.panel))
        elif args.operation == 'draft':
            result = operator.check_public(args.card)
        elif args.operation == 'capture-child':
            result = operator.capture_child(args.parent, args.key, alias=args.alias, principal=args.principal)
            if args.text and result['status'] == 'prepared':
                print(result['card']['body'])
                return 0
        elif args.operation == 'bind':
            result = operator.bind(args.card, args.uri, args.cid)
        else:
            result = operator.receive(args.uri, args.cid, interpretation=loads(args.interpretation.read_bytes()) if args.interpretation else None)
        print(result['body'] if args.text and 'body' in result else clerk.world.wire_dumps(result))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, clerk.delve.Failure) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
