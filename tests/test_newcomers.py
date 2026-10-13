"""An open town's limits for newcomers (docs/DEPLOY.md "A second instance"): the host's journaled quotas `turnQuota`
(a hand's turns a clock hour), `objectQuota` (the objects a hand keeps) and `paintQuota` (the town's paints a day),
beside `modelQuota` (hob's readings a day, which now answers with the card's spells); serve's `--scratch-quota`; the
feed's posts an hour; and `hand limits`, which sets the config's in the world with a reading. A world that never sets
them is as it was.

Evidence for docs/DEPLOY.md "A second instance" (layer: host). Refuted by a turn past the hour's quota admitted, the
count lost at a reopen or kept past the hour, the opener or another hand counted, an object past the quota made, a paint
queued past the day's budget or a card left without saying why, hob's spent day answering without the card's spells,
a second scratch world opened, or an invited town's settings, status or snapshot changed.
"""
import os
import tempfile
import unittest
from pathlib import Path

from tests.bend import counter_modules
from tests.host import HostCase, served
from tests.town import Town
from tests.wire import label, nat, record
from transport.config import Config
from transport.delve import Failure
from transport.host import HostClient
from transport.state import State

KIM, LEE = 'guest:obend.example:kim', 'guest:obend.example:lee'


class Quotas(HostCase):
    """The host's quotas on a bare world: the opener `ember`, the clock `clock`."""

    def setUp(self):
        super().setUp()
        r = self.host.send(op='world-open', path=self.path, principal='ember', clock='clock', opener='ember')
        self.assertNotEqual(r.get('status'), 'error', r)
        made = self.host.send(op='world-create', principal='ember', identity='mk-c', object='c', modules=counter_modules(),
                              entry='initial', seed=record(count=nat(0)))
        self.assertEqual(made['status'], 'created', made)
        self.advance(5)

    def advance(self, height):
        r = self.host.send(op='world-advance', principal='clock', identity=f'tick{height}', height=height)
        self.assertEqual(r['status'], 'advanced', r)

    def settings(self, **quotas):
        r = self.host.send(op='world-settings', principal='ember', reading='newcomers', **quotas)
        self.assertEqual(r['status'], 'settings', r)
        return r

    def bump(self, principal, identity):
        return self.host.send(op='world-turn', principal=principal, object='c', method='bump', argument=record(), identity=identity)

    def test_a_world_that_sets_none_counts_none(self):
        status = self.host.send(op='world-status', principal=KIM)
        self.assertEqual((status['turnQuota'], status['objectQuota'], status['paintQuota']['quota']), (0, 128, 0))
        self.assertNotIn('turns', status)
        for i in range(70):
            self.assertEqual(self.bump(KIM, f'k{i}')['status'], 'admitted')
        self.assertEqual(self.host.send(op='world-snapshot')['status'], 'snapshot')
        snapshot = next(p for p in os.listdir(os.path.dirname(self.path)) if p.startswith(os.path.basename(self.path) + '.snapshot.'))
        raw = Path(os.path.dirname(self.path), snapshot).read_bytes()
        for key in (b'turnsStarted', b'turnQuota', b'objectQuota', b'paintQuota'):
            self.assertNotIn(key, raw)  # a world that never set one keeps its snapshot's bytes

    def test_the_hours_turns_are_counted_per_hand_and_the_next_waits_for_the_hour(self):
        settings = self.settings(turnQuota=3)
        self.assertEqual(settings['receipt']['outcome']['turnQuota'], 3)
        for i in range(3):
            self.assertEqual(self.bump(KIM, f'k{i}')['status'], 'admitted')
        self.assertEqual(self.host.send(op='world-status', principal=KIM)['turns'], {'remaining': 0, 'next': 60})
        r = self.bump(KIM, 'k3')
        out = r['receipt']['outcome']
        self.assertEqual((r['status'], out['class'], out['clause'], out['next']), ('refused', 'quota', 'turnQuota', 60), r)
        self.assertIn('3 turns an hour from each hand', out['reason'])
        public = self.host.send(op='world-receipt', principal=LEE, identity='k3', of=KIM)
        self.assertEqual((public['class'], public['next']), ('quota', 60), public)
        # another hand has its own hour; the opener is never counted, nor is a spell's quota refusal itself
        self.assertEqual(self.bump(LEE, 'l0')['status'], 'admitted')
        for i in range(5):
            self.assertEqual(self.bump('ember', f'e{i}')['status'], 'admitted')
        self.assertNotIn('turns', self.host.send(op='world-status', principal='ember'))
        # the count is the journal's: it stands after a reopen, and the refusal was transient, so the hour lets it run
        self.reopen()
        self.assertEqual(self.bump(KIM, 'k3')['receipt']['outcome']['class'], 'quota')
        self.advance(60)
        self.assertEqual(self.host.send(op='world-status', principal=KIM)['turns'], {'remaining': 3, 'next': 120})
        self.assertEqual(self.bump(KIM, 'k3')['status'], 'admitted')
        # slow is the same setting lower, and none lifts it
        self.settings(turnQuota=1)
        self.assertEqual(self.bump(KIM, 'k4')['receipt']['outcome']['class'], 'quota')
        self.settings(turnQuota=0)
        self.assertEqual(self.bump(KIM, 'k4')['status'], 'admitted')

    def test_the_objects_a_hand_keeps_are_its_quotas(self):
        self.settings(objectQuota=1)
        made = lambda who, name: self.host.send(op='world-create', principal=who, identity='mk-' + name, object=name,
                                                modules=counter_modules(), entry='initial', seed=record(count=nat(0)))
        self.assertEqual(made(KIM, 'k-one')['status'], 'created')
        second = made(KIM, 'k-two')
        self.assertEqual((second['status'], second['receipt']['outcome']['class']), ('refused', 'capacity'), second)
        self.assertIn('objectsPerPrincipal', second['receipt']['outcome']['reason'])
        self.assertEqual(made(LEE, 'l-one')['status'], 'created')
        self.assertEqual(made('ember', 'e-two')['status'], 'created')
        self.assertEqual(self.host.send(op='world-status', principal=KIM)['objectQuota'], 1)
        self.reopen()
        self.assertEqual(self.host.send(op='world-status')['objectQuota'], 1)  # journaled: replay sets it again


class Budgets(unittest.TestCase):
    """The town's day of paints and of hob's readings, on a town as genesis made it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)

    def settings(self, **quotas):
        r = self.town.send(op='world-settings', principal=self.town.opener, reading='budgets', **quotas)
        self.assertEqual(r['status'], 'settings', r)

    def test_past_the_days_paints_a_card_is_read_exact_saying_why(self):
        self.settings(paintQuota=1)
        first = self.town.send(op='world-render', principal=KIM, object='porch')
        self.assertNotEqual(first.get('reason'), 'budget', first)  # queued for the worker: the day's one
        used = self.town.send(op='world-status')['paintQuota']
        self.assertEqual(used['quota'], 1)
        second = self.town.send(op='world-render', principal=KIM, object='bell/1')
        self.assertEqual((second['status'], second['reason']), ('exact', 'budget'), second)
        self.assertIn("paints for the day are spent", second['detail'])
        from transport.host import place
        here = place(HostClient(self.town.process.sock), KIM, 'bell/1', sleep=lambda _: None)
        self.assertIsNone(here['paint'])
        self.assertIn('paints for the day are spent', here['spent'])
        from transport import pages
        self.assertIn('<p class="aside spent">', pages.place(here['card'], here['paint'], here['wants'], here.get('spent')))
        self.settings(paintQuota=0)  # no cap again
        self.assertNotEqual(self.town.send(op='world-render', principal=KIM, object='bell/2').get('reason'), 'budget')

    def test_hobs_spent_day_answers_with_the_cards_spells(self):
        self.settings(modelQuota=0)
        r = self.town.send(op='world-turn', principal=KIM, object='bell/1', method='receive', identity='hob-spent', reach='direct',
                           argument=record(text=label('could it ring softly for the moths?'), post=label('')))
        out = r['receipt']['outcome']
        self.assertEqual((r['status'], out['class']), ('refused', 'quota'), r)
        self.assertIn('model readings for the day are spent', out['reason'])
        self.assertIn('delvetalk bell/1 ', out['hint'])  # the card's spells, which need no reading
        public = self.town.send(op='world-receipt', principal=LEE, identity='hob-spent', of=KIM)
        self.assertEqual(public['hint'], out['hint'])
        self.settings(modelQuota=2000)


class Transport(unittest.TestCase):
    """What the transport holds of an open town's limits: serve's scratch worlds, the feed's hour, `hand limits`."""

    def state(self, **config):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return tmp.name, State(tmp.name, config=Config(**config))

    def test_an_open_town_serves_one_scratch_world_a_hand_and_an_invited_town_two(self):
        for arrival, held in (('open', 1), ('invited', 2)):
            directory, _ = self.state()
            server = served(directory, cleanup=self.addCleanup, arrival=arrival, scratch_quota=1)
            host = HostClient(server.sock)
            self.addCleanup(host.close)
            opened = [host.send({'op': 'world-scratch', 'principal': KIM, 'name': f's{n}'}).get('status') for n in range(3)]
            self.assertEqual(opened, ['scratch'] * held + ['refused'] * (3 - held), arrival)

    def test_the_feeds_hour_is_the_open_towns_own(self):
        from transport.feed import Feed, HOUR_POSTS
        _, st = self.state(arrival='open', feed_quota=2)
        feed = Feed(st)
        self.addCleanup(feed.close)
        author = {'did': KIM, 'handle': 'kim'}
        for n in range(2):
            feed.post(author, f'post {n}', now=1000.0 + n)
        with self.assertRaises(Failure) as caught:
            feed.post(author, 'one more', now=1010.0)
        self.assertEqual(caught.exception.code, 'feed_quota')
        _, invited = self.state(feed_quota=2)
        self.assertEqual(Feed(invited).quota, HOUR_POSTS)

    def test_hand_limits_sets_the_configs_in_the_world_and_an_invited_town_refuses(self):
        from transport import hand
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        town = Town(tmp.name, cleanup=self.addCleanup, furnished=False)
        st = State(town.state, config=Config(arrival='open', turn_quota=7, object_quota=5, paint_budget=9, hob_budget=11,
                                             root_socket=town.process.root, host_socket=town.process.sock, opener=town.opener))
        got = hand.Hand(st, town.client).limits()
        self.assertEqual(got['status'], 'settings', got)
        status = town.send(op='world-status', principal=KIM)
        self.assertEqual((status['turnQuota'], status['objectQuota'], status['paintQuota']['quota'], status['modelQuota']['quota'],
                          status['turns']['remaining']), (7, 5, 9, 11, 7))
        invited = State(town.state, config=Config(root_socket=town.process.root, host_socket=town.process.sock, opener=town.opener))
        with self.assertRaises(hand.HandError):
            hand.Hand(invited, town.client).limits()
        # the root page shows them and sets them again, on an open town only
        h = hand.Hand(st, town.client, token='t')
        jar = f'{hand.HAND_COOKIE}=t'
        code, page, _ = h.handle('GET', '/hand/town/root/', jar)
        self.assertEqual(code, 200)
        self.assertIn('<h2>Newcomers</h2>', page)
        self.assertIn('turns a hand an hour: 7', page)
        code, _, headers = h.handle('POST', '/hand/town/newcomers/limits', jar, {'reading': 'again'})
        self.assertEqual(code, 303)
        self.assertIn('limits%3A+settings', dict(headers)['Location'])
        code, page, _ = hand.Hand(invited, town.client, token='t').handle('GET', '/hand/town/root/', jar)
        self.assertNotIn('<h2>Newcomers</h2>', page)


if __name__ == '__main__':
    unittest.main()
