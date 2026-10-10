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


def run_observer(posts, state):
    t = Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                  'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
    ob = observe.Observer(state, delve.Client(t))
    ob.poll()
    out = []
    ob.drain(out.append)
    return [json.loads(x) for x in out], ob


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
            mk(8, 'delvetalk garden ?'),  # a spell or not is the host's parser's answer (bridge.spelled)
        ])
        self.assertEqual({k: v['kind'] for k, v in obs.items()},
                         {'00000' + str(i): k for i, k in enumerate(
                             ['wiki-page', 'wiki-edit', 'wiki-merge', 'summon', 'reply', 'reply', 'post', 'post'], 1)})
        self.assertEqual(obs['000001']['wiki'], {'op': 'page', 'title': 'GSB Welcome Message (v2)', 'section': None})
        self.assertEqual(obs['000002']['wiki']['section'], 'Beds')
        self.assertEqual(obs['000004']['mentions'], [{'did': OTHER, 'handle': 'livedelvetalk.delve.town'}])
        self.assertEqual(obs['000004']['tags'], ['gsb'])
        self.assertEqual(obs['000006']['replyTo'], BASE['uri'])
        self.assertEqual(set(obs['000006']), {'uri', 'cid', 'author', 'createdAt', 'text', 'replyTo', 'root',
                                              'mentions', 'tags', 'kind', 'wiki'})

    def test_a_summon_is_a_mention_of_the_portal_or_the_gsb_tag(self):
        obs, _ = self.kinds([mk(1, 'hello @livedelvetalk.delve.town'), mk(2, 'a #gsb post', parent=BASE['uri']),
                             mk(3, '#gsb\ndelvetalk garden plant'), mk(4, 'not delvetalk garden plant')])
        self.assertEqual([obs[k]['kind'] for k in sorted(obs)], ['summon', 'summon', 'summon', 'post'])

    def test_the_recorded_fixture_page_is_observed_with_over_twenty_posts_and_none_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ob = observe.Observer(d, delve.Client(delve.FixtureTransport(FIX)))
            ob.poll()
            out = []
            ob.drain(out.append)
        self.assertGreater(len(out), 20)
        self.assertEqual(ob.refused, [])

    def test_a_handle_mention_in_text_without_a_facet_is_still_a_summon(self):
        obs, _ = self.kinds([mk(1, 'hi @livedelvetalk.delve.town #GSB')])
        self.assertEqual(obs['000001']['kind'], 'summon')


class Idempotence(unittest.TestCase):
    def test_rerun_emits_nothing(self):
        posts = [mk(i, f'p{i}') for i in range(5)]
        with tempfile.TemporaryDirectory() as d:
            first, _ = run_observer(posts, d)
            second, _ = run_observer(posts, d)
        self.assertEqual((len(first), second), (5, []))

    def test_a_crash_mid_page_or_mid_emit_loses_and_repeats_no_post(self):
        posts = [mk(i, f'p{i}') for i in range(6)]
        with tempfile.TemporaryDirectory() as d:
            calls = {'n': 0}

            def search(p):
                calls['n'] += 1
                if calls['n'] > 1:
                    raise RuntimeError('crash')
                return 200, {'posts': posts[:3], 'cursor': 'c1'}
            t = Script(**{'town.delve.feed.searchPosts': search, 'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
            ob = observe.Observer(d, delve.Client(t))
            with self.assertRaises(RuntimeError):
                ob.poll()
            seen = []

            def die_on_second(js):
                if len(seen) == 1:
                    raise RuntimeError('crash during emit')
                seen.append(js)
            with self.assertRaises(RuntimeError):
                ob.drain(die_on_second)
            ob.db.close()
            out, _ = run_observer(posts, d)
        got = [json.loads(x)['uri'] for x in seen] + [o['uri'] for o in out]
        self.assertEqual(sorted(got), sorted(p['uri'] for p in posts))
        self.assertEqual(len(got), len(set(got)))


class Bounds(unittest.TestCase):
    def test_a_thousand_post_page_is_observed_whole(self):
        posts = [mk(i, f'wiki: T{i}\n#gsb @a.delve.town') for i in range(1000)]
        with tempfile.TemporaryDirectory() as d:
            obs, _ = run_observer(posts, d)
        self.assertEqual(len(obs), 1000)

    def test_one_mebibyte_body_refused_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            obs, ob = run_observer([mk(1, 'x' * (1 << 20)), mk(2, 'ok')], d)
        self.assertEqual([o['text'] for o in obs], ['ok'])
        self.assertEqual(ob.refused[0][0], 'post_body_too_large')

    def test_the_post_writer_refuses_a_one_mebibyte_text_as_post_body_too_large(self):
        with self.assertRaises(delve.Failure) as c:
            post.build_request('x' * (1 << 20))
        self.assertEqual(c.exception.code, 'post_body_too_large')

    def test_a_client_refuses_an_oversized_response_and_a_redirect_by_name(self):
        c = delve.Client(lambda *a: (200, b'{' + b' ' * delve.MAX_RESPONSE + b'}'))
        with self.assertRaises(delve.Failure) as e:
            c.search('x')
        self.assertEqual(e.exception.code, 'response_too_large')
        c = delve.Client(lambda *a: (302, b''))
        with self.assertRaises(delve.Failure) as e:
            c.search('x')
        self.assertEqual(e.exception.code, 'redirect_refused')

    def test_client_cannot_write_or_reach_other_endpoints(self):
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
        self.id = identity.Identity(self.tmp.name, delve.Client(self.t), clock=lambda: self.now[0])
        self.ch = self.id.challenge(self.HANDLE)
        self.uri = f'at://{DID}/town.delve.feed.post/3abc'

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, text=None, uri=None, status=200):
        self.record['r'] = lambda p: (status, {'uri': uri or self.uri, 'cid': 'bafyx',
                                               'value': {'text': self.ch['text'] if text is None else text}})

    def refused(self, code, uri=None):
        with self.assertRaises(identity.IdentityError) as e:
            self.id.verify(self.HANDLE, uri or self.uri)
        self.assertEqual(e.exception.code, code)

    def test_a_challenge_is_a_short_spoken_word_of_two_proquints(self):
        self.assertRegex(self.ch['text'], r'^[bdfghjklmnprstvz][aiou][bdfghjklmnprstvz][aiou][bdfghjklmnprstvz]-[bdfghjklmnprstvz][aiou][bdfghjklmnprstvz][aiou][bdfghjklmnprstvz]$')

    def listing(self, *records, status=200):
        self.t.routes['com.atproto.repo.listRecords'] = lambda p: (status, {'records': list(records)})
        return lambda text, n=1, repo=DID: {'uri': f'at://{repo}/town.delve.feed.post/{n}', 'cid': 'bafy' + str(n), 'value': {'text': text}}

    def test_a_claim_finds_the_word_among_the_newest_posts_and_logs_the_account_in(self):
        rec = self.listing()
        self.listing(rec('good morning', 1), rec('  ' + self.ch['text'] + ' \n', 2), rec('a later post', 3))
        got = self.id.claim(self.HANDLE)
        self.assertEqual((got['did'], got['uri']), (DID, f'at://{DID}/town.delve.feed.post/2'))
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)
        with self.assertRaises(identity.IdentityError) as e:
            self.id.claim(self.HANDLE)
        self.assertEqual(e.exception.code, 'challenge_consumed')

    def claim_refused(self, code):
        with self.assertRaises(identity.IdentityError) as e:
            self.id.claim(self.HANDLE)
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
        self.assertEqual(self.id.verify(self.HANDLE, self.uri)['did'], DID)
        self.assertEqual(self.id.authenticate(self.ch['credential'])['did'], DID)
        self.refused('challenge_consumed')

    def test_a_revoked_credential_cannot_authenticate_or_be_verified_again(self):
        self.serve()
        self.id.verify(self.HANDLE, self.uri)
        self.id.revoke(self.ch['credential'])
        with self.assertRaises(identity.IdentityError):
            self.id.authenticate(self.ch['credential'])
        self.refused('challenge_revoked')

    def test_unverified_credential_does_not_authenticate(self):
        with self.assertRaises(identity.IdentityError):
            self.id.authenticate(self.ch['credential'])

    def test_a_proof_post_by_another_did_is_refused_as_wrong_author(self):
        self.serve()
        self.refused('wrong_author', f'at://{OTHER}/town.delve.feed.post/3abc')

    def test_a_proof_post_that_merely_contains_the_challenge_text_is_refused_as_a_mismatch(self):
        self.serve(text='look: ' + self.ch['text'] + ' !')
        self.refused('proof_text_mismatch')

    def test_a_challenge_past_its_ttl_is_refused_as_expired(self):
        self.serve()
        self.now[0] += identity.TTL
        self.refused('challenge_expired')

    def test_a_redirect_when_fetching_the_proof_is_refused_as_proof_unavailable(self):
        self.serve(status=302)
        self.refused('proof_unavailable:redirect_refused')

    def test_a_record_returned_under_a_different_uri_is_refused_as_proof_mismatch(self):
        self.serve(uri=f'at://{DID}/town.delve.feed.post/other')
        self.refused('proof_mismatch')

    def test_a_newer_challenge_by_someone_else_does_not_invalidate_the_proof_of_mine(self):
        self.now[0] += 1
        theirs = self.id.challenge(self.HANDLE)  # anyone may ask for a challenge for any handle, a second later
        self.serve()  # the resident posts the word of the challenge they asked for
        self.assertEqual(self.id.verify(self.HANDLE, self.uri)['did'], DID)
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

    def test_ninth_attempt_refused_even_if_correct(self):
        self.serve(text='nope')
        for _ in range(8):
            self.refused('proof_text_mismatch')
        self.serve()
        self.refused('too_many_attempts')

    def test_a_non_delve_handle_gets_no_challenge_and_a_malformed_proof_uri_is_refused(self):
        with self.assertRaises(identity.IdentityError):
            self.id.challenge('evil.example.com')
        self.refused('invalid_proof_uri', 'at://x/y/z')



class Posting(unittest.TestCase):
    def test_no_flag_sends_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.txt'
            f.write_text('hello')
            out = io.StringIO()
            with mock.patch.object(urllib.request.OpenerDirector, 'open', side_effect=AssertionError('network')) as op, \
                    mock.patch.object(post, 'send', side_effect=AssertionError('send')):
                code = post.main(['--state', d, 'post', '--text-file', str(f), '--intent', 'test',
                                  '--credentials', str(Path(d) / 'absent.json')], out)
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
        code = post.main(['--state', d, 'post', '--intent', 't', *args], out, client)
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

    def test_reply_to_a_reply_keeps_the_thread_root(self):
        root = {'uri': f'at://{DID}/town.delve.feed.post/root01', 'cid': 'bafyroot'}
        got = {'uri': f'at://{DID}/town.delve.feed.post/r2', 'cid': 'bafyr2', 'value': {'reply': {'root': root, 'parent': root}}}
        client = delve.Client(Script(**{'com.atproto.repo.getRecord': lambda p: (200, got)}))
        ref = post.reply_ref(client, got['uri'])
        self.assertEqual(ref, {'root': root, 'parent': {'uri': got['uri'], 'cid': 'bafyr2'}})

    def test_wiki_page_and_edit_texts(self):
        uri, client, _, _ = self.parent()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'b.txt'
            f.write_text('Body line')
            _, page = self.dry(d, ['--wiki-page', 'GSB Welcome', '--body-file', str(f)], client)
            _, edit = self.dry(d, ['--wiki-edit', 'GSB Welcome \u203a Intro', '--body-file', str(f), '--reply-to', uri], client)
        self.assertEqual(page['request']['body']['record']['text'], 'wiki: GSB Welcome\n\nBody line')
        self.assertNotIn('reply', page['request']['body']['record'])
        self.assertEqual(edit['request']['body']['record']['text'], 'edit: GSB Welcome \u203a Intro\n\nBody line')
        self.assertIn('reply', edit['request']['body']['record'])
        # the observer reads back what the writer writes
        self.assertEqual(observe.classify(page['request']['body']['record']['text'], None, [], [])[0], 'wiki-page')
        self.assertEqual(observe.classify(edit['request']['body']['record']['text'], uri, [], [])[0], 'wiki-edit')

    def test_wiki_edit_needs_a_page_to_reply_to_and_flag_off_sends_nothing(self):
        uri, client, t, _ = self.parent()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'b.txt'
            f.write_text('x')
            with mock.patch.object(post, 'send', side_effect=AssertionError('send')):
                self.assertEqual(post.main(['--state', d, 'post', '--intent', 't', '--wiki-edit', 'A \u203a B', '--body-file', str(f)], io.StringIO(), client), 1)
                self.assertEqual(post.main(['--state', d, 'post', '--intent', 't', '--text-file', str(f), '--reply-to', uri], io.StringIO(), client), 2)
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

    def test_dry_run_shows_facets_and_the_quota_source(self):
        t = Script(**{'com.atproto.identity.resolveHandle': lambda p: (200, {'did': OTHER})})
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.txt'
            f.write_text('ping @glm.delve.town')
            code, req = self.dry(d, ['--text-file', str(f)], delve.Client(t))
        self.assertEqual((code, req['quota']), (2, {'limit': 16, 'source': 'constant'}))
        self.assertEqual(req['request']['body']['record']['facets'][0]['features'][0]['did'], OTHER)

    def test_quota_comes_from_the_host_when_it_has_one(self):
        class H:
            def send(self, r): return {'status': 'world', 'postQuota': 3}
        self.assertEqual(post.quota_limit(H()), (3, 'host'))
        self.assertEqual(post.quota_limit(type('H', (), {'send': lambda s, r: {'status': 'world'}})()), (16, 'constant'))
        with tempfile.TemporaryDirectory() as d:
            for _ in range(3):
                post.take_slot(Path(d), 1.0, 3)
            with self.assertRaises(delve.Failure):
                post.take_slot(Path(d), 2.0, 3)

    def test_record_posted_builds_world_posted_from_the_confirmed_result(self):
        seen = []
        h = type('H', (), {'send': lambda s, r: seen.append(r) or {'status': 'posted'}})()
        post.record_posted(h, {'uri': f'at://{DID}/town.delve.feed.post/x1', 'cid': 'bafyc'}, 'directory', post.slot_record(f'{DID}:welcome-1'))
        self.assertEqual(seen, [{'op': 'world-posted', 'principal': 'transport', 'uri': f'at://{DID}/town.delve.feed.post/x1',
                                 'cid': 'bafyc', 'object': 'directory', 'slot': {'principal': DID, 'intent': 'welcome-1'}}])
        for bad in ('welcome', ':x', 'x:'):
            with self.assertRaises(delve.Failure):
                post.slot_record(bad)

    def test_record_without_a_journal_is_refused_before_anything_happens(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 't.txt'
            f.write_text('x')
            with mock.patch.object(post, 'send', side_effect=AssertionError('send')):
                code = post.main(['--state', d, 'post', '--intent', 't', '--text-file', str(f), '--record', 'directory'], io.StringIO())
        self.assertEqual(code, 1)

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
            draft.write_text(json.dumps({'text': 'Planted.', 'replyTo': None, 'object': 'garden-1', 'slot': f'{DID}:ask-1', 'posted': False}))
            code, req = self.dry(d, ['--draft', str(draft), '--host-socket', str(Path(d) / 'nope.sock')], delve.Client(Script()))
            self.assertEqual(code, 2)
            self.assertEqual(req['record'], {'op': 'world-posted', 'object': 'garden-1', 'slot': {'principal': DID, 'intent': 'ask-1'}})
            self.assertEqual(req['request']['body']['record']['text'], 'Planted.')
            draft.write_text(json.dumps({'text': 'x', 'posted': True}))
            self.assertEqual(post.main(['--state', d, 'post', '--intent', 't', '--draft', str(draft)], io.StringIO()), 1)

    def test_the_post_slot_limit_refuses_one_more_in_the_window_and_frees_after_it(self):
        with tempfile.TemporaryDirectory() as d:
            for _ in range(post.LIMIT):
                post.take_slot(Path(d), 5000.0)
            with self.assertRaises(delve.Failure):
                post.take_slot(Path(d), 5001.0)
            post.take_slot(Path(d), 5000.0 + post.WINDOW + 1)


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
    """A host whose first `fail` world-posted calls answer an error."""
    def __init__(self, fail=0):
        self.posted, self.fail = [], fail

    def send(self, req):
        if req['op'] != 'world-posted':
            return {'status': 'status', 'postQuota': 16}
        self.posted.append(req)
        if self.fail:
            self.fail -= 1
            return {'status': 'error', 'message': 'journal busy'}
        return {'status': 'posted'}


class Idempotent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.creds = self.state / 'creds.json'
        self.creds.write_text('{"identifier": "a", "password": "b"}')
        self.draft = self.state / 'outbox' / '7-aaaa.json'
        self.draft.parent.mkdir()
        self.draft.write_text(json.dumps({'text': 'Planted.', 'replyTo': None, 'object': 'garden-1', 'slot': None, 'posted': False}))

    def test_a_retry_after_the_reply_was_lost_adopts_the_record_and_never_posts_twice(self):
        pds, host = Pds(lose=1), Recorder()
        with self.assertRaises(delve.Failure):
            post.post_draft(self.draft, self.state, host, self.creds, reader=pds, client=pds)
        got = post.post_draft(self.draft, self.state, host, self.creds, reader=pds, client=pds)
        self.assertEqual((pds.creates, len(pds.records)), (1, 1))
        self.assertEqual(got['uri'], next(iter(pds.records.values()))['uri'])
        self.assertEqual([r['uri'] for r in host.posted], [got['uri']])

    def test_a_post_whose_registration_failed_is_registered_apart_from_sending(self):
        pds, host = Pds(), Recorder(fail=1)
        got = post.post_draft(self.draft, self.state, host, self.creds, reader=pds, client=pds)
        d = json.loads(self.draft.read_text())
        self.assertEqual((d['posted'], d['sent']['uri'], d['recorded']['status']), (True, got['uri'], 'error'))
        self.assertEqual(post.record_sent(self.state, host), [self.draft.name])
        self.assertEqual(json.loads(self.draft.read_text())['recorded']['status'], 'posted')
        self.assertEqual(post.record_sent(self.state, host), [])
        self.assertEqual((pds.creates, [r['uri'] for r in host.posted]), (1, [got['uri']] * 2))


    def test_a_publication_draft_is_recorded_for_its_publications_object_by_the_hand_and_the_cli(self):
        page = {'publication': {'id': 'p1', 'height': 3, 'object': 'genesis'}, 'page': 'Genesis', 'section': '',
                'replyTo': None, 'text': 'wiki: Genesis\n\nbody', 'posted': False}
        self.draft.write_text(json.dumps(page))
        pds, host = Pds(), Recorder()
        got = post.post_draft(self.draft, self.state, host, self.creds, reader=pds, client=pds)
        self.assertEqual([(r['object'], r['uri'], r['page']) for r in host.posted], [('genesis', got['uri'], 'Genesis')])
        self.draft.write_text(json.dumps(page))
        code, plan = 0, io.StringIO()
        code = post.main(['--state', str(self.state), 'post', '--intent', 'x', '--draft', str(self.draft),
                          '--host-socket', str(self.state / 'none.sock')], plan, pds)
        self.assertEqual((code, json.loads(plan.getvalue())['record']['object']), (2, 'genesis'))

if __name__ == '__main__':
    unittest.main()
