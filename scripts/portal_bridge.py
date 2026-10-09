#!/usr/bin/env python3
"""Offline saved-draft handoff to repository publication and local clerk receipts."""
import argparse
import copy
import hashlib
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affordances
import clerk
import portal
import receipts

FORMAT = 'delvetalk-portal-repository-v1'


def equal(left, right, message):
    if clerk.canonical(left) != clerk.canonical(right):
        raise ValueError(message)


class Bridge:
    """Local custody only. A source binding is a claim until clerk reconciliation."""
    def __init__(self, app):
        self.app = app
        self.state = app.state / 'repository'
        self.state.mkdir(exist_ok=True, mode=0o700)

    def _path(self, draft):
        # Validate using the portal's own saved-reference boundary.
        self.app._read('drafts', draft)
        return self.state / (draft + '.json')

    def _prepared(self, draft, *, reconstruct=True):
        saved = self.app._read('drafts', draft)
        card = self.app._read('cards', saved['card'])
        request = saved['request']
        equal(saved['runtime'], card['runtime'], 'Draft runtime differs from captured card')
        equal(request['principal'], saved['localPrincipal'] or 'portal-preview',
              'Draft local identity differs from its captured session')
        derived = request
        if reconstruct:
            derived = affordances.request(card['view'], saved['action'], request['principal'],
                                          request['intent'], saved['fields'])
            equal(request, derived, 'Draft request differs from captured action')
        wire = {key: value for key, value in derived.items() if key not in ('principal', 'intent')}
        equal(saved['wire'], wire, 'Draft wire differs from captured action')
        raw = clerk.canonical(wire).decode('utf-8')
        if len(raw.encode('utf-8')) > portal.MAX_BODY:
            raise ValueError('Repository request exceeds the host envelope')
        record = receipts.encode('request', raw)
        # Portal's random original intent prevents independent identical drafts
        # from becoming one remote operation, while restart keeps this identity.
        identity = clerk.digest({'binding': portal.loads((self.app.state / 'binding.json').read_bytes()),
                                 'draft': draft, 'request': request, 'runtime': saved['runtime'],
                                 'capture': card, 'action': saved['action'], 'fields': saved['fields']})
        return {'format': FORMAT, 'draft': draft, 'card': saved['card'],
                'wire': wire, 'requestJson': raw, 'record': record,
                'runtime': saved['runtime'], 'publicationIntent': 'portal:' + identity}

    def prepare(self, draft):
        """Derive exact existing request wire, without credentials or publication."""
        with portal.bounded_lock(self.state / 'bridge.lock'):
            path = self._path(draft)
            # A retry checks the retained capture bytes without reinterpreting
            # them under a possibly upgraded affordance constructor.
            expected = self._prepared(draft, reconstruct=not path.exists())
            if path.exists():
                value = portal.loads(path.read_bytes())
                equal(value['prepared'], expected, 'Prepared draft changed; preserve original custody')
            else:
                value = {'prepared': expected}
                clerk.save(path, value)
            return copy.deepcopy(value['prepared'])

    def bind(self, draft, uri, cid):
        """Retain the external operation identity; this does not authenticate it."""
        author, _, _ = clerk.parse_uri(uri, (clerk.COLLECTION,))
        if not isinstance(cid, str) or not cid or len(cid) > 200:
            raise ValueError('Expected source CID is required')
        prepared = self.prepare(draft)
        source = {'uri': uri, 'cid': cid, 'author': author, 'pds': clerk.PDS}
        # The receiving envelope adds these identity fields and must also fit.
        request = {'principal': author, 'intent': 'delve:' + uri, **prepared['wire']}
        if len(clerk.canonical(request)) > portal.MAX_BODY:
            raise ValueError('Derived repository request exceeds the host envelope')
        with portal.bounded_lock(self.state / 'bridge.lock'):
            path = self._path(draft)
            saved = portal.loads(path.read_bytes())
            if 'source' in saved:
                equal(saved['source'], source, 'Draft already bound to another URI or CID')
            else:
                saved['source'] = source
                clerk.save(path, saved)
        return {'draft': draft, 'source': source, 'kind': 'uncertain',
                'summary': 'Repository identity retained; no admission receipt confirmed.'}

    def reconcile(self, draft, receiver):
        """Read trusted local clerk custody; never fetch, submit, or accept browser receipts."""
        self.prepare(draft)
        with portal.bounded_lock(self.state / 'bridge.lock'):
            path = self._path(draft)
            saved = portal.loads(path.read_bytes())
            source = saved.get('source')
            if source is None:
                return {'draft': draft, 'kind': 'uncertain',
                        'summary': 'Prepared for repository publication; no source is bound.'}
            # An explicitly supplied local Clerk is the trust boundary, not a DID
            # or a self-consistent digest in a caller-supplied receipt document.
            receiver_path = str(receiver.state.resolve())
            if 'receiver' in saved:
                equal(saved['receiver'], receiver_path, 'Draft belongs to another clerk custody')
            else:
                saved['receiver'] = receiver_path
                clerk.save(path, saved)
            journal = receiver.state / 'requests' / (hashlib.sha256(source['uri'].encode()).hexdigest() + '.json')
            with portal.bounded_lock(receiver.state / 'clerk.lock'):
                if not journal.is_file():
                    return self._uncertain(draft, source)
                entry = clerk.loads(journal.read_bytes())
                expected = {'principal': source['author'], 'intent': 'delve:' + source['uri'],
                            **saved['prepared']['wire']}
                equal(entry['source'], source, 'Clerk source identity differs from bound repository request')
                equal(entry['record'], saved['prepared']['record'], 'Clerk record differs from prepared draft')
                equal(entry['request'], expected, 'Clerk derived request differs from prepared draft')
                with portal.bounded_lock(str(receiver.database) + '.lock'):
                    world = clerk.loads(receiver.database.read_bytes())
                retained = next((item['receipt'] for item in world['receipts']
                                 if clerk.canonical(item['request']) == clerk.canonical(expected)), None)
                if retained is None:
                    if 'receipt' in entry:
                        raise ValueError('Clerk receipt has no matching retained world admission')
                    return self._uncertain(draft, source)
                receipt = {'format': 'delvetalk-clerk-receipt-v1', 'source': source,
                           'request': expected, 'reply': retained, 'profile': entry['profile']}
                receipt['id'] = clerk.digest(receipt)
                if 'receipt' in entry:
                    equal(entry['receipt'], receipt, 'Clerk receipt differs from retained world admission')
            kind = retained['kind']
            if kind not in ('committed', 'refused'):
                raise ValueError('Unexpected retained admission outcome')
            outcome = {'draft': draft, 'kind': kind, 'source': source, 'reply': retained,
                       'receipt': receipt, 'summary': 'Action committed.' if kind == 'committed'
                       else str(retained.get('data', 'Action refused.')),
                       'links': {'refresh': '/api/object?object=' + quote(expected['object'], safe='')}}
            if 'outcome' in saved:
                equal(saved['outcome'], outcome, 'Retained repository outcome changed')
            else:
                saved['outcome'] = outcome
                clerk.save(path, saved)
            return copy.deepcopy(outcome)

    @staticmethod
    def _uncertain(draft, source):
        return {'draft': draft, 'source': source, 'kind': 'uncertain',
                'summary': 'No confirmed admission. Recover this same repository URI and CID.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='portal world directory')
    parser.add_argument('--state', type=Path, help='existing portal custody directory')
    commands = parser.add_subparsers(dest='op', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('draft')
    bind = commands.add_parser('bind')
    bind.add_argument('draft')
    bind.add_argument('uri')
    bind.add_argument('--cid', required=True)
    reconcile = commands.add_parser('reconcile')
    reconcile.add_argument('draft')
    reconcile.add_argument('--clerk-state', type=Path, required=True)
    args = parser.parse_args()
    try:
        bridge = Bridge(portal.Portal(args.directory, state=args.state))
        if args.op == 'prepare':
            result = bridge.prepare(args.draft)
        elif args.op == 'bind':
            result = bridge.bind(args.draft, args.uri, args.cid)
        else:
            result = bridge.reconcile(args.draft, clerk.Clerk(args.clerk_state))
        print(clerk.canonical(result).decode())
    except (ValueError, OSError, KeyError, TypeError, receipts.Failure) as error:
        print('portal-bridge: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
