"""Bend authoring as obend's residents met it on 2026-10-14 (tests/fixtures/authoring/obend-2026-10-14.json): every
workshop check, scratch check, REPL step and spell they sent, sent again as they sent it through the HTTP front of a
genesis town, each answer read as the resident reads it. `then` is what came back that night; TEACHES names, per step,
what the answer must now say: the line to write, so the next send is the fix. Refuted by a step in TEACHES whose answer
does not carry it.

DELVETALK_CORPUS_OUT=<file> also writes {id: answer} for every step (the before/after table).

    python3 -W error -m unittest tests.test_authoring_corpus -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.test_http import PEOPLE, Provider
from tests.town import Town
from transport import delve, identity
from transport.config import Config
from transport.host import HostClient
from transport.http import Front
from transport.state import State
from tests.host import serve

CORPUS = json.loads((Path(__file__).resolve().parent / 'fixtures' / 'authoring' / 'obend-2026-10-14.json').read_text())
WHO = {'yue': 'talkie.delve.town', 'kestrel-of-tulip': 'glm.delve.town', 'claude': 'mimo.delve.town'}

# What each step's answer must now carry (substrings, all of them): the line to write. By where the answer is made: the
# compiler's diagnostics, the workshop's and the library's Bend, the host's request surfaces.
OWN = ('For fields of its own, write a whole package instead', 'delvetalk library read / page: object')
COMPILER = {
    'yue-01': ('`0n`', "write 0, not Bend's 0n"),
    'claude-04': ('`true`', 'a law that always holds is no law: leave it out'),
    'yue-02': ('write {shade: set 3n}',),
    'yue-06': ('there is no sub', 'write {shade: set state.shade - 1n}'),
    'yue-07': ('let warm(…) names a case its call does not answer; write let written(_) = …',),
    **{'yue-%02d' % n: OWN + ('its own record State with shade',) for n in (10, 15, 16, 17, 18, 19, 20, 21, 22, 27)},
    **{'yue-%02d' % n: OWN + ('its own record State with warmth, ash',) for n in (32, 33, 34)},
    'yue-29': ('keep() is the write that changes nothing and takes no fields', 'let written(_) = write {field: set VALUE}'),
    'yue-40': ('it takes a record: set({value: …})',),
    'yue-44': ('it takes {delta: …}, not {value: …}: add({delta: …})',),
    'yue-45': ('it takes a record: add({delta: …})',),
    'yue-47': ('./Kind.obend is what this layer lays over', 'delvetalk workshop check / over: kind/<name>'),
    'yue-49': ("a module's name is what its import names between ./ and .obend, Layer1",),
    'yue-50': ('./Kind.obend is what this layer lays over',),
    'yue-52': ('Form declares ',),
    'yue-61': ('the type of what world.viewDerived answers is named at the call: world.viewDerived::<T>(…)',),
    'yue-63': ("the world's calls are written on world, lowercase: world.viewDerived::<T>(…)",),
    'kestrel-of-tulip-08': ("unexpected indentation: line 33 is indented where a declaration begins", "a def's body is one expression"),
}
RECEIVE = ('def receive(state: State, input: Card.Reply, context: Abi.Context) -> Activity<Card.Replied>:\n'
           '  Card.answer(input, context, forms(), render(state, context))')
WORKSHOP = {
    'yue-08': (RECEIVE, 'import ./Card.obend as Card'),
    'claude-02': (RECEIVE,),
    'claude-03': ('This block begins with edition: a whole package, with a State of its own. Check it without over:',),
}
HOST = {
    'yue-39': ('entry names a definition of source (a name, like repl), and this is an expression: send it as source', '1n + 2n'),
    'kestrel-of-tulip-01': ('this is a spell: a spell is cast with POST …/world/<object>/receive {intent, spell}',),
    'yue-57': ('created',),
    'yue-66': ('repl is an Activity: it runs as a method of the object repl, made from this source', 'def initial() -> State'),
    'claude-05': ('render of commonplace draws its card and is read, not cast',),
}
TEACHES = {**COMPILER, **WORKSHOP, **HOST}

# What an answer must no longer carry: noise past the line that says what to send.
SHEDS = {'kestrel-of-tulip-06': ('selected generic instances',)}

def said(status, reply):
    """An HTTP answer as a resident reads it: the line, the offers, a refusal's message, diagnostic and hint."""
    if not isinstance(reply, dict):
        return '%d %s' % (status, reply)
    parts = [str(status)] if status != 200 else []
    for k in ('line', 'message', 'hint'):
        if reply.get(k):
            parts.append(str(reply[k]))
    parts += [o if isinstance(o, str) else o.get('text', '') for o in reply.get('offers') or []]
    d = reply.get('diagnostic')
    if d:
        parts.append(d.get('message', '') + (' (hint: %s)' % d['hint'] if d.get('hint') and d.get('hint') != reply.get('hint') else ''))
    if reply.get('status') in ('checked', 'finished', 'created', 'admitted', 'defined') and not d:
        parts.append(reply['status'])
    return '\n'.join(p for p in parts if p).strip()


class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.now = [1000.0]
        cls.provider = Provider()
        st = State(os.path.join(cls.tmp.name, 'front'), config=Config(host_socket=cls.town.process.sock, repo_keys=os.path.join(cls.tmp.name, 'repo')))
        ident = identity.Identity(st, delve.Client(cls.provider), clock=lambda: cls.now[0])
        cls.front = serve(Front(st, HostClient(cls.town.process.sock), ident, ('127.0.0.1', 0), clock=lambda: cls.now[0]))
        cls.addClassCleanup(cls.front.server_close)
        cls.addClassCleanup(cls.front.shutdown)
        cls.port = cls.front.server_address[1]
        cls.tokens = {who: cls.login(handle) for who, handle in WHO.items()}
        for who in WHO:
            status, opened = cls.call('POST', '/AGENTS.md/scratch', {'name': 'lab'}, cls.tokens[who])
            assert opened.get('status') == 'scratch', opened
        cls.answers = {}
        for n, step in enumerate(CORPUS['steps']):
            cls.answers[step['id']] = cls.send(step, n)
        if os.environ.get('DELVETALK_CORPUS_OUT'):
            Path(os.environ['DELVETALK_CORPUS_OUT']).write_text(json.dumps(cls.answers, indent=1, ensure_ascii=False))

    @classmethod
    def call(cls, method, path, body, token):
        import http.client
        cls.now[0] += 10  # under the front's rate limit
        c = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=120)
        c.request(method, path, json.dumps(body), {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data.decode(errors='replace')

    @classmethod
    def login(cls, handle):
        did = PEOPLE[handle]
        s, ch = cls.call('POST', '/AGENTS.md/challenge', {'handle': handle}, '')
        cls.provider.texts[did] = ch['text']
        s, v = cls.call('POST', '/AGENTS.md/verify', {'handle': handle, 'uri': f'at://{did}/town.delve.feed.post/3abc'}, ch['credential'])
        assert v.get('status') == 'verified', v
        cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        return ch['credential']

    @classmethod
    def send(cls, step, n):
        tok, intent = cls.tokens[step['who']], 'corpus-%d' % n
        surface = step['surface']
        for k, before in enumerate(step.get('setup') or []):
            cls.call('POST', f'/AGENTS.md/world/{before["object"].replace("/", "%2F")}/receive', {'intent': '%s-setup-%d' % (intent, k), 'spell': before['spell']}, tok)
        if surface in ('workshop', 'spell'):
            obj = step.get('object') or step['spell'].split()[1]
            return said(*cls.call('POST', f'/AGENTS.md/world/{obj.replace("/", "%2F")}/receive', {'intent': intent, 'spell': step['spell']}, tok))
        if surface == 'method':
            return said(*cls.call('POST', f'/AGENTS.md/world/{step["object"]}/{step["method"]}', {'intent': intent, 'fields': {}}, tok))
        body = dict(step['body'])
        if surface == 'objects':
            body['intent'] = intent
        return said(*cls.call('POST', f'/AGENTS.md/scratch/lab/{"objects" if surface == "objects" else surface}', body, tok))

    def test_every_step_is_answered(self):
        for step in CORPUS['steps']:
            with self.subTest(step=step['id']):
                self.assertTrue(self.answers[step['id']], step)

    def check(self, who, source, over=''):
        spell = 'delvetalk workshop check\n' + ('over: %s\n' % over if over else '') + 'source: <<BEND\n' + source + 'BEND'
        return said(*self.call('POST', '/AGENTS.md/world/workshop/receive', {'intent': 'corpus-x-%d' % len(source), 'spell': spell}, self.tokens[who]))

    def test_the_receive_a_check_names_is_the_one_step(self):
        """claude's radio as sent at 03:20:15, with the two lines the answer names and the import it names: it compiles and a
        spell reaches it. Refuted by the named lines not compiling, or the check still saying no spell reaches it."""
        [step] = [s for s in CORPUS['steps'] if s['id'] == 'claude-02']
        source = step['spell'].split('source: <<BEND\n', 1)[1].rsplit('BEND', 1)[0]
        told = self.answers['claude-02']
        lines = told[told.index('def receive('):told.index('\nOr draft')]
        fixed = source.replace('import ./Text.obend as Text\n', 'import ./Text.obend as Text\nimport ./Card.obend as Card\n') + lines + '\n'
        answer = self.check('claude', fixed)
        self.assertIn('Checked: it compiles.', answer)
        self.assertNotIn('No spell reaches it', answer)

    def test_the_library_coin_jar_compiles_and_a_spell_reaches_it(self):
        """The object page's jar, which the night's three standalone packages were copied from: refuted by its check saying
        no spell reaches it (it had no receive) or by its not compiling."""
        from deploy import genesis
        page = genesis.page_body('object')
        answer = self.check('yue', ''.join(line + '\n' for line in page.splitlines()[1:] if not line.startswith('Next:')))
        self.assertIn('Checked: it compiles.', answer)
        self.assertNotIn('No spell reaches it', answer)
        self.assertLessEqual(len(page), genesis.PAGE_LIMIT)

    def test_each_refusal_names_what_to_write(self):
        for sid, wants in TEACHES.items():
            with self.subTest(step=sid):
                for want in wants:
                    self.assertIn(want, self.answers[sid])
        for sid, noise in SHEDS.items():
            with self.subTest(step=sid):
                for n in noise:
                    self.assertNotIn(n, self.answers[sid])


if __name__ == '__main__':
    unittest.main()
