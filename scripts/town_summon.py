"""Explicit operator custody for source-owned sessions from verified public posts.

Tags discover posts; they neither authenticate an author nor authorize execution.
The configured service calls the captured source factory under its current law.
"""
import copy
import hashlib
from pathlib import Path

import clerk
import source_offers
import town_cards
import world

FORMAT = 'delvetalk-town-summoner-v1'


class Summoner:
    def __init__(self, operator):
        self.operator = operator
        self.state = operator.state / 'summons'

    def configure(self, *, factory, offer, principal, followups=()):
        if any(not isinstance(value, str) or not value or len(value.encode('utf-8')) > 512
               for value in (factory, offer, principal)):
            raise ValueError('explicit bounded factory, offered preparation and service principal required')
        if (not isinstance(followups, (list, tuple)) or len(followups) > 8
                or any(not isinstance(item, dict) or set(item) != {'object', 'offer'}
                       or any(not isinstance(value, str) or not value or len(value.encode('utf-8')) > 512
                              for value in item.values()) for item in followups)):
            raise ValueError('followups require at most eight explicit object/offer selections')
        binding = {'format': FORMAT, 'factory': factory, 'offer': offer, 'principal': principal,
                   'followups': copy.deepcopy(list(followups))}
        with self.operator.lock():
            config, _ = self.operator._configuration()
            if config.get('runtimeProfile', 'world') != 'compiled':
                raise ValueError('source session factory requires compiled runtime')
            if factory not in config['objects']:
                raise ValueError('session factory must already be enrolled')
            path = self.state / 'configuration.json'
            if path.exists() and clerk.loads(path.read_bytes()) != binding:
                raise ValueError('summoner already has a different explicit configuration')
            clerk.save(path, binding)
        return binding

    def _followup(self, entry, path, book):
        """One source-selected continuation within an explicit physical allowlist."""
        if 'followup' not in entry:
            data = entry['reply'].get('data', {})
            results = data.get('results', []) if isinstance(data, dict) else []
            result = results[0] if results and isinstance(results[0], dict) else {}
            descriptor = result.get('followup')
            followup = {'descriptor': descriptor}
            if descriptor is None or (isinstance(descriptor, dict) and descriptor.get('enabled') is False):
                followup['outcome'] = {'status': 'not-requested'}
            elif (not isinstance(descriptor, dict)
                  or set(descriptor) != {'enabled', 'object', 'offer', 'fields'}
                  or descriptor['enabled'] is not True
                  or {'object': descriptor['object'], 'offer': descriptor['offer']} not in entry['binding']['followups']):
                followup['outcome'] = {'status': 'refused', 'message': 'The source followup is outside the configured service scope.'}
            elif descriptor['fields'] != {'did': entry['source']['author'], 'proof': entry['source']['cid']}:
                followup['outcome'] = {'status': 'refused', 'message': 'The followup differs from the verified original post identity.'}
            entry['followup'] = followup
            clerk.save(path, entry)
        followup = entry['followup']
        if 'outcome' in followup:
            return followup['outcome']
        descriptor = followup['descriptor']
        try:
            if 'invitation' not in followup:
                view, capture = self.operator._capture_view(descriptor['object'], book.metadata()['runtime'], 'compiled', principal=entry['binding']['principal'])
                if view is None:
                    raise ValueError('configured followup object is absent')
                offers = source_offers.capture(view, **self.operator._capture_parts(capture))
                if descriptor['offer'] not in offers:
                    raise ValueError('configured followup invitation is unavailable')
                followup['invitation'] = offers[descriptor['offer']]
                clerk.save(path, entry)
            if 'preparation' not in followup:
                followup['preparation'] = source_offers.prepare(followup['invitation'], entry['binding']['principal'],
                    entry['intent'] + ':followup', descriptor['fields'], database=self.operator.clerk.database)
                prepared = followup['preparation']
                if prepared['kind'] == 'ready':
                    request = prepared['request']
                    if (request.get('principal') != entry['binding']['principal']
                            or request.get('intent') != entry['intent'] + ':followup'):
                        raise ValueError('followup changed its bound service identity')
                clerk.save(path, entry)
            prepared = followup['preparation']
            if prepared['kind'] != 'ready':
                followup['outcome'] = {'status': prepared['kind'], 'preparation': prepared}
                if isinstance(prepared.get('message'), str):
                    followup['outcome']['message'] = prepared['message']
            else:
                request = prepared['request']
                reply = world.retained_reply(self.operator.clerk.database, request)
                if reply is None:
                    reply = world.exchange(self.operator.clerk.database, request, profile='compiled', timeout=30)
                followup['outcome'] = {'status': reply['kind'], 'receipt': reply}
            clerk.save(path, entry)
            return followup['outcome']
        except (OSError, RuntimeError) as error:
            # Keep the exact request pending. Successful session creation stands.
            return {'status': 'uncertain', 'message': 'Check this original post to recover the separate membership outcome.',
                    'detail': type(error).__name__}
        except (ValueError, KeyError, TypeError) as error:
            if followup.get('preparation', {}).get('kind') == 'ready':
                return {'status': 'uncertain', 'message': 'The retained membership request needs operator inspection; session creation stands.',
                        'detail': type(error).__name__}
            followup['outcome'] = {'status': 'unavailable', 'message': str(error)[:2000]}
            clerk.save(path, entry)
            return followup['outcome']

    def _recover_receipts(self, entry, path):
        """Read exact retained effects before asking whether new work may run."""
        prepared = entry.get('preparation', {})
        if 'reply' not in entry and prepared.get('kind') == 'ready':
            request = prepared['request']
            if (request.get('principal') != entry['binding']['principal']
                    or request.get('intent') != entry['intent']):
                raise ValueError('retained session request differs from its service identity')
            reply = world.retained_reply(entry['database'] if 'database' in entry else self.operator.clerk.database, request)
            if reply is not None:
                entry['reply'] = reply
                clerk.save(path, entry)
        followup = entry.get('followup', {})
        prepared = followup.get('preparation', {})
        if (entry.get('reply', {}).get('kind') == 'committed'
                and 'outcome' not in followup and prepared.get('kind') == 'ready'):
            request = prepared['request']
            if (request.get('principal') != entry['binding']['principal']
                    or request.get('intent') != entry['intent'] + ':followup'):
                raise ValueError('retained followup request differs from its service identity')
            reply = world.retained_reply(entry['database'] if 'database' in entry else self.operator.clerk.database, request)
            if reply is not None:
                followup['outcome'] = {'status': reply['kind'], 'receipt': reply}
                clerk.save(path, entry)

    @staticmethod
    def _receipt_only(entry):
        """Report existing evidence without rendering or starting a continuation."""
        reply = entry['reply']
        membership = entry.get('followup', {}).get('outcome')
        if membership is None:
            membership = {'status': 'unavailable',
                'message': 'Membership continuation requires the original configured runtime.'}
        body = ('Session: ' + reply['kind'] + '. The original native result is retained.\n'
                'Current cards and unfinished continuations require the original configured runtime. '
                'Check this original post; do not summon again.')
        if 'receipt' in membership:
            body += '\nShared membership: ' + membership['status'] + '. Its original native result is retained.'
        return {'format': 'delvetalk-town-summon-response-v1', 'status': reply['kind'],
            'source': entry['source'], 'replyTo': {k: entry['source'][k] for k in ('uri', 'cid')},
            'reply': reply, 'request': entry['preparation']['request'],
            'interpretation': entry['interpretation'], 'cards': [], 'notices': [],
            'membership': copy.deepcopy(membership), 'presentation': {'status': 'unavailable'},
            'body': body, 'textSha256': town_cards.sha(body), 'publication': 'paused'}

    def summon(self, uri, cid, *, interpreter, basis):
        decision = clerk.manual_intake.validate({'status': 'act', 'interpreter': interpreter,
            'basis': basis, 'request': {}})
        source = town_cards.publication_source({'uri': uri, 'cid': cid})
        author, _, _ = clerk.parse_uri(uri, (clerk.FEED,))
        source.update(author=author, pds=clerk.PDS)
        path = self.state / 'requests' / (hashlib.sha256(uri.encode()).hexdigest() + '.json')
        with self.operator.lock():
            entry = clerk.loads(path.read_bytes()) if path.exists() else None
            if entry is not None:
                if entry['source'] != source:
                    raise ValueError('original summon URI already has a different CID; use a new rkey')
                if entry['decision'] != decision:
                    raise ValueError('original summon already has a different operator interpretation')
                if 'response' in entry:
                    return entry['response']
                # Receipt lookup has no dependency on current source or display pins.
                # In particular, never re-admit a lost reply merely to recover it.
                try:
                    self._recover_receipts(entry, path)
                except (OSError, RuntimeError, ValueError) as error:
                    if 'reply' in entry:
                        return self._receipt_only(entry)
                    return {'status': 'uncertain', 'source': source, 'publication': 'paused',
                        'body': 'Session outcome unknown. Check this original post; do not summon again.',
                        'detail': type(error).__name__}
            try:
                config, book = self.operator._configuration()
                binding = clerk.loads((self.state / 'configuration.json').read_bytes())
                if config.get('runtimeProfile', 'world') != 'compiled':
                    raise ValueError('source session factory requires compiled runtime')
                pins = {'clerk': config['profile'], 'adapter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'operator': hashlib.sha256(Path(__file__).with_name('town.py').read_bytes()).hexdigest(),
                        'cardbook': config['townCards']}
                if entry is not None and (entry['binding'] != binding or entry['pins'] != pins
                        or entry.get('database', str(self.operator.clerk.database)) != str(self.operator.clerk.database)):
                    raise ValueError('pending summon belongs to another configured source/runtime')
            except (OSError, RuntimeError, ValueError):
                if entry is not None and 'reply' in entry:
                    return self._receipt_only(entry)
                raise
            if entry is None:
                self.operator.clerk.verify_repository(author)
                record = self.operator.clerk.fetch_record(uri, cid, (clerk.FEED,))
                if (not isinstance(record, dict) or record.get('$type') != clerk.FEED
                        or not isinstance(record.get('text'), str) or len(clerk.canonical(record)) > 1024 * 1024):
                    raise ValueError('summoning requires an exact bounded public post')
                sequence = len(list((self.state / 'requests').glob('*.json'))) + 1
                if sequence > 10000:
                    raise ValueError('summon custody retention bound reached')
                entry = {'format': FORMAT, 'source': source, 'record': record,
                    'recordSha256': clerk.digest(record), 'decision': decision,
                    'interpretation': clerk.manual_intake.attestation(decision, source, clerk.digest(record)),
                    'binding': binding, 'pins': pins, 'sequence': sequence, 'database': str(self.operator.clerk.database),
                    'intent': 'delve-summon:' + uri}
                clerk.save(path, entry)
            if 'invitation' not in entry:
                view, capture = self.operator._capture_view(binding['factory'], book.metadata()['runtime'], 'compiled', principal=binding['principal'])
                if view is None:
                    raise ValueError('configured session factory is absent')
                offers = source_offers.capture(view, **self.operator._capture_parts(capture))
                if binding['offer'] not in offers:
                    raise ValueError('configured source factory does not offer that preparation')
                entry['invitation'] = offers[binding['offer']]
                clerk.save(path, entry)
            if 'preparation' not in entry:
                entry['preparation'] = source_offers.prepare(entry['invitation'], binding['principal'], entry['intent'],
                    {'author': author, 'originUri': uri, 'originCid': cid}, database=self.operator.clerk.database)
                if entry['preparation']['kind'] == 'ready':
                    request = entry['preparation']['request']
                    if request.get('principal') != binding['principal'] or request.get('intent') != entry['intent']:
                        raise ValueError('source preparation changed bound service principal or attempt identity')
                    entry['interpretation'] = clerk.manual_intake.attestation(
                        {**decision, 'request': request}, source, entry['recordSha256'])
                clerk.save(path, entry)
            prepared = entry['preparation']
            if prepared['kind'] != 'ready':
                response = {'status': prepared['kind'], 'source': source, 'preparation': prepared,
                            'body': prepared.get('message', 'The source factory did not prepare a session.'),
                            'publication': 'paused'}
                entry['response'] = response
                clerk.save(path, entry)
                return response
            if 'reply' not in entry:
                request = prepared['request']
                try:
                    reply = world.retained_reply(self.operator.clerk.database, request)
                    if reply is None:
                        reply = world.exchange(self.operator.clerk.database, request, profile='compiled', timeout=30)
                    entry['reply'] = reply
                    clerk.save(path, entry)
                except (OSError, RuntimeError) as error:
                    return {'status': 'uncertain', 'source': source, 'publication': 'paused',
                            'body': 'Session outcome unknown. Check this original post; do not summon again.',
                            'detail': type(error).__name__}
            reply = entry['reply']
            allocated = town_cards.affordances.allocated_refs(reply) if reply['kind'] == 'committed' else []
            # Transport enrollment follows actual source allocation. It creates no
            # grant; source-owned laws still govern every subsequent operation.
            if allocated:
                with clerk.delve.locked(self.operator.clerk.state / 'clerk.lock'):
                    current = self.operator.clerk.config()
                    current['objects'] = sorted(set(current['objects']) | {item['object'] for item in allocated})
                    current['repositories'] = sorted(set(current['repositories']) | {author})
                    clerk.save(self.operator.clerk.state / 'clerk.json', current)
            membership = self._followup(entry, path, book) if reply['kind'] == 'committed' else {'status': 'not-requested'}
            if 'views' not in entry:
                entry['views'], entry['notices'] = [], []
                for item in allocated:
                    object_id = item['object']
                    try:
                        view, capture = self.operator._capture_view(object_id, book.metadata()['runtime'], 'compiled', principal=entry['source']['author'])
                        if view is None:
                            raise ValueError('allocated object is currently absent')
                        entry['views'].append({'view': view, 'capture': capture,
                            'alias': 'summon-' + str(entry['sequence']) + '-' + str(len(entry['views']) + 1)})
                    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                        entry['notices'].append({'object': object_id, 'detail': str(error)[:2000]})
                clerk.save(path, entry)
            cards, notices = [], copy.deepcopy(entry['notices'])
            for captured in entry['views']:
                try:
                    cards.append(book.capture(captured['view'], alias=captured['alias'],
                        **self.operator._capture_parts(captured['capture'])))
                except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
                    notices.append({'object': captured['view']['object'], 'detail': str(error)[:2000]})
            body = book.prepare_outcome(reply, label='Session')['body']
            body += '\nOperator interpretation: ' + town_cards.canonical(basis)
            if membership['status'] != 'not-requested':
                body += '\nShared membership: ' + membership['status'] + '. Session creation is recorded separately.'
                if 'message' in membership:
                    body += '\n' + '\n'.join('| ' + line for line in membership['message'].splitlines())
            if cards:
                body += '\n\n' + '\n\n'.join(card['body'] for card in cards)
            if notices:
                body += '\nSome current views are unavailable; ask the operator to inspect the retained result.'
            response = {'format': 'delvetalk-town-summon-response-v1', 'status': reply['kind'],
                'source': source, 'replyTo': {'uri': uri, 'cid': cid}, 'reply': reply,
                'request': prepared['request'], 'interpretation': entry['interpretation'],
                'cards': cards, 'notices': notices, 'membership': membership, 'body': body, 'textSha256': town_cards.sha(body),
                'publication': 'paused'}
            if membership['status'] != 'uncertain':
                entry['response'] = response
                clerk.save(path, entry)
            return response
