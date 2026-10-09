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
import worker

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
        if config['profile']['pins'] != clerk.pins(config.get('runtimeProfile', 'world')):
            raise ValueError('clerk runtime pins changed')
        selection = config.get('townCards')
        if selection is None or config['profile'].get('townCards') != digest(selection):
            raise ValueError('operator requires the clerk’s explicitly configured cardbook')
        self.clerk.card_configuration(selection, config.get('runtimeProfile', 'world'))
        book = town_cards.CardBook(selection['path'])
        owner = {'format': FORMAT, 'clerkState': str(self.clerk.state), 'state': str(self.state)}
        stored = bootstrap.desk_module.immutable(book.path / 'operator.json', owner)
        if canonical(stored) != canonical(owner):
            raise ValueError('cardbook already belongs to another operator custody directory')
        return config, book

    def _views(self, object_ids, expected_runtime):
        with _lock(Path(str(self.clerk.database) + '.lock')):
            snapshot = loads(self.clerk.database.read_bytes())
        views = []
        for object_id in object_ids:
            root = snapshot['objects'].get(object_id)
            if root is None:
                raise ValueError('object absent from current world: ' + object_id)
            artifact = bootstrap.bound_room_artifact(self.clerk.database.parent, root)
            views.append(bootstrap.room.inspect_object(root, object_id, artifact,
                                                       expected_runtime=expected_runtime))
        return views

    def capture(self, object_id, *, alias=None):
        with self.lock():
            config, book = self._configuration()
            if object_id not in config['objects']:
                raise ValueError('object is not enrolled in this clerk')
            captured = book.capture(self._views([object_id], book.metadata()['runtime'])[0], alias=alias)
            return {'status': 'prepared', **captured}

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
            return book.bind(alias, {'uri': uri, 'cid': cid}, verified)

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
                    return entry['response']  # No book, network, rendering, or changed pins needed.
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
                    if receipt.get('format') != 'delvetalk-clerk-receipt-v1' or any(receipt['source'][k] != source[k] for k in source):
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
            if 'views' not in entry:
                # Snapshot presentation after receipt recovery. Other admitted turns may
                # have advanced the world; the reply distinguishes receipt from current view.
                request = receipt['request']
                targets = [request['object']] if 'object' in request else sorted(request['reads'])
                targets = list(dict.fromkeys(targets + [child['object'] for child in town_cards.affordances.allocated_refs(receipt['reply'])]))
                with _lock(Path(str(self.clerk.database) + '.lock')):
                    snapshot = loads(self.clerk.database.read_bytes())
                entry['views'], entry['notices'] = [], []
                for target in targets:
                    root = snapshot['objects'].get(target)
                    if root is None:
                        entry['notices'].append({'object': target, 'reason': 'absent'})
                        continue
                    try:
                        artifact = bootstrap.bound_room_artifact(self.clerk.database.parent, root)
                        entry['views'].append(bootstrap.room.inspect_object(root, target, artifact,
                                                    expected_runtime=book.metadata()['runtime']))
                    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                        entry['notices'].append({'object': target, 'reason': 'view-unavailable', 'detail': str(error)[:2000]})
                entry['aliases'] = ['reply-' + str(entry['sequence']) + '-' + str(n + 1) for n in range(len(entry['views']))]
                save(path, entry)  # Capture exact views before allocating any follow-up card.
            cards = []
            notices = list(entry.get('notices', []))
            for view, alias in zip(entry['views'], entry['aliases']):
                try:
                    cards.append(book.capture(view, alias=alias))
                except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                    notices.append({'object': view['object'], 'reason': 'card-unavailable', 'detail': str(error)[:2000]})
            prepared = book.prepare_outcome(receipt['reply'])
            author = receipt['source']['author']
            name = book.metadata()['displayNames'].get(author, 'the participant')
            key = uri.rsplit('/', 1)[1]
            link = 'https://delve.town/profile/' + quote(author, safe=':') + '/post/' + quote(key, safe='')
            body = 'For ' + town_cards.canonical(name) + ' · [original reply](' + link + ')\n' + prepared['body']
            if 'interpretation' in receipt:
                decision = receipt['interpretation']['decision']
                body += '\nOperator interpretation (' + town_cards.canonical(decision['interpreter']) + '): ' + town_cards.canonical(decision['basis'])
            for notice in notices:
                body += '\nNo next card for ' + town_cards.canonical(notice['object']) + (': object is currently absent.' if notice['reason'] == 'absent' else ': its view could not be prepared; ask the operator to inspect it.')
            if cards:
                body += '\n\nCurrent captured views and next actions:\n' + '\n\n'.join(card['body'] for card in cards)
            response = {'format': 'delvetalk-town-response-v1', 'status': 'prepared', 'source': source,
                        'replyTo': source, 'receipt': receipt, 'cards': cards, 'notices': notices,
                        'body': body, 'textSha256': town_cards.sha(body), 'publication': 'paused'}
            entry['response'] = response
            save(path, entry)
            return response


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
    bind = commands.add_parser('bind')
    bind.add_argument('card')
    bind.add_argument('uri')
    bind.add_argument('--cid', required=True)
    receive = commands.add_parser('receive')
    receive.add_argument('uri')
    receive.add_argument('--cid', required=True)
    receive.add_argument('--interpretation', type=Path, help='explicit local interpretation of the original post')
    args = parser.parse_args()
    try:
        operator = Town(args.clerk_state, state=args.state)
        if args.operation == 'capture':
            result = operator.capture(args.object, alias=args.alias)
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
