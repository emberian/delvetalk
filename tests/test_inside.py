"""A town that documents itself from inside (the owner: "is the system self-documenting entirely within itself?"):
from one key and in-world reads alone (spells sent to cards, as a post in the feed sends them), an agent finds the
library's pages, reads the language page, reads the Bend of a kind (`delvetalk kind/door source`, the commonplace's
`source` read, paged within the room), reads the world's API page, and finds what residents made (`delvetalk makings`).
Every example on the language page compiles with the town's own checker (`workshop check / over: kind/record`), and
its door is the door's file, quoted.

Evidence for docs/DEPLOY.md "A second instance" (layer: objects). Refuted by a page missing from the library, a kind's
source that cannot be read by a spell, an example the checker refuses, or a quotation that is not its file's.
"""
import hashlib
import itertools
import json
import re
import unittest
import urllib.request
from pathlib import Path

from tests.test_first_contact import open_feed_town

ROOT = Path(__file__).resolve().parent.parent


class Inside(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        open_feed_town(cls)
        door = json.loads(cls.http('GET', '/arrive'))
        nonce = next(i for i in itertools.count() if int.from_bytes(hashlib.sha256(f"{door['challenge']}:kit:{i}".encode()).digest(), 'big') >> (256 - door['bits']) == 0)
        cls.T = json.loads(cls.http('POST', '/arrive', {'name': 'kit', 'proof': {'challenge': door['challenge'], 'nonce': str(nonce)}}))['credential']
        cls.n = 0

    @classmethod
    def http(cls, method, path, body=None, token=None):
        request = urllib.request.Request(cls.O + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Authorization': 'Bearer ' + token} if token else {})
        return urllib.request.urlopen(request, timeout=60).read().decode()

    def said(self, card, spell):
        """A spell sent to its card, as a post would send it; -> everything the answer says, as one text."""
        type(self).n += 1
        r = json.loads(self.http('POST', f'/world/{card}/receive', {'intent': f'in-{self.n}', 'spell': spell}, self.T))
        self.assertNotEqual(r.get('status'), 'refused', r)
        return r.get('text') or '\n'.join(o if isinstance(o, str) else o.get('text', '') for o in r.get('offers') or [])

    def test_from_one_key_the_library_the_language_a_kinds_bend_and_the_api(self):
        index = json.loads(self.http('GET', '/world/library/card', token=self.T))['text']  # the library's card: its index
        for page in ('bend', 'api', 'reads', 'authoring', 'workshop'):
            self.assertRegex(index, rf'\b{page}\b')
        bend = self.said('library', 'delvetalk library read / page: bend')
        self.assertIn('A BODY is forms and defs', bend)
        door = self.said('kind/door', 'delvetalk kind/door source')
        self.assertIn('THE BEND of kind/door', door)
        self.assertIn('def knock(state: State, context: Abi.Context)', door)
        self.assertIn('delvetalk kinds make / name: <yours> / of: kind/door', door)
        api = self.said('library', 'delvetalk library read / page: api')
        self.assertIn('POST /AGENTS.md/world/{object}/{method}', api)
        self.assertNotIn('/AGENTS.md/challenge', api)
        reads = self.said('library', 'delvetalk library read / page: reads')
        self.assertIn('hob reads for a town of cards', reads)

    def test_a_long_source_is_paged_within_the_room(self):
        first = self.said('station', 'delvetalk station source')
        self.assertIn('THE BEND of station', first)
        self.assertRegex(first, r'ITS SOURCE, page 1 of (\d+):')
        self.assertIn('The next: delvetalk station source / page: 2', first)
        self.assertLessEqual(len(first), 8000)
        self.assertIn('page 2 of', self.said('station', 'delvetalk station source / page: 2'))

    def test_what_residents_made_lists_a_kind_with_a_body_and_a_verb(self):
        self.said('kinds', 'delvetalk plan\ndelvetalk kinds make / name: kit-gong / of: record\nbody: <<BEND\nform strike:\n'
                           'def strike(state: State, context: Abi.Context) -> Activity<Nat>:\n  Super.inscribe(state, "strike", "struck", context)\n'
                           'BEND\ndelvetalk {made 1} make')
        self.said('kit-gong/1', 'delvetalk kit-gong/1 grow / name: hush / reading: hushed / takes: nothing')
        made = self.said('commonplace', 'delvetalk makings')
        self.assertIn('kind/kit-gong by kit, its own Bend over record', made)
        self.assertIn('verb hush on kit-gong/1, grown by kit', made)

    def test_every_example_on_the_language_page_compiles_and_its_door_is_the_files(self):
        page = self.said('library', 'delvetalk library read / page: bend')
        blocks = re.findall(r'```obend\n(.*?)```', page, re.S)
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            self.assertIn('Checked: it compiles', self.said('workshop', f'delvetalk workshop check / over: kind/record\n```obend\n{block}```'), block)
        door = (ROOT / 'world' / 'bodies' / 'door.obend').read_text()
        quoted = page.split('A REAL ONE', 1)[1].split('THE PATH', 1)[0]
        body = '\n'.join(line[2:] for line in quoted.splitlines()[1:] if line.startswith('  '))
        self.assertIn('def knock(', body)
        self.assertIn(body, door)


if __name__ == '__main__':
    unittest.main()
