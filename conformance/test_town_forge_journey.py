"""Literal text spells, actual Bend execution, and explicit posts-only adoption."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import compiler_queue
import desk
import town
import town_cards
import workspace

forge = clerk.module('town_forge_journey_protocol', 'protocols/town-forge/generate.py')
MAKER = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
VISITOR = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'
ISSUER = 'did:plc:cccccccccccccccccccccccc'
COMPILER = 'forge-compiler'
PAPER_RESULT = 'The paper door swings open onto a tiny lantern-lit room.'
MOON_RESULT = 'The silver door opens into a room full of small moons.'


class PublicRecords:
    """The only simulated service: public GETs of explicitly supplied records."""
    def __init__(self):
        self.records = {}
        self.calls = []

    def __call__(self, method, base, nsid, *, params):
        assert method == 'GET' and base == clerk.PDS
        self.calls.append((method, nsid, copy.deepcopy(params)))
        author = params['repo']
        if nsid.endswith('describeRepo'):
            return {'did': author, 'didDoc': {'id': author, 'service': [{
                'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer',
                'serviceEndpoint': clerk.PDS}]}}
        uri = f'at://{author}/{params["collection"]}/{params["rkey"]}'
        cid, value = self.records[uri]
        return {'uri': uri, 'cid': cid, 'value': copy.deepcopy(value)}


class TownForgeJourneyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='town-forge-journey-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'world'
        factories = forge.build([VISITOR], COMPILER)
        seed = workspace.initialize(self.home, [
            {'id': key, 'syntax': 'protocol-json@1',
             'source': clerk.canonical(protocol), 'law': forge.factory_law([MAKER])}
            for key, protocol in factories.items()],
            entry_objects=['objects', 'desks', 'writers'], principal=MAKER, profile='compiled',
            title='The visitor and the spell maker', world_id='urn:test:town-forge-journey')
        self.pds = PublicRecords()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        roots = clerk.loads((self.home / 'world.json').read_bytes())['objects']
        self.clerk.attach(self.home, roots, [MAKER, VISITOR],
                          expected_genesis=seed['genesis'], expected_seed_head=seed['head'],
                          runtime_profile='compiled')
        self.book = town_cards.CardBook.create(self.base / 'cards', issuer_did=ISSUER,
            world_id='urn:test:town-forge-journey', runtime=workspace.bootstrap.history.runtime('compiled'))
        self.clerk.upgrade(self.clerk.profile()['sha256'], town_cards={
            'path': str(self.book.path.resolve()), 'issuers': [ISSUER], 'metadata': self.book.metadata()})
        self.operator = town.Town(self.clerk.state, request=self.pds)
        self.queue = compiler_queue.CompilerQueue(self.base / 'compiler', self.clerk.database,
                                                  self.home / 'artifacts', profile='compiled')
        self.sequence = 0
        self.assertEqual(self.clerk.database, (self.home / 'world.json').resolve())
        self.assertFalse((self.clerk.state / 'world.json').exists())

    def root(self, object_id):
        try:
            return self.clerk.snapshot(object_id)['root']
        except ValueError as error:
            if 'pins changed' not in str(error):
                raise
            retained = self.clerk.config()['profile']['pins']
            current = clerk.pins('compiled')
            changed = sorted(path for path in retained.keys() | current.keys()
                             if retained.get(path) != current.get(path))
            raise ValueError(f'{error}: {changed}') from error

    def candidate_state(self, object_id):
        return desk.candidate_state(self.root(object_id))

    def publish(self, cards, body=None):
        self.sequence += 1
        publication = {'uri': f'at://{ISSUER}/{clerk.FEED}/card-{self.sequence}',
                       'cid': f'card-cid-{self.sequence}'}
        self.pds.records[publication['uri']] = (publication['cid'], {
            '$type': clerk.FEED, 'text': body or '\n\n'.join(card['body'] for card in cards)})
        for card in cards:
            self.operator.bind(card['alias'], publication['uri'], publication['cid'])
        return publication

    def post(self, card, fields, *, author=MAKER, parent=None, action=None):
        parent = parent or self.publish([card])
        self.sequence += 1
        source = (f'at://{author}/{clerk.FEED}/reply-{self.sequence}', f'reply-cid-{self.sequence}')
        if card['format'] == 'delvetalk-town-adoption-card-v1':
            self.assertEqual(fields, {})
            text = 'delvetalk ' + card['alias'] + ' adopt'
        else:
            actions = card['card']['actions']
            selected = next(item for item in actions
                            if (action is None or item['id'] == action)
                            and item.get('available') and not item.get('inspectOnly'))
            selector = town_cards.action_word(selected, actions)
            self.assertEqual(selector, selected['command'], 'the offered method is the human selector')
            text = town_cards.spell(card['alias'], selected, fields, selector=selector)
        self.assertEqual(town_cards.parse_reply(text)['syntax'], 'delvetalk-town-spell-v1')
        self.pds.records[source[0]] = (source[1], {'$type': clerk.FEED, 'text': text,
                                               'reply': {'root': parent, 'parent': parent}})
        return source

    def capture(self, object_id):
        self.sequence += 1
        return self.operator.capture(object_id, alias='view-' + str(self.sequence))

    def reply(self, card, fields, **kwargs):
        source = self.post(card, fields, **kwargs)
        response = self.operator.receive(*source)
        self.assertEqual(response['receipt']['source']['uri'], source[0])
        return source, response

    def committed(self, response):
        self.assertEqual(response['receipt']['reply']['kind'], 'committed', response)

    def make(self, factory, name, *, author=MAKER, **fields):
        _, response = self.reply(self.capture(factory), {'name': name, **fields}, author=author)
        self.committed(response)
        identity = factory + '/' + name
        self.assertIn(identity, self.clerk.config()['objects'])
        return identity, next(card for card in response['cards'] if card['card']['object'] == identity)

    def submit(self, candidate, card, target, source_text, examples_text, *, syntax=None, author=MAKER):
        self.assertTrue(source_text.startswith('edition ObjectiveBend 1\n'))
        self.assertTrue(examples_text.startswith('examples DelveTalk 1\n'))
        self.assertEqual(card['card']['object'], candidate)
        syntax = syntax or forge.SPELL_SYNTAX
        _, writing = self.make('writers', candidate.rsplit('/', 1)[-1] + '-writing',
                               author=author, candidate=candidate, target=target, syntax=syntax)
        captured_state = self.root(target)['state']
        fields = {'source': source_text, 'scenarios': examples_text}
        source, response = self.reply(writing, fields, author=author)
        post_text = self.pds.records[source[0]][1]['text']
        self.assertIn('source: <<', post_text)
        self.assertIn('scenarios: <<', post_text)
        self.committed(response)
        self.assertEqual(response['receipt']['request']['op'], 'transaction')
        state = self.candidate_state(candidate)
        self.assertEqual(state['status'], 'pending')
        self.assertEqual(state['proposal']['syntax'], syntax)
        self.assertEqual(state['proposal']['source'], fields['source'])
        self.assertEqual(state['proposal']['scenarios'], fields['scenarios'])
        self.assertEqual(state['migration'], captured_state)
        self.assertEqual(state['target'], target)
        return source

    def check(self, candidate, source):
        import town_authoring
        submission_reply = self.operator.receive(*source)
        job = self.queue.enqueue(candidate, COMPILER, 'check:' + source[0], self.root(candidate))
        report = self.queue.run(deadline_seconds=60)
        self.assertEqual(report['errors'], [], report)
        self.assertEqual(report['blocked'], [], report)
        self.assertEqual(self.queue.inspect(job['job'])['phase'], 'finished')
        followups = town_authoring.TownAuthoring(self.operator, self.queue)
        result = followups.prepare(*source, job['job'])
        self.assertEqual(result['source'], {'uri': source[0], 'cid': source[1]})
        self.assertEqual(result['publication'], 'paused')
        self.assertEqual(followups.prepare(*source, job['job']), result)
        self.assertEqual(self.operator.receive(*source), submission_reply,
                         'the compiler follow-up must not rewrite the original submission reply')
        return result

    def test_maker_checks_installs_and_revises_a_door_visitors_can_use(self):
        target, chalk_card = self.make('objects', 'lantern')
        candidate, desk_card = self.make('desks', 'first-spell')
        chalk = self.root(target)
        source = self.submit(candidate, desk_card, target, forge.spell_source(1), forge.example_source(1))
        ready = self.check(candidate, source)
        self.assertEqual(ready['status'], 'ready', ready)
        self.assertEqual(len(ready['fixtures']), 5)
        self.assertEqual(ready['fixtures'][0]['observe'], 'main')
        self.assertEqual(ready['fixtures'][0]['observed']['view']['title'], 'The paper door')
        self.assertTrue(all(not fixture['failures'] for fixture in ready['fixtures']))
        self.assertIn('expected', ready['body'])
        self.assertIn('observed', ready['body'])
        self.assertIn('not installed', ready['body'])
        self.assertEqual(self.root(target), chalk, 'checking examples must not install the spell')
        self.assertEqual(len(ready['cards']), 1)

        # A visitor acts while the maker is reviewing. The old adoption must
        # refuse atomically, including the desk's lastRelease write.
        adoption = ready['cards'][0]
        parent = self.publish([adoption], ready['body'])
        _, chalk_reply = self.reply(chalk_card, {'word': 'hello'}, author=VISITOR)
        self.committed(chalk_reply)
        before_candidate, before_target = self.root(candidate), self.root(target)
        _, stale = self.reply(adoption, {}, parent=parent)
        self.assertEqual(stale['receipt']['reply']['kind'], 'refused')
        self.assertEqual(stale['receipt']['reply']['data'], 'stale read root')
        self.assertEqual(self.root(candidate), before_candidate)
        self.assertEqual(self.root(target), before_target)
        fresh = self.book.capture_adoption(candidate, before_candidate, target, before_target,
                                           alias='review-current-door')
        _, installed = self.reply(fresh, {})
        self.committed(installed)
        self.assertEqual(self.root(target)['protocol'], desk.candidate_state(before_candidate)['protocol'])
        paper_protocol = self.root(target)['protocol']
        self.assertEqual(paper_protocol['commands']['knock']['result'][0], 'package')
        self.assertEqual(paper_protocol['commands']['knock']['result'][1]['modules'][0]['source'],
                         forge.spell_source(1))
        self.assertEqual(self.candidate_state(candidate)['lastRelease'], MAKER)
        paper_card = self.capture(target)
        self.assertIn('The paper door', paper_card['body'])
        self.assertIn('please', paper_card['body'])

        # Fault injection is only after actual Lean admission, at response-file
        # custody. Recovery must return the same visitor turn, without GETs or
        # repeating the knock against the now advanced root.
        lost_source = self.post(paper_card, {'word': 'please'}, author=VISITOR)
        save = town.save
        def lose_response(path, value):
            if 'response' in value:
                raise OSError('injected lost presentation save after admission')
            return save(path, value)
        with patch.object(town, 'save', side_effect=lose_response), self.assertRaises(OSError):
            self.operator.receive(*lost_source)
        committed_bytes = self.clerk.database.read_bytes()
        records, calls = self.pds.records, len(self.pds.calls)
        self.pds.records = {}
        self.operator = town.Town(self.clerk.state, request=self.pds)
        recovered = self.operator.receive(*lost_source)
        self.committed(recovered)
        self.assertEqual(recovered['receipt']['reply']['data']['result'], PAPER_RESULT)
        self.assertIn(PAPER_RESULT, recovered['body'])
        self.assertEqual(self.clerk.database.read_bytes(), committed_bytes)
        self.assertEqual(len(self.pds.calls), calls)
        self.assertEqual(self.operator.receive(*lost_source), recovered)
        with self.assertRaisesRegex(ValueError, 'different CID'):
            self.operator.receive(lost_source[0], 'edited-source')
        self.pds.records = records

        # A visitor's counterexample is checked against literal source in its
        # own desk. A failed example changes neither the live door nor its law.
        challenge_desk, challenge_card = self.make('desks', 'moon-challenge')
        before_challenge = self.root(target)
        challenge_source = self.submit(challenge_desk, challenge_card, target,
                                       forge.spell_source(1), forge.challenge_source())
        failed = self.check(challenge_desk, challenge_source)
        self.assertEqual(failed['status'], 'failed', failed)
        self.assertEqual(failed['cards'], [])
        self.assertEqual(len(failed['fixtures']), 1)
        self.assertTrue(failed['fixtures'][0]['failures'])
        self.assertIn('precondition failed', town_cards.canonical(failed['fixtures'][0]['observed']))
        self.assertIn('precondition failed', failed['body'])
        self.assertEqual(self.root(target), before_challenge)

        revision, revision_card = self.make('desks', 'moon-revision')
        revision_source = self.submit(revision, revision_card, target, forge.spell_source(2),
                                      forge.example_source(2))
        second_ready = self.check(revision, revision_source)
        self.assertEqual(second_ready['status'], 'ready', second_ready)
        self.assertEqual(len(second_ready['fixtures']), 6)
        self.assertEqual(second_ready['fixtures'][0]['observe'], 'main')
        self.assertEqual(second_ready['fixtures'][0]['observed']['view']['title'], 'The moon door')
        self.assertTrue(all(not fixture['failures'] for fixture in second_ready['fixtures']))
        self.assertEqual(self.root(target), before_challenge)
        _, revised = self.reply(second_ready['cards'][0], {})
        self.committed(revised)
        moon_card = self.capture(target)
        self.assertIn('The moon door', moon_card['body'])
        self.assertIn('Whisper moon', moon_card['body'])
        moon_parent = self.publish([moon_card])
        _, old_word = self.reply(moon_card, {'word': 'please'}, author=VISITOR, parent=moon_parent)
        self.assertEqual(old_word['receipt']['reply']['kind'], 'refused')
        self.assertEqual(old_word['receipt']['reply']['data'], 'precondition failed')
        _, moon_reply = self.reply(moon_card, {'word': 'moon'}, author=VISITOR, parent=moon_parent)
        self.committed(moon_reply)
        self.assertEqual(moon_reply['receipt']['reply']['data']['result'], MOON_RESULT)
        self.assertIn(MOON_RESULT, moon_reply['body'])
        moon_protocol = self.root(target)['protocol']
        self.assertEqual(moon_protocol, self.candidate_state(revision)['protocol'])
        self.assertEqual(moon_protocol['commands']['knock']['result'][0], 'package')
        self.assertEqual(moon_protocol['commands']['knock']['result'][1]['modules'][0]['source'],
                         forge.spell_source(2))


if __name__ == '__main__':
    unittest.main()
