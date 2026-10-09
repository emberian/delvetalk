"""Native source publication audience, private read separation and opaque forms."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world
import town_cards
import runtime_profile
import town
import clerk
import history
import opaque_offers
import source_offers
from conformance.test_clerk import FakePDS

OWNER = 'did:plc:' + 'a' * 24
VISITOR = 'did:plc:' + 'b' * 24
ISSUER = 'did:plc:' + 'c' * 24


def source_authority(entry, public=None, *, owner=OWNER, visitor=VISITOR):
    modules = source_object.read_closure([
        ('Authority', ROOT / 'world/lib/prelude/Authority.obend'),
        ('PublicationAuthority', ROOT / 'conformance/fixtures/PublicationAuthority.obend')])
    arguments = [source_object.data(owner), source_object.data(visitor)]
    if public is not None:
        arguments.append(source_object.data(public))
    authored = source_object.evaluate(modules, entry, arguments)
    return source_object.values('decode', [authored])[0]


class PublicationProjection(unittest.TestCase):
    def test_public_source_form_private_secret_current_audience_and_exact_retry(self):
        protocol = source_object.load(source_object.read_modules([
            ('Counter', ROOT / 'conformance/fixtures/PublicationCounter.obend')]), syntax='objective-bend-object')
        # Extra source data fields need no adapter whitelist; executable values
        # still fail the native bounded package-data schema check.
        executable = (ROOT / 'conformance/fixtures/PublicationCounter.obend').read_bytes().decode('utf-8')
        executable = executable.replace('extension: {caption: String', 'extension: {caption: Nat -> Nat')
        executable = executable.replace('caption: "An editable source extension"',
            'caption: fn(value: Nat) -> Nat: value')
        with self.assertRaisesRegex(ValueError, 'serializable package data'):
            source_object.load([{'name': 'Counter', 'source': executable}], syntax='objective-bend-object')
        authority = source_authority('counter', True)
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'world.json'
            created = world.exchange(database, {'op': 'create', 'object': 'counter',
                'principal': OWNER, 'intent': 'create-publication', 'protocol': protocol, 'law': authority})
            self.assertEqual(created['kind'], 'committed', created)
            private = world.opaque_view(database, 'counter', principal=OWNER, panel='private')
            self.assertIn('private-counter-state-secret', private['result']['prose'])
            with self.assertRaises((RuntimeError, ValueError)):
                world.opaque_view(database, 'counter', principal=OWNER, panel='private', audience='public')
            public = world.opaque_view(database, 'counter', principal=OWNER, audience='public')
            self.assertEqual(public['result']['extension'],
                {'caption': 'An editable source extension', 'nested': {'count': 0}})
            book = town_cards.CardBook.create(Path(temporary) / 'cards', issuer_did=ISSUER,
                world_id='publication-fixture', runtime=runtime_profile.hash_paths(runtime_profile.paths('compiled'), root=ROOT))
            card = book.capture_public('counter', public, alias='public')
            self.assertNotIn('private-counter-state-secret', town_cards.canonical(card))
            self.assertNotIn('private-counter-diagnostic-secret', town_cards.canonical(card))
            self.assertEqual(card['actions'][0]['fields'][0]['name'], 'amount')
            out_of_range = world.exchange(database, world.opaque_request('counter', public['reference'],
                'add', {'amount': 101}, principal=VISITOR, intent='source-refuses-range'))
            self.assertEqual(out_of_range['kind'], 'refused')
            self.assertNotIn('private-counter-diagnostic-secret', town_cards.canonical(out_of_range))
            request = world.opaque_request('counter', public['reference'], 'add', {'amount': 7},
                principal=VISITOR, intent='public-add')
            committed = world.exchange(database, request)
            self.assertEqual(committed['kind'], 'committed', committed)
            self.assertEqual(committed['data']['result'], {'count': 7})
            with self.assertRaises((RuntimeError, ValueError)):
                world.opaque_view(database, 'counter', principal=OWNER, audience='public', expected=public['reference'])
            fresh = world.opaque_view(database, 'counter', principal=OWNER, audience='public', expected=committed['data']['reference'])
            self.assertEqual(fresh['result']['prose'], 'Count: 7')
            root = world.capture_roots(database, ['counter'], principal=OWNER)['roots']['counter']['root']
            revoked = source_authority('counter', False)
            changed = world.exchange(database, {'op': 'law', 'object': 'counter', 'principal': OWNER,
                'intent': 'close-publication', 'expected': root, 'law': revoked})
            self.assertEqual(changed['kind'], 'committed', changed)
            with self.assertRaises((RuntimeError, ValueError)):
                world.opaque_view(database, 'counter', principal=OWNER, audience='public')
            self.assertEqual(world.exchange(database, request), committed)
            self.assertNotIn('private-counter-state-secret', town_cards.canonical(committed))
            self.assertNotIn('private-counter-diagnostic-secret', town_cards.canonical(committed))
            # A principal named public in an ACL is not the public audience.
            collision = world.exchange(database, {'op': 'create', 'object': 'literal-public-principal',
                'principal': 'public', 'intent': 'literal-public', 'protocol': protocol,
                'law': source_authority('counter', False, owner='public')})
            self.assertEqual(collision['kind'], 'committed', collision)
            self.assertEqual(world.opaque_view(database, 'literal-public-principal',
                principal='public')['audience'], 'principal')
            with self.assertRaises((RuntimeError, ValueError)):
                world.opaque_view(database, 'literal-public-principal', principal='public', audience='public')

    def test_town_verified_reply_source_form_and_revoked_saved_draft(self):
        protocol = source_object.load(source_object.read_modules([
            ('Counter', ROOT / 'conformance/fixtures/PublicationCounter.obend')]), syntax='objective-bend-object')
        authority = source_authority('counter', True)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pds = FakePDS()
            custody = clerk.Clerk(base / 'clerk', pds)
            created = custody.bootstrap('counter', protocol, authority, [OWNER, VISITOR])
            self.assertEqual(created['kind'], 'committed', created)
            book = town_cards.CardBook.create(base / 'cards', issuer_did=ISSUER,
                world_id='publication-town', runtime=history.runtime('compiled'))
            custody.upgrade(custody.profile()['sha256'], town_cards={'path': str(book.path),
                'issuers': [ISSUER], 'metadata': book.metadata()})
            operator = town.Town(custody.state, request=pds)
            card = operator.capture('counter', alias='opening', principal=OWNER)
            self.assertNotIn('private-counter-state-secret', town_cards.canonical(card))
            parent = {'uri': 'at://' + ISSUER + '/' + clerk.FEED + '/opening', 'cid': 'opening-cid'}
            pds.records[parent['uri']] = (parent['cid'], {'$type': clerk.FEED, 'text': card['body']})
            operator.bind('opening', parent['uri'], parent['cid'])
            uri = 'at://' + VISITOR + '/' + clerk.FEED + '/answer'
            pds.records[uri] = ('answer-cid', {'$type': clerk.FEED,
                'text': 'delvetalk opening add\namount: 9', 'reply': {'parent': parent, 'root': parent}})
            response = operator.receive(uri, 'answer-cid')
            self.assertEqual(response['receipt']['reply']['kind'], 'committed', response)
            self.assertEqual(response['receipt']['request']['op'], 'opaque-invoke')
            self.assertIn('Count: 9', response['body'])
            self.assertNotIn('private-counter-state-secret', response['body'])
            self.assertNotIn('private-counter-diagnostic-secret', response['body'])
            root = world.capture_roots(custody.database, ['counter'], principal=OWNER)['roots']['counter']['root']
            closed = source_authority('counter', False)
            changed = world.exchange(custody.database, {'op': 'law', 'object': 'counter',
                'principal': OWNER, 'intent': 'close-public-draft', 'expected': root, 'law': closed})
            self.assertEqual(changed['kind'], 'committed', changed)
            with self.assertRaises((ValueError, RuntimeError)):
                operator.check_public(response['cards'][0]['alias'])
            pds.records.clear()
            retry = town.Town(custody.state, request=pds).receive(uri, 'answer-cid')
            self.assertEqual(retry['receipt'], response['receipt'])
            self.assertEqual(retry['cards'], [])
            self.assertEqual(retry['presentation']['status'], 'unavailable')

    def test_directory_and_source_desk_public_invitations_keep_actual_source_workflows(self):
        directory = clerk.module('publication_directory', 'protocols/root-directory/package.py')
        desks = clerk.module('publication_desks', 'protocols/source-desk/package.py')
        modules = source_object.read_closure([
            ('Directory', ROOT / 'protocols/root-directory/Directory.obend'),
            ('GSBWelcome', ROOT / 'protocols/root-directory/GSBWelcome.obend')])
        door = {'key': 'workshop', 'label': 'Source workshop', 'object': 'desk', 'panel': 'main',
            'description': 'Make a source desk', 'example': 'I want to write', 'available': True, 'show': True}
        directory_protocol = source_object.load(modules, syntax='objective-bend-object')
        desk_protocol = desks.factory('compiler', [], reviewers=[OWNER])
        directory_law = source_authority('directory')
        desk_law = source_authority('desk')
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            pds = FakePDS()
            custody = clerk.Clerk(base / 'clerk', pds)
            opened = custody.bootstrap('directory', directory_protocol, directory_law, [OWNER, VISITOR])
            self.assertEqual(opened['kind'], 'committed', opened)
            initial_directory = world.capture_roots(custody.database, ['directory'], principal=OWNER)['roots']['directory']['root']
            connected = world.exchange(custody.database, {'op': 'invoke', 'object': 'directory',
                'principal': OWNER, 'intent': 'connect-source-workshop', 'expected': initial_directory,
                'command': 'setDoor', 'input': door})
            self.assertEqual(connected['kind'], 'committed', connected)
            made = world.exchange(custody.database, {'op': 'create', 'object': 'desk', 'principal': OWNER,
                'intent': 'desk-factory', 'protocol': desk_protocol, 'law': desk_law})
            self.assertEqual(made['kind'], 'committed', made)
            configured = custody.config()
            configured['objects'].append('desk')
            clerk.save(custody.state / 'clerk.json', configured)
            book = town_cards.CardBook.create(base / 'cards', issuer_did=ISSUER,
                world_id='publication-workshops', runtime=history.runtime('compiled'))
            custody.upgrade(custody.profile()['sha256'], town_cards={'path': str(book.path),
                'issuers': [ISSUER], 'metadata': book.metadata()})
            operator = town.Town(custody.state, request=pds)
            def act(object_id, alias, text, *, question=False):
                card = operator.capture(object_id, alias=alias, principal=VISITOR)
                self.assertTrue(any(action.get('preparation') for action in card['actions']))
                self.assertNotIn('"protocol"', town_cards.canonical(card))
                self.assertNotIn('"state"', town_cards.canonical(card))
                parent = {'uri': 'at://' + ISSUER + '/' + clerk.FEED + '/' + alias, 'cid': alias + '-cid'}
                pds.records[parent['uri']] = (parent['cid'], {'$type': clerk.FEED, 'text': card['body']})
                operator.bind(alias, parent['uri'], parent['cid'])
                uri = 'at://' + VISITOR + '/' + clerk.FEED + '/reply-' + alias
                pds.records[uri] = (alias + '-reply-cid', {'$type': clerk.FEED, 'text': text,
                    'reply': {'root': parent, 'parent': parent}})
                response = operator.receive(uri, alias + '-reply-cid')
                if question:
                    self.assertEqual(response['status'], 'question', response)
                    self.assertIn('Which open door', response['body'])
                    self.assertEqual(response['preparation']['publicSelection']['audience'], 'public')
                    with self.assertRaises(source_offers.PreparationOutcome) as direct:
                        opaque_offers.prepare(custody.database, card['publicInvitations']['choose'],
                            VISITOR, 'same-physical-contribution',
                            {'original': 'x' * 600, 'newword': 'source-decides'})
                    self.assertEqual(direct.exception.outcome, response['preparation'])
                    return response
                self.assertEqual(response['receipt']['request']['op'], 'opaque-transaction')
                self.assertEqual(response['receipt']['reply']['kind'], 'committed', response)
                return response
            question = act('directory', 'directory-question',
                'delvetalk directory-question choose\noriginal: ' + 'x' * 600 + '\nnewword: source-decides', question=True)
            selected = act('directory', 'directory-card',
                'delvetalk directory-card choose\ndoor: workshop\noriginal: I want to write')
            self.assertIn('DELVETALK', selected['body'])
            directory_root = world.capture_roots(custody.database, ['directory'], principal=OWNER)['roots']['directory']['root']
            withdrawn = world.exchange(custody.database, {'op': 'law', 'object': 'directory',
                'principal': OWNER, 'intent': 'withdraw-directory-public-audience',
                'expected': directory_root, 'law': source_authority('counter', False)})
            self.assertEqual(withdrawn['kind'], 'committed', withdrawn)
            stale_question = operator.public_response(question)
            self.assertEqual(stale_question['presentation']['status'], 'unavailable')
            self.assertNotIn('Which open door', stale_question['body'])
            self.assertEqual(stale_question['receipt'], question['receipt'])
            created = act('desk', 'desk-card', 'delvetalk desk-card make\nname: my-source-desk')
            self.assertEqual(created['publication'], 'paused')
            owner_state = world.capture_roots(custody.database, ['desk/my-source-desk'], principal=VISITOR)
            self.assertIsNotNone(owner_state['roots']['desk/my-source-desk'])


if __name__ == '__main__': unittest.main()
