"""Observation, identity and posting: posts classified, observed once, bounded; proof of control by
DID; replies threaded and gated behind the posting flag.

Evidence for FOUNDATION §7 (layer: transport).
"""
import copy
import io
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from transport import delve, identity, observe, post
from transport.__main__ import main
from transport.config import Config
from transport.state import State

FIX = Path(__file__).parent / 'fixtures' / 'delve'
FEED = json.loads((FIX / 'town.delve.feed.getFeed.json').read_text())
BASE = FEED['feed'][0]['post']
DID = 'did:plc:' + 'a' * 24
OTHER = 'did:plc:' + 'b' * 24


def mk(n, text, parent=None, facets=None):
    p = copy.deepcopy(BASE)
    p['uri'] = f'at://{DID}/town.delve.feed.post/r{n:06d}'
    p['cid'] = f'bafy{n}'
    p['record'] = {'$type': 'town.delve.feed.post', 'createdAt': '2026-10-09T10:00:00.000Z', 'text': text}
    if parent:
        p['record']['reply'] = {'parent': {'uri': parent, 'cid': 'x'}, 'root': {'uri': parent, 'cid': 'x'}}
    if facets:
        p['record']['facets'] = facets
    for k in ('author',):
        p[k] = {'did': DID, 'handle': 'talkie.delve.town'}
    return p


class Script:
    """Offline transport: routes by nsid to a callable(params) -> (status, obj|bytes)."""
    def __init__(self, **routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers, body):
        import urllib.parse as up
        self.calls.append((method, url))
        parts = up.urlsplit(url)
        params = {k: v[0] for k, v in up.parse_qs(parts.query).items()}
        status, obj = self.routes[parts.path.rsplit('/', 1)[-1]](params)
        return status, obj if isinstance(obj, bytes) else json.dumps(obj).encode()


def stored(ob, after=0):
    return [json.loads(js) for (js,) in ob.db.execute('SELECT json FROM observations WHERE seq > ? ORDER BY seq', (after,))]


def run_observer(posts, state):
    """-> (the observations this poll stored, the observer)."""
    t = Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                  'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
    ob = observe.Observer(State(state), delve.Client(t))
    before = ob.db.execute('SELECT COALESCE(MAX(seq), 0) FROM observations').fetchone()[0]
    ob.poll()
    return stored(ob, before), ob


class Classification(unittest.TestCase):
    def kinds(self, posts):
        with tempfile.TemporaryDirectory() as d:
            obs, ob = run_observer(posts, d)
        return {o['uri'][-6:]: o for o in obs}, ob

    def test_each_post_shape_is_classified_wiki_page_edit_merge_summon_reply_or_post(self):
        mention = [{'index': {'byteStart': 0, 'byteEnd': 25},
                    'features': [{'$type': 'town.delve.richtext.facet#mention', 'did': OTHER}]}]
        obs, _ = self.kinds([
            mk(1, 'wiki: GSB Welcome Message (v2)\n\nbody'),
            mk(2, 'edit: Garden › Beds\nnew text'),
            mk(3, 'merge: Garden', parent=BASE['uri']),
            mk(4, '@livedelvetalk.delve.town hello #gsb', facets=mention),
            mk(5, 'sure\ndelvetalk garden plant\nseed: fern', parent=BASE['uri']),
            mk(6, 'just words', parent=BASE['uri']),
            mk(7, 'merge conflicts are fun'),
            mk(8, 'delvetalk garden ?'),  # a spell or not is the host's parser's answer (bridge.parsed)
            mk(9, 'hello @livedelvetalk.delve.town'), mk(10, 'a #gsb post', parent=BASE['uri']),  # a summon: the portal or the tag
            mk(11, '#gsb\ndelvetalk garden plant'), mk(12, 'hi @livedelvetalk.delve.town #GSB'),  # a handle in text, no facet
            mk(13, 'not delvetalk garden plant'),
            mk(14, 'hi @ember.delve.town'),  # the account that carries the town's replies is not its address
        ])
        self.assertEqual({k: v['kind'] for k, v in obs.items()},
                         {'%06d' % i: k for i, k in enumerate(
                             ['wiki-page', 'wiki-edit', 'wiki-merge', 'summon', 'reply', 'reply', 'post', 'post',
                              'summon', 'summon', 'summon', 'summon', 'post', 'post'], 1)})
        self.assertEqual(observe.wiki_target(obs['000001']['text']), ('GSB Welcome Message (v2)', ''))
        self.assertEqual(observe.wiki_target(obs['000002']['text'])[1], 'Beds')
        self.assertEqual(obs['000004']['mentions'], [{'did': OTHER, 'handle': 'livedelvetalk.delve.town'}])
        self.assertEqual(obs['000004']['tags'], ['gsb'])
        self.assertEqual(obs['000006']['replyTo'], BASE['uri'])
        self.assertEqual(set(obs['000006']), {'uri', 'cid', 'author', 'createdAt', 'text', 'replyTo', 'root',
                                              'mentions', 'tags', 'kind'})

class Idempotence(unittest.TestCase):
    def test_rerun_emits_nothing(self):
        posts = [mk(i, f'p{i}') for i in range(5)]
        with tempfile.TemporaryDirectory() as d:
            first, _ = run_observer(posts, d)
            second, _ = run_observer(posts, d)
        self.assertEqual((len(first), second), (5, []))

    def test_a_crash_mid_page_loses_and_repeats_no_post(self):
        posts = [mk(i, f'p{i}') for i in range(6)]
        with tempfile.TemporaryDirectory() as d:
            calls = {'n': 0}

            def search(p):
                calls['n'] += 1
                if calls['n'] > 1:
                    raise RuntimeError('crash')
                return 200, {'posts': posts[:3], 'cursor': 'c1'}
            t = Script(**{'town.delve.feed.searchPosts': search, 'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
            ob = observe.Observer(State(d), delve.Client(t))
            with self.assertRaises(RuntimeError):
                ob.poll()
            seen = stored(ob)
            ob.db.close()
            out, _ = run_observer(posts, d)
        got = [o['uri'] for o in seen + out]
        self.assertEqual(sorted(got), sorted(p['uri'] for p in posts))
        self.assertEqual(len(got), len(set(got)))


class Bounds(unittest.TestCase):
    def test_a_thousand_post_page_is_observed_whole_and_a_one_mebibyte_body_refused_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            obs, ob = run_observer([mk(i, f'wiki: T{i}\n#gsb @a.delve.town') for i in range(1000)] + [mk(1000, 'x' * (1 << 20))], d)
        self.assertEqual(len(obs), 1000)
        with self.assertRaises(delve.Failure) as c:
            observe.observation(mk(1000, 'x' * (1 << 20)))
        self.assertEqual(c.exception.code, 'post_body_too_large')

    def test_the_writer_and_the_client_refuse_what_is_too_large_a_redirect_and_any_other_endpoint_by_name(self):
        with self.assertRaises(delve.Failure) as c:
            post.build_request('x' * (1 << 20))
        self.assertEqual(c.exception.code, 'post_body_too_large')
        for answer, code in (((200, b'{' + b' ' * delve.MAX_RESPONSE + b'}'), 'response_too_large'), ((302, b''), 'redirect_refused')):
            with self.assertRaises(delve.Failure) as e:
                delve.Client(lambda *a, answer=answer: answer).search('x')
            self.assertEqual(e.exception.code, code)
        c = delve.Client(lambda *a: self.fail('sent'))
        for fn in (lambda: c.write('com.atproto.repo.createRecord', {}),
                   lambda: c.get('com.atproto.server.createSession')):
            with self.assertRaises(delve.Failure):
                fn()


class Identity(unittest.TestCase):
    HANDLE = 'talkie.delve.town'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1000.0]
        self.record = {}
        self.t = Script(**{
            'com.atproto.identity.resolveHandle': lambda p: (200, {'did': DID}),
            'com.atproto.repo.getRecord': lambda p: self.record['r'](p)})
        self.id = identity.Identity(State(self.tmp.name), delve.Client(self.t), clock=lambda: self.now[0])
        self.ch = self.id.challenge(self.HANDLE)
        self.uri = f'at://{DID}/town.delve.feed.post/3abc'

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, text=None, uri=None, status=200):
        self.record['r'] = lambda p: (status, {'uri': uri or self.uri, 'cid': 'bafyx',
                                               'value': {'text': self.ch['text'] if text is None else text}})

    def refused(self, code, uri=None):
        with self.assertRaises(identity.IdentityError) as e:
            self.id.verify(self.HANDLE, uri or self.uri, self.ch['credential'])
        self.assertEqual(e.exception.code, code)


    def listing(self, *records, status=200):
        self.t.routes['com.atproto.repo.listRecords'] = lambda p: (status, {'records': list(records)})
        return lambda text, n=1, repo=DID: {'uri': f'at://{repo}/town.delve.feed.post/{n}', 'cid': 'bafy' + str(n), 'value': {'text': text}}

    def test_a_claim_finds_the_word_among_the_newest_posts_and_logs_the_account_in(self):
        rec = self.listing()
        self.listing(rec('good morning', 1), rec('  ' + self.ch['text'] + ' \n', 2), rec('a later post', 3))
        got = self.id.claim(self.HANDLE, self.ch['credential'])
        self.assertEqual((got['did'], got['uri']), (DID, f'at://{DID}/town.delve.feed.post/2'))
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)
        with self.assertRaises(identity.IdentityError) as e:
            self.id.claim(self.HANDLE, self.ch['credential'])
        self.assertEqual(e.exception.code, 'challenge_consumed')

    def claim_refused(self, code):
        with self.assertRaises(identity.IdentityError) as e:
            self.id.claim(self.HANDLE, self.ch['credential'])
        self.assertEqual(e.exception.code, code)

    def test_a_claim_without_the_word_posted_or_with_it_in_another_account_or_inside_a_longer_post_is_no_post_yet(self):
        rec = self.listing()
        self.listing(rec('good morning'), rec(self.ch['text'] + ' and more', 2), rec(self.ch['text'], 3, repo=OTHER))
        self.claim_refused('no_post_yet')
        self.listing()
        self.claim_refused('no_post_yet')

    def test_a_listing_we_cannot_read_is_hidden_and_a_lapsed_word_is_expired(self):
        self.listing(status=403)
        self.claim_refused('posts_hidden')
        self.listing(status=200)
        self.t.routes['com.atproto.repo.listRecords'] = lambda p: (200, {'nothing': 1})
        self.claim_refused('posts_hidden')
        self.now[0] += 1000
        self.claim_refused('challenge_expired')

    def test_claims_are_counted_before_any_read(self):
        self.listing()
        for _ in range(identity.MAX_ATTEMPTS):
            self.claim_refused('no_post_yet')
        self.claim_refused('too_many_attempts')
        self.assertEqual(self.id.pending(self.HANDLE)['text'], self.ch['text'])

    def test_a_challenge_verifies_once_then_is_consumed_and_refused_a_second_time(self):
        self.serve()
        self.assertEqual(self.id.verify(self.HANDLE, self.uri, self.ch['credential'])['did'], DID)
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)
        self.refused('challenge_consumed')

    def test_a_revoked_credential_cannot_authenticate_or_be_verified_again(self):
        self.serve()
        self.id.verify(self.HANDLE, self.uri, self.ch['credential'])
        self.id.revoke(self.ch['credential'])
        with self.assertRaises(identity.IdentityError):
            self.id.authenticate(self.ch['credential'])
        self.refused('challenge_revoked')

    def test_a_newer_challenge_by_someone_else_does_not_invalidate_the_proof_of_mine(self):
        self.now[0] += 1
        theirs = self.id.challenge(self.HANDLE)  # anyone may ask for a challenge for any handle, a second later
        self.serve()  # the resident posts the word of the challenge they asked for
        self.assertEqual(self.id.verify(self.HANDLE, self.uri, self.ch['credential'])['did'], DID)
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)
        with self.assertRaises(identity.IdentityError):
            self.id.authenticate(theirs['credential'])

    def test_verification_with_my_credential_answers_my_challenge_and_the_claim_finds_my_word(self):
        self.now[0] += 1
        self.id.challenge(self.HANDLE)
        self.assertEqual(self.id.pending(self.HANDLE, self.ch['credential'])['text'], self.ch['text'])
        rec = self.listing()
        self.listing(rec(self.ch['text'], 2))
        self.assertEqual(self.id.claim(self.HANDLE, self.ch['credential'])['did'], DID)
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)

    def test_a_request_without_the_challenges_credential_spends_none_of_its_attempts(self):
        self.serve(text='not the word')
        for held in (None, 'dt_agent_' + 'x' * 43):
            for _ in range(identity.MAX_ATTEMPTS + 1):
                with self.assertRaises(identity.IdentityError) as e:
                    self.id.verify(self.HANDLE, self.uri, held)
                self.assertEqual(e.exception.code, 'no_challenge')
            with self.assertRaises(identity.IdentityError) as e:
                self.id.claim(self.HANDLE, held)
            self.assertEqual(e.exception.code, 'no_challenge')
        self.assertEqual(self.id.db.execute('SELECT attempts FROM challenges').fetchone()[0], 0)
        self.serve()
        self.assertEqual(self.id.verify(self.HANDLE, self.uri, self.ch['credential'])['did'], DID)

    def test_a_malformed_proof_uri_is_refused_before_an_attempt_is_counted(self):
        with self.assertRaises(identity.IdentityError) as e:
            self.id.verify(self.HANDLE, 'at://nothing', self.ch['credential'])
        self.assertEqual(e.exception.code, 'invalid_proof_uri')
        self.assertEqual(self.id.db.execute('SELECT attempts FROM challenges').fetchone()[0], 0)

    def test_a_session_ends_when_it_says_so_and_a_claim_or_guest_does_not_end_with_its_deadline(self):
        from transport import oauth
        session = oauth.admit(self.id, self.HANDLE, DID)
        self.serve()
        self.id.verify(self.HANDLE, self.uri, self.ch['credential'])
        self.now[0] += oauth.KEEP - 1
        self.assertEqual(self.id.authenticate(session)['did'], DID)
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)  # the claim's deadline was 15 minutes
        self.now[0] += 2
        with self.assertRaises(identity.IdentityError) as e:
            self.id.authenticate(session)
        self.assertEqual(e.exception.code, 'invalid_credential')
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)

    def test_a_strangers_challenges_do_not_exhaust_the_owners(self):
        # Challenges are counted per requesting address (the root's queue, from transport4's review):
        # eight asked from one address for a handle refuse that address's ninth, not the owner's.
        for _ in range(8):
            self.id.challenge(self.HANDLE, address='203.0.113.9')
        with self.assertRaises(identity.IdentityError) as refused:
            self.id.challenge(self.HANDLE, address='203.0.113.9')
        self.assertEqual(refused.exception.code, 'rate_limited')
        mine = self.id.challenge(self.HANDLE, address='198.51.100.4')
        self.assertTrue(mine['credential'].startswith('dt_agent_'))

    def test_a_proof_is_refused_by_name_unless_it_is_the_word_posted_by_that_did_at_that_uri_in_time(self):
        with self.assertRaises(identity.IdentityError):
            self.id.authenticate(self.ch['credential'])  # unverified
        with self.assertRaises(identity.IdentityError):
            self.id.challenge('evil.example.com')  # not a delve handle
        for serve, uri, code in (({}, f'at://{OTHER}/town.delve.feed.post/3abc', 'wrong_author'),
                                 ({'text': 'look: ' + self.ch['text'] + ' !'}, None, 'proof_text_mismatch'),
                                 ({'status': 302}, None, 'proof_unavailable:redirect_refused'),
                                 ({'uri': f'at://{DID}/town.delve.feed.post/other'}, None, 'proof_mismatch'),
                                 ({}, 'at://x/y/z', 'invalid_proof_uri')):
            self.serve(**serve)
            self.refused(code, uri)
        self.serve()
        self.now[0] += identity.TTL
        self.refused('challenge_expired')

    def test_ninth_attempt_refused_even_if_correct(self):
        self.serve(text='nope')
        for _ in range(8):
            self.refused('proof_text_mismatch')
        self.serve()
        self.refused('too_many_attempts')

class Posting(unittest.TestCase):
    def test_no_flag_sends_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.txt'
            f.write_text('hello')
            out = io.StringIO()
            with mock.patch.object(urllib.request.OpenerDirector, 'open', side_effect=AssertionError('network')) as op, \
                    mock.patch.object(post, 'send', side_effect=AssertionError('send')):
                code = main(['post', '--state', d, '--text-file', str(f), '--intent', 'test'], out)
            self.assertEqual(code, 2)
            self.assertEqual(op.call_count, 0)
            req = json.loads(out.getvalue())
            self.assertTrue(req['dry_run'])
            self.assertEqual(req['request']['body']['record']['text'], 'hello')
            self.assertEqual(list(Path(d).iterdir()), [Path(d) / 't.txt'])

    def parent(self):
        uri = f'at://{DID}/town.delve.feed.post/page01'
        got = {'uri': uri, 'cid': 'bafyparent', 'value': {'text': 'wiki: T'}}
        calls = []
        t = Script(**{'com.atproto.repo.getRecord': lambda p: calls.append(p) or (200, got)})
        return uri, delve.Client(t), t, calls

    def dry(self, d, args, client):
        out = io.StringIO()
        code = main(['post', '--state', d, '--intent', 't', *args], out, client=client)
        return code, json.loads(out.getvalue())

    def test_threaded_reply_record_shape_and_only_gets(self):
        uri, client, t, calls = self.parent()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'b.txt'
            f.write_text('hi')
            code, req = self.dry(d, ['--text-file', str(f), '--reply-to', uri], client)
        rec = req['request']['body']['record']
        self.assertEqual(code, 2)
        self.assertEqual(rec['reply'], {'root': {'uri': uri, 'cid': 'bafyparent'}, 'parent': {'uri': uri, 'cid': 'bafyparent'}})
        self.assertEqual(calls, [{'repo': DID, 'collection': 'town.delve.feed.post', 'rkey': 'page01'}])
        self.assertEqual({m for m, _ in t.calls}, {'GET'})
        # a reply to a reply keeps the thread's root
        root = {'uri': f'at://{DID}/town.delve.feed.post/root01', 'cid': 'bafyroot'}
        got = {'uri': f'at://{DID}/town.delve.feed.post/r2', 'cid': 'bafyr2', 'value': {'reply': {'root': root, 'parent': root}}}
        client = delve.Client(Script(**{'com.atproto.repo.getRecord': lambda p: (200, got)}))
        ref = post.reply_ref(client, got['uri'])
        self.assertEqual(ref, {'root': root, 'parent': {'uri': got['uri'], 'cid': 'bafyr2'}})

    def test_wiki_edit_needs_a_page_to_reply_to_and_flag_off_sends_nothing(self):
        uri, client, t, _ = self.parent()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'b.txt'
            f.write_text('x')
            with mock.patch.object(post, 'send', side_effect=AssertionError('send')):
                (Path(d) / 'e.txt').write_text('edit: A \u203a B\n\nx')
                with mock.patch('sys.stderr', io.StringIO()):
                    self.assertEqual(main(['post', '--state', d, '--intent', 't', '--text-file', str(Path(d) / 'e.txt')], io.StringIO(), client=client), 1)
                self.assertEqual(main(['post', '--state', d, '--intent', 't', '--text-file', str(f), '--reply-to', uri], io.StringIO(), client=client), 2)
        self.assertNotIn('POST', {m for m, _ in t.calls})

    def test_mention_facets_use_utf8_byte_offsets_and_resolved_dids(self):
        t = Script(**{'com.atproto.identity.resolveHandle': lambda p: (200, {'did': OTHER}) if p['handle'] == 'glm.delve.town' else (400, {'error': 'x'})})
        text = 'h\u00e9llo @glm.delve.town, and @ghost.delve.town.'
        facets = post.mention_facets(delve.Client(t), text)
        self.assertEqual(len(facets), 1)
        f = facets[0]
        self.assertEqual(text.encode()[f['index']['byteStart']:f['index']['byteEnd']], b'@glm.delve.town')
        self.assertEqual(f['features'], [{'$type': 'town.delve.richtext.facet#mention', 'did': OTHER}])
        # and the observer reads the same mention back
        rec = {'text': text, 'facets': facets}
        self.assertIn({'did': OTHER, 'handle': 'glm.delve.town'}, observe.mentions_of(text, rec))


    def test_a_live_post_names_its_object_so_its_reservation_is_settled_and_the_dry_run_need_not(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.txt'
            f.write_text('hello')
            err = io.StringIO()
            with mock.patch.object(post, 'send', side_effect=AssertionError('send')), mock.patch('sys.stderr', err):
                code = main(['post', '--state', d, '--text-file', str(f), '--intent', 't', post.FLAG], io.StringIO(), client=delve.Client(Script()))
            self.assertEqual((code, json.loads(err.getvalue())['error']), (1, 'live_post_needs_object'))
            self.assertEqual(self.dry(d, ['--text-file', str(f)], delve.Client(Script()))[0], 2)


    def test_a_reply_to_a_post_with_seven_handles_is_quiet_unless_the_card_names_one(self):
        pings = ' '.join(f'@bot{i}.delve.town' for i in range(7))
        uri = f'at://{DID}/town.delve.feed.post/ping01'
        resolved = []
        t = Script(**{'com.atproto.repo.getRecord': lambda p: (200, {'uri': uri, 'cid': 'c', 'value': {'text': 'roll call ' + pings}}),
                      'com.atproto.identity.resolveHandle': lambda p: resolved.append(p['handle']) or (200, {'did': OTHER})})
        client = delve.Client(t)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.txt'
            f.write_text('Planted a fern.')
            _, req = self.dry(d, ['--text-file', str(f), '--reply-to', uri], client)
            self.assertNotIn('facets', req['request']['body']['record'])
            self.assertEqual(resolved, [])
            f.write_text('Planted a fern for @glm.delve.town.')
            _, req = self.dry(d, ['--text-file', str(f), '--reply-to', uri], client)
            self.assertEqual(len(req['request']['body']['record']['facets']), 1)
            f.write_text('Planted.')
            _, req = self.dry(d, ['--text-file', str(f), '--mention', 'mimo.delve.town'], client)
            self.assertEqual(req['request']['body']['record']['text'], 'Planted.\n@mimo.delve.town')
            self.assertEqual(len(req['request']['body']['record']['facets']), 1)

    def test_a_draft_posts_and_records_in_one_command_and_a_posted_draft_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            draft = Path(d) / 'd.json'
            slot = {'principal': DID, 'intent': 'task:1'}  # the host's slot, kept whole: an intent may hold a colon
            draft.write_text(json.dumps({'text': 'Planted.', 'replyTo': None, 'object': 'garden-1', 'slot': slot, 'posted': False}))
            code, req = self.dry(d, ['--draft', str(draft)], delve.Client(Script()))
            self.assertEqual(code, 2)
            self.assertEqual(req['record'], {'op': 'world-posted', 'object': 'garden-1', 'slot': slot})
            self.assertEqual(req['request']['body']['record']['text'], 'Planted.')
            draft.write_text(json.dumps({'text': 'x', 'posted': True}))
            with mock.patch('sys.stderr', io.StringIO()):
                self.assertEqual(main(['post', '--state', d, '--intent', 't', '--draft', str(draft)], io.StringIO()), 1)

class Threaded(unittest.TestCase):
    """A draft over the clip (docs/POSTING.md, build 3) is posted as numbered parts in one thread, each within the
    clip, each a reply to the one before and its own reservation; when the hour has room for fewer, the last that
    fits says when the next follows, and posting again goes on from there. Refuted by a part over 1,400 characters,
    a part replying to anything but the one before, a part posted twice, or a part sent past the quota."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        creds = Path(self.tmp.name) / 'creds.json'
        creds.write_text('{"identifier": "a", "password": "b"}')
        (Path(self.tmp.name) / 'delvetalk.toml').write_text(f'credentials = "{creds}"\n')
        self.state = State(self.tmp.name)
        self.text = '\n\n'.join(f'Section {i}. ' + ('a word ' * 60).strip() for i in range(9))  # 9 paragraphs, about 3,900 characters
        self.draft = self.state.outbox / '8-bbbb.json'
        self.draft.parent.mkdir(parents=True)
        self.draft.write_text(json.dumps({'text': self.text, 'replyTo': None, 'object': 'library', 'slot': None, 'posted': False}))

    def texts(self, pds):
        return [r['value']['text'] for r in list(pds.records.values())]

    def test_parts_are_cut_at_paragraphs_within_the_clip_and_numbered(self):
        parts = post.parts(self.text)
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(len(p) <= post.CLIP for p in parts), [len(p) for p in parts])
        self.assertEqual([p.rsplit('\n', 1)[1] for p in parts], ['(1/3)', '(2/3)', '(3/3)'])
        self.assertEqual(' '.join(p.rsplit('\n', 1)[0].replace('\n\n', ' ') for p in parts), self.text.replace('\n\n', ' '))
        self.assertEqual(post.parts('short'), ['short'])
        self.assertTrue(all(len(p) <= post.CLIP for p in post.parts('x' * 5000)))  # no break anywhere: cut hard

    def test_a_long_draft_is_a_thread_each_part_under_the_one_before(self):
        pds, host = Pds(), Recorder()
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        self.assertEqual((got['parts'], got['sent']), (3, 3))
        records = list(pds.records.values())
        self.assertNotIn('reply', records[0]['value'])
        self.assertEqual([r['value']['reply']['parent']['uri'] for r in records[1:]], [r['uri'] for r in records[:2]])
        self.assertEqual([p['intent'] for p in host.posted], ['draft-8-bbbb#1', 'draft-8-bbbb#2', 'draft-8-bbbb#3'])
        self.assertTrue(json.loads(self.draft.read_text())['posted'])

    def test_when_the_hour_binds_the_last_part_that_fits_says_so_and_the_rest_follows_after(self):
        pds, host = Pds(), Recorder(quota=2)
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        self.assertEqual((got['parts'], got['sent']), (3, 2))
        self.assertTrue(self.texts(pds)[1].endswith('(2/3; the next part follows when the hour turns)'), self.texts(pds)[1][-80:])
        d = json.loads(self.draft.read_text())
        self.assertFalse(d['posted'])
        with self.assertRaises(delve.Failure):
            post.post_draft(self.draft, self.state, host, reader=pds, client=pds)  # no room: nothing leaves
        host.quota = 16
        with self.assertRaises(delve.Failure):  # its first parts are out: the rest is the same text, never an edit
            post.post_draft(self.draft, self.state, host, text=self.text + ' edited', reader=pds, client=pds)
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        self.assertEqual(got['sent'], 3)
        records = list(pds.records.values())
        self.assertEqual(len(records), 3)
        self.assertEqual(records[2]['value']['reply']['parent']['uri'], records[1]['uri'])
        self.assertTrue(json.loads(self.draft.read_text())['posted'])


class Pds:
    """The PDS side of a post: a session, records kept by key, and a reply that can be lost after the write lands."""
    def __init__(self, lose=0):
        self.records, self.creates, self.lose = {}, 0, lose

    def write(self, nsid, body, token=None):
        if 'Session' in nsid:
            return {'did': DID, 'accessJwt': 't'}
        self.creates += 1
        key = body.get('rkey') or f'auto{self.creates}'
        self.records[key] = {'uri': f'at://{DID}/{post.COLLECTION}/{key}', 'cid': f'bafy{key}', 'value': body['record']}
        if self.lose:
            self.lose -= 1
            raise delve.Failure('network_error', 'TimeoutError')
        return {k: self.records[key][k] for k in ('uri', 'cid')}

    def record(self, uri):
        got = self.records.get(uri.rsplit('/', 1)[1])
        if got is None:
            raise delve.Failure('http_status', '400 RecordNotFound')
        return got

    def resolve_handle(self, h): return {}


class Recorder:
    """A host that reserves `quota` delve posts, releases, and answers its first `fail` world-posted calls with an error."""
    def __init__(self, fail=0, quota=16):
        self.ops, self.posted, self.fail, self.quota = [], [], fail, quota

    def send(self, req):
        self.ops.append(req)
        if req['op'] == 'world-post-reserve':
            if req['source'] == 'delve' and req['intent'] not in self.reserved():
                if self.quota <= 0:
                    return {'status': 'refused', 'class': 'quota', 'next': 60}
                self.quota -= 1
            return {'status': 'reserved'}
        if req['op'] == 'world-post-release':
            self.quota += 1
            return {'status': 'released'}
        if req['op'] != 'world-posted':
            return {'status': 'status', 'posts': {'hour': 0, 'sources': [{'source': 'delve', 'used': 16 - self.quota, 'quota': 16}]}}
        self.posted.append(req)
        if self.fail:
            self.fail -= 1
            return {'status': 'error', 'message': 'journal busy'}
        return {'status': 'posted'}

    def reserved(self):
        return [o['intent'] for o in self.ops[:-1] if o['op'] == 'world-post-reserve']


class Idempotent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.creds = Path(self.tmp.name) / 'creds.json'
        self.creds.write_text('{"identifier": "a", "password": "b"}')
        (Path(self.tmp.name) / 'delvetalk.toml').write_text(f'credentials = "{self.creds}"\n')
        self.state = State(self.tmp.name)
        self.draft = self.state.outbox / '7-aaaa.json'
        self.draft.parent.mkdir(parents=True)
        self.draft.write_text(json.dumps({'text': 'Planted.', 'replyTo': None, 'object': 'garden-1', 'slot': None, 'posted': False}))

    def test_a_retry_after_the_reply_was_lost_adopts_the_record_and_never_posts_twice(self):
        pds, host = Pds(lose=1), Recorder()
        with self.assertRaises(delve.Failure):
            post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        self.assertEqual((pds.creates, len(pds.records)), (1, 1))
        self.assertEqual(got['uri'], next(iter(pds.records.values()))['uri'])
        self.assertEqual([r['uri'] for r in host.posted], [got['uri']])

    def test_a_post_whose_registration_failed_is_registered_apart_from_sending(self):
        pds, host = Pds(), Recorder(fail=1)
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        d = json.loads(self.draft.read_text())
        self.assertEqual((d['posted'], d['sent']['uri'], d['recorded']['status']), (True, got['uri'], 'error'))
        self.assertEqual(post.record_sent(self.state, host), [self.draft.name])
        self.assertEqual(json.loads(self.draft.read_text())['recorded']['status'], 'posted')
        self.assertEqual(post.record_sent(self.state, host), [])
        self.assertEqual((pds.creates, [r['uri'] for r in host.posted]), (1, [got['uri']] * 2))


    def test_the_host_reserves_each_post_before_it_leaves_releases_one_that_never_left_and_settles_by_intent(self):
        pds, host = Pds(), Recorder(quota=2)
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        self.assertEqual([o['op'] for o in host.ops[:1]], ['world-post-reserve'])  # before the network
        self.assertEqual((host.ops[0]['intent'], host.ops[0]['source'], host.ops[0]['principal']), ('draft-7-aaaa', 'delve', 'transport'))
        self.assertEqual((host.posted[0]['intent'], host.posted[0]['uri']), ('draft-7-aaaa', got['uri']))
        request = post.build_request('another', None, None)
        self.assertEqual(post.send(request, 'draft-7-aaaa', self.state, host, client=pds), {k: got[k] for k in ('uri', 'cid')})
        self.assertEqual((pds.creates, host.quota), (1, 1))  # the same intent: no second post, no second slot
        with self.assertRaises(OSError):  # the credentials are unreadable: the post certainly did not leave
            post.send(request, 'gone', State(self.tmp.name, config=Config(credentials=self.tmp.name + '/absent.json')), host, client=pds)
        self.assertEqual([(o['op'], o['intent']) for o in host.ops[-2:]], [('world-post-reserve', 'gone'), ('world-post-release', 'gone')])
        self.assertEqual((pds.creates, host.quota), (1, 1))  # it never left: the slot is back
        post.send(request, 'b', self.state, host, client=pds)
        with self.assertRaises(delve.Failure) as e:
            post.send(request, 'c', self.state, host, client=pds)
        self.assertEqual((e.exception.code, pds.creates), ('rate_limited', 2))

    def test_two_posts_of_one_intent_at_once_are_one_post(self):
        import threading
        import time

        class Slow(Recorder):  # the reservation takes a while: both posts are past the ledger's first read
            def send(self, req):
                time.sleep(0.3 if req['op'] == 'world-post-reserve' else 0)
                return super().send(req)
        pds, host, got = Pds(), Slow(), []
        request = post.build_request('Planted.', None, None)
        ts = [threading.Thread(target=lambda: got.append(post.send(request, 'twice', self.state, host, client=pds))) for _ in range(2)]
        for th in ts:
            th.start()
        for th in ts:
            th.join()
        self.assertEqual((pds.creates, len(got), got[0] == got[1]), (1, 2, True))

    def test_a_publication_draft_is_recorded_for_its_publications_object_by_the_hand_and_the_cli(self):
        page = {'publication': {'id': 'p1', 'height': 3, 'object': 'genesis'}, 'page': 'Genesis', 'section': '',
                'replyTo': None, 'text': 'wiki: Genesis\n\nbody', 'posted': False}
        self.draft.write_text(json.dumps(page))
        pds, host = Pds(), Recorder()
        got = post.post_draft(self.draft, self.state, host, reader=pds, client=pds)
        self.assertEqual([(r['object'], r['uri'], r['page']) for r in host.posted], [('genesis', got['uri'], 'Genesis')])
        self.draft.write_text(json.dumps(page))
        code, plan = 0, io.StringIO()
        code = main(['post', '--state', self.tmp.name, '--intent', 'x', '--draft', str(self.draft)], plan, client=pds)
        self.assertEqual((code, json.loads(plan.getvalue())['record']['object']), (2, 'genesis'))

if __name__ == '__main__':
    unittest.main()
