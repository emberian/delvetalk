"""The town's own feed (transport/feed.py, docs/WEB.md "The town's own feed"): a guest with no delve.town account plays the whole town by
posting at /AGENTS.md/feed, and the bridge's replies land in the feed with no hand between, through the one pipeline a
delve.town post takes (observe, reach, turn, draft), the posting journey of tests/test_posting.py over the feed.

Evidence for docs/WEB.md "The town's own feed" (layer: transport).

Refuted by: a feed post the bridge does not answer as it answers the same text posted on delve.town, a town reply that
waits for the hand, a reply under the town's answer that reaches nothing, or a feed post that is not an observation.
"""
import http.client
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tests.host import serve
from tests.town import Town
from transport import bridge, delve, feed, identity, post
from transport.config import Config
from transport.host import HostClient
from transport.http import Front
from transport.state import State


class Nobody:
    """delve.town, which the feed never asks."""
    def __call__(self, *a):
        raise AssertionError('the feed asked delve.town')


class Feed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.st = State(Path(cls.tmp.name) / 'front', config=Config(origin='http://127.0.0.1:8765'))
        cls.ident = identity.Identity(cls.st, delve.Client(Nobody()))
        cls.front = serve(Front(cls.st, HostClient(cls.town.process.sock), cls.ident, ('127.0.0.1', 0)))
        cls.addClassCleanup(cls.front.server_close)
        cls.addClassCleanup(cls.front.shutdown)

    def request(self, method, path, body=None, token=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.front.server_address[1], timeout=60)
        c.request(method, path, json.dumps(body) if isinstance(body, dict) else body,
                  {**({'Authorization': 'Bearer ' + token} if token else {}), **(headers or {})})
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def guest(self, name):
        code = self.ident.invite(None, 'the feed')['code']
        s, _, body = self.request('POST', '/AGENTS.md/accept', {'code': code, 'name': name})
        self.assertEqual(s, 200, body)
        return json.loads(body)['credential']

    def say(self, token, text, reply_to=None):
        """Post on the feed, run the bridge's step, -> (the post, the town's replies under it, in order)."""
        s, _, body = self.request('POST', '/AGENTS.md/feed', {'text': text, **({'reply_to': reply_to} if reply_to else {})}, token)
        self.assertEqual(s, 200, body)
        mine = json.loads(body)['post']
        bridge.run(self.st, self.town.client)
        s, _, body = self.request('GET', '/AGENTS.md/feed?thread=' + urllib.parse.quote(mine['root'] or mine['uri'], safe=''), token=token)
        [thread] = json.loads(body)['threads']
        replies = [p for p in thread['replies'] if p['town']]
        chain, under = [], mine['uri']
        while True:  # the town's answer, and its further parts each under the one before
            nxt = next((p for p in replies if p['replyTo'] == under), None)
            if nxt is None:
                return mine, chain
            chain.append(nxt)
            under = nxt['uri']

    def said(self, token, text, reply_to=None):
        mine, chain = self.say(token, text, reply_to)
        self.assertTrue(chain, f'no answer in the feed to {text!r}')
        self.assertTrue(all(len(p['text']) <= post.CLIP for p in chain))
        return '\n'.join(p['text'] for p in chain), chain

    def test_a_guest_who_only_uses_the_feed_learns_makes_grows_rules_and_sees_the_rule_fire(self):
        t = self.guest('wren')
        text = lambda s: self.said(t, s)[0]  # noqa: E731
        self.assertIn('hob: the guide, in', text('delvetalk guide'))
        self.assertIn('KINDS', text('delvetalk commonplace since / entry: 0'))
        make = 'delvetalk kinds make / name: wick / of: record / form: light: text 1..80'
        preview = text('delvetalk try\n  ' + make)
        self.assertTrue(preview.startswith('preview, nothing done'), preview)
        self.assertEqual(self.town.client.send({'op': 'world-view', 'principal': 'anonymous', 'object': 'kind/wick'})['status'], 'unknown')
        guard = next(line for line in preview.splitlines() if line.startswith('if: '))
        self.assertIn('admitted', text(guard + '\n' + make))
        thing, chain = self.said(t, 'delvetalk kind/wick make / light: moth glow')
        self.assertIn('admitted', thing)
        made = re.search(r'\b(wick/\d+)\b', thing)[1]
        grown = text(f'delvetalk {made} grow / name: trim / reading: the wick trimmed / takes: nothing\ndelvetalk {made} trim')
        self.assertEqual(grown.count(f'admitted {made}'), 2, grown)
        ruled = text(f'delvetalk {made} rule / name: lit / when: count(new.lines) >= 1 / then: delvetalk me note / text: the wick is lit')
        self.assertIn('admitted', ruled)
        # A reply under the town's answer reaches the card that answer was for, as a reply on delve.town does.
        fired, _ = self.said(t, f'delvetalk {made} trim', reply_to=chain[-1]['uri'])
        self.assertIn('lit', fired)
        self.assertIn('fired', fired)
        slug = re.search(r'receipt ([a-z]+-[a-z]+)', ruled)[1]
        self.assertIn(f'receipt {slug}', text(f'delvetalk receipt / of: {slug}'))
        # Every draft answering the feed was posted by the bridge, none waits for the hand, and each is recorded.
        waiting = [d for _, d in self.st.unposted() if feed.is_feed(d.get('replyTo'), self.st.config.origin)]
        self.assertEqual(waiting, [])
        # The feed's posts are the observer's observations, as delve.town's are.
        observed = {o['uri']: o for o in self.st.observations()}
        mine = [r for r in feed.Feed(self.st).rows() if not r['town']]
        self.assertTrue(mine and all(r['uri'] in observed for r in mine))
        self.assertEqual(observed[mine[0]['uri']]['author']['handle'], 'wren')

    def test_the_feed_page_shows_the_thread_its_receipt_and_takes_a_post_from_a_signed_in_browser(self):
        t = self.guest('robin')
        mine, chain = self.say(t, 'delvetalk library read / page: laws')
        self.assertTrue(chain)
        s, _, page = self.request('GET', '/feed', headers={'Accept': 'text/html'})
        page = page.decode()
        self.assertEqual(s, 200)
        self.assertIn('robin', page)
        self.assertRegex(page, r'class="post reply town"[^>]*>.*?the town.*?receipt [a-z]+-[a-z]+')
        s, _, page = self.request('GET', '/feed', headers={'Accept': 'text/html', 'Cookie': 'dt_credential=' + t})
        self.assertIn('<form class="say" method="post" action="/feed">', page.decode())
        s, headers, _ = self.request('POST', '/feed', 'text=' + urllib.parse.quote('delvetalk bell/1 ?'),
                                     headers={'Cookie': 'dt_credential=' + t, 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(s, 303)
        self.assertTrue(headers['Location'].startswith('/feed?posted='))
        s, _, page = self.request('GET', headers['Location'].split('#')[0], headers={'Accept': 'text/html', 'Cookie': 'dt_credential=' + t})
        self.assertIn('http-equiv="refresh"', page.decode())  # waiting for the town, the page looks again
        s, headers, _ = self.request('POST', '/feed', 'text=hello', headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual((s, headers['Location']), (303, '/enter'))  # nobody signed in: the door

    def test_a_guests_name_is_a_mention_and_a_top_level_post_is_said_to_the_town(self):
        a, b = self.guest('kit'), self.guest('moss')
        mine, chain = self.say(b, 'hello @kit, the porch is quiet')
        [obs] = [o for o in self.st.observations() if o['uri'] == mine['uri']]
        self.assertEqual([m['did'] for m in obs['mentions']], ['guest:127.0.0.1:kit'])
        self.assertEqual(obs['kind'], 'summon')
        s, _, body = self.request('POST', '/AGENTS.md/feed', {'text': 'under nothing', 'reply_to': 'at://did:web:127.0.0.1/town.delve.feed.post/nope'}, a)
        self.assertEqual(s, 400, body)


if __name__ == '__main__':
    unittest.main()
