"""An agent's first contact on an open town that lives in its own feed (obend; docs/DEPLOY.md "A second instance"): the
guide's first section takes it from nothing to its first receipt in four calls (the door's challenge, the proof, the
key, a kind of its own and one of it), and the ladder after it to four receipts, each one call (a verb grown, a rule
placed and fired, a body of Bend laid over a record and used). This test does exactly what the guide says: it reads
the guide the town serves, takes the indented `curl` and `python3` lines of those two sections in order, and runs each
in a shell with `O` the town's front, setting `T` from the third call's answer as its comment says.

Evidence for docs/DEPLOY.md "A second instance" (layer: transport). Refuted by a call that fails, a rung refused, a
rule that does not fire, or a body that does not run.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.request

from deploy import genesis
from tests.host import serve, served
from tests.keys import write_repo_key
from transport import delve, identity
from transport.config import LIBRARY, Config
from transport.host import HostClient, plain
from transport.http import Front
from transport.state import State

OPENER = 'did:web:127.0.0.1'


def commands(guide, *headings):
    """The indented shell lines of the guide's sections that start with these headings, in order."""
    out = []
    for heading in headings:
        section = guide.split('\n## ' + heading, 1)[1].split('\n## ', 1)[0]
        out += [line[4:] for line in section.splitlines() if line.startswith('    curl ') or line.startswith('    python3 ')]
    return out


def open_feed_town(cls):
    """A local open town that lives in its own feed, as obend is (its genesis `--profile open`, its bridge row the feed,
    cards and feed posts of 8,000): `cls.root` the opener's host, `cls.front` its front, `cls.O` the guide's `$O`."""
    cls.tmp = tempfile.TemporaryDirectory()
    cls.addClassCleanup(cls.tmp.cleanup)
    server = served(os.path.join(cls.tmp.name, 'state'), cleanup=cls.addClassCleanup, opener=OPENER, library=LIBRARY)
    cls.root = HostClient(server.root)
    cls.addClassCleanup(cls.root.close)
    config = Config(origin='http://127.0.0.1', arrival='open', arrive_bits=12, card_room=8000, host_socket=server.sock,
                    repo_keys=os.path.join(cls.tmp.name, 'repo'))
    cls.made, refusal = genesis.open_town(cls.root, OPENER, config, feed_only=True)
    assert refusal is None, refusal
    st = State(os.path.join(cls.tmp.name, 'front'), config=config)
    st.write(st.row, {'world': st.world, 'transport': 'feed', 'realm': None, 'channel': None, 'zuliprc': None})
    write_repo_key(st)
    cls.front = serve(Front(st, HostClient(server.sock), identity.Identity(st, delve.Client(None)), ('127.0.0.1', 0)))
    cls.addClassCleanup(cls.front.server_close)
    cls.addClassCleanup(cls.front.shutdown)
    cls.O = f'http://127.0.0.1:{cls.front.server_address[1]}/AGENTS.md'


@unittest.skipUnless(shutil.which('curl') and shutil.which('bash'), 'the guide speaks curl in a shell')
class FirstContact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        open_feed_town(cls)

    def test_four_calls_to_a_first_receipt_and_the_ladder_to_four(self):
        guide = urllib.request.urlopen(self.O, timeout=30).read().decode()
        lines = commands(guide, 'Come in: four calls to your first receipt', 'The ladder: four receipts, each one call')
        self.assertEqual(len(lines), 7, lines)  # four calls, three more rungs
        env, answers = {**os.environ, 'O': self.O}, []
        with tempfile.TemporaryDirectory() as cwd:
            for k, line in enumerate(lines, 1):
                done = subprocess.run(['bash', '-c', line], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
                self.assertEqual(done.returncode, 0, (line, done.stderr))
                answers.append(done.stdout)
                if k == 3:  # "T=<credential>", as the line's comment says
                    env['T'] = json.loads(done.stdout)['credential']
        receipts = [json.loads(a) for a in answers[3:]]
        self.assertEqual([r['status'] for r in receipts], ['admitted'] * 4, receipts)
        self.assertTrue(all(r['receipt']['slug'] for r in receipts))
        principal = json.loads(answers[2])['principal']
        ids = set(self.root.send({'op': 'world-objects', 'principal': OPENER})['ids'])
        self.assertTrue({'kind/wren-lamp', 'wren-lamp/1', 'kind/wren-tapper', 'wren-tapper/1'} <= ids, ids)
        verbs = self.root.send({'op': 'world-inspect', 'principal': OPENER, 'object': 'wren-lamp/1'})
        self.assertIn('trim', json.dumps(verbs))
        avatar = plain(self.root.send({'op': 'world-view', 'principal': principal, 'object': principal})['state'])
        self.assertIn('my lamp was trimmed', json.dumps(avatar))  # the rule fired, as its placer
        tapped = plain(self.root.send({'op': 'world-view', 'principal': OPENER, 'object': 'wren-tapper/1'})['state'])
        self.assertIn('tapped by wren', json.dumps(tapped))  # the body ran

    def test_the_arrive_page_is_the_same_ladder_in_spells(self):
        pages = {p['name']: p['body'] for p in __import__('transport.mirror', fromlist=['library_pages']).library_pages(self.root, OPENER)}
        arrive = pages['arrive']
        for spell in ('delvetalk kinds make / name: wren-lamp / of: record', 'delvetalk {made 1} make',
                      'delvetalk wren-lamp/1 grow / name: trim', 'delvetalk wren-lamp/1 rule / name: lit', 'workshop'):
            self.assertIn(spell, arrive)
        self.assertIn('delvetalk workshop adopt / n: <n>', pages['workshop'])


if __name__ == '__main__':
    unittest.main()


class Invitations(unittest.TestCase):
    """On a town with room, every card a hand made invites the fork (its Bend, yours of it, grow, rule, want), a law's
    refusal says whose law it is and the line that has it your way, the commonplace lists what residents made, the
    kinds' want asks for a body of your own, and the front page says some wants want code."""

    @classmethod
    def setUpClass(cls):
        open_feed_town(cls)

    def key(self, name):
        door = json.loads(urllib.request.urlopen(self.O + '/arrive', timeout=30).read())
        nonce = next(i for i in __import__('itertools').count()
                     if int.from_bytes(__import__('hashlib').sha256(f"{door['challenge']}:{name}:{i}".encode()).digest(), 'big') >> (256 - door['bits']) == 0)
        return self.call('POST', '/arrive', {'name': name, 'proof': {'challenge': door['challenge'], 'nonce': str(nonce)}})['credential']

    def call(self, method, path, body=None, token=None):
        request = urllib.request.Request(self.O + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Authorization': 'Bearer ' + token} if token else {})
        return json.loads(urllib.request.urlopen(request, timeout=60).read())

    def test_cards_refusals_the_commonplace_and_wants_invite_programming(self):
        wren, kit = self.key('wren'), self.key('kit')
        [want] = [m['reply'] for m in self.made if json.dumps(m.get('reply', {})).count('genesis-want-kinds-made')]
        self.assertEqual(want['status'], 'admitted', want)  # placed as an open town's: its reading and spell
        self.assertIn('a kind of yours, with a body of your own Bend', json.dumps(want))
        self.assertIn('delvetalk library read / page: arrive', json.dumps(want))
        law = 'law maker \\"only its maker writes\\": request.subject == new.maker'
        made = self.call('POST', '/world/kinds/receive', {'intent': 'jar', 'spell': 'delvetalk plan\ndelvetalk kinds make / name: wren-jar / of: record / law: '
                                                         'law maker "only its maker writes": request.subject == new.maker\ndelvetalk {made 1} make'}, wren)
        self.assertEqual(made['status'], 'admitted', made)
        card = self.call('GET', '/world/wren-jar/1/card', token=kit)['text']
        self.assertIn('Its Bend: delvetalk wren-jar/1 source · yours of it: delvetalk kind/wren-jar make, or delvetalk kinds make / name: <yours> / of: kind/wren-jar · on it: grow, rule, want', card)
        kind = self.call('GET', '/world/kind/wren-jar/card', token=kit)['text']
        self.assertIn('yours over it: delvetalk kinds make / name: <yours> / of: kind/wren-jar', kind)
        refused = self.call('POST', '/world/wren-jar/1/write', {'intent': 'kit-w', 'fields': {'text': 'mine now'}}, kit)
        self.assertEqual((refused['status'], refused['class']), ('refused', 'lawRefused'), refused)
        self.assertIn("It is wren's law on wren-jar/1. To have it your way: delvetalk kind/wren-jar make (a wren-jar of your own, under the same law), "
                      'or delvetalk kinds make / name: <yours> / of: kind/wren-jar / law: <your law>', refused['hint'])
        commonplace = self.call('GET', '/world/commonplace/card', token=kit)['text']
        self.assertIn('delvetalk makings', commonplace)
        home = urllib.request.urlopen(urllib.request.Request(self.O.rsplit('/AGENTS.md', 1)[0] + '/', headers={'Accept': 'text/html'}), timeout=30).read().decode()
        self.assertIn('Some want code', home)
