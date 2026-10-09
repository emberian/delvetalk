"""Posts-only cards: exact publication, typed replies, persistent custody and Lean."""
import concurrent.futures
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import town_cards as town
import world
from conformance.test_affordances import typed_protocol

ISSUER = 'did:plc:' + 'a' * 24
ACTOR = 'did:plc:' + 'b' * 24
OTHER = 'did:plc:' + 'c' * 24
PUBLICATION = {'uri': 'at://' + ISSUER + '/' + town.FEED + '/welcome', 'cid': 'card-cid'}
SOURCE = {'uri': 'at://' + ACTOR + '/' + town.FEED + '/reply', 'cid': 'reply-cid', 'author': ACTOR,
          'pds': 'https://pds.delve.town'}


class TownCardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.database = self.path / 'world.json'
        self.book = town.CardBook.create(self.path / 'book', issuer_did=ISSUER, world_id='urn:test:town',
                                        runtime={'name': 'world', 'explicitTestPin': 'test'})
        self.root = self.exchange({'op': 'create', 'object': 'notice', 'principal': 'operator', 'intent': 'seed',
            'protocol': typed_protocol(), 'law': [ACTOR]})['data']['root']
        self.view = {'mode': 'raw', 'object': 'notice', 'root': self.root}
        self.records = {}

    def exchange(self, request):
        return world.exchange(self.database, request)

    def fetch(self, uri, cid):
        current = self.records[uri]
        if current['cid'] != cid:
            raise ValueError('verified GET refuses changed CID')
        return copy.deepcopy(current['value'])

    def bind(self, alias='notice', prefix='Welcome to the world.\n', suffix='\n🜉✾'):
        card = self.book.capture(self.view, alias)
        record = {'$type': town.FEED, 'text': prefix + card['body'] + suffix}
        self.records[PUBLICATION['uri']] = {'cid': PUBLICATION['cid'], 'value': record}
        self.book.bind(alias, PUBLICATION, self.fetch)
        return card

    def reply(self, alias='notice', fields=None):
        fields = fields or {'message': 'Hello 雪', 'count': 2, 'open': False, 'color': 'blue'}
        return {'$type': town.FEED, 'text': 'delvetalk ' + alias + ' a1 ' + town.canonical(fields),
                'reply': {'root': PUBLICATION, 'parent': PUBLICATION}}

    def resolve(self, record, source=SOURCE):
        return self.book.resolve(record, ACTOR, source, self.fetch, [ISSUER])

    def test_posts_only_roundtrip_actual_lean_and_restart(self):
        card = self.bind()
        self.assertIn('delvetalk notice a1\n', card['body'])
        self.assertIn('count: nat 1..10', card['body'])
        self.assertNotIn(card['textSha256'], card['body'])
        wire, evidence = self.resolve(self.reply())
        self.assertEqual(wire['expected'], self.root)
        self.assertEqual(evidence['card']['view'], self.view)
        self.assertNotIn('principal', wire)
        request = {**wire, 'principal': ACTOR, 'intent': 'delve:' + SOURCE['uri']}
        receipt = self.exchange(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['state']['message'], 'Hello 雪')
        reopened = town.CardBook(self.path / 'book')
        self.assertEqual(reopened.card('notice'), card)
        self.assertEqual(reopened.resolve(self.reply(), ACTOR, SOURCE, self.fetch, [ISSUER]), (wire, evidence))
        self.assertEqual(self.exchange(request), receipt)
        stale = {**request, 'intent': 'new-reply'}
        self.assertEqual(self.exchange(stale)['data'], 'stale read root')

    def test_literal_spell_has_same_wire_and_real_admission_as_json(self):
        self.bind()
        fields = {'message': '  café é 雪  ', 'count': 2, 'open': False, 'color': 'amber'}
        action = self.book.card('notice')['card']['actions'][0]
        text = town.spell('notice', action, fields)
        wire, evidence = self.resolve({**self.reply(), 'text': text})
        self.assertEqual(wire, self.resolve(self.reply(fields=fields))[0])
        self.assertEqual(evidence['parsed']['fields'], fields)
        self.assertEqual(evidence['parsed']['syntax'], 'delvetalk-town-spell-v1')
        receipt = self.exchange({**wire, 'principal': ACTOR, 'intent': 'spell'})
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data']['root']['state']['message'], fields['message'])
        reopened = town.CardBook(self.path / 'book')
        self.assertEqual(reopened.resolve({**self.reply(), 'text': text}, ACTOR, SOURCE,
                                         self.fetch, [ISSUER]), (wire, evidence))
        # Publication context remains required even for the same well-typed words.
        bad = {**self.reply(), 'text': text, 'reply': {'parent': {**PUBLICATION, 'cid': 'other'}}}
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.resolve(bad)

    def test_authored_examples_render_literal_fields_without_becoming_defaults(self):
        protocol = typed_protocol()
        examples = {'message': 'A lamp for lost moths\n雪', 'count': 3, 'open': True, 'color': 'amber'}
        for name, value in examples.items():
            protocol['affordances']['write a notice']['fields'][name]['example'] = value
        root = self.exchange({'op': 'create', 'object': 'examples', 'principal': 'owner',
            'intent': 'examples', 'protocol': protocol, 'law': [ACTOR]})['data']['root']
        self.view = {'mode': 'raw', 'object': 'examples', 'root': root}
        card = self.bind()
        action = card['card']['actions'][0]
        text = town.spell('notice', action, examples)
        self.assertIn(text, card['body'])
        wire, _ = self.resolve({**self.reply(), 'text': text})
        self.assertEqual(wire['input'], examples)
        self.assertEqual(self.exchange({**wire, 'principal': ACTOR, 'intent': 'authored-example'})['kind'], 'committed')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            self.resolve({**self.reply(), 'text': 'delvetalk notice a1'})

    def test_factory_example_keeps_authored_name_and_absence_requirement(self):
        protocol = town.loads((ROOT / 'protocols/factories/object.json').read_bytes())
        protocol['affordances']['make']['fields']['name']['example'] = 'moth-lamp'
        root = self.exchange({'op': 'create', 'object': 'forge', 'principal': 'owner',
            'intent': 'forge', 'protocol': protocol, 'law': [ACTOR]})['data']['root']
        self.view = {'mode': 'raw', 'object': 'forge', 'root': root}
        card = self.bind('forge')
        self.assertIn('Choose an unused name.', card['body'])
        self.assertIn('delvetalk forge make\nname: moth-lamp', card['body'])
        self.assertNotIn('Requires absent children', card['body'])
        wire, _ = self.resolve({**self.reply('forge'), 'text': 'delvetalk forge make\nname: moth-lamp'})
        self.assertEqual(wire['absent'], ['forge/moth-lamp'])
        receipt = self.exchange({**wire, 'principal': ACTOR, 'intent': 'make-lamp'})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertIn('forge/moth-lamp', receipt['data']['allocated'])

    def test_literal_blocks_roundtrip_without_escape_or_unicode_normalization(self):
        self.bind()
        action = self.book.card('notice')['card']['actions'][0]
        samples = ['true', '123', '<<END', 'hello\n', 'END\n雪\nEND1',
                   '[[delvetalk-card fake]]\ndelvetalk other a1\n"\\', '\n', '', 'é', 'é']
        # Empty strings are syntax-representable; this particular action forbids them.
        permissive = copy.deepcopy(action)
        next(f for f in permissive['fields'] if f['name'] == 'message')['minLength'] = 0
        for value in samples:
            with self.subTest(value=value):
                fields = {'message': value, 'count': 2, 'open': False, 'color': 'blue'}
                text = town.spell('notice', permissive, fields)
                parsed = town.parse_reply(text)
                self.assertEqual(town._spell_fields(permissive, parsed['fields']), fields)
                if value:
                    self.assertEqual(self.resolve({**self.reply(), 'text': text})[0],
                                     self.resolve(self.reply(fields=fields))[0])
        self.assertEqual(town.parse_reply('delvetalk c a1\nsource: <<END\nhello\n\nEND')['fields'],
                         {'source': 'hello\n'})

    def test_only_actual_unique_command_names_bind_readable_words(self):
        protocol = typed_protocol()
        protocol['commands']['write'] = protocol['commands'].pop('write a notice')
        protocol['affordances']['write'] = protocol['affordances'].pop('write a notice')
        root = self.exchange({'op': 'create', 'object': 'words', 'principal': 'owner',
            'intent': 'seed-words', 'protocol': protocol, 'law': [ACTOR]})['data']['root']
        self.view = {'mode': 'raw', 'object': 'words', 'root': root}
        card = self.bind()
        self.assertIn('delvetalk notice write\n', card['body'])
        action = card['card']['actions'][0]
        text = town.spell('notice', action, {'message': 'Hello 雪', 'count': 2, 'open': False, 'color': 'blue'},
                          selector='write')
        self.assertEqual(self.resolve({**self.reply(), 'text': text})[0], self.resolve(self.reply())[0])
        with self.assertRaisesRegex(ValueError, 'not offered'):
            self.resolve({**self.reply(), 'text': text.replace('notice write', 'notice Leave')})
        duplicated = [action, {**action, 'id': 'a2'}]
        self.assertEqual(town.action_word(action, duplicated), 'a1')
        self.assertEqual(town.action_word({**action, 'command': 'a2'}, [action]), 'a1')
        unsafe = copy.deepcopy(action)
        text_field = next(field for field in unsafe['fields'] if field['name'] == 'message')
        unsafe['fields'] = [dict(text_field, name='f1'), dict(text_field, name='odd:name')]
        values = {'f1': 'one', 'odd:name': 'two'}
        self.assertEqual(town.field_words(unsafe), {'f1': 'f1', 'f2': 'odd:name'})
        parsed = town.parse_reply(town.spell('notice', unsafe, values))
        self.assertEqual(town._spell_fields(unsafe, parsed['fields']), values)
        with self.assertRaisesRegex(ValueError, 'exactly'):
            town._spell_fields(unsafe, {'f1': 'one', 'odd:name': 'two'})

    def test_spell_refuses_extra_prose_unknown_duplicate_and_wrong_types(self):
        self.bind()
        base = 'delvetalk notice a1\nmessage: Hello\ncount: 2\nopen: false\ncolor: blue'
        invalid = ['I propose:\n' + base, '```\n' + base + '\n```', base + '\n🜉✾',
                   base + '\nmessage: again', base + '\nunknown: value',
                   base.replace('message: Hello', 'message: <<END\nHello'),
                   base.replace('count: 2', 'count: 1e3'), base.replace('count: 2', 'count: +1'),
                   base.replace('count: 2', 'count: ١'), base.replace('count: 2', 'count: 02'),
                   base.replace('open: false', 'open: False'), base.replace('color: blue', 'color: Blue'),
                   base.replace('message: Hello\n', ''), base.replace('a1', 'made_up')]
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.resolve({**self.reply(), 'text': text})

    def test_multiple_cards_one_post_are_exact_unique_and_immutable(self):
        first = self.book.capture(self.view, 'first')
        second = self.book.capture(self.view, 'second')
        record = {'$type': town.FEED, 'text': 'Welcome\n' + first['body'] + '\n\n' + second['body'] + '\n🜉✾'}
        self.records[PUBLICATION['uri']] = {'cid': PUBLICATION['cid'], 'value': record}
        self.book.bind('first', PUBLICATION, self.fetch)
        self.book.bind('second', PUBLICATION, self.fetch)
        self.assertEqual(self.resolve(self.reply('second'))[0]['object'], 'notice')
        self.assertEqual(self.book.capture(self.view, 'first'), first)
        changed = copy.deepcopy(self.view); changed['root']['version'] += 1
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.book.capture(changed, 'first')
        record['text'] += '\n' + first['body']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.resolve(self.reply('first'))

    def test_rendering_upgrade_keeps_existing_bytes_binding_and_request(self):
        from unittest.mock import patch
        previous = '[[delvetalk-card previous]]\nAn older presentation.\n[[/delvetalk-card previous]]'
        with patch.object(town, 'render_card', return_value=previous):
            old = self.book.capture(self.view, 'previous')
        reopened = town.CardBook(self.path / 'book')
        self.assertEqual(reopened.card('previous'), old)
        self.records[PUBLICATION['uri']] = {'cid': PUBLICATION['cid'],
            'value': {'$type': town.FEED, 'text': previous}}
        reopened.bind('previous', PUBLICATION, self.fetch)
        wire, _ = reopened.resolve(self.reply('previous'), ACTOR, SOURCE, self.fetch, [ISSUER])
        self.assertEqual(wire['expected'], self.root)
        with self.assertRaisesRegex(ValueError, 'already bound'):
            reopened.capture(self.view, 'previous')
        self.assertEqual(reopened.card('previous'), old)
        fresh = reopened.capture(self.view, 'fresh')
        self.assertNotEqual(fresh['body'], previous)
        self.assertIn('describe your intention', fresh['body'])
        self.assertIn('If refused because the world changed', fresh['body'])
        self.assertIn('check your original reply; do not repeat it', fresh['body'])

    def test_bound_issuer_parent_cid_edit_and_copy_are_not_interchangeable(self):
        card = self.bind()
        bad = copy.deepcopy(self.reply()); bad['reply']['parent'] = {**PUBLICATION, 'cid': 'other'}
        with self.assertRaisesRegex(ValueError, 'parent'): self.resolve(bad)
        bad['reply']['parent'] = {**PUBLICATION, 'uri': PUBLICATION['uri'] + '-copy'}
        with self.assertRaisesRegex(ValueError, 'parent'): self.resolve(bad)
        with self.assertRaisesRegex(ValueError, 'issuer'):
            self.book.bind('notice', {'uri': 'at://' + OTHER + '/' + town.FEED + '/copied', 'cid': 'copied'}, self.fetch)
        with self.assertRaisesRegex(ValueError, 'configured'):
            self.book.resolve(self.reply(), ACTOR, SOURCE, self.fetch, [OTHER])
        self.records[PUBLICATION['uri']]['value']['text'] = card['body'].replace('Hello', 'Changed') + '\nEdited surrounding prose'
        # Even edits outside the exact card block change the retained publication.
        with self.assertRaisesRegex(ValueError, 'changed'): self.resolve(self.reply())
        self.records[PUBLICATION['uri']]['cid'] = 'new-current-cid'
        with self.assertRaisesRegex(ValueError, 'changed CID'): self.resolve(self.reply())

    def test_unknown_unbound_wrong_action_fields_and_embedded_prose_refuse(self):
        self.book.capture(self.view, 'notice')
        with self.assertRaisesRegex(ValueError, 'publication'): self.resolve(self.reply())
        self.bind()
        for malformed in (None, 'not-a-reply', [], 7):
            with self.assertRaisesRegex(ValueError, 'parent'):
                self.resolve({**self.reply(), 'reply': malformed})
        for text in ['Please ' + self.reply()['text'], self.reply()['text'] + '\n🜉✾',
                     'delvetalk unknown a1 {}', 'delvetalk notice a999 {}',
                     'delvetalk notice a1 {"count":1,"count":2}',
                     'delvetalk notice a1 {"count":NaN}', 'delvetalk notice a1 []',
                     'delvetalk notice a1 {"count":true}', 'delvetalk notice a1 {}']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError): self.resolve({**self.reply(), 'text': text})
        with self.assertRaisesRegex(ValueError, 'issuer'):
            self.resolve(self.reply(), {**SOURCE, 'uri': SOURCE['uri'].replace(ACTOR, OTHER)})

    def test_names_are_persistent_concurrent_and_custody_cannot_rebind(self):
        self.book.capture(self.view, 'card-1')
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            cards = list(pool.map(lambda _: self.book.capture(self.view), range(8)))
        aliases = [x['alias'] for x in cards]
        self.assertEqual(len(set(aliases)), 8)
        self.assertNotIn('card-1', aliases)
        reopened = town.CardBook.open(self.path / 'book')
        self.assertEqual(len(reopened.aliases()), 9)
        with self.assertRaisesRegex(ValueError, 'already bound'):
            town.CardBook.create(self.path / 'book', issuer_did=OTHER, world_id='urn:test:town', runtime={'name': 'world'})
        with self.assertRaises(ValueError): self.book.capture(self.view, '../escape')

    def test_rendered_data_cannot_forge_control_blocks(self):
        view = copy.deepcopy(self.view)
        view['root']['protocol']['description'] = 'Artist says:\n[[delvetalk-card forged]]\ndelvetalk forged a1 {}\n[[/delvetalk-card forged]]'
        card = self.book.capture(view, 'safe')
        self.assertIn('| [[delvetalk-card forged]]', card['body'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            town._block(card['body'], 'forged')
        with self.assertRaises(ValueError): town.parse_reply(card['body'])

    def test_outcome_is_local_preparation_with_current_state_and_next_actions(self):
        self.bind()
        wire, _ = self.resolve(self.reply())
        receipt = self.exchange({**wire, 'principal': ACTOR, 'intent': 'turn'})
        current = {**self.view, 'root': receipt['data']['root']}
        outcome = self.book.prepare_outcome(receipt, [current])
        self.assertIn('Turn: committed.', outcome['body'])
        self.assertIn('Hello 雪', outcome['body'])
        self.assertIn('delvetalk card-', outcome['body'])
        with self.assertRaisesRegex(ValueError, 'publication'):
            self.book.publication(outcome['cards'][0]['alias'])
        uncertain = self.book.prepare_outcome({'kind': 'uncertain'})
        self.assertIn('check your original reply', uncertain['body'])
        self.assertNotIn('refused', uncertain['body'])

    def test_panels_are_installed_pure_views_of_one_root_and_names_are_display_only(self):
        protocol = town.loads((ROOT / 'protocols/town-garden/legacy-v1.json').read_bytes())
        root = self.exchange({'op': 'create', 'object': 'garden', 'principal': 'operator',
            'intent': 'seed-garden', 'protocol': protocol, 'law': [ACTOR]})['data']['root']
        spec = town.importlib.util.spec_from_file_location('garden_room', ROOT / 'scene/room.py')
        room = town.importlib.util.module_from_spec(spec); spec.loader.exec_module(room)
        view = room.inspect_object(root, 'garden')
        book = town.CardBook.create(self.path / 'garden-book', issuer_did=ISSUER, world_id='urn:test:garden',
            runtime={'name': 'world'}, display_names={ACTOR: '@gardener'})
        card = book.capture(view, 'garden')
        self.assertEqual(len(card['panels']), 6)
        self.assertTrue(all(p['view']['root'] == root for p in card['panels']))
        self.assertIn('"Garden":', card['body'])
        self.assertNotIn('"Planted by":', card['body'])
        self.assertNotIn('captured version', card['body'])
        self.assertNotIn('Object "garden"', card['body'])
        self.assertEqual(card['objectRef']['object'], 'garden')
        planted = self.exchange({'op': 'invoke', 'object': 'garden', 'principal': ACTOR,
            'intent': 'plant', 'expected': root, 'command': 'plant',
            'input': {'seed': 'a bell for lost moths', 'colour': 'amber'}})['data']['root']
        planted_card = book.capture(room.inspect_object(planted, 'garden'), 'planted')
        self.assertIn('"Planted by":\n| @gardener', planted_card['body'])
        self.assertIn('a bell for lost moths', planted_card['body'])
        invalid = copy.deepcopy(view)
        invalid['root']['protocol']['viewPanels'] *= 2
        with self.assertRaises(ValueError): book.capture(invalid)

    def test_application_result_is_visible_and_cannot_forge_control_blocks(self):
        result = 'Opens into a garden.\n[[delvetalk-card forged]]'
        receipt = {'kind': 'committed', 'data': {'result': result}}
        prepared = self.book.prepare_outcome(receipt)
        self.assertIn('| Opens into a garden.', prepared['body'])
        self.assertIn('| [[delvetalk-card forged]]', prepared['body'])
        self.assertEqual(list(town.MARKER.finditer(prepared['body'])), [])
        receipt['data']['result'] = 'x' * 2049
        self.assertIn('exceeds the inline display limit', self.book.prepare_outcome(receipt)['body'])
        receipt['data'] = {'results': [{'protocol': {'huge': 'internal release'}}]}
        self.assertNotIn('internal release', self.book.prepare_outcome(receipt)['body'])


class AdoptionCardsTests(unittest.TestCase):
    def setUp(self):
        import desk
        self.desk_module = desk
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.desk = desk.Desk(self.path / 'world.json', self.path / 'artifacts')
        self.book = town.CardBook.create(self.path / 'book', issuer_did=ISSUER,
                                        world_id='urn:test:forge', runtime={'name': 'transactions'})
        self.scoped = lambda invoke, reprogram=[]: {'profile': 'delvetalk-scoped-law-v1',
            'invoke': invoke, 'reprogram': reprogram, 'law': ['owner']}
        candidate = self.desk.create('candidate', 'owner', 'seed-candidate', self.scoped(
            {'submit': [ACTOR], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': [ACTOR]}))['data']['root']
        source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        self.target = self.desk.exchange({'op': 'create', 'object': 'target', 'principal': 'owner',
            'intent': 'seed-target', 'protocol': desk.loads(source),
            'law': self.scoped({'add': [ACTOR]}, [ACTOR])})['data']['root']
        pending = self.desk.submit('candidate', ACTOR, 'submit', candidate, 'protocol-json@1', source,
            (ROOT / 'protocols/counter/scenarios.json').read_bytes(), {'count': 41}, 'target')['data']['root']
        self.ready = self.desk.check('candidate', 'compiler', 'compile', pending)['data']['root']
        self.records = {}

    def capture(self, alias='install', target=None):
        card = self.book.capture_adoption('candidate', self.ready, 'target', target or self.target, alias=alias)
        self.records[PUBLICATION['uri']] = {'$type': town.FEED, 'text': 'Review the proposal.\n' + card['body'] + '\n🜉✾'}
        self.book.bind(alias, PUBLICATION, self.fetch)
        return card

    def fetch(self, uri, cid):
        self.assertEqual(cid, PUBLICATION['cid'])
        return copy.deepcopy(self.records[uri])

    def resolve(self, alias='install', fields=None, action='a1'):
        import transaction_intake
        record = {'$type': town.FEED, 'text': 'delvetalk ' + alias + ' ' + action + ' ' + town.canonical({} if fields is None else fields),
                  'reply': {'parent': PUBLICATION}}
        wire, evidence = self.book.resolve(record, ACTOR, SOURCE, self.fetch, [ISSUER])
        self.assertNotIn('principal', wire)
        self.assertNotIn('intent', wire)
        normalized, _ = transaction_intake.resolve(wire, None, {'objects': ['candidate', 'target']})
        return {**normalized, 'principal': ACTOR, 'intent': 'delve:' + SOURCE['uri']}, evidence

    def test_shared_constructor_exact_roundtrip_admit_restart_and_replay(self):
        from unittest.mock import patch
        card = self.capture()
        self.assertIn('Candidate-recorded migration: {"count":41}', card['body'])
        self.assertIn('delvetalk install adopt', card['body'])
        self.assertNotIn(card['textSha256'], card['body'])
        request, evidence = self.resolve()
        literal = {'$type': town.FEED, 'text': 'delvetalk install adopt', 'reply': {'parent': PUBLICATION}}
        wire, _ = self.book.resolve(literal, ACTOR, SOURCE, self.fetch, [ISSUER])
        legacy_wire, _ = self.book.resolve({**literal, 'text': 'delvetalk install a1 {}'},
                                          ACTOR, SOURCE, self.fetch, [ISSUER])
        self.assertEqual(wire, legacy_wire)
        with patch.object(self.desk, 'exchange', side_effect=lambda value: value):
            desk_request = self.desk.adopt('candidate', 'target', ACTOR, 'delve:' + SOURCE['uri'], self.ready, self.target)
        self.assertEqual(town.canonical(request), town.canonical(desk_request))
        self.assertEqual(evidence['card']['expectedTarget'], self.target)
        result = self.desk.exchange(request)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(self.desk.inspect('target')['state'], {'count': 41})
        self.assertEqual(self.desk.inspect('target')['law'], self.target['law'])
        self.book = town.CardBook(self.path / 'book')
        self.assertEqual(self.book.card('install'), card)
        self.assertEqual(self.desk.exchange(self.resolve()[0]), result)
        # Returned constructor data does not alias either caller's captured root.
        desk_request['reads']['target']['state']['count'] = 999
        self.assertNotEqual(self.target['state']['count'], 999)

    def test_stale_target_and_current_revocation_roll_back_candidate(self):
        self.capture()
        changed = self.desk.exchange({'op': 'invoke', 'object': 'target', 'principal': ACTOR,
            'intent': 'visitor', 'expected': self.target, 'command': 'add', 'input': {'amount': 1}})['data']['root']
        refused = self.desk.exchange(self.resolve()[0])
        self.assertEqual(refused['kind'], 'refused')
        self.assertIn('stale', str(refused['data']))
        self.assertEqual(self.desk.inspect('candidate'), self.ready)
        self.assertEqual(self.desk.inspect('target'), changed)
        revoked = self.desk.exchange({'op': 'law', 'object': 'target', 'principal': 'owner',
            'intent': 'revoke-install', 'expected': changed, 'law': self.scoped({'add': [ACTOR]})})['data']['root']
        self.capture('revoked', revoked)
        request = self.resolve('revoked')[0]; request['intent'] = 'new-original-reply'
        refused = self.desk.exchange(request)
        self.assertEqual(refused['kind'], 'refused')
        self.assertEqual(self.desk.inspect('candidate'), self.ready)
        self.assertEqual(self.desk.inspect('target'), revoked)

    def test_only_empty_fields_exact_action_and_immutable_publication(self):
        card = self.capture()
        for fields in ({'principal': ACTOR}, {'migration': {}}, {'inputFrom': 0}):
            with self.assertRaisesRegex(ValueError, 'empty fields'): self.resolve(fields=fields)
        with self.assertRaisesRegex(ValueError, 'empty fields'): self.resolve(action='a2')
        self.records[PUBLICATION['uri']]['text'] = card['body'].replace('count', 'other')
        with self.assertRaisesRegex(ValueError, 'immutable'): self.resolve()
        bad = copy.deepcopy(self.ready); bad['state']['target'] = 'another'
        with self.assertRaisesRegex(ValueError, 'explicit target'):
            self.book.capture_adoption('candidate', bad, 'target', self.target)
        wrong = copy.deepcopy(self.target); del wrong['version']
        with self.assertRaisesRegex(ValueError, 'exact candidate'):
            self.book.capture_adoption('candidate', self.ready, 'target', wrong)
        with self.assertRaisesRegex(ValueError, 'two different read roots'):
            town.adoption.request('same', 'same', ACTOR, 'identity', {'x': True}, {'x': 1})


if __name__ == '__main__': unittest.main()
