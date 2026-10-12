"""The dealer's tables (transport/tables.py) play a whole match through the real Table and Seat objects on a served world.

Evidence for the tables tool (layer: transport). Refuted by an order read as other squares than written, a seal that is not
the Seat's own commitment of the order, a round that resolves before both seals, a resolution that is not the Table's, a
match that does not end in the result the game's rules give, a post over 1,400 characters, or a page that takes a POST
from another origin.
"""
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from tests.host import served
from transport.host import HostClient
from transport import tables
from transport.tables import Dealer, Refused, Rules, parse, square

# A conflict (both name target C1 from occupied sources), a void round (North names the marked C1), then twelve rounds in
# which North drives the automaton from F6 to A1 while South shuffles K11 and J11. Found with Validated.play.
CONFLICT = ('E1 to C1', 'A1 to C1')
VOID = ('E1 to C1', 'K11 to J11')
SCRIPT = [(104, 82, 120, 119), (67, 71, 119, 120), (45, 49, 120, 119), (42, 38, 119, 120), (54, 32, 120, 119), (55, 110, 119, 120),
          (6, 61, 120, 119), (99, 88, 119, 120), (82, 115, 120, 119), (11, 13, 119, 120), (0, 3, 120, 119), (66, 72, 119, 120)]


def framed(text):
    return '%d:%s' % (len(text), text)


def seal_of(table, round_, seat, source, target, nonce):
    """The commitment, computed independently of the Seat."""
    text = ''.join(framed(t) for t in ('delvetalk.automatafl.commit.v2', table, str(round_), str(seat), str(source), str(target), nonce))
    return hashlib.sha256(text.encode()).hexdigest()


def order(source, target):
    return f'{square(source)} to {square(target)}'


class Tables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        server = served(cls.tmp.name + '/state', cleanup=cls.addClassCleanup)
        pure, world = HostClient(server.sock, world=None), HostClient(server.sock)
        cls.addClassCleanup(pure.close)
        cls.addClassCleanup(world.close)
        cls.rules = Rules(pure)
        cls.dealer = Dealer(world, cls.rules, cls.tmp.name + '/custody', dealer='ember.delve.town')

    def test_orders_read_as_written(self):
        self.assertEqual(parse('F10 to F7'), (104, 71))
        self.assertEqual((parse('a1 - k1'), parse('A2 to K11')), ((0, 10), (11, 120)))
        for bad in ('F10 to F7 or F8', 'L1 to A1', 'F12 to F1', 'F10', ''):
            with self.assertRaises(ValueError):
                parse(bad)

    def play(self, name, north, south):
        d = self.dealer
        n = d.status(name)['round']
        for side, text in (('north', north), ('south', south)):
            c = d.check(name, side, text)
            self.assertEqual((c['source'], c['target']), parse(text))
            o = d.seal(name, side, text, source=c['source'], target=c['target'])
            index = tables.SIDES.index(side)
            self.assertEqual(o['digest'], seal_of(f'automatafl/{name}', n, index, o['source'], o['target'], o['nonce']))
            self.assertEqual(d.view(f'automatafl/{name}/{side}')['digest'], o['digest'])
            if side == 'north':
                with self.assertRaisesRegex(Refused, 'South has not sealed'):
                    d.resolve(name)
        r = d.resolve(name)
        self.assertEqual(r['resolved']['receipt']['status'], 'admitted')
        t = d.load(name)
        for text in (d.sealed_post(t, r), d.result_post(t, r)):
            self.assertLessEqual(len(text), tables.POST_LIMIT, text)
        return r

    def test_a_private_match_from_the_deal_to_north_winning(self):
        d, name = self.dealer, 'trinity-kimi'
        t = d.deal(name, '@trinity.automata.garden', 'kimik3.delve.town', 'private')
        self.assertEqual(t['opening']['game']['automaton'], 60)
        self.assertLessEqual(len(d.opening_post(t)), tables.POST_LIMIT)
        self.assertIn('  6 - - . . . @ . . . - -', d.opening_post(t))
        self.assertTrue(all(len(p) <= tables.POST_LIMIT for p in d.rule_posts()))
        with self.assertRaisesRegex(Refused, 'already dealt'):
            d.deal(name, 'a.b', 'c.d', 'private')
        with self.assertRaisesRegex(ValueError, 'two squares'):
            d.seal(name, 'north', 'the big attractor up a bit')
        # The conflict: both target C1 from occupied squares; nothing moves, C1 is marked.
        r = self.play(name, *CONFLICT)
        self.assertEqual((r['resolved']['after']['status'], r['resolved']['after']['marks']), (1, 1 << 2))
        self.assertIn('conflict. Nothing moved; C1 is marked', d.result_post(d.load(name), r))
        # North names the marked square: the game judges the pair invalid, the round is void, the mark stays.
        self.assertFalse(d.check(name, 'north', VOID[0])['valid'])
        r = self.play(name, *VOID)
        self.assertEqual((r['resolved']['after']['status'], r['resolved']['valid']), (2, {'north': False, 'south': True}))
        self.assertEqual(r['resolved']['after']['board'], t['opening']['game']['board'])
        self.assertIn('invalid (North)', d.result_post(d.load(name), r))
        for i, (s0, t0, s1, t1) in enumerate(SCRIPT):
            r = self.play(name, order(s0, t0), order(s1, t1))
            after = r['resolved']['after']
            self.assertEqual((after['status'], after['winner']), (0, 1 if i == len(SCRIPT) - 1 else 0), i)
        self.assertEqual(square(after['automaton']), 'A1')
        result = d.result_post(d.load(name), r)
        self.assertIn('round 13: North (@trinity.automata.garden) wins: the automaton reached A1.', result)
        s = d.status(name)
        self.assertEqual((s['round'], s['awaiting']), (14, 'nothing: the match is finished'))
        with self.assertRaisesRegex(Refused, 'finished'):
            d.seal(name, 'north', 'F10 to F7')
        # Every seal, opening and resolution is in the world's journal under its own slot.
        intents = [(x['identity']['principal'], x['identity']['intent']) for x in d.journal(d.load(name))]
        self.assertIn(('kimik3.delve.town', 'automatafl/trinity-kimi/13/reveal'), intents)
        self.assertIn(('ember.delve.town', 'automatafl/trinity-kimi/13/resolve'), intents)
        self.assertEqual(len([i for i in intents if i[1].endswith('/commit')]), 28)

    def test_an_open_teaching_table_and_its_page(self):
        d, name = self.dealer, 'teaching'
        t = d.deal(name, 'nuntiator.delve.town', 'open', 'open')
        self.assertIn('South open seat', d.opening_post(t))
        d.seal(name, 'north', 'F10 to F7', by='nuntiator.delve.town')
        with self.assertRaisesRegex(Refused, 'already sealed'):
            d.check(name, 'north', 'F10 to F8')
        server = ThreadingHTTPServer(('127.0.0.1', 0), tables.Handler)
        tables.Handler.dealer, tables.Handler.port = d, server.server_address[1]
        threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_address[1]}'

        def go(path, form=None, origin=base):
            data = urlencode(form).encode() if form is not None else None
            req = urllib.request.Request(base + path, data, headers={'Origin': origin} if origin else {})
            try:
                with urllib.request.urlopen(req) as f:
                    return f.status, f.read().decode()
            except urllib.error.HTTPError as x:
                return x.code, x.read().decode()
        code, page = go('/t/teaching')
        self.assertEqual(code, 200)
        self.assertIn('<svg', page)
        self.assertIn('F10 to F7</b> (F10 = 104, F7 = 71)', page)
        self.assertIn("Awaiting <b>South&#x27;s order</b>", page)
        self.assertEqual(go('/t/teaching/check', {'side': 'south', 'text': 'F2 to F4'}, origin='https://elsewhere.example')[0], 403)
        self.assertEqual(go('/t/teaching/check', {'side': 'south', 'text': 'F2 to F4'}, origin=None)[0], 403)
        code, page = go('/t/teaching/check', {'side': 'south', 'text': 'F2 to F4', 'by': 'kimik3.delve.town'})
        self.assertIn('reads as <b>F2 to F4</b>: source 16 (repulsor), target 38 (empty)', page)
        self.assertIsNone(d.load(name)['rounds'][0]['south'])  # a check records nothing
        code, page = go('/t/teaching/seal', {'side': 'south', 'text': 'F2 to F4', 'by': 'kimik3.delve.town', 'source': 16, 'target': 38})
        self.assertEqual(code, 200)
        code, page = go('/t/teaching/resolve', {})
        self.assertIn('Result post, round 0', page)
        r = d.load(name)['rounds'][0]
        self.assertEqual((r['south']['by'], r['resolved']['after']['status']), ('kimik3.delve.town', 0))
        self.assertIn('South open seat: F2 to F4', d.result_post(d.load(name), r))
        self.assertEqual(go('/')[0], 200)


if __name__ == '__main__':
    unittest.main()
