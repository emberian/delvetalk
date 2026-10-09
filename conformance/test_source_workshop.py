"""A fresh workshop creates source objects and Candidates through authenticated cards."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import compiler_queue
import desk
import source_object
import town
import town_cards
import workshop

A, B, ISSUER = ('did:plc:' + letter * 24 for letter in 'abc')


class PublicRecords:
    def __init__(self):
        self.records = {}

    def __call__(self, method, base, nsid, *, params):
        assert method == 'GET' and base == clerk.PDS
        author = params['repo']
        if nsid.endswith('describeRepo'):
            return {'did': author, 'didDoc': {'id': author, 'service': [{
                'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': clerk.PDS}]}}
        uri = f'at://{author}/{params["collection"]}/{params["rkey"]}'
        cid, record = self.records[uri]
        return {'uri': uri, 'cid': cid, 'value': deepcopy(record)}


class SourceWorkshop(unittest.TestCase):
    def test_fresh_source_factories_cards_current_authority_and_exact_retry(self):
        with tempfile.TemporaryDirectory(prefix='source-workshop-') as temporary:
            base = Path(temporary)
            home = base / 'world'
            seed = workshop.initialize(home, builders=(A, B), compiler='compiler',
                steward='steward', world_id='urn:test:source-workshop')
            client = desk.Desk(home / 'world.json', home / 'artifacts')
            records = PublicRecords()
            receiver = clerk.Clerk(base / 'clerk', records)
            receiver.attach(home, desk.world.snapshot(client.database)['objects'], [A, B],
                expected_genesis=seed['genesis'], expected_seed_head=seed['head'], runtime_profile='compiled')
            book = town_cards.CardBook.create(base / 'cards', issuer_did=ISSUER,
                world_id=seed['worldId'], runtime=desk.history.runtime('compiled'))
            receiver.upgrade(receiver.profile()['sha256'], town_cards={
                'path': str(book.path.resolve()), 'issuers': [ISSUER], 'metadata': book.metadata()})
            operator = town.Town(receiver.state, request=records)
            sequence = 0

            def reply(object_id, fields, author=A):
                nonlocal sequence
                sequence += 1
                card = operator.capture(object_id, alias='work-' + str(sequence))
                self.assertIn('sourcePackages', card['view']['root']['protocol'])
                publication = {'uri': f'at://{ISSUER}/{clerk.FEED}/card-{sequence}', 'cid': 'card-' + str(sequence)}
                records.records[publication['uri']] = (publication['cid'], {'$type': clerk.FEED, 'text': card['body']})
                operator.bind(card['alias'], publication['uri'], publication['cid'])
                action = next(item for item in card['card']['actions'] if item.get('available') and not item.get('inspectOnly'))
                text = town_cards.spell(card['alias'], action, fields,
                    selector=town_cards.action_word(action, card['card']['actions']))
                source = (f'at://{author}/{clerk.FEED}/reply-{sequence}', 'reply-' + str(sequence))
                records.records[source[0]] = (source[1], {'$type': clerk.FEED, 'text': text,
                    'reply': {'root': publication, 'parent': publication}})
                result = operator.receive(*source)
                self.assertEqual(result['receipt']['reply']['kind'], 'committed', result)
                self.assertEqual(operator.receive(*source), result)
                return result

            reply('factory:objects', {'name': 'lantern'})
            child = 'factory:objects/lantern'
            before = client.inspect(child)
            self.assertEqual(before['law'], [A, B])
            reply(child, {'text': 'A light for visitors.'}, author=B)
            self.assertEqual(source_object.plain(client.inspect(child)['state']['model'])['text'], 'A light for visitors.')
            reply('factory:desks', {'name': 'variation'})
            candidate = 'factory:desks/variation'
            candidate_root = client.inspect(candidate)
            self.assertTrue(desk.is_source_desk_protocol(candidate_root['protocol']))
            self.assertEqual(desk.candidate_state(candidate_root)['status'], 'empty')
            self.assertEqual(candidate_root['law']['invoke']['compiled'], ['compiler'])
            self.assertEqual(candidate_root['law']['invoke']['adopt'], [A])
            reply('factory:writing', {'name': 'lantern', 'candidate': candidate,
                'target': child, 'syntax': 'protocol-json@1'})
            writer = 'factory:writing/lantern'
            # The source Writing participant owns preservation of the captured
            # target state. This fixture submits the exact retained source program.
            scenarios = [{'name': 'write', 'law': [A], 'steps': [
                {'principal': A, 'command': 'write', 'input': {'text': 'A tested variation.'},
                 'root': 'initial', 'kind': 'committed'}]}]
            reply(writer, {'source': desk.canonical(before['protocol']).decode(),
                'scenarios': desk.canonical(scenarios).decode()})
            pending = client.inspect(candidate)
            self.assertEqual(desk.candidate_state(pending)['migration'], client.inspect(child)['state'])
            denied = client.check(candidate, B, 'not-the-compiler', pending)
            self.assertEqual(denied['kind'], 'refused', denied)
            self.assertEqual(client.inspect(candidate), pending)
            queue = compiler_queue.CompilerQueue(base / 'compiler', client.database, client.artifact_store)
            job = queue.enqueue(candidate, 'compiler', 'compile-variation', pending)['job']
            self.assertEqual(queue.run()['errors'], [])
            completed = queue.inspect(job)['receipt']
            self.assertEqual(completed['kind'], 'committed', completed)
            ready = client.inspect(candidate)
            self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
            expected_target = client.inspect(child)
            denied = client.adopt(candidate, child, B, 'not-the-reviewer', ready, expected_target)
            self.assertEqual(denied['kind'], 'refused', denied)
            self.assertEqual(client.inspect(candidate), ready)
            adopted = client.adopt(candidate, child, A, 'adopt-variation', ready, expected_target)
            self.assertEqual(adopted['kind'], 'committed', adopted)
            self.assertEqual(client.adopt(candidate, child, A, 'adopt-variation', ready, expected_target), adopted)
            self.assertEqual(client.inspect(child)['state'], expected_target['state'])


if __name__ == '__main__':
    unittest.main()
