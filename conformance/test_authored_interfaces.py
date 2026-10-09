#!/usr/bin/env python3
"""Authored examples become town spells over real source-host garden turns.

Publication records are local fixtures, not PDS authentication evidence. Source
evaluation, action construction, card binding and durable admission are real.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import town_cards as town
import world

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


room = module('authored_interface_room', 'scene/room.py')
bundle = module('authored_interface_bundle', 'syntaxes/source_bundle.py')
GARDEN = ROOT / 'protocols/town-garden'
ISSUER, MOSS, IRIS = ['did:plc:' + c * 24 for c in 'abc']


class AuthoredInterfaces(unittest.TestCase):
    def test_source_examples_cards_contributions_and_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            database = base / 'world.json'
            runtime = history.runtime('compiled')
            protocol = bundle.load(GARDEN / 'binding.json', [('Garden', GARDEN / 'Garden.obend')])
            self.assertEqual(protocol, json.loads((GARDEN / 'protocol.json').read_bytes()))
            call = lambda request: world.exchange(database, request, profile='compiled')
            inspect = lambda: call({'op': 'inspect', 'object': 'garden', 'principal': MOSS})
            law = {'profile': 'delvetalk-scoped-law-v1',
                   'invoke': {'plant': [MOSS, IRIS], 'rain': [MOSS, IRIS]}, 'reprogram': [], 'law': []}
            created = call({'op': 'create', 'object': 'garden', 'principal': 'operator',
                            'intent': 'seed-world', 'protocol': protocol, 'law': law})
            self.assertEqual(created['kind'], 'committed', created)
            book = town.CardBook.create(base / 'cards', issuer_did=ISSUER,
                world_id='urn:test:authored-interfaces', runtime=runtime,
                display_names={MOSS: '@moss', IRIS: '@iris'})
            records = {}

            def fetch(uri, cid):
                recorded_cid, value = records[uri]
                self.assertEqual(cid, recorded_cid)
                return copy.deepcopy(value)

            def capture(alias):
                view = room.inspect_object(inspect(), 'garden', expected_runtime=runtime)
                self.assertEqual(view['mode'], 'projection', view.get('reason'))
                card = book.capture(view, alias)
                publication = {'uri': f'at://{ISSUER}/{town.FEED}/{alias}', 'cid': 'cid-' + alias}
                records[publication['uri']] = (publication['cid'], {'$type': town.FEED, 'text': card['body']})
                book.bind(alias, publication, fetch)
                return card, publication

            def attempt(card, publication, actor, key):
                action, = card['card']['actions']
                values = {field['name']: field['example'] for field in action['fields']}
                text = town.spell(card['alias'], action, values,
                                  selector=town.action_word(action, card['card']['actions']))
                self.assertIn(text, card['body'])
                parsed = town.parse_reply(text)
                self.assertEqual(parsed['syntax'], 'delvetalk-town-spell-v1')
                record = {'$type': town.FEED, 'text': text,
                          'reply': {'root': publication, 'parent': publication}}
                source = {'uri': f'at://{actor}/{town.FEED}/{key}', 'cid': 'cid-' + key,
                          'author': actor, 'pds': 'https://pds.delve.town'}
                wire, evidence = book.resolve(record, actor, source, fetch, [ISSUER])
                self.assertEqual(evidence['parsed']['fields'], values)
                self.assertEqual(wire['input'], values)
                self.assertNotIn('principal', wire)
                return {**wire, 'principal': actor, 'intent': 'delve:' + source['uri']}

            opening, publication = capture('garden-open')
            self.assertIn('A bell for lost moths', opening['body'])
            self.assertNotIn('"Planted by":', opening['body'])  # no blank panels
            plant = attempt(opening, publication, MOSS, 'plant')
            planted = call(plant)
            self.assertEqual(planted['kind'], 'committed', planted)
            waiting, publication = capture('garden-rain')
            self.assertEqual([a['command'] for a in waiting['card']['actions']], ['rain'])
            self.assertIn('@moss', waiting['body'])
            rain = attempt(waiting, publication, IRIS, 'rain')
            same_voice = {**rain, 'principal': MOSS, 'intent': 'same-voice'}
            refusal = call(same_voice)
            self.assertEqual(refusal['kind'], 'refused', refusal)
            self.assertIn('different participant', refusal['data'])
            self.assertEqual(inspect(), planted['data']['root'])
            rained = call(rain)
            self.assertEqual(rained['kind'], 'committed', rained)
            blooming, _ = capture('garden-bloom')
            panels = {p['id']: p['view']['data']['prose'] for p in blooming['panels']}
            self.assertEqual(panels['seed'], plant['input']['seed'])
            self.assertEqual(panels['rain'], rain['input']['line'])
            self.assertEqual(panels['planter'], MOSS)
            self.assertEqual(panels['rainmaker'], IRIS)
            self.assertIn('AMBER', panels['image'])
            self.assertIn('@moss', blooming['body'])
            self.assertIn('@iris', blooming['body'])
            self.assertEqual([a['command'] for a in blooming['card']['actions']], ['plant'])
            current = inspect()
            self.assertEqual(current['protocol']['viewProgram']['package']['modules'],
                             [{'name': 'Garden', 'source': (GARDEN / 'Garden.obend').read_text()}])
            self.assertEqual(current['protocol']['commands']['plant']['transition']['package']['entry'], 'plantTurn')
            # Every exchange starts a new native host: retained identity recovers
            # its old answer, while the same words as a new attempt are stale.
            book = town.CardBook(base / 'cards')
            self.assertEqual(book.card('garden-open'), opening)
            self.assertEqual(call(plant), planted)
            self.assertEqual(call(rain), rained)
            stale = call({**plant, 'intent': 'new-attempt-from-old-card'})
            self.assertEqual(stale['kind'], 'refused', stale)
            self.assertEqual(stale['data'], 'stale read root')
            self.assertEqual(inspect(), current)
            self.assertEqual(book.card('garden-open')['view']['root'], plant['expected'])


if __name__ == '__main__':
    unittest.main()
