"""The bridge turns observed posts into turns in creation order, routes a reply by its nearest
recorded ancestor, and drafts each offer once, never posting.

Evidence for FOUNDATION §7 (layer: transport).
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import genesis
from deploy.genesis import DOORS, STUDIO
from tests import test_outbound
from tests.test_receive import door
from tests.test_chain import town_garden
from tests.test_transport import DID, Script, mk
from transport import bridge, delve, observe
from tests.host import ServeCase, served
from transport.config import Config
from transport.host import HostClient, PUBLIC, typed
from transport.hand import Hand
from transport.state import State
from tests.wire import label, listing, nat, record
from tests.bend import closure, declared

CARD = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  seen: Nat
%s
def initial() -> State:
  {seen: 5n}
def act(context: Abi.Context) -> Activity<Nat>:
%s
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Nat>:
  act(context)
def plant(state: State, input: {seed: String, colour: String}, context: Abi.Context) -> Activity<Nat>:
  act(context)
""")
OFFERING = """  match world.offer({to: "", document: Document.text(textConcat("hello ", context.principal))}):
    case offered(_): 1n
    case _: 0n"""
REFUSING = """  match world.write(extend(keep(), {seen: Plans.Edit::<Nat, Nat>.set({value: 0n})})):
    case written(_): 1n
    case _: 0n"""


def modules(body, law=''):
    return closure('Document', 'World') + [{'name': 'Card', 'source': CARD % (law, body)}]


def spell_post(n, card, ts):
    p = mk(n, f'delvetalk {card} plant\nseed: a\ncolour: amber')
    p['record']['createdAt'] = ts
    return p


def summon_post(n, ts):
    p = mk(n, '@livedelvetalk.delve.town hi #gsb')
    p['record']['createdAt'] = ts
    return p


LOOPBACK = Config(origin='http://127.0.0.1:8765')  # a front only this machine opens: drafts cite no link (bridge.reachable)


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = State(Path(self.tmp.name) / 'state', config=LOOPBACK)
        self.state.append(self.state.taught, DID)  # not a newcomer: a first reply's next moves are test_posting's

    @property
    def host(self):
        """A `serve` of this test's own, started by the first test that talks to a real host
        (the routing tests drive a Stub and never do)."""
        if '_host' not in self.__dict__:
            serving = served(str(Path(self.tmp.name) / 'serve'), cleanup=self.addCleanup)
            self._host = HostClient(serving.sock)
        return self._host

    def make(self, name, body=OFFERING, law='', **more):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-' + name, 'object': name,
                            'modules': modules(body, law), 'entry': 'initial', 'seed': record(seen=nat(5)), **more})
        self.assertEqual(r['status'], 'created', r)

    def observe(self, posts):
        t = Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                      'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})
        ob = observe.Observer(self.state, delve.Client(t))
        ob.poll()
        ob.db.close()

    def drafts(self):
        return [json.loads(p.read_text()) for p in sorted(self.state.outbox.glob('*.json'),
                                                         key=lambda p: int(p.name.split('-')[0]))]

    def run_bridge(self):
        return bridge.run(self.state, self.host)


class DirectReplies(BridgeCase):
    """A reply in a card's own thread is addressed to it: the commonplace hears prose naming
    nothing (and no policy to read it) as a turn that offers nothing, so no reply is drafted."""

    def test_prose_naming_nothing_in_the_commonplaces_thread_is_heard_and_drafts_no_reply(self):
        cites = [door(*d) for d in DOORS] + [door(STUDIO[0], '', (), STUDIO[1])]
        made = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-commonplace', 'object': 'commonplace',
                               'modules': closure('Menu', 'Policies', 'Record'), 'entry': 'initial', 'law': genesis.RECORD_LAW,
                               'seed': record(owner=label('ember'), keeper=label('ember'), head=label('THE COMMONPLACE'), cites=listing(cites))})
        self.assertEqual(made['status'], 'created', made)
        body = self.host.send({'op': 'world-reprogram', 'principal': 'ember', 'identity': 'body-commonplace', 'object': 'commonplace', 'version': 0,
                               'package': genesis.body_of('commonplace'), 'mode': 'extend'})
        self.assertEqual(body['status'], 'admitted', body)
        hub = 'at://did:plc:ember/town.delve.feed.post/hub'
        self.host.send({'op': 'world-post-reserve', 'principal': 'transport', 'intent': 'hub', 'source': 'delve'})  # a post settles its reservation
        recorded = self.host.send({'op': 'world-posted', 'principal': 'transport', 'uri': hub, 'cid': 'bafyhub', 'object': 'commonplace', 'intent': 'hub'})
        self.assertNotEqual(recorded.get('status'), 'error', recorded)
        posts = [mk(n, text, parent=hub) for n, text in enumerate(('hello, what is this?', 'lovely evening', 'thanks all'), 1)]
        for n, p in enumerate(posts):
            p['record']['createdAt'] = '2026-10-09T10:00:0%dZ' % n
        self.observe(posts)
        self.run_bridge()
        texts = [d['text'] for d in self.drafts()]
        self.assertEqual(texts, ['', '', ''])  # three journaled turns, none with words to post
        self.assertEqual([d['object'] for d in self.drafts()], ['commonplace'] * 3)


class OpenerPosts(BridgeCase):
    """The opener's privileges are the root socket's, which the bridge never holds (HOST-HANDOFF §5 "Serve"); her
    ordinary turns are the public socket's: a post by the opener runs as a resident's turn, not skipped."""

    @property
    def host(self):
        if '_host' not in self.__dict__:
            serving = served(str(Path(self.tmp.name) / 'serve'), cleanup=self.addCleanup, opener=DID)
            self._host = HostClient(serving.sock)
        return self._host

    def test_a_post_by_the_opener_runs_as_a_residents_turn(self):
        self.make('garden-1')
        post = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        self.observe([post])
        got = self.run_bridge()
        self.assertEqual((got['turns'], got['failed']), ([post['uri']], []), got)
        skipped = self.state.skipped
        self.assertFalse(skipped.exists() and post['uri'] in skipped.read_text().split())
        self.assertEqual(self.run_bridge()['turns'], [])


class Bridging(BridgeCase):

    def test_three_posts_three_turns_in_created_order_then_nothing(self):
        self.make('garden-1')
        self.make('commonplace')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:03Z'), summon_post(2, '2026-10-09T10:00:01Z'),
                      spell_post(3, 'garden-1', '2026-10-09T10:00:02Z')])
        first = self.run_bridge()
        order = [u[-6:] for u in first['turns']]
        self.assertEqual(order, ['000002', '000003', '000001'])
        drafts = self.drafts()
        self.assertEqual(len(drafts), 3)
        self.assertEqual([d['replyTo'][-6:] for d in drafts], order)
        for d in drafts:
            self.assertFalse(d['posted'])
            self.assertFalse(d['principalVerified'])
            self.assertEqual((d['principal'], d['replyHandle']), (DID, 'talkie.delve.town'))
            self.assertEqual(d['text'], f"hello {DID}\n{bridge.receipt_line(d['receipt'])}")
        self.assertEqual(self.run_bridge(), {'turns': [], 'failed': []})
        self.assertEqual(len(self.drafts()), 3)

    def test_a_post_of_two_spells_is_two_turns_and_one_draft_with_both_lines(self):
        self.make('garden-1')
        p = mk(1, 'delvetalk garden-1 plant\ndelvetalk garden-1 plant')
        self.observe([p])
        self.assertEqual(self.run_bridge()['turns'], [p['uri']])
        (d,) = self.drafts()
        receipts = [self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': f"{p['uri']}#{n}"})['receipt'] for n in (1, 2)]
        self.assertEqual(d['receipt']['hash'], receipts[1]['hash'])
        self.assertEqual(d['text'], ''.join(bridge.receipt_line(r) for r in receipts))  # the lines, no cards: three fit one reply

    def test_a_plan_is_one_turn_one_draft_and_one_post_of_the_quota(self):
        """A plan (HOST-HANDOFF §5 "Plans and try") is one turn under the post's identity: one draft, so one post of the town's hour,
        its acts' lines above the receipt; a refused plan's draft names the act."""
        self.make('garden-1')
        p = mk(1, 'delvetalk plan\ndelvetalk garden-1 plant / seed: a / colour: amber\ndelvetalk garden-1 plant / seed: b / colour: amber')
        q = mk(2, 'delvetalk plan\ndelvetalk garden-1 plant / seed: a / colour: amber\ndelvetalk garden-1 prune')
        q['record']['createdAt'] = '2026-10-09T10:00:09Z'
        self.observe([p, q])
        self.assertEqual(self.run_bridge()['turns'], [p['uri'], q['uri']])
        d, e = self.drafts()
        self.assertEqual(d['receipt']['identity']['intent'], p['uri'])
        self.assertEqual(e['receipt']['height'], d['receipt']['height'] + 1)  # one entry a plan
        self.assertIn('1. delvetalk garden-1 plant / seed: a / colour: amber: done\n2. delvetalk garden-1 plant / seed: b / colour: amber: done\n', d['text'])
        self.assertTrue(e['text'].startswith('act 2 of 2 refused, so none of the plan was done:\nrefused noAction: act 2 (delvetalk garden-1 prune)'), e['text'])

    def test_crash_between_turn_and_draft_recovers_with_the_same_receipt(self):
        self.make('garden-1')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        with mock.patch.object(State, 'write', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                self.run_bridge()
        self.assertEqual(self.drafts(), [])
        uri = f'at://{DID}/town.delve.feed.post/r000001'
        before = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': uri})['receipt']
        self.run_bridge()
        (d,) = self.drafts()
        self.assertEqual(d['receipt']['hash'], before['hash'])
        self.assertEqual(self.host.send({'op': 'world-status'})['height'], before['height'])  # no second turn
        self.assertEqual(d['receipt']['height'], before['height'])
        self.assertNotIn('not retained', d['text'])  # the journal retains offers: the retry has the card

    def test_refused_spell_yields_a_refusal_draft_with_class_and_no_state(self):
        self.make('stern', REFUSING, 'law seen: monotone(seen)\n')
        self.observe([spell_post(1, 'stern', '2026-10-09T10:00:00Z')])
        self.run_bridge()
        (d,) = self.drafts()
        self.assertTrue(d['text'].startswith("refused "), d['text'])
        self.assertNotIn('proposal observed', d['text'])
        import re
        self.assertFalse(re.search(r'bafy|[0-9a-f]{64}', d['text']), d['text'])
        self.assertTrue(d['text'].startswith('refused seen: stern\nreceipt '), d['text'])  # the clause names the law line; no state value


    def test_host_error_without_receipt_leaves_the_post_for_retry(self):
        self.make('garden-1')
        p = mk(1, 'delvetalk garden-1 plant\nseed: a')
        self.observe([p])
        with mock.patch.object(self.host, 'send', return_value={'status': 'error', 'message': 'boom'}):
            r = self.run_bridge()
        self.assertEqual((r['turns'], r['failed'][0]['message']), ([], 'boom'))
        self.assertEqual(self.run_bridge()['turns'], [p['uri']])


    def test_a_spell_post_to_a_real_garden_is_bridged_into_a_draft_saying_planted(self):
        town_garden(lambda **q: self.host.send(q), id='garden-1')
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        (d,) = self.drafts()
        self.assertIn('planted', d['text'])
        self.assertTrue(d['text'].endswith(f"● admitted garden-1 v1, entry {d['receipt']['height']}, receipt {d['receipt']['slug']}\n"), d['text'])


    def test_a_preview_is_drafted_under_the_card_it_tries_never_the_word_try(self):
        """Refuted by gsb's draft `0-e59ba2be855e712f` (2026-10-14): a `delvetalk try` post drafted under `try`, which the
        host answers `unknown object try` at every registration, once a bridge poll, since."""
        from tests.town import Town
        town = Town(str(Path(self.tmp.name) / 'town'), cleanup=self.addCleanup)
        host = type('TownHost', (), {'send': lambda _, req: town.send(**req)})()
        post = mk(1, 'delvetalk try\n  delvetalk bell/1 tend')
        self.observe([post])
        self.assertEqual(bridge.run(self.state, host)['failed'], [])
        (d,) = [d for d in self.drafts() if d.get('replyTo') == post['uri']]
        self.assertEqual((d['preview'], d['object']), (True, 'bell/1'), d)
        self.assertTrue(d['text'].startswith('preview, nothing done'), d['text'])

    def test_the_host_refuses_a_post_naming_no_object_and_journals_nothing(self):
        """Refuted by a thrown error (which the transport asks again at every poll) or by an entry for it."""
        from transport.host import CLOCK
        before = self.host.send({'op': 'world-status', 'principal': CLOCK})['height']
        got = self.host.send({'op': 'world-posted', 'principal': CLOCK, 'uri': f'at://{DID}/town.delve.feed.post/p9', 'cid': 'c', 'object': 'try', 'intent': 'feed-9'})
        self.assertEqual((got['status'], got['class']), ('refused', 'unknownObject'), got)
        self.assertEqual(self.host.send({'op': 'world-status', 'principal': CLOCK})['height'], before)

    def test_a_registration_the_host_refuses_is_final_and_one_it_never_answered_is_retried(self):
        """Refuted by a registration asked again at every poll after the host refused it (gsb's `error op=world-posted`
        254 times), or by a host error or timeout treated as a refusal."""
        from transport import post as posting
        answers = []

        class Host:
            def send(self, req):
                answers.append(req['op'])
                return reply[0]
        uri = f'at://{DID}/town.delve.feed.post/p1'
        for name, first, final in (('refused', {'status': 'refused', 'class': 'unknownObject', 'message': 'unknown object try'}, True),
                                   ('unavailable', {'status': 'error', 'class': 'hostUnavailable', 'message': 'down'}, False),
                                   ('error', {'status': 'error', 'message': 'busy'}, False)):
            with self.subTest(name):
                answers.clear()
                reply = [first]
                path = self.state.outbox / f'9-{name}.json'
                self.state.write(path, {'object': 'try', 'text': 'preview', 'posted': True, 'sent': {'uri': uri, 'cid': 'c'},
                                        'sentParts': [{'uri': uri, 'cid': 'c', 'part': 1, 'intent': 'feed-9', 'text': 'preview'}]})
                posting.record_sent(self.state, Host())
                posting.record_sent(self.state, Host())
                self.assertEqual(len(answers), 1 if final else 2)
                path.unlink()


class Private(BridgeCase):
    """A reply is posted where everyone reads it: what a turn offered from a thing the public may not read is the
    author's alone, so its draft carries the receipt line and not the offer."""

    def test_a_public_guide_read_uses_the_same_request_as_the_public_reader_and_drafts_its_whole_reply(self):
        post = mk(1, 'delvetalk guide')
        self.observe([post])
        stub = Stub({post['uri']: {'status': 'reached', 'object': 'commonplace', 'how': 'spell'}})
        send = stub.send
        head = 'hob: the guide, in the town.\n'
        public = head + 'x' * (observe.MAX_TEXT - len(head))
        def answer(request):
            if request['op'] in ('world-turn', 'world-try'):
                stub.ops.append(request)
                return {'status': 'admitted', 'tried': True, 'inPublic': True, 'offers': [{'principal': PUBLIC, 'text': public}],
                        'receipt': {'outcome': {'tag': 'admitted', 'writes': []}}} if request['principal'] == PUBLIC else {'status': 'usage', 'text': 'caller-only guide note'}
            return send(request)
        stub.send = answer
        self.assertEqual(bridge.run(self.state, stub)['failed'], [])
        self.assertEqual(self.drafts()[0]['text'], public)
        caller, projected = [r for r in stub.ops if r['op'] in ('world-turn', 'world-try')]
        self.assertEqual(projected['argument'], caller['argument'])
        self.assertEqual(projected['object'], caller['object'])
        self.assertEqual((projected['op'], projected['principal']), ('world-try', PUBLIC))

    def test_alices_book_of_a_diary_only_she_reads_drafts_no_diary_text(self):
        from tests.town import Town
        from deploy.seed import closure, modules_on_disk
        town = Town(str(Path(self.tmp.name) / 'town'), cleanup=self.addCleanup, furnished=False)
        town.send(op='world-arrive', principal='transport', did=DID, handle='alice.delve.town')
        created = town.send(op='world-create', principal=DID, identity='alice-diary', object='alice-diary',
                            modules=closure('Record', modules_on_disk()), entry='initial', law=genesis.RECORD_LAW,
                            read={'principals': [DID]}, seed=genesis.rec(owner=genesis.lab(DID), maker=genesis.lab(DID), makerHandle=genesis.lab('alice.delve.town')))
        self.assertEqual(created['status'], 'created', created)
        caller = town.client.send({'op': 'world-turn', 'principal': DID, 'object': 'me', 'method': 'receive', 'identity': 'read-diary',
                                   'argument': record(text=label('delvetalk me book'), post=label(''))})
        self.assertEqual(caller['status'], 'usage', caller)
        self.assertIn('alice-diary', caller.get('whole') or caller['text'])
        post = mk(1, 'delvetalk me book')
        self.observe([post])
        bridge.run(self.state, town.client)
        (draft,) = [d for d in self.drafts() if d['replyTo'] == post['uri']]
        self.assertNotIn('alice-diary', draft['text'])
        self.assertIn("its reader's", draft['text'])

    def test_a_callers_book_text_never_enters_a_public_draft_even_at_the_observation_limit(self):
        prefix = 'delvetalk diary reveal\n'
        for secret in ('Alice alone reads this diary.', prefix + 'x' * (observe.MAX_TEXT - len(prefix))):
            with self.subTest(length=len(secret)):
                reply = {'status': 'usage', 'text': secret, 'whole': secret, 'paint': {'day': 1}}
                self.assertFalse(secret in bridge.draft_text(reply))
                self.assertIn("its reader's", bridge.draft_text(reply))

    def test_a_private_usage_child_and_private_preview_never_publish_the_callers_words(self):
        secret = 'Alice alone reads this diary.'
        stub = Spells(['admitted', 'usage'])
        send = stub.send
        def answer(req):
            r = send(req)
            if r.get('status') == 'spells':
                r['turns'][1].update(text=secret, whole=secret)
            return r
        stub.send = answer
        self.observe([mk(1, 'delvetalk bell-1 rain\ntext: hello\ndelvetalk me book')])
        bridge.run(self.state, stub)
        self.assertNotIn(secret, self.drafts()[0]['text'])
        self.assertNotIn(secret, bridge.preview_text({'tried': True, 'status': 'spells', 'turns': [{'status': 'usage', 'text': secret}]}))

    def test_an_offer_from_a_thing_only_its_reader_may_read_is_not_drafted_into_a_public_reply(self):
        self.make('diary', read={'principals': [DID]})
        self.make('garden-1')
        self.observe([spell_post(1, 'diary', '2026-10-09T10:00:00Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:01Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        private, public = self.drafts()
        self.assertEqual(private['text'], bridge.receipt_line(private['receipt']))
        self.assertEqual(public['text'], f"hello {DID}\n{bridge.receipt_line(public['receipt'])}")
        # Whether a draft may carry the offers is the host's answer (`inPublic`), never a `world-view` per object (simplify (1)).
        for d, seen in ((private, False), (public, True)):
            r = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': d['receipt']['identity']['intent']})
            self.assertEqual(r.get('inPublic'), seen, r)


class HostParses(BridgeCase):
    """Whether a post is a spell, and to which card, is the host's answer (`world-reach` reads it with its parser), never Python's."""
    def test_a_standalone_question_mark_spell_reaches_the_card_and_is_answered_with_its_public_usage(self):
        self.make('garden-1')
        post = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        post['record']['text'] = 'delvetalk garden-1 ?'
        self.observe([post])
        got = self.run_bridge()
        self.assertEqual(got['turns'], [post['uri']], got)
        (d,) = self.drafts()
        self.assertTrue(d['usage'], d)
        self.assertIn('delvetalk garden-1', d['text'])
        self.assertEqual(self.run_bridge()['turns'], [])  # answered once, not retried

    def test_a_line_the_host_does_not_read_as_a_spell_is_not_routed_by_its_second_word(self):
        self.make('garden-1')
        post = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        post['record']['text'] = f"delvetalk {'g' * 129} plant\nseed: a\ncolour: amber"  # past 128 bytes the host reads no card
        self.observe([post])
        got = self.run_bridge()
        self.assertEqual((got['turns'], self.drafts()), ([], []), got)


class Stub:
    """A host that answers from canned data and records everything it is sent."""
    RESUMED = {'hash': 'h', 'height': 9, 'slug': 'lodif-rukuz', 'outcome': {'tag': 'admitted'}, 'roots': [{'object': 'garden-1', 'version': 1}]}
    def __init__(self, reaches=None, mentions=4):
        self.ops, self.reaches, self.suspending, self.offers, self.silent = [], reaches or {}, set(), {}, set()
        self.mentions = mentions

    def send(self, req):
        self.ops.append(req)
        op = req['op']
        if op == 'world-reach':  # the host's answer, by the post (tests/test_reach.py checks the host's own): else a spell
            lines = [l.split() for l in req['text'].split('\n') if l.startswith('delvetalk ') and len(l.split()) > 2]  # line's card, a summons the commonplace
            return self.reaches.get(req['uri']) or ({'status': 'reached', 'object': lines[-1][1], 'how': 'spell'} if lines else
                {'status': 'reached', 'object': 'commonplace', 'how': 'mention'} if req['kind'] == 'summon' else {'status': 'unreached'})
        if op == 'world-offers':
            return {'status': 'offers', 'offers': self.offers.get(req['principal'], []), 'more': False}
        if op == 'world-turn' and req['object'] in self.suspending:
            return {'status': 'suspended', 'receipt': {'hash': 'h', 'height': 5, 'outcome': {'tag': 'suspended'}}}
        if op == 'world-turn':
            return {'status': 'admitted', 'receipt': {'hash': 'h', 'height': len(self.ops), 'outcome': {'tag': 'admitted'}}, 'inPublic': True,
                    **({} if req['object'] in self.silent else {'offers': [{'principal': req['principal'], 'text': 'to ' + req['object']}]})}
        if op == 'world-receipt':  # a suspended turn stays suspended until its offer is there
            return {'status': 'receipt', 'receipt': self.RESUMED, 'inPublic': True} if self.offers.get(req['principal']) else \
                {'status': 'receipt', 'receipt': {'outcome': {'tag': 'suspended'}}}
        if op == 'world-pending':
            return {'status': 'pending', 'count': 0}
        if op == 'bounds':
            return {'status': 'bounds', 'host': {'mentionsAddressed': self.mentions}}
        if op == 'world-publications':
            return {'status': 'publications', 'publications': [], 'more': False}
        return {'status': 'ok'}


class Reaching(BridgeCase):
    """Where a post reaches is the host's (`world-reach`): the bridge passes the post and the ancestors it saw with their
    authors, sends the turn the host's answer names, and skips, once, a post that reaches nothing."""
    def test_the_bridge_passes_what_it_saw_and_turns_where_the_host_says(self):
        u = lambda n: f'at://{DID}/town.delve.feed.post/{n}'
        reached = lambda obj, how, replyTo=None: {'status': 'reached', 'object': obj, 'how': how, **({'replyTo': replyTo} if replyTo else {})}
        posts = [mk(1, 'a fern, please', parent=u('card')), mk(2, 'plant: a bell', parent=u(1)), mk(3, 'the anthology', parent=u(2)),
                 mk(4, 'chatter', parent=u(3)), summon_post(5, '2026-10-09T10:00:09Z')]
        for i, p in enumerate(posts[:4]):
            p['uri'] = u(i + 1)
            p['record']['createdAt'] = f'2026-10-09T10:00:0{i}Z'
        stub = Stub({u(1): reached('garden-1', 'reply', u('card')), u(2): reached('garden-1', 'fields'), u(3): reached('anthology', 'door'),
                     posts[4]['uri']: reached('commonplace', 'mention')})
        self.observe(posts)
        r = bridge.run(self.state, stub)
        asked = {o['uri']: o for o in stub.ops if o['op'] == 'world-reach'}
        self.assertEqual([a['uri'] for a in asked[u(4)]['chain']], [u(3), u(2), u(1)])  # every ancestor it saw, nearest first
        self.assertEqual(asked[u(4)]['chain'][-1], {'uri': u(1), 'author': DID, 'replyTo': u('card')})
        self.assertEqual((asked[u(4)]['replyTo'], asked[u(4)]['mentions'], asked[u(4)]['author']), (u(3), 0, DID))
        turns = {t['identity']: (t['object'], t.get('reach'), t.get('replyTo')) for t in stub.ops if t['op'] == 'world-turn'}
        self.assertEqual(turns, {u(1): ('garden-1', None, u('card')), u(2): ('garden-1', 'fields', u(1)), u(3): ('anthology', 'door', u(2)),
                                 posts[4]['uri']: ('commonplace', 'mention', None)})
        self.assertEqual([f['name'] for f in stub.ops[[o['op'] for o in stub.ops].index('world-turn')]['argument']['fields']], ['text', 'post'])
        self.assertEqual(len(r['turns']), 4)
        self.assertIn(u(4), self.state.skipped.read_text())
        n = len([o for o in stub.ops if o['op'] == 'world-reach'])
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-reach']), n)  # drafts and skips are remembered

    def test_a_cycle_in_what_was_observed_passes_each_ancestor_once(self):
        a, b = f'at://{DID}/town.delve.feed.post/ca', f'at://{DID}/town.delve.feed.post/cb'
        stub = Stub()
        x, y = mk(1, 'x', parent=b), mk(2, 'y', parent=a)
        x['uri'], y['uri'] = a, b
        self.observe([x, y])
        bridge.run(self.state, stub)
        self.assertEqual([[c['uri'] for c in o['chain']] for o in stub.ops if o['op'] == 'world-reach'], [[b, a], [a, b]])


class Suspended(BridgeCase):
    def test_a_failed_external_poll_does_not_stop_a_local_feed_reply_or_tick(self):
        from transport import feed
        store = feed.Feed(self.state)
        self.addCleanup(store.close)
        for error in (delve.Failure('http_status', '503'), OSError('offline')):
            with self.subTest(error=type(error).__name__):
                p = store.post({'did': DID, 'handle': 'alice'}, 'delvetalk garden-1 plant\nseed: a\ncolour: amber')
                observer = mock.Mock()
                observer.poll.side_effect = error
                observer.problems = []
                stub = Stub()
                send = stub.send
                stub.send = lambda req: {'status': 'reserved'} if req['op'] == 'world-post-reserve' else send(req)
                result = bridge.run(self.state, stub, observer, now=60)
                self.assertEqual(result['failed'], [{'source': 'delve', 'message': str(error)}])
                self.assertTrue(any(o['op'] == 'world-advance' for o in stub.ops))
                self.assertTrue(result['answered'])
                self.assertTrue(any(r['town'] and r['parent'] == p['uri'] for r in store.rows()))

    def test_a_programming_error_in_an_external_poll_still_escapes(self):
        observer = mock.Mock()
        observer.poll.side_effect = ValueError('bad observer')
        with self.assertRaisesRegex(ValueError, 'bad observer'):
            bridge.run(self.state, Stub(), observer)

    def test_a_feed_only_bridge_command_never_constructs_a_delve_client(self):
        import io
        from types import SimpleNamespace
        from transport.__main__ import main
        self.assertEqual(main(['open', '--state', str(self.state.root), '--transport', 'feed'], io.StringIO()), 0)
        host = mock.Mock(send=Stub().send)
        with mock.patch.object(self.state, 'host', return_value=host), mock.patch.object(bridge, 'Client', side_effect=AssertionError('external client')):
            output = io.StringIO()
            bridge.command(self.state, SimpleNamespace(since=None, now=60, once=True), output)
        self.assertEqual(json.loads(output.getvalue())['failed'], [])
        host.close.assert_called_once()

    def test_a_suspended_turn_has_no_draft_then_the_resumed_offer_is_drafted_once(self):
        stub = Stub()
        stub.suspending = {'garden-1'}
        p = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        self.observe([p])
        bridge.run(self.state, stub)
        self.assertEqual(self.drafts(), [])
        turns = len([o for o in stub.ops if o['op'] == 'world-turn'])
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-turn']), turns)  # not re-run while it waits
        self.assertEqual(self.drafts(), [])  # settled with no offer: still no draft
        stub.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': {'principal': DID, 'intent': p['uri']}, 'text': 'Planted.'},
                            {'height': 9, 'ordinal': 1, 'identity': {'principal': DID, 'intent': 'someone-else'}, 'text': 'not mine'}]
        r = bridge.run(self.state, stub)
        self.assertEqual(r['offered'], [p['uri']])
        (d,) = self.drafts()
        self.assertEqual((d['text'], d['replyTo'], d['principal'], d['posted']), ('Planted.\n' + bridge.receipt_line(Stub.RESUMED), p['uri'], DID, False))
        self.assertNotIn('offered', bridge.run(self.state, stub))
        self.assertEqual(len(self.drafts()), 1)

    def test_an_offer_for_a_handed_on_turn_is_drafted_against_the_originating_post(self):
        stub = Stub()
        stub.suspending = {'garden-1'}
        p = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')
        self.observe([p])
        bridge.run(self.state, stub)
        stub.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': {'principal': DID, 'intent': 'handed-on-turn'},
                             'from': {'principal': DID, 'intent': p['uri']}, 'text': 'Handed over.'}]
        self.assertEqual(bridge.run(self.state, stub)['offered'], [p['uri']])
        (d,) = self.drafts()
        self.assertEqual((d['text'], d['replyTo']), ('Handed over.\n' + bridge.receipt_line(Stub.RESUMED), p['uri']))


class Spells(Stub):
    """Each post of several spells answered as the host answers one: a turn per spell line, `segments` naming each
    one's status (`usage` for a `?`, `suspended`, else admitted)."""
    def __init__(self, segments):
        super().__init__()
        self.segments = segments

    def send(self, req):
        if req['op'] != 'world-turn':
            return super().send(req)
        self.ops.append(req)
        turns = []
        for n, status in enumerate(self.segments, 1):
            identity = {'principal': req['principal'], 'intent': f"{req['identity']}#{n}"}
            rc = {'hash': f'h{n}', 'height': 10 + n, 'slug': f'lodif-ruku{"zb"[n % 2]}', 'identity': identity,
                  'outcome': {'tag': 'suspended' if status == 'suspended' else 'admitted'}, 'roots': [{'object': 'bell-1', 'version': n}]}
            turns.append({'status': 'usage', 'text': 'delvetalk bell-1 rain / text: <1 to 200>\n'} if status == 'usage' else
                         {'status': status, 'object': 'bell-1', 'receipt': rc})
        return {'status': 'spells', 'turns': turns}


class SeveralSpells(BridgeCase):
    def test_a_usage_line_among_the_spells_is_answered_with_the_others(self):
        stub = Spells(['admitted', 'usage'])
        self.observe([mk(1, 'delvetalk bell-1 rain\ntext: hello\ndelvetalk bell-1 ?')])
        self.assertEqual(bridge.run(self.state, stub)['failed'], [])
        (d,) = self.drafts()
        self.assertIn('admitted bell-1 v1', d['text'])
        self.assertEqual(d['text'], '● admitted bell-1 v1, entry 11, receipt lodif-rukub\n' +
                         "a `?` or a read is its reader's; read the card, book, chronicle or map on the web\n")
        self.assertNotIn('delvetalk bell-1 rain / text: <1 to 200>', d['text'])

    def test_a_suspended_spell_among_them_is_answered_when_its_offer_comes(self):
        stub = Spells(['admitted', 'suspended'])
        p = mk(1, 'delvetalk bell-1 rain\ntext: hello\ndelvetalk bell-1 tend')
        self.observe([p])
        self.assertEqual(bridge.run(self.state, stub)['failed'], [])
        stub.offers[DID] = [{'height': 20, 'ordinal': 0, 'identity': {'principal': DID, 'intent': p['uri'] + '#2'}, 'text': 'Tended.'}]
        self.assertEqual(bridge.run(self.state, stub)['offered'], [p['uri'] + '#2'])
        later = [d for d in self.drafts() if 'Tended.' in d['text']]
        self.assertEqual([d['replyTo'] for d in later], [p['uri']])

    def test_a_suspended_child_refusal_reaches_the_same_post_once_without_recasting_the_parent(self):
        stub = Spells(['admitted', 'suspended'])
        p = mk(1, 'delvetalk bell-1 rain\ntext: hello\ndelvetalk bell-1 tend')
        self.observe([p])
        bridge.run(self.state, stub)
        turns = sum(o['op'] == 'world-turn' for o in stub.ops)
        send = stub.send
        outcome = {'tag': 'refused', 'class': 'lawRefused', 'reason': 'refused owner: another hand'}
        stub.send = lambda req: ({'status': 'receipt', 'receipt': {**Stub.RESUMED, 'outcome': outcome}, 'public': outcome}
                                if req['op'] == 'world-receipt' else send(req))
        self.assertEqual(bridge.run(self.state, stub)['offered'], [p['uri'] + '#2'])
        later = [d for d in self.drafts() if d.get('receipt', {}).get('outcome', {}).get('tag') == 'refused']
        self.assertEqual(len(later), 1)
        self.assertEqual(later[0]['replyTo'], p['uri'])
        self.assertIn('refused owner: another hand', later[0]['text'])
        self.assertNotIn('offered', bridge.run(self.state, stub))
        self.assertEqual(sum(o['op'] == 'world-turn' for o in stub.ops), turns)


class Mentions(BridgeCase):
    """Whoever a post mentions hears it, reached or not: each mention of an arrived resident is queued as its note (the
    author, their handle, the post's URI and its first NOTE_TEXT characters), and once a resident's oldest queued note is
    MENTION_MINUTES old the town tells their avatar the hour's notes in one turn (`mentions`, at most NOTES_PER_TURN), so
    the journal holds a turn per resident an hour, never one per post. A turn the host gave no receipt for is sent again;
    `world-reach` is asked once a post."""
    GLM, KIMI = 'did:plc:' + 'b' * 24, 'did:plc:' + 'c' * 24
    REACHED = {'status': 'reached', 'object': 'commonplace', 'how': 'mention'}
    T = 1_800_000_000  # the wall clock of the first run; the posts are older

    def facet(self, text, handle, did):
        start = text.index('@' + handle)
        return {'index': {'byteStart': start, 'byteEnd': start + len(handle) + 1}, 'features': [{'$type': 'app.bsky.richtext.facet#mention', 'did': did}]}

    def seen(self, n, did, handle):
        p = mk(n, f'{handle} was here')
        p['author'] = {'did': did, 'handle': handle}
        return p

    def glm(self):
        return self.seen(1, self.GLM, 'glm.delve.town')

    def told(self, stub):
        return [o for o in stub.ops if o['op'] == 'world-turn' and o['method'] == 'mentions']

    def notes(self, turn):
        return plain_notes(turn['argument'])

    def hour(self, stub, runs=1):
        """The first run, then `runs` an hour on."""
        out = [bridge.run(self.state, stub, now=self.T)]
        for k in range(runs):
            out.append(bridge.run(self.state, stub, now=self.T + bridge.MENTION_MINUTES * 60 * (k + 1)))
        return out

    def test_a_post_that_reaches_no_card_is_still_heard_by_whom_it_mentions(self):
        """Refuted by the live gsb after the edition-19 carry: 0 mention turns from 09:10Z against 28 to 85 an hour before,
        every mentioning post skipped as unreached and its mentions with it."""
        post = mk(2, 'hello @glm.delve.town, any news?')
        stub = Stub()
        self.observe([self.glm(), post])
        first, later = self.hour(stub)
        self.assertNotIn('mentioned', first)
        (turn,) = self.told(stub)
        self.assertEqual((turn['principal'], turn['object']), (self.state.config.opener, self.GLM))
        self.assertEqual(self.notes(turn), [{'from': DID, 'handle': 'talkie.delve.town', 'text': post['record']['text'], 'post': post['uri']}])
        self.assertEqual(later['mentioned'], [post['uri']])
        self.assertIn(post['uri'], self.state.skipped.read_text().split())  # skipped for every card, heard by its resident
        self.assertEqual(sum(o['op'] == 'world-reach' for o in stub.ops if o.get('uri') == post['uri']), 1)

    def test_nothing_is_told_before_the_oldest_note_is_an_hour_old(self):
        """Refuted by a turn a post: the first run queues, and only a run MENTION_MINUTES after it tells."""
        stub = Stub()
        self.observe([self.glm(), mk(2, 'hello @glm.delve.town')])
        bridge.run(self.state, stub, now=self.T)
        bridge.run(self.state, stub, now=self.T + bridge.MENTION_MINUTES * 60 - 1)
        self.assertEqual(self.told(stub), [])
        bridge.run(self.state, stub, now=self.T + bridge.MENTION_MINUTES * 60)
        self.assertEqual(len(self.told(stub)), 1)

    def test_an_hour_of_mentions_is_one_turn_per_resident_whatever_the_posts_and_authors(self):
        """Refuted by a turn per post (gsb's hour at 497765: 58 mention entries for 15 residents)."""
        text = 'hello @glm.delve.town and @kimi.delve.town'
        posts = [mk(2, text, facets=[self.facet(text, 'kimi.delve.town', self.KIMI)]), mk(3, 'again @glm.delve.town'), self.seen(4, self.KIMI, 'kimi.delve.town')]
        posts.append(mk(5, 'and @glm.delve.town once more'))
        posts[-1]['author'] = {'did': self.KIMI, 'handle': 'kimi.delve.town'}
        stub = Stub({posts[0]['uri']: self.REACHED})  # reached or not, a mention is told the same way
        self.observe([self.glm()] + posts)
        self.hour(stub)
        turns = {t['object']: self.notes(t) for t in self.told(stub)}
        self.assertEqual(sorted(turns), sorted([self.GLM, self.KIMI]))
        self.assertEqual([(n['from'], n['post']) for n in turns[self.GLM]], [(DID, posts[0]['uri']), (DID, posts[1]['uri']), (self.KIMI, posts[3]['uri'])])
        self.assertEqual([n['post'] for n in turns[self.KIMI]], [posts[0]['uri']])
        self.assertEqual([o for o in stub.ops if o['op'] == 'world-turn' and o.get('reach') == 'mentioned'], [])

    def test_a_note_carries_the_uri_and_only_the_first_280_characters(self):
        """Refuted by the whole 40 KB post in the argument (the live gsb stored 3.7 KB a mention, up to 40 KB)."""
        text = '@glm.delve.town ' + 'y' * 40_000
        post = mk(2, text)
        stub = Stub()
        self.observe([self.glm(), post])
        self.hour(stub)
        (turn,) = self.told(stub)
        (note,) = self.notes(turn)
        self.assertEqual((note['text'], note['post'], bridge.NOTE_TEXT), (text[:280], post['uri'], 280))
        self.assertLess(len(json.dumps(turn['argument'])), 1024)

    def test_the_clip_never_splits_a_character(self):
        """Refuted by a clip in bytes or UTF-16 units: the 280th character is an astral emoji or a multibyte letter, and
        the note is its first 280 characters whole, as `textTake` counts scalars."""
        head = '@glm.delve.town '
        posts = []
        for k, last in enumerate(('\U0001F600', 'é', '\u2603')):
            posts.append(mk(10 + k, head + 'a' * (279 - len(head)) + last + 'tail' * 50))
        past = head + 'a' * (280 - len(head)) + '\U0001F600' + 'tail'  # the emoji is the 281st: it is left out whole
        posts.append(mk(20, past))
        stub = Stub()
        self.observe([self.glm()] + posts)
        self.hour(stub)
        (turn,) = self.told(stub)
        got = [n['text'] for n in self.notes(turn)]
        self.assertEqual(got, [p['record']['text'][:280] for p in posts])
        self.assertEqual([(len(t), t[-1]) for t in got[:3]], [(280, '\U0001F600'), (280, 'é'), (280, '\u2603')])

    def test_a_resident_mentioned_past_the_turns_bound_hears_the_rest_in_the_next_turn(self):
        """Refuted by an unbounded argument, or by notes past NOTES_PER_TURN lost: the maximum-length case."""
        posts = [mk(10 + k, f'@glm.delve.town number {k} ' + 'z' * 400) for k in range(bridge.NOTES_PER_TURN * 2 + 1)]
        stub = Stub()
        self.observe([self.glm()] + posts)
        self.hour(stub)
        sizes = [len(self.notes(t)) for t in self.told(stub)]
        self.assertEqual(sizes, [bridge.NOTES_PER_TURN, bridge.NOTES_PER_TURN, 1])
        self.assertEqual([n['post'] for t in self.told(stub) for n in self.notes(t)], [p['uri'] for p in posts])
        self.assertTrue(all(len(json.dumps(t['argument'])) < 16 * 1024 for t in self.told(stub)))

    def test_a_post_naming_fifty_residents_tells_only_the_hosts_first_addressed(self):
        """Refuted by a note per name: the bound is the host's `mentionsAddressed`, however many a post names."""
        dids = [f'did:plc:{i:024d}' for i in range(50)]
        names = [f'r{i}.delve.town' for i in range(50)]
        post = mk(1, ' '.join('@' + n for n in names))
        stub = Stub(mentions=4)
        self.observe([post] + [self.seen(10 + i, d, n) for i, (d, n) in enumerate(zip(dids, names))])
        self.hour(stub)
        self.assertEqual(sorted(t['object'] for t in self.told(stub)), dids[:4])

    def test_a_turn_the_host_gave_no_receipt_for_is_sent_again_and_then_never(self):
        """Refuted by a lost note (no retry), a note told twice, or a second `world-reach` for the post."""
        post = mk(2, 'hello @glm.delve.town')
        stub = Stub()
        send, failing = stub.send, [True]

        def busy(req):
            got = send(req)
            return {'status': 'error', 'message': 'busy'} if req.get('method') == 'mentions' and failing else got
        stub.send = busy
        self.observe([self.glm(), post])
        self.hour(stub)
        self.assertEqual((self.state.words(self.state.mentioned), len(self.told(stub))), (set(), 1))
        failing.clear()
        r = bridge.run(self.state, stub, now=self.T + 7200)
        self.assertEqual((r['mentioned'], self.state.words(self.state.mentioned)), ([post['uri']], {post['uri']}))
        self.assertEqual(self.told(stub)[0]['identity'], self.told(stub)[1]['identity'])  # the host answers a repeated identity with its first receipt
        bridge.run(self.state, stub, now=self.T + 3 * 3600)
        self.assertEqual(len(self.told(stub)), 2)
        self.assertEqual(sum(o['op'] == 'world-reach' for o in stub.ops if o.get('uri') == post['uri']), 1)

    def test_a_skipped_post_dropped_from_the_store_keeps_its_queued_note(self):
        """Refuted by a note read from the observation: a skipped post is pruned to its hash 15 minutes after it was
        written, before the hour is up."""
        post = mk(2, 'hello @glm.delve.town')
        stub = Stub()
        self.observe([self.glm(), post])
        bridge.run(self.state, stub, now=self.T)
        observe.prune(self.state, self.state.observations(), [], at=self.T + 3600)
        self.assertEqual(self.state.observations(), [])
        bridge.run(self.state, stub, now=self.T + bridge.MENTION_MINUTES * 60)
        (turn,) = self.told(stub)
        self.assertEqual([n['post'] for n in self.notes(turn)], [post['uri']])

    def test_a_resident_whose_posts_were_dropped_is_still_mentioned_by_handle(self):
        """Refuted by the author map read from the kept observations: the handle of a dropped author would not resolve."""
        stub = Stub()
        self.observe([self.glm()])
        bridge.run(self.state, stub, now=self.T)  # skipped
        (gone,) = self.state.observations()
        observe.prune(self.state, [gone], [], at=observe.instant(gone['createdAt']) + 7200)
        post = mk(2, 'hello @glm.delve.town')
        post['record']['createdAt'] = '2026-10-12T11:00:00Z'
        self.observe([post])
        self.hour(stub)
        self.assertEqual([t['object'] for t in self.told(stub)], [self.GLM])

    def test_a_never_seen_handle_and_the_author_themself_are_told_nothing(self):
        text = 'hello @glm.delve.town and @ghost.delve.town and me, @talkie.delve.town'
        post = mk(2, text, facets=[self.facet(text, 'ghost.delve.town', self.KIMI)])  # kimi was never observed
        stub = Stub()
        self.observe([self.glm(), post])
        r = self.hour(stub)
        arrivals = [o['did'] for o in stub.ops if o['op'] == 'world-arrive']
        self.assertEqual(sorted(arrivals), sorted([DID, self.GLM]))  # every observed author, once; never the unseen kimi
        self.assertEqual([t['object'] for t in self.told(stub)], [self.GLM])
        self.assertIn(f"{post['uri']}#mention:{self.KIMI}", self.state.skipped.read_text().split())
        self.assertEqual([x['failed'] for x in r], [[], []])

    def test_a_legacy_owed_post_is_queued_and_told(self):
        """Refuted by an `owed` row (an edition-19 store: a reached post whose mention turn had no receipt) left unsent."""
        post = mk(2, 'hello @glm.delve.town')
        self.observe([self.glm(), post])
        observe.owe(self.state, post['uri'])
        self.state.append(self.state.skipped, post['uri'])  # its reach was asked and answered before
        stub = Stub()
        self.hour(stub)
        (turn,) = self.told(stub)
        self.assertEqual([n['post'] for n in self.notes(turn)], [post['uri']])
        self.assertEqual(observe.owed(self.state), set())

    def test_the_town_tells_a_real_avatar_and_a_resident_cannot(self):
        """Through a real host: the avatar keeps the town's notes in its inbox, each from its post's author with the
        post's URI; the same turn by a resident (a forged note) is refused by name and writes nothing."""
        from tests.town import Town
        town = Town(str(Path(self.tmp.name) / 'town'), cleanup=self.addCleanup)
        host = type('TownHost', (), {'send': lambda _, req: town.send(**req)})()
        self.state = State(Path(self.tmp.name) / 'state2', config=Config(origin=LOOPBACK.origin, opener=town.opener))
        self.state.append(self.state.taught, DID)
        post = mk(2, 'a bell for @glm.delve.town, from the porch')
        self.observe([self.glm(), post])
        bridge.run(self.state, host, now=self.T)
        r = bridge.run(self.state, host, now=self.T + bridge.MENTION_MINUTES * 60)
        self.assertEqual((r['mentioned'], r['failed']), ([post['uri']], []), r)
        card = host.send({'op': 'world-card', 'principal': self.GLM, 'object': self.GLM})
        shown = json.dumps(card)
        self.assertIn('a bell for @glm.delve.town, from the porch', shown)
        forged = host.send({'op': 'world-turn', 'principal': DID, 'object': self.GLM, 'method': 'mentions', 'identity': 'forged',
                            'argument': typed({'notes': [{'from': 'did:plc:' + 'f' * 24, 'handle': 'someone', 'text': 'forged', 'post': 'at://x'}]})})
        self.assertEqual((forged['receipt']['outcome']['tag'], forged['receipt']['outcome'].get('clause')), ('refused', 'notTown'), forged)
        self.assertNotIn('forged', json.dumps(host.send({'op': 'world-card', 'principal': self.GLM, 'object': self.GLM})))


    def test_posts_skipped_before_the_fix_are_heard_again_once_and_nothing_else_is_asked(self):
        """The operator's replay of gsb's 803 posts skipped from 09:07Z (`bridge --hear-again ISO`): refuted by a post
        asked of reach or turned again, a note told twice, a post from before ISO or one never skipped heard, or a
        replayed note held another hour."""
        stub = Stub()
        old, new, told = mk(2, 'before @glm.delve.town'), mk(3, 'after @glm.delve.town'), mk(4, 'told @glm.delve.town')
        old['record']['createdAt'], new['record']['createdAt'], told['record']['createdAt'] = '2026-10-14T08:00:00Z', '2026-10-14T10:00:00Z', '2026-10-14T10:05:00Z'
        self.observe([self.glm()])
        bridge.run(self.state, stub, now=self.T)
        for post in (old, new, told):  # skipped by edition 19, which queued nothing, and pruned to their hashes
            self.state.append(self.state.skipped, post['uri'])
        self.state.append(self.state.mentioned, told['uri'])
        page = {'feed': [{'post': p} for p in (told, new, old)], 'cursor': None}
        t = Script(**{'town.delve.feed.getFeed': lambda q: (200, page)})
        before = len(stub.ops)
        queued = bridge.hear_again(self.state, stub, observe.Observer(self.state, delve.Client(t)), '2026-10-14T09:07:00Z', now=self.T + 60)
        self.assertEqual(queued, [new['uri']])
        self.assertEqual([o['op'] for o in stub.ops[before:] if o['op'] in ('world-reach', 'world-turn')], [])
        bridge.run(self.state, stub, now=self.T + 120)  # due at once: these are late already
        (turn,) = self.told(stub)
        self.assertEqual([n['post'] for n in self.notes(turn)], [new['uri']])
        self.assertEqual(bridge.hear_again(self.state, stub, observe.Observer(self.state, delve.Client(t)), '2026-10-14T09:07:00Z', now=self.T + 180), [])


def plain_notes(argument):
    """The notes of a `mentions` argument as plain dicts."""
    (field,) = argument['fields']
    return [{f['name']: f['value']['value'] for f in item['fields']} for item in field['value']['items']]


class Forgetting(BridgeCase):
    """What the bridge answers the observer's store forgets (observe.py's docstring): never a post twice asked, never an
    ancestor reach needs."""
    def test_a_skipped_post_is_dropped_to_its_hash_and_never_asked_again(self):
        """Refuted by a dropped post that the next page of the feed inserts and asks again."""
        post = mk(1, 'chatter')
        stub = Stub()
        self.observe([post])
        bridge.run(self.state, stub)
        (obs,) = self.state.observations()
        observe.prune(self.state, [obs], [], at=observe.instant(obs['createdAt']) + 2 * 3600)
        self.assertEqual(self.state.observations(), [])
        self.observe([post])  # the feed shows it again
        self.assertEqual(self.state.observations(), [])
        bridge.run(self.state, stub)
        self.assertEqual(sum(o['op'] == 'world-reach' for o in stub.ops), 1)

    def test_a_dropped_replys_stub_still_stands_in_the_chain_reach_is_shown(self):
        """Refuted by a chain that stops at a dropped skipped ancestor: the host walks it to find the recorded post."""
        u = lambda n: f'at://{DID}/town.delve.feed.post/{n}'
        a, b, c = mk(1, 'plan', parent=u('card')), mk(2, 'chatter', parent=u(1)), mk(3, 'more', parent=u(2))
        for i, p in enumerate((a, b, c), 1):
            p['uri'] = u(i)
            p['record']['createdAt'] = f'2026-10-09T10:00:0{i}Z'
        stub = Stub({u(1): {'status': 'reached', 'object': 'garden-1', 'how': 'reply'}})
        self.observe([a, b])
        bridge.run(self.state, stub)
        rows = {o['uri']: o for o in self.state.observations()}
        observe.prune(self.state, [rows[u(2)]], [], at=observe.instant(rows[u(2)]['createdAt']) + 2 * 3600)
        self.assertEqual(set(o['uri'] for o in self.state.observations()), {u(1)})
        self.observe([c])
        bridge.run(self.state, stub)
        asked = [o for o in stub.ops if o['op'] == 'world-reach' and o['uri'] == u(3)]
        self.assertEqual([x['uri'] for x in asked[0]['chain']], [u(2), u(1)])
        self.assertEqual(asked[0]['chain'][0], {'uri': u(2), 'author': DID, 'replyTo': u(1)})

    def test_an_answered_post_is_kept_until_it_is_old_and_a_pending_one_is_never_dropped(self):
        """Refuted by a draft's post dropped within the window, or a post with no answer dropped at any age."""
        done, waiting = mk(1, 'delvetalk garden-1 plant\nseed: a\ncolour: amber'), mk(2, 'delvetalk garden-1 plant\nseed: b\ncolour: amber')
        stub = Stub()
        self.observe([done, waiting])
        stub.suspending.add('nowhere')
        bridge.run(self.state, stub)
        rows = self.state.observations()
        self.assertEqual(len(rows), 2)
        start = observe.instant(rows[0]['createdAt'])
        self.assertEqual(observe.prune(self.state, [], rows, at=start + 6 * 86400), 0)
        self.assertEqual(observe.prune(self.state, [], rows, at=start + 8 * 86400), 2)
        self.assertEqual(self.state.observations(), [])
        # a post the host gave no receipt for has no draft, so the bridge does not call it answered
        failing = mk(3, 'delvetalk garden-1 plant\nseed: c\ncolour: amber')
        send = stub.send
        stub.send = lambda req: {'status': 'error', 'message': 'busy'} if req['op'] == 'world-turn' else send(req)
        self.observe([failing])
        self.assertEqual(bridge.run(self.state, stub)['failed'][0]['uri'], failing['uri'])
        self.assertEqual([o['uri'] for o in self.state.observations()], [failing['uri']])


class Unaddressed(BridgeCase):
    """Whether a refusal is drafted is the host's fact: its `public` projection. The post's wording is never read for it."""
    def run_refused(self, post, public=True):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        stub = Stub({post['uri']: {'status': 'reached', 'object': 'commonplace', 'how': 'reply', 'replyTo': parent}})
        real = stub.send
        outcome = {'tag': 'refused', 'class': 'quota', 'reason': 'the interpreter has read 48 this hour; reply with the spell itself, or wait.', 'next': 600}
        stub.send = lambda req: ({'status': 'refused', 'receipt': {'hash': 'h', 'height': 5, 'slug': 'bofab-lukid', 'outcome': outcome},
                                  **({'public': {'status': 'refused', 'class': 'quota', 'reason': outcome['reason'], 'next': 600}} if public else {})}
                                 if req['op'] == 'world-turn' else real(req))
        self.observe([post])
        bridge.run(self.state, stub)
        return self.drafts()

    def test_a_plain_prose_reply_refused_by_quota_is_drafted_with_the_hosts_explanation(self):
        parent = f'at://{DID}/town.delve.feed.post/welcome'
        (chatter,) = self.run_refused(mk(1, 'lovely thread, thanks all', parent=parent))
        self.assertEqual(chatter['text'], 'refused quota: the interpreter has read 48 this hour; reply with the spell itself, or wait.\nreceipt bofab-lukid\n')

    def test_a_refusal_the_host_gives_no_public_projection_is_journaled_not_drafted(self):
        (spell,) = self.run_refused(spell_post(2, 'garden-1', '2026-10-09T10:00:00Z'), public=False)
        self.assertEqual((spell['text'], spell['receipt']['outcome']['class']), ('', 'quota'))


class Silence(BridgeCase):
    def test_a_turn_that_offers_nothing_has_no_draft_in_the_outbox_unless_asked(self):
        stub = Stub()
        stub.silent = {'garden-1'}
        self.observe([spell_post(1, 'garden-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(len(bridge.run(self.state, stub)['turns']), 1)
        self.assertEqual(bridge.run(self.state, stub)['turns'], [])  # journaled once, not re-run
        hand = Hand(self.state, stub)
        self.assertEqual(hand.outbox(), [])
        self.assertEqual(len(hand.outbox(all=True)[0]['drafts']), 1)


    def test_a_spell_that_changed_something_and_offered_nothing_is_answered_with_its_receipt(self):
        self.make('still-1', body=REFUSING)  # writes `seen`, offers no card
        self.observe([spell_post(1, 'still-1', '2026-10-09T10:00:00Z')])
        self.assertEqual(self.run_bridge()['failed'], [])
        (d,) = self.drafts()
        self.assertEqual(d['text'], bridge.receipt_line(d['receipt']))


class RealOffers(test_outbound.TellerWorld):
    def test_offer_drafts_match_the_hosts_real_identity_shape(self):
        self.turn("teller", "tell", record(to=label(""), text=label("hello")), principal="ann", identity="t-1")
        self.assertIsInstance(self.host.send(op="world-offers", principal="ann")["offers"][0]["identity"], dict)
        with tempfile.TemporaryDirectory() as d:
            d = State(d, config=LOOPBACK)
            d.write(bridge.awaiting_path(d, "t-1"), {"uri": "t-1", "principal": "ann", "replyHandle": "ann.delve.town",
                                                                 "object": "teller", "slot": None, "height": 0})
            outer = self

            class H:
                def send(self, req):
                    return outer.host.send(**req)
            self.assertEqual(bridge.offer_drafts(d, H()), ["t-1"])
            (draft,) = list(d.outbox.glob("*.json"))
            slug = self.host.send(op="world-receipt", principal="ann", identity="t-1")["receipt"]["slug"]
            self.assertRegex(json.loads(draft.read_text())["text"], rf"^hello\n● admitted teller v\d+, entry \d+, receipt {slug}\n$")
            self.assertEqual(bridge.offer_drafts(d, H()), [])


class PublicReads(ServeCase):
    def test_a_public_card_read_is_posted_whole_and_a_diary_read_is_not_and_neither_public_read_journals(self):
        from deploy.seed import closure, modules_on_disk
        from transport import feed, post as posting
        alice = 'did:plc:' + 'b' * 24
        for obj, principal, read in (('public-read-card', self.OPENER, {}), ('private-read-diary', alice, {'principals': [alice]})):
            created = self.root.send({'op': 'world-create', 'principal': principal, 'identity': obj, 'object': obj,
                                      'entry': 'initial', 'modules': closure('Record', modules_on_disk()), 'law': genesis.RECORD_LAW,
                                      **({'read': read} if read else {}), 'seed': genesis.rec(owner=genesis.lab(principal), maker=genesis.lab(principal))})
            self.assertEqual(created['status'], 'created', created)
        with tempfile.TemporaryDirectory() as directory:
            st = State(directory, config=LOOPBACK)
            store = feed.Feed(st)
            self.addCleanup(store.close)
            for obj in ('public-read-card', 'private-read-diary'):
                spell = f'delvetalk {obj} ?'
                request = {'op': 'world-turn', 'principal': alice, 'object': obj, 'method': 'receive', 'identity': 'read-' + obj,
                           'argument': typed({'text': spell, 'post': ''})}
                caller = self.host.send(request)
                self.assertEqual(caller['status'], 'usage', caller)
                height = self.host.send({'op': 'world-status'})['height']
                text = bridge.draft_text(caller, host=self.host, request=request)
                self.assertEqual(self.host.send({'op': 'world-status'})['height'], height)
                if obj == 'public-read-card':
                    public = self.host.send({**request, 'op': 'world-try', 'principal': PUBLIC, 'identity': 'anonymous-public-read'})
                    self.assertEqual(public['status'], 'usage', public)
                    self.assertEqual(text, public.get('whole') or public['text'])
                    self.assertEqual(self.host.send({'op': 'world-status'})['height'], height)
                else:
                    self.assertIn("its reader's", text)
                    self.assertNotIn(obj, text)
                post = store.post({'did': alice, 'handle': 'alice'}, spell)
                bridge.run(st, self.host, now=60)
                posted = '\n'.join(r['text'] for r in store.rows() if r['town'] and r['answers'] == post['uri'])
                self.assertEqual(posted, '\n'.join(posting.parts(text)))


class Projection(unittest.TestCase):
    def test_a_settled_receipt_replaces_the_suspended_xrpc_answer_at_the_maximum_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            st = State(directory)
            source = bridge.xrpc_source(DID, 'é' * 128)
            suspended = {'outcome': {'status': 'suspended', 'line': 'waiting'},
                         'receipt': {'slug': 'first', 'height': 1, 'entry': {'$link': 'suspended'}}}
            settled = {'outcome': {'status': 'admitted', 'line': 'rang'},
                       'receipt': {'slug': 'second', 'height': 2, 'entry': {'$link': 'settled'}}}
            bridge.write_answer(st, source, suspended)
            bridge.write_answer(st, source, settled)
            saved = json.loads(bridge.answer_path(st, source).read_text())
            self.assertEqual((saved['outcome'], saved['receipt'], saved['height']),
                             (settled['outcome'], settled['receipt'], 2))

    def test_an_answered_record_request_keeps_its_first_bytes_even_when_later_deliveries_add_offers(self):
        with tempfile.TemporaryDirectory() as directory:
            st, host = State(directory, config=LOOPBACK), Stub()
            uri = f'at://{DID}/{bridge.NS}request/3aaaaaaaaaaa2'
            obs = {'uri': uri, 'cid': 'proven', 'kind': 'request', 'createdAt': '2026-10-12T00:00:00Z',
                   'author': {'did': DID, 'handle': 'talkie.delve.town'}, 'text': '', 'replyTo': None, 'mentions': [],
                   'request': {'call': {'object': 'bell', 'verb': 'rain', 'fields': {'tag': 'blue'}}}}
            st.observations = mock.Mock(return_value=[obs])
            admitted = {'status': 'admitted', 'inPublic': True, 'offers': [{'text': 'Planted.'}],
                        'receipt': {**Stub.RESUMED, 'identity': {'principal': DID, 'intent': uri}}}
            bridge.answer_turn(st, host, obs, admitted)
            path = bridge.answer_path(st, bridge.request_source(obs))
            first = path.read_bytes()
            host.offers[DID] = [{'height': 10, 'identity': {'principal': DID, 'intent': uri}, 'text': "kind/bell's made"}]
            send = host.send
            def no_retry(req):
                self.assertNotIn(req['op'], ('world-receipt', 'world-turn', 'world-reach'))
                return send(req)
            host.send = no_retry
            ran = bridge.run(st, host, now=0)
            self.assertEqual(ran['failed'], [])
            self.assertEqual(ran['turns'], [])
            self.assertEqual(path.read_bytes(), first)

    def test_a_tried_admitted_public_read_drafts_its_offers_without_a_hypothetical_receipt(self):
        request = {'op': 'world-turn', 'principal': DID, 'object': 'commonplace', 'method': 'receive', 'identity': 'a-read',
                   'argument': typed({'text': 'delvetalk guide', 'post': ''})}
        for text in ('hob: the guide, in 17 parts.', 'x' * observe.MAX_TEXT):
            with self.subTest(length=len(text)):
                host = mock.Mock()
                host.send.return_value = {'status': 'admitted', 'tried': True, 'inPublic': True,
                                          'offers': [{'principal': PUBLIC, 'text': text}],
                                          'receipt': {'height': 10, 'slug': 'lodif-rukuz', 'outcome': {'tag': 'admitted', 'writes': []}}}
                self.assertEqual(bridge.draft_text({'status': 'usage', 'text': 'caller-only'}, host=host, request=request), text)
                self.assertEqual(host.send.call_args.args[0]['op'], 'world-try')

    def test_a_public_trial_that_changes_the_world_sends_publishes_or_offers_nothing_is_not_drafted_as_a_read(self):
        request = {'op': 'world-turn', 'principal': DID, 'object': 'diary', 'method': 'receive', 'identity': 'a-read',
                   'argument': typed({'text': 'delvetalk diary book', 'post': ''})}
        read = {'status': 'admitted', 'tried': True, 'inPublic': True, 'offers': [{'principal': PUBLIC, 'text': 'an act'}],
                'receipt': {'outcome': {'tag': 'admitted'}}}
        cases = [{'receipt': {'outcome': {'tag': 'admitted', key: [{}]}}}
                 for key in ('writes', 'creates', 'reprograms', 'amendments', 'grants', 'revokes', 'spent', 'placements')]
        cases += [{'receipt': {**read['receipt'], key: [{}]}} for key in ('sends', 'publishes')]
        cases += [{'offers': []}, {'inPublic': False}, {'tried': False}]
        for changed in cases:
            with self.subTest(changed=changed):
                host = mock.Mock()
                host.send.return_value = {**read, **changed}
                text = bridge.draft_text({'status': 'usage', 'text': 'caller-only'}, host=host, request=request)
                self.assertIn("its reader's", text)
                self.assertNotIn('an act', text)
    def test_a_public_refusal_keeps_the_receipts_clause_and_reading_even_when_its_projection_only_names_the_class(self):
        receipt = {'height': 9, 'slug': 'lodif-rukuz', 'outcome': {'tag': 'refused', 'class': 'lawRefused', 'clause': 'seen', 'reason': 'stern'}}
        reply = {'status': 'refused', 'receipt': receipt, 'public': {'class': 'lawRefused'}}
        self.assertEqual(bridge.draft_text(reply), 'refused seen: stern\nreceipt lodif-rukuz\n')
        self.assertEqual(bridge.draft_text({k: v for k, v in reply.items() if k != 'public'}), '')

    def test_a_public_read_drafts_the_whole_public_text_and_paint_at_the_observation_limit(self):
        request = {'op': 'world-turn', 'principal': DID, 'object': 'commonplace', 'method': 'receive', 'identity': 'a-read',
                   'argument': typed({'text': 'delvetalk chronicle', 'post': ''})}
        caller = {'status': 'usage', 'text': 'a caller-private day', 'whole': 'a caller-private day', 'paint': {'day': 1}}
        for whole in ('A public day.', 'x' * observe.MAX_TEXT):
            with self.subTest(length=len(whole)):
                host = mock.Mock()
                host.send.side_effect = [{'status': 'usage', 'text': 'first page', 'whole': whole, 'paint': {'day': 1}},
                                         {'status': 'painted', 'text': 'A public painting.'}]
                self.assertEqual(bridge.draft_text(caller, host=host, request=request), 'A public painting.\n\n' + whole)
                sent = host.send.call_args_list[0].args[0]
                self.assertEqual((sent['op'], sent['principal'], sent['object'], sent['argument']),
                                 ('world-try', PUBLIC, request['object'], request['argument']))
                self.assertNotEqual(sent['identity'], request['identity'])
                self.assertEqual(host.send.call_args_list[1].args[0]['principal'], PUBLIC)

    def test_a_read_denied_to_the_public_drafts_no_caller_text_or_refusal_text(self):
        request = {'op': 'world-turn', 'principal': DID, 'object': 'diary', 'method': 'receive', 'identity': 'a-private-read',
                   'argument': typed({'text': 'delvetalk diary ?', 'post': ''})}
        host = mock.Mock()
        host.send.return_value = {'status': 'refused', 'message': 'the caller-private reason'}
        text = bridge.draft_text({'status': 'usage', 'text': 'the caller-private diary'}, 'https://x.example', host=host, request=request)
        self.assertIn("its reader's", text)
        self.assertIn('https://x.example/', text)
        self.assertNotIn('caller-private', text)
        self.assertEqual(host.send.call_count, 1)

    def test_a_single_read_preview_keeps_its_height_and_the_public_text(self):
        request = {'op': 'world-turn', 'principal': DID, 'object': 'commonplace', 'method': 'receive', 'identity': 'guide-preview',
                   'argument': typed({'text': 'delvetalk try\n  delvetalk guide', 'post': ''})}
        host = mock.Mock()
        host.send.return_value = {'status': 'usage', 'text': 'A public guide.'}
        reply = {'status': 'usage', 'tried': True, 'text': 'caller-only guide note', 'against': {'height': 10}}
        self.assertEqual(bridge.preview_text(reply, host=host, request=request),
                         'preview, nothing done (as of entry 10):\nA public guide.\n')

    def test_a_carried_receipt_lookup_says_the_hosts_message_without_requiring_an_entry(self):
        found = {'status': 'resolved', 'kind': 'receipt', 'slug': 'nosap-hodaz', 'cid': 'old',
                 'carried': {'at': 1400, 'height': 1336, 'world': 'town'},
                 'message': 'entry 1336 of the world before the carry (town)'}
        self.assertEqual(bridge.lookup_text({'of': found['slug'], 'found': found}),
                         'receipt nosap-hodaz: entry 1336 of the world before the carry (town)\n')

    def test_a_draft_cites_the_slug_and_no_draft_text_carries_a_hash_or_a_blob(self):
        h = 'bafyrei' + 'a' * 52
        receipt = {'hash': h, 'slug': 'babab-dabab', 'height': 9, 'roots': [{'object': 'garden', 'version': 3}], 'outcome': {'tag': 'admitted'}, 'offers': 1}
        unslugged = {k: v for k, v in receipt.items() if k != 'slug'}
        texts = [bridge.draft_text({'receipt': receipt}, 'https://x.example'), bridge.draft_text({'receipt': unslugged}, 'https://x.example'),
                 bridge.draft_text({'status': 'refused', 'receipt': {**receipt, 'outcome': {'tag': 'refused', 'class': 'lawRefused'}},
                                    'public': {'class': 'lawRefused', 'root': {'object': 'garden', 'version': 3}}}),
                 bridge.draft_text({'status': 'refused', 'receipt': {**unslugged, 'hash': 'f' * 64, 'outcome': {'tag': 'refused', 'class': 'lawRefused'}}, 'public': {}}, 'https://x.example'),
                 bridge.draft_text({'status': 'refused', 'receipt': unslugged, 'public': {'class': 'lawRefused', 'root': {'object': 'g', 'version': 1, 'cid': h}}})]
        self.assertIn('● admitted garden v3, entry 9, receipt babab-dabab\n', texts[0])  # VOICE's turn line, as the JSON `line` has it
        self.assertIn('● admitted garden v3, entry 9\nhttps://x.example/o/garden#v3', texts[1])
        self.assertIn('receipt babab-dabab\n', texts[2])
        for t in texts:
            self.assertFalse(re.search(r'bafy|[0-9a-f]{64}', t), t)


class Principals(BridgeCase):
    def test_each_author_is_registered_once_by_the_clock_principal_at_their_first_post(self):
        stub = Stub()
        a, b = spell_post(1, 'garden-1', '2026-10-09T10:00:00Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:01Z')
        b['author'] = {'did': 'did:plc:' + 'b' * 24, 'handle': 'glm.delve.town'}
        self.observe([a, b, spell_post(3, 'garden-1', '2026-10-09T10:00:02Z')])
        bridge.run(self.state, stub)
        regs = [o for o in stub.ops if o['op'] == 'world-arrive']
        self.assertEqual(regs, [{'op': 'world-arrive', 'principal': 'transport', 'did': DID, 'handle': 'talkie.delve.town'},
                                {'op': 'world-arrive', 'principal': 'transport', 'did': 'did:plc:' + 'b' * 24, 'handle': 'glm.delve.town'}])
        first_turn = next(i for i, o in enumerate(stub.ops) if o['op'] == 'world-turn')
        self.assertLess(max(i for i, o in enumerate(stub.ops) if o['op'] == 'world-arrive'), first_turn)
        bridge.run(self.state, stub)
        self.assertEqual(len([o for o in stub.ops if o['op'] == 'world-arrive']), 2)


class Daemon(unittest.TestCase):
    def test_a_live_pid_file_blocks_a_second_daemon(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            st = State(d, config=Config(poll=0))
            st.home.mkdir(parents=True)
            st.pidfile('bridge').write_text(str(os.getpid()))
            with self.assertRaises(SystemExit):
                st.daemon('bridge', lambda: None)
            st.pidfile('bridge').write_text('999999')  # stale
            import threading
            stop = threading.Event()
            st.daemon('bridge', stop.set, stop)


class Names(unittest.TestCase):
    """A turn line never carries a DID to a post: a person's own cards are named by their handle."""

    def test_a_persons_cards_are_named_by_handle(self):
        did = 'did:plc:' + 'k' * 24
        handles = {did: 'kestrel'}
        for obj, name in ((did, "kestrel's avatar"), ('garden', 'garden'), ('did:plc:' + 'z' * 24, 'did:plc:' + 'z' * 24)):
            self.assertEqual(bridge.card_name(obj, handles), name)
        receipt = {'height': 9, 'slug': 'lodif-rukuz', 'roots': [{'object': did, 'version': 3}], 'outcome': {'tag': 'admitted'}}
        self.assertEqual(bridge.turn_words(receipt, handles=handles), "admitted kestrel's avatar v3, entry 9, receipt lodif-rukuz")


if __name__ == '__main__':
    unittest.main()
