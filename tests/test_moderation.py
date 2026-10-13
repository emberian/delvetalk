"""Moderation for an open door (docs/DEPLOY.md "A second instance"): the town's slow switch, a guest quieted from the
hand's guest list, an arrival from a flagged address held for the owner (let in, or turned away), and the hand's flags;
each act a line in the hand's log and, where the world changes, an entry in the journal.

Evidence for docs/DEPLOY.md "A second instance" (layer: transport). Refuted by a slow town admitting a hand's turn past
its slow hour, slow off not restoring the open town's hour, a quieted guest's turn admitted, a held key opening anything
before it is let in, a let-in guest not arriving in the world, a turned-away name able to act, or a moderation act the
journal does not hold.
"""
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tests.test_arrival import BITS, solve
from tests.test_http import FrontCase
from tests.town import Town
from tests.wire import label, record
from transport import hand
from transport.config import Config
from transport.host import HostClient
from transport.state import State

KIM = 'guest:obend.example:kim'


def opener_entries(host, opener):
    """The journal's newest entries as the opener reads them."""
    return host.send({'op': 'world-entries', 'principal': opener, 'reverse': True, 'limit': 50}).get('entries') or []


class Slow(unittest.TestCase):
    """The slow switch on a town as genesis made it, open and invited."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)

    def hand(self, **config):
        st = State(self.town.state, config=Config(root_socket=self.town.process.root, host_socket=self.town.process.sock,
                                                  opener=self.town.opener, **config))
        return hand.Hand(st, self.town.client, token='t')

    def turn(self, n):
        return self.town.send(op='world-turn', principal=KIM, object='bell/2', method='receive', identity=f'slow-{n}', reach='direct',
                              argument=record(text=label('delvetalk bell/2 rain\ntext: a slow rain'), post=label('')))

    def test_slow_holds_every_hand_to_its_hour_and_off_gives_the_open_towns_back(self):
        h = self.hand(arrival='open', turn_quota=10, slow_turns=1)
        code, _, headers = h.handle('POST', '/hand/town/newcomers/slow', f'{hand.HAND_COOKIE}=t', {'slow': 'on', 'reading': 'a flood at the porch'})
        self.assertEqual(code, 303)
        self.assertEqual(self.town.send(op='world-status', principal=KIM)['turnQuota'], 1)
        first, second = self.turn(1), self.turn(2)
        self.assertNotEqual(first['status'], 'error', first)
        refused = second['turns'][0] if second.get('status') == 'spells' else second
        self.assertEqual(refused['receipt']['outcome']['class'], 'quota', second)
        page = h.handle('GET', '/hand/town/root/', f'{hand.HAND_COOKIE}=t')[1]
        self.assertIn('<span class="code">slow</span> on', page)
        h.slow(False, 'quiet again')
        self.assertEqual(self.town.send(op='world-status', principal=KIM)['turnQuota'], 10)
        readings = [e['outcome'].get('reading') for e in opener_entries(self.town.client, self.town.opener) if (e.get('outcome') or {}).get('tag') == 'settings']
        self.assertEqual(readings[:2], ['slow off: quiet again', 'slow: a flood at the porch'])  # the journal holds both acts
        self.hand().slow(True, 'any town')  # an invited town has the switch too, and off is no cap
        self.hand().slow(False, 'over')
        self.assertEqual(self.town.send(op='world-status', principal=KIM)['turnQuota'], 0)
        log = [json.loads(line) for line in Path(self.town.state, 'hand-log.jsonl').read_text().splitlines()]
        self.assertGreaterEqual(sum(1 for line in log if line.get('what') == 'mod:settings'), 4)


class Door(FrontCase):
    """An open town's door over a real serve, moderated from the hand: held arrivals, flags, a guest quieted."""
    OPENER = 'did:plc:' + 'm' * 24
    hosted_accounts = True
    config = {'arrival': 'open', 'arrive_bits': BITS, 'arrive_per_address': 5, 'arrive_per_hour': 20, 'trust_proxy': True,
              'arrive_flagged': '192.0.2.0/24'}

    def setUp(self):
        super().setUp()
        st = State(self.tmp.name, config=Config(arrival='open', opener=self.OPENER, host_socket=self.socket, root_socket=self.root_socket))
        self.hand = hand.Hand(st, self.root, token='t')

    def ask(self, name, address):
        c = self.call('GET', '/AGENTS.md/arrive')[1]['challenge']
        s, _, body = self.request('POST', '/AGENTS.md/arrive', {'name': name, 'proof': {'challenge': c, 'nonce': solve(c, name)}},
                                  headers={'X-Forwarded-For': address})
        return s, json.loads(body)

    def worlds(self, form):
        code, page, _ = self.hand.handle('POST', '/hand/', f'{hand.HAND_COOKIE}=t', form)
        self.assertEqual(code, 200)
        return page

    def test_a_flagged_address_is_held_until_the_owner_lets_it_in(self):
        name = f'held-{self.c}'
        s, got = self.ask(name, '192.0.2.44')
        self.assertEqual((s, got['status'], got['handle']), (202, 'held', name), got)
        s, me = self.call('GET', '/AGENTS.md/me', token=got['credential'])
        self.assertEqual((s, me['class']), (403, 'denied'), me)
        self.assertIn('held at the door', me['message'])
        page = self.hand.worlds_page({})
        self.assertIn('<h2>The door</h2>', page)
        self.assertIn('held, from 192.0.2.44', page)
        self.assertIn('let in', page)
        self.worlds({'guest': 'let-in', 'name': name, 'reading': 'a postmark resident'})
        s, me = self.call('GET', '/AGENTS.md/me', token=got['credential'])
        self.assertEqual((s, me['handle']), (200, name))
        arrived = [e for e in opener_entries(self.root, self.OPENER) if json.dumps(e).find(got['principal']) >= 0]
        self.assertTrue(arrived, 'the arrival is journaled once the owner lets the guest in')

    def test_a_held_arrival_turned_away_ends_its_key_and_the_world_quiets_the_name(self):
        name = f'flood-{self.c}'
        s, got = self.ask(name, '192.0.2.45')
        self.assertEqual(got['status'], 'held')
        page = self.worlds({'guest': 'turn-away', 'name': name, 'reading': 'one of forty from one address'})
        self.assertIn(f'turned {name} away', page)
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=got['credential'])[0], 401)
        quiet = [e for e in opener_entries(self.root, self.OPENER) if (e.get('outcome') or {}).get('power') == 'quiet']
        self.assertEqual(quiet[0]['outcome']['principal'], got['principal'])
        self.assertEqual(quiet[0]['outcome']['reading'], 'turned away at the door: one of forty from one address')

    def test_the_hand_flags_an_address_and_unflags_it(self):
        self.worlds({'guest': 'flag', 'address': '198.51.100.0/24'})
        self.assertEqual(self.ask(f'f1-{self.c}', '198.51.100.9')[1]['status'], 'held')
        self.assertIn('198.51.100.0/24', self.hand.worlds_page({}))
        self.worlds({'guest': 'unflag', 'address': '198.51.100.0/24'})
        self.assertEqual(self.ask(f'f2-{self.c}', '198.51.100.9')[1]['status'], 'arrived')
        self.assertEqual(self.ask(f'f3-{self.c}', '203.0.113.7')[1]['status'], 'arrived')  # no flag, no hold
        log = [json.loads(line)['what'] for line in Path(self.tmp.name, 'hand-log.jsonl').read_text().splitlines()]
        self.assertEqual([w for w in log if w in ('flag', 'unflag')], ['flag', 'unflag'])

    def test_a_guest_is_quieted_from_the_guest_list_and_unquieted(self):
        s, got = self.ask(f'loud-{self.c}', '203.0.113.8')
        self.assertEqual(got['status'], 'arrived')
        self.assertIn('<input type="hidden" name="guest" value="quiet">', self.hand.worlds_page({}))
        self.worlds({'guest': 'quiet', 'name': got['handle'], 'hours': '2', 'reading': 'shouting on the porch'})
        s, r = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': {'tag': 'record', 'fields': []}, 'intent': 'q1'}, got['credential'])
        self.assertEqual((r['status'], r.get('class')), ('refused', 'quiet'), r)
        powers = [(e['outcome'].get('power'), e['outcome'].get('reading')) for e in opener_entries(self.root, self.OPENER)
                  if (e.get('outcome') or {}).get('tag') == 'moderated']
        self.assertIn(('quiet', 'shouting on the porch'), powers)
        self.worlds({'guest': 'unquiet', 'name': got['handle'], 'reading': 'calmer now'})
        s, r = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': {'tag': 'record', 'fields': []}, 'intent': 'q2'}, got['credential'])
        self.assertEqual(r['status'], 'admitted', r)


if __name__ == '__main__':
    unittest.main()
