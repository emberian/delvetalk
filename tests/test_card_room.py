"""A world's room (docs/DEPLOY.md "A second instance"): the characters a reader is shown of a card were 1,400 because
that is what one delve.town post holds. A town that lives in its own feed gives its readers kilobytes: `world-settings
{cardRoom}` (the opener's, journaled, replayed and kept by a snapshot; `hand limits` sets it from the config's
`card_room`), which the host's clip of a card applies and every running method reads as `Context.room`, so Bend's
`Card.limit` and the pages it paginates follow. The model's copy of a card stays at one post. A feed-only town's
answers are posted whole up to the same room, and threaded only past it; the hour's delve.town posts and one
resident's share of them count nothing there. A world that sets no room is as it was, byte for byte.

Evidence for docs/DEPLOY.md "A second instance" (layer: host).
"""
import json
import tempfile
import unittest

from tests.host import HostCase
from tests.test_transport import Recorder
from tests.bend import declared
from tests.wire import field, label, record
from transport import feed, post
from transport.config import Config
from transport.state import State

ROOMY = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
import ./Card.obend as Card
record State:
  room: Nat
  limit: Nat
def initial() -> State:
  {room: 0n, limit: 0n}
def look(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write({room: Plans.Edit::<Nat, Nat>.set({value: context.room}), limit: Plans.Edit::<Nat, Nat>.set({value: Card.limit(context)})}):
    case written(_): context.room
    case _: 0n
""")
LONG = ('A long card, line after line of it. ' * 160).strip() + '\n'  # about 5,600 characters


class Room(HostCase):
    def setUp(self):
        super().setUp()
        from transport.config import LIBRARY
        r = self.host.send(op="world-open", path=self.path, library=str(LIBRARY), principal="ember", opener="ember")
        self.assertEqual(r["status"], "opened", r)
        made = self.host.send(op="world-create", principal="ember", identity="mk-roomy", object="roomy", source=ROOMY,
                              entry="initial", seed=record())
        self.assertEqual(made["status"], "created", made)
        card = self.host.send(op="world-root", principal="ember", reason="a long card", act={"kind": "card", "object": "roomy", "text": LONG})
        self.assertEqual(card["status"], "root", card)

    def looked(self, intent):
        r = self.host.send(op="world-turn", principal="ember", object="roomy", method="look", argument=record(), identity=intent)
        self.assertEqual(r["status"], "admitted", r)
        state = self.host.send(op="world-view", principal="ember", object="roomy")["state"]
        return int(field(state, "room")["value"]), int(field(state, "limit")["value"])

    def shown(self):
        return self.host.send(op="world-card", principal="ember", object="roomy")["text"]

    def settings(self, **values):
        return self.host.send(op="world-settings", principal="ember", reading="a town that lives in its own feed", **values)

    def test_a_world_that_sets_no_room_shows_one_post(self):
        self.assertEqual(self.looked("a")[0], 1400)
        self.assertLessEqual(len(self.shown()), 1400)
        self.assertIn('[clipped at 1400 characters', self.shown())
        self.assertNotIn("cardRoom", self.host.send(op="world-status"))

    def test_a_room_given_is_the_cards_and_every_methods_and_survives_replay(self):
        self.assertEqual(self.settings(cardRoom=8000)["status"], "settings")
        room, limit = self.looked("b")
        self.assertEqual((room, limit), (8000, 8000 - (2 * len("roomy") + 120)))
        self.assertEqual(self.shown(), LONG)
        self.assertEqual(self.host.send(op="world-status")["cardRoom"], 8000)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.release()
        h = self.spawn()
        self.assertEqual(h.send(op="world-open", path=self.path, verify=True)["status"], "opened")
        self.assertEqual(h.send(op="world-card", principal="ember", object="roomy")["text"], LONG)
        self.assertEqual(h.send(op="world-status")["cardRoom"], 8000)

    def test_a_room_outside_its_bounds_is_refused_and_the_moderated_power_names_none(self):
        for n in (1000, 65537):
            r = self.settings(cardRoom=n)
            self.assertEqual(r["status"], "error", r)
            self.assertIn("cardRoom is 1400 to 65536", r["message"])
        self.assertEqual(self.looked("c")[0], 1400)

    def test_the_feeds_posts_count_against_no_hour_and_no_share(self):
        from transport.host import CLOCK
        reserve = lambda intent, source: self.host.send(op="world-post-reserve", principal=CLOCK, intent=intent, source=source, **{"for": "guest:local:wren"})
        self.assertTrue(all(reserve(f"f{n}", "feed")["status"] == "reserved" for n in range(40)))
        delve = [reserve(f"d{n}", "delve")["status"] for n in range(6)]
        self.assertEqual(delve, ["reserved"] * 4 + ["refused"] * 2)  # a quarter of the hour's 16 answer one resident there


class FeedAnswers(unittest.TestCase):
    """A town's answer in its own feed: one post up to its room on a feed-only town, numbered parts past one post's
    1,400 elsewhere; the feed's reservations count against no hour's delve.town quota."""

    def drafted(self, transport, room):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = State(tmp.name, config=Config(card_room=room))
        if transport:
            st.write(st.row, {'world': st.world, 'transport': transport, 'realm': None, 'channel': None, 'zuliprc': None})
        local = feed.Feed(st)
        self.addCleanup(local.close)
        parent = local.post({'did': 'guest:local:wren', 'handle': 'wren'}, 'delvetalk library')
        for n in range(20):  # more answers than the town-wide 16 and one resident's 4, to one resident
            st.write(st.outbox / f'{n + 1}-feed.json', {'text': LONG, 'replyTo': parent['uri'], 'object': 'library', 'posted': False,
                                                         'principal': 'guest:local:wren'})
        host = Recorder(quota=16)
        feed.post_drafts(st, host, local)
        rows = local.db.execute('SELECT text FROM feed WHERE town=1').fetchall()
        return [r[0] for r in rows], host

    def test_a_feed_only_town_posts_each_answer_whole(self):
        texts, host = self.drafted('feed', 8000)
        self.assertEqual(texts, [LONG] * 20)
        self.assertTrue(all(op['source'] == 'feed' for op in host.ops if op['op'] == 'world-post-reserve'))

    def test_elsewhere_an_answer_is_threaded_at_one_posts_room(self):
        texts, _ = self.drafted(None, 8000)  # the default row speaks delve.town: one post holds 1,400 whatever the config
        self.assertEqual(len(texts), 20 * len(post.parts(LONG)))
        self.assertTrue(all(len(t) <= post.CLIP for t in texts))


if __name__ == '__main__':
    unittest.main()


class LibraryRoom(unittest.TestCase):
    """A library page holds what one reply of the library shows (`Card.limit`): 1,266 characters at one post's room,
    the room less the receipt line where the world gives more. A page past it is refused `tooLong`, never cut."""

    def test_a_page_is_bounded_by_the_worlds_room(self):
        from deploy import genesis
        from tests.town import Town
        from tests.wire import nat
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        town = Town(tmp.name, cleanup=self.addCleanup, furnished=False)
        shelve = lambda n, body: town.send(op='world-turn', principal=town.opener, object='library', method='shelve', identity=f'shelve-{n}',
                                           argument=record(name=label(f'long-{n}'), kind={'tag': 'variant', 'label': 'page', 'payload': record()},
                                                           title=label('a long page'), body=label(body)))
        self.assertEqual(shelve(1, 'x' * genesis.page_limit()).get('status'), 'admitted')
        over = shelve(2, 'x' * (genesis.page_limit() + 1))
        self.assertEqual((over['status'], over['receipt']['outcome'].get('clause')), ('refused', 'tooLong'), over)
        self.assertEqual(town.send(op='world-settings', principal=town.opener, reading='a feed-only town', cardRoom=8000)['status'], 'settings')
        self.assertEqual(shelve(3, 'x' * genesis.page_limit(8000)).get('status'), 'admitted')
        self.assertEqual(shelve(4, 'x' * (genesis.page_limit(8000) + 1))['status'], 'refused')
        read = town.send(op='world-turn', principal='guest:t:wren', object='library', method='read', identity='read-3',
                         argument=record(page=label('long-3')))
        self.assertIn('x' * genesis.page_limit(8000), json.dumps(read))
