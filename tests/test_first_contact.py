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
    made, refusal = genesis.open_town(cls.root, OPENER, config, feed_only=True)
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
