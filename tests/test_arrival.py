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
from tests.test_http import FrontCase, serve
from transport.http import Front
from transport import delve, identity
from transport.config import Config
from transport.host import PUBLIC, handles
from transport.identity import IdentityError, proof_digest, zero_bits
from transport.pages import told
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
        self.assertNotIn('did', got)  # hosted accounts off (the default): the guest principal alone, nothing hosted
        self.assertNotIn('did', self.id.accept(self.id.invite('kite')['code']))
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
        self.assertIn('id="arrive"', text)
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
        self.assertIn(b"getElementById('arrive')", self.request('GET', '/static/say.js')[2])
        s, _, page = self.request('GET', '/', headers={'Accept': 'text/html'})
        self.assertIn(b'Ask the door for a key', page)

    def page_form(self, path='/enter'):
        """A browser's first look at a page: its cookies, its form's token, an arrival challenge when it has one."""
        s, headers, page = self.request('GET', path, headers={'Accept': 'text/html'})
        text = page.decode()
        jar = '; '.join(v.split(';')[0] for k, v in headers if k == 'Set-Cookie')
        challenge = re.search(r'data-challenge="([^"]+)"', text)
        return jar, re.search(r'name="csrf" value="([^"]+)"', text)[1], challenge and html.unescape(challenge[1])

    def post_form(self, form, jar, path='/enter'):
        s, headers, page = self.request('POST', path, raw=urllib.parse.urlencode(form),
                                        headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar, 'Origin': self.front.origin})
        return s, headers, html.unescape(page.decode())

    def test_a_name_the_door_cannot_take_comes_back_as_the_nearest_it_would_and_pressing_again_takes_it(self):
        """obend 10-14 12:55: a visitor's five names were refused 400 (a capital, a space) and they left. The refusal puts
        the nearest name the door takes in the box and says so; the page's work done again over it, the guest is in."""
        jar, csrf, challenge = self.page_form()
        typed = f'Wren Of {self.c.upper()}'
        s, _, page = self.post_form({'name': typed, 'challenge': challenge, 'nonce': '1', 'csrf': csrf}, jar)
        near = f'wren-of-{self.c}'
        self.assertEqual(s, 400)
        self.assertIn(f'“{typed}” cannot be one. “{near}” is in the box instead', page)
        self.assertIn(f'id="arrive-name" name="name" value="{near}"', page)
        challenge = re.search(r'data-challenge="([^"]+)"', page)[1]
        s, _, page = self.post_form({'name': near, 'challenge': challenge, 'nonce': solve(challenge, near), 'csrf': csrf}, jar)
        self.assertEqual(s, 200, page[:400])
        self.assertIn(f'Welcome, {near}', page)
        # Nothing left to suggest (no letter in it): the plain line. Braces and markup in what was typed are words, escaped.
        s, _, page = self.post_form({'name': '4242', 'challenge': challenge, 'nonce': '1', 'csrf': csrf}, jar)
        self.assertEqual(s, 400)
        self.assertIn('A name starts with a lowercase letter', page)
        s, _, raw = self.request('POST', '/enter', raw=urllib.parse.urlencode({'name': '{minutes}<b>', 'challenge': challenge, 'nonce': '1', 'csrf': csrf}),
                                 headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar, 'Origin': self.front.origin})
        self.assertEqual(s, 400)
        self.assertIn('“{minutes}&lt;b&gt;” cannot be one. “minutes-b” is in the box', raw.decode().replace('&#x27;', "'"))
        # An agent is told the nearest name beside the reason; the longest typed name suggests at most 32 characters.
        s, _, body = self.request('POST', '/AGENTS.md/arrive', {'name': 'Q' * 300, 'proof': {'challenge': challenge, 'nonce': '1'}})
        got = json.loads(body)
        self.assertEqual((s, got['reason'], got['suggested']), (400, 'invalid_guest_name', 'q' * 32))

    def test_a_name_with_no_code_on_an_open_town_is_pointed_at_asking_and_a_key_or_code_in_the_wrong_box_is_read_as_itself(self):
        jar, csrf, _ = self.page_form()
        s, _, page = self.post_form({'code': '', 'name': 'robin', 'csrf': csrf}, jar)
        self.assertEqual(s, 400)
        self.assertIn('No invitation? Then ask for a key above: your name is in its box', page)
        self.assertIn('id="arrive-name" name="name" value="robin"', page)
        code = self.front.identity.invite(None, 'postmark')['code']
        s, _, page = self.post_form({'credential': code, 'csrf': csrf}, jar)  # the code in the key's box: it lets you choose a name
        self.assertEqual(s, 400)
        self.assertIn('This invitation lets you choose your name', page)
        self.assertIn(f'value="{code}"', page)
        name = f'kite-{self.c}'
        key = self.front.identity.accept(self.front.identity.invite(name, 'k')['code'])['credential']
        s, headers, _ = self.post_form({'code': key, 'name': '', 'csrf': csrf}, jar)  # a key in the code's box signs in
        self.assertEqual((s, dict(headers)['Location']), (303, '/play/'))
        s, _, page = self.post_form({'credential': 'dt_agent_' + 'x' * 43, 'csrf': csrf}, jar)
        self.assertEqual(s, 401)
        self.assertIn('Lost it? Ask for a new key above, under another name.', page)

    def test_a_form_drawn_before_a_restart_or_a_sign_in_still_comes_in(self):
        """obend 10-14: every restart (a config change, a carry) drew a new secret, so each open page's form was refused
        403 and each unanswered challenge 400; gabriel's first two plays were refused so. The door's key is kept: a page
        drawn by one front comes in through the next. A form from an earlier session of the browser comes back to send again."""
        jar, csrf, challenge = self.page_form()
        st = self.front.st
        again = serve(Front(st, self.host, identity.Identity(st, delve.Client(self.provider), clock=lambda: self.now[0]),
                            ('127.0.0.1', 0), clock=lambda: self.now[0]))
        self.addCleanup(again.server_close)
        self.addCleanup(again.shutdown)
        self.port = again.server_address[1]
        name = f'lark-{self.c}'
        s, _, page = self.request('POST', '/enter', raw=urllib.parse.urlencode({'name': name, 'challenge': challenge, 'nonce': solve(challenge, name), 'csrf': csrf}),
                                  headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar, 'Origin': again.origin})
        self.assertEqual(s, 200, page[:400])
        # The welcome rotated this browser's session: the old page's form now comes back as a page to send it again.
        s, _, page = self.request('POST', '/enter', raw=urllib.parse.urlencode({'code': 'dt_invite_x', 'name': 'my <name>', 'csrf': csrf}),
                                  headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar.replace('dt_browser=', 'dt_browser=x'), 'Origin': again.origin})
        text = page.decode()
        self.assertEqual(s, 403)
        self.assertIn('Send it again', text)
        self.assertIn('<input type="hidden" name="name" value="my &lt;name&gt;">', text)
        self.assertRegex(text, r'name="csrf" value="[0-9a-f]{64}"')
        s, _, page = self.request('POST', '/enter', raw=urllib.parse.urlencode({'credential': 'dt_agent_secret', 'csrf': csrf}),
                                  headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': 'dt_browser=other', 'Origin': again.origin})
        self.assertEqual(s, 403)
        self.assertNotIn(b'dt_agent_secret', page)  # a key is never written back
        self.assertIn(b'Your key is not kept here', page)
        # Another site's form is no earlier session: refused as before, nothing carried back.
        s, _, page = self.request('POST', '/enter', raw=urllib.parse.urlencode({'name': 'x', 'csrf': csrf}),
                                  headers={'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar, 'Origin': 'https://elsewhere.example'})
        self.assertEqual(s, 403)
        self.assertNotIn(b'Send it again', page)

    def test_a_get_of_the_doors_api_says_what_it_takes_and_where_a_person_comes_in(self):
        s, got = self.call('GET', '/AGENTS.md/accept')
        self.assertEqual((s, got['class']), (405, 'methodNotAllowed'))
        self.assertEqual(got['hint'], 'OPTIONS /AGENTS.md/accept says what it takes. A person comes in at /enter.')
        self.assertEqual(got['_links']['enter'], {'href': '/enter'})

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
        self.assertNotIn(b'id="arrive"', page)
        s, _, page = self.request('GET', '/', headers={'Accept': 'text/html'})
        self.assertIn(b'Come in with your invitation', page)
        self.assertNotIn(b'Ask the door', page)
        s, catalogue = self.call('GET', '/AGENTS.md/api')
        self.assertFalse({'arrive', 'arriveProof'} & {r['name'] for r in catalogue['routes']})
        self.assertNotIn('arrival', catalogue)
        s, _, guide = self.request('GET', '/AGENTS.md')
        old = told((Path(__file__).resolve().parent.parent / 'docs' / 'AGENTS-API.md').read_text(), 'delve', 'invited').replace('{{arrive}}\n', '')
        self.assertEqual(guide.decode(), old.replace('{{origin}}', self.front.origin))
        # a form posted with a challenge but no code is an invitation's door as before: it asks for the code
        s, _, page = self.request('POST', '/enter', raw=urllib.parse.urlencode({'name': 'wren', 'challenge': 'x', 'nonce': '1'}),
                                  headers={'Accept': 'text/html', 'Content-Type': FORM})
        self.assertIn('Type the code', html.unescape(page.decode()))


if __name__ == '__main__':
    unittest.main()
