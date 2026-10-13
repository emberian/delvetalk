"""An open town's door (docs/DEPLOY.md "A second instance"; config `arrival = "open"`): a key for the asking, by a page
or by the API, for a small proof of work, so many an hour from one address and in all; a name taken is refused and the
proof stays unspent; invitations still work; an invited town's door is as it was.

Evidence for docs/DEPLOY.md "A second instance" (layer: transport).
"""
import hashlib
import html
import itertools
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tests.keys import write_repo_key
from tests.test_http import FrontCase
from transport import delve, identity
from transport.config import Config
from transport.host import PUBLIC, handles
from transport.identity import IdentityError, proof_digest, zero_bits
from transport.state import State

FORM = 'application/x-www-form-urlencoded'
BITS = 8  # a test's proof: about 256 tries


def solve(challenge, name, bits=BITS):
    """A nonce for which SHA-256 of `challenge:name:nonce` begins with `bits` zero bits: the work the page and an agent do."""
    return next(str(n) for n in itertools.count() if zero_bits(proof_digest(challenge, name, str(n))) >= bits)


def short(challenge, name, bits=BITS):
    """A nonce that falls short of `bits`."""
    return next(str(n) for n in itertools.count() if zero_bits(proof_digest(challenge, name, str(n))) < bits)


class Proof(unittest.TestCase):
    """The door's rules in transport/identity.py `arrive`, on a clock of the test's own."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = State(tmp.name, config=Config(repo_keys=str(Path(tmp.name) / 'repo')))
        write_repo_key(st)
        self.now = [10_000.0]
        self.id = identity.Identity(st, delve.Client(None), clock=lambda: self.now[0])

    def arrive(self, name, address='192.0.2.1', nonce=None, challenge=None, **limits):
        c = challenge or self.id.arrival_challenge(BITS)['challenge']
        return self.id.arrive(name, {'challenge': c, 'nonce': nonce or solve(c, name)}, address, BITS, **limits)

    def refused(self, code, *a, **k):
        with self.assertRaises(IdentityError) as caught:
            self.arrive(*a, **k)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_a_proved_name_is_a_guest_with_a_credential_that_authenticates(self):
        got = self.arrive('wren')
        self.assertEqual((got['status'], got['handle']), ('arrived', 'wren'))
        self.assertEqual(self.id.authenticate(got['credential'])['did'], got['principal'])
        [row] = [r for r in self.id.invitations() if r['name'] == 'wren']
        self.assertEqual((row['state'], row['note']), ('accepted', 'arrived'))  # the hand lists it, and revokes it, as any guest
        self.id.revoke_invitation('wren')
        with self.assertRaises(IdentityError):
            self.id.authenticate(got['credential'])

    def test_the_proof_is_judged_and_bound_to_its_name_and_its_ten_minutes(self):
        c = self.id.arrival_challenge(BITS)['challenge']
        self.refused('proof_short', 'wren', challenge=c, nonce=short(c, 'wren'))
        robin = solve(c, 'robin')
        if zero_bits(proof_digest(c, 'wren', robin)) < BITS:  # a nonce found for one name does not serve another
            self.refused('proof_short', 'wren', challenge=c, nonce=robin)
        forged = c.rsplit('.', 1)[0] + '.' + '0' * 32
        self.refused('proof_invalid', 'wren', challenge=forged, nonce=solve(forged, 'wren'))
        weaker = self.id.arrival_challenge(BITS - 4)['challenge']  # a challenge asking less than the town's bits now
        self.refused('proof_short', 'wren', challenge=weaker, nonce=short(weaker, 'wren'))
        self.refused('proof_invalid', 'wren', challenge=c, nonce='two words')
        self.refused('invalid_guest_name', 'Wren!', challenge=c, nonce='1')
        late = self.id.arrival_challenge(BITS)['challenge']
        self.now[0] += 601
        self.refused('proof_expired', 'wren', challenge=late)
        self.assertEqual(self.id.invitations(), [])  # no refusal wrote anything

    def test_a_proof_gives_one_key_and_a_taken_name_leaves_it_unspent(self):
        c = self.id.arrival_challenge(BITS)['challenge']
        self.arrive('wren', challenge=c)
        self.refused('proof_spent', 'wren', challenge=c)
        self.id.invite('kit', 'named')  # an invitation's name, and a claimed handle's, are taken too
        for name in ('wren', 'kit'):
            c = self.id.arrival_challenge(BITS)['challenge']
            self.refused('taken', name, challenge=c)
        self.arrive('robin', challenge=c)  # that last proof, for another name, still works once made for it

    def test_so_many_keys_an_hour_from_one_address_and_in_all(self):
        limits = {'per_address': 2, 'per_hour': 3}
        self.arrive('a1', '192.0.2.1', **limits)
        self.now[0] += 60
        self.arrive('a2', '192.0.2.1', **limits)
        e = self.refused('rate_limited', 'a3', '192.0.2.1', **limits)
        self.assertEqual(e.retry, 3600 - 60)  # the first key leaves the hour then
        self.arrive('b1', '198.51.100.7', **limits)
        e = self.refused('rate_limited', 'b2', '198.51.100.7', **limits)  # the whole town's three for the hour
        self.now[0] += 3600 - 60
        self.arrive('a3', '192.0.2.1', **limits)


class OpenDoor(FrontCase):
    """The front of an open town over a real serve: the API and the page, the limits by address, invitations beside."""
    OPENER = 'did:plc:' + 'w' * 24
    hosted_accounts = True
    config = {'arrival': 'open', 'arrive_bits': BITS, 'arrive_per_address': 2, 'arrive_per_hour': 3, 'trust_proxy': True}

    def ask(self, name, address='192.0.2.1', solved=True):
        s, got = self.call('GET', '/AGENTS.md/arrive')
        self.assertEqual((s, got['status'], got['bits']), (200, 'proof', BITS))
        c = got['challenge']
        nonce = solve(c, name) if solved else short(c, name)
        return self.request('POST', '/AGENTS.md/arrive', {'name': name, 'proof': {'challenge': c, 'nonce': nonce}},
                            headers={'X-Forwarded-For': address})

    def test_an_agent_asks_for_a_key_and_plays_as_the_name_it_chose(self):
        name = f'wren-{self.c}'
        s, headers, body = self.ask(name)
        got = json.loads(body)
        self.assertEqual((s, got['status'], got['handle']), (200, 'arrived', name), got)
        self.assertEqual(got['principal'], f'guest:gsb.fg-goose.online:{name}')
        self.assertIn('dt_credential=', dict(headers)['Set-Cookie'])
        s, me = self.call('GET', '/AGENTS.md/me', token=got['credential'])
        self.assertEqual((s, me['handle']), (200, name))
        s, r = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': {'tag': 'record', 'fields': []}, 'intent': 'first'}, got['credential'])
        self.assertEqual(r['status'], 'admitted', r)
        self.assertEqual(handles(self.host, PUBLIC, [got['principal']], {}).get(got['principal']), name)  # the host was told it arrived

    def test_a_refusal_says_which_and_the_limits_count_by_address(self):
        s, _, body = self.ask(f'a-{self.c}', solved=False)
        self.assertEqual((s, json.loads(body)['reason']), (400, 'proof_short'))
        self.assertEqual(self.ask(f'a-{self.c}')[0], 200)
        s, _, body = self.ask(f'a-{self.c}')
        self.assertEqual((s, json.loads(body)['reason']), (400, 'taken'))
        self.assertEqual(self.ask(f'b-{self.c}')[0], 200)
        s, headers, body = self.ask(f'c-{self.c}')  # the address's two for the hour
        self.assertEqual((s, json.loads(body)['class']), (429, 'rateLimited'))
        self.assertGreater(int(dict(headers)['Retry-After']), 3000)
        self.assertEqual(self.ask(f'c-{self.c}', '198.51.100.7')[0], 200)
        self.assertEqual(self.ask(f'd-{self.c}', '203.0.113.9')[0], 429)  # the town's three for the hour

    def test_a_person_asks_at_the_page_which_does_the_work(self):
        s, headers, page = self.request('GET', '/enter', headers={'Accept': 'text/html'})
        text = page.decode()
        self.assertEqual(s, 200)
        self.assertIn('No invitation? Ask for a key', text)
        self.assertIn('<script src="/static/arrive.js" defer></script>', text)
        self.assertIn('I have an invitation', text)  # invitations still come in at the same door
        self.assertIn("This town's door is open: ask it for a key", text)
        challenge = html.unescape(re.search(r'data-challenge="([^"]+)"', text)[1])
        bits = int(re.search(r'data-bits="(\d+)"', text)[1])
        csrf = re.search(r'name="csrf" value="([^"]+)"', text)[1]
        jar = '; '.join(v.split(';')[0] for k, v in headers if k == 'Set-Cookie')
        name = f'robin-{self.c}'
        form = {'name': name, 'challenge': challenge, 'nonce': solve(challenge, name, bits), 'csrf': csrf}
        s, headers, page = self.request('POST', '/enter', raw=urllib.parse.urlencode(form),
                                        headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar, 'Origin': self.front.origin})
        self.assertEqual(s, 200, page[:400])
        self.assertIn(f'Welcome, {name}'.encode(), page)
        key = next(v for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_credential=')).split(';')[0].split('=', 1)[1]
        self.assertIn(f'<pre class="key">{key}</pre>'.encode(), page)
        self.assertEqual(self.request('GET', '/static/arrive.js')[0], 200)
        s, _, page = self.request('GET', '/', headers={'Accept': 'text/html'})
        self.assertIn(b'Ask the door for a key', page)

    def test_invitations_still_come_in_and_the_guide_and_catalogue_say_the_door_is_open(self):
        code = self.front.identity.invite(None, 'postmark')['code']
        s, got = self.call('POST', '/AGENTS.md/accept', {'code': code, 'name': f'kit-{self.c}'})
        self.assertEqual((s, got['status']), (200, 'accepted'))
        s, _, guide = self.request('GET', '/AGENTS.md')
        self.assertIn(b"This town's door is open: ask it for a key.", guide)
        self.assertNotIn(b'{{arrive}}', guide)
        s, catalogue = self.call('GET', '/AGENTS.md/api')
        self.assertEqual({r['name'] for r in catalogue['routes']} >= {'arrive', 'arriveProof'}, True)
        self.assertEqual(catalogue['arrival'], {'bits': BITS, 'perAddressPerHour': 2, 'perHour': 3})


class InvitedDoor(FrontCase):
    """An invited town (the live one's `arrival`, the default) is as it was: no route, no form, no word of asking."""
    OPENER = 'did:plc:' + 'v' * 24
    hosted_accounts = True

    def test_the_door_gives_no_key_and_says_nothing_of_one(self):
        for method in ('GET', 'POST'):
            s, got = self.call(method, '/AGENTS.md/arrive', {'name': 'wren'} if method == 'POST' else None)
            self.assertEqual((s, got['class']), (404, 'unknownRoute'), got)
        s, got = self.call('OPTIONS', '/AGENTS.md/arrive')
        self.assertEqual(s, 404)
        s, _, page = self.request('GET', '/enter', headers={'Accept': 'text/html'})
        self.assertNotIn(b'Ask for a key', page)
        self.assertNotIn(b'arrive.js', page)
        s, _, page = self.request('GET', '/', headers={'Accept': 'text/html'})
        self.assertIn(b'Come in with your invitation', page)
        self.assertNotIn(b'Ask the door', page)
        s, catalogue = self.call('GET', '/AGENTS.md/api')
        self.assertFalse({'arrive', 'arriveProof'} & {r['name'] for r in catalogue['routes']})
        self.assertNotIn('arrival', catalogue)
        s, _, guide = self.request('GET', '/AGENTS.md')
        old = (Path(__file__).resolve().parent.parent / 'docs' / 'AGENTS-API.md').read_text().replace('{{arrive}}\n', '')
        self.assertEqual(guide.decode(), old.replace('{{origin}}', self.front.origin))
        # a form posted with a challenge but no code is an invitation's door as before: it asks for the code
        s, _, page = self.request('POST', '/enter', raw=urllib.parse.urlencode({'name': 'wren', 'challenge': 'x', 'nonce': '1'}),
                                  headers={'Accept': 'text/html', 'Content-Type': FORM})
        self.assertIn('Type the code', html.unescape(page.decode()))


if __name__ == '__main__':
    unittest.main()
