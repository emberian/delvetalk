"""The hand's root console and moderation verbs (docs/ROOT.md 1.6 and 2.3, HOST-HANDOFF 5.126): each verb, from the CLI
and from /hand/root/, is one request on the root socket under the opener, and none is sent without its reason or
reading; against a real `serve`, the acts land in the journal, public and marked.

Evidence for ROOT 1.6, 2.3 (layer: transport). Refuted by a verb that sends another shape, a write sent without its
reason or reading, a root page on the public port, or an act the journal does not show.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from deploy.genesis import OPENER
from tests.host import HostdCase
from tests.test_hand import TOKEN, HandCase, StubHost
from tests.test_turn_world import counter_modules, label, nat, record
from transport import hand

EMPTY = {'tag': 'record', 'fields': []}


class Shapes(unittest.TestCase):
    """The request each verb sends, against a stub host."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state, self.host = Path(self.tmp.name), StubHost()

    def run_hand(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            code = hand.main([*argv, '--state', str(self.state)], out, host=self.host)
        return code, self.host.ops[-1] if self.host.ops else None

    def root(self, verb, *flags):
        return self.run_hand('root', verb, *flags)[1]

    def test_each_root_act_is_one_world_root_with_its_reason(self):
        lib = self.state / 'lib'
        lib.mkdir()
        (lib / 'Tiny.obend').write_text('edition ObjectiveBend 1\n')
        (self.state / 'card.txt').write_text('a card the hand wrote')
        cases = [
            (('set', '--object', 'garden', '--field', 'state', '--value', json.dumps(EMPTY)), {'kind': 'set', 'object': 'garden', 'field': 'state', 'value': EMPTY}),
            (('delete', '--object', 'garden/bell/1'), {'kind': 'delete', 'object': 'garden/bell/1'}),
            (('as', '--principal', 'did:plc:x', '--object', 'c', '--method', 'bump', '--argument', json.dumps(EMPTY), '--intent', 'i1'),
             {'kind': 'as', 'principal': 'did:plc:x', 'turn': {'object': 'c', 'method': 'bump', 'argument': EMPTY, 'identity': 'i1'}}),
            (('settings', '--clock', '5', '--modelQuota', '10'), {'kind': 'settings', 'clock': 5, 'modelQuota': 10}),
            (('library', '--dir', str(lib)), {'kind': 'library', 'modules': [{'name': 'Tiny', 'source': 'edition ObjectiveBend 1\n'}]}),
            (('ignore', '--height', '7'), {'kind': 'ignore', 'height': 7}), (('unignore', '--height', '7'), {'kind': 'unignore', 'height': 7}),
            (('card', '--object', 'garden', '--text-file', str(self.state / 'card.txt')), {'kind': 'card', 'object': 'garden', 'text': 'a card the hand wrote'}),
            (('card', '--object', 'garden'), {'kind': 'card', 'object': 'garden', 'text': None}),
            (('quiet', '--principal', 'did:plc:x', '--hours', '0'), {'kind': 'quiet', 'principal': 'did:plc:x', 'hours': 0}),
            (('hide', '--object', 'garden'), {'kind': 'hide', 'object': 'garden'}), (('revoke', '--grant', 'g1'), {'kind': 'revoke', 'grant': 'g1'})]
        for flags, act in cases:
            self.assertEqual(self.root(*flags, '--reason', 'because'), {'op': 'world-root', 'principal': OPENER, 'reason': 'because', 'act': act}, flags)
        logged = [json.loads(l) for l in (self.state / 'hand-log.jsonl').read_text().splitlines()]
        self.assertEqual([l['what'] for l in logged][:2], ['root:set', 'root:delete'])
        self.assertEqual({l['reason'] for l in logged}, {'because'})

    def test_no_act_without_a_reason_and_no_power_without_a_reading(self):
        with self.assertRaises(SystemExit):
            self.root('delete', '--object', 'garden')
        with self.assertRaises(SystemExit):
            self.run_hand('quiet', '--who', 'x', '--hours', '1')
        self.assertEqual(self.root('delete', '--object', 'garden', '--reason', '  '), None)  # blank is no reason: nothing sent
        self.assertEqual(self.host.ops, [])

    def test_each_power_is_a_turn_on_world_or_the_card_with_its_reading(self):
        def turn(*argv):
            code, req = self.run_hand(*argv)
            self.assertEqual((code, req['op'], req['principal']), (0, 'world-turn', OPENER), argv)
            self.assertTrue(req['identity'].startswith('hand:' + argv[0]), req)
            return req['object'], req['method'], req['argument']
        self.assertEqual(turn('quiet', '--who', 'mallory', '--hours', '24', '--reading', 'flood'),
                         ('world', 'quiet', record(who=label('mallory'), hours=nat(24), reading=label('flood'))))
        self.assertEqual(turn('unquiet', '--who', 'mallory', '--reading', 'calm'), ('world', 'unquiet', record(who=label('mallory'), reading=label('calm'))))
        for power in ('retire', 'unretire', 'hide', 'show'):
            self.assertEqual(turn(power, '--object', 'counter', '--reading', 'r'), ('counter', power, record(reading=label('r'))))
        self.assertEqual(turn('revoke', '--grant', 'g1', '--reading', 'not mine'), ('world', 'revoke', record(grant=label('g1'), reading=label('not mine'))))
        self.assertEqual(turn('expire', '--scratch', 'junk', '--reading', 'r'), ('world', 'expire', record(scratch=label('junk'), reading=label('r'))))
        code, req = self.run_hand('settings', '--modelQuota', '500', '--interpretQuota', '24', '--reading', 'a quiet week')
        self.assertEqual(req, {'op': 'world-settings', 'principal': OPENER, 'reading': 'a quiet week', 'modelQuota': 500, 'interpretQuota': 24})

    def test_the_reads_ask_as_the_opener(self):
        self.root('dump', 'garden')
        self.assertEqual([(o['op'], o['principal'], o['object']) for o in self.host.ops],
                         [('world-view', OPENER, 'garden'), ('world-object', OPENER, 'garden'), ('world-inspect', OPENER, 'garden'), ('world-dump', OPENER, 'garden')])
        self.run_hand('modlog', '--object', 'garden')
        self.assertEqual(self.host.ops[-1], {'op': 'world-history', 'principal': OPENER, 'object': 'garden'})
        self.run_hand('find', 'gard')
        self.assertEqual(self.host.ops[-1], {'op': 'world-objects', 'principal': OPENER, 'prefix': 'gard'})


class Page(HandCase):
    """/hand/root/ behind the hand's token, on the hand's listener only (test_hand.Listener: the public front has no /hand/)."""

    def test_the_root_page_has_its_rule_its_forms_and_each_form_needs_its_reason(self):
        s, page, _ = self.get('/hand/root/')
        self.assertEqual(s, 200)
        self.assertIn('<hr class="root">', page)
        for verb in ('set', 'delete', 'as', 'ignore', 'card', 'library', 'settings', 'quiet', 'retire', 'hide', 'revoke', 'expire'):
            self.assertIn(f'/{verb}"', page, verb)
        self.assertEqual(page.count('required placeholder="reason (required)"') + page.count('required placeholder="reading (required)"'),
                         page.count('<form method="post"'))
        self.assertEqual(self.req('GET', '/hand/root/')[0], 404)  # no token, no page
        before = len(self.host.ops)
        s, _, h = self.req('POST', '/hand/root/delete', {'object': 'garden'}, cookie=f'dt_hand={TOKEN}')
        self.assertEqual((s, [o for o in self.host.ops[before:] if o['op'] == 'world-root']), (303, []))
        self.assertIn('needs+a+reason', h['Location'])
        self.req('POST', '/hand/root/delete', {'object': 'garden', 'reason': 'squatted'}, cookie=f'dt_hand={TOKEN}')
        self.assertEqual(self.host.ops[-1], {'op': 'world-root', 'principal': OPENER, 'reason': 'squatted', 'act': {'kind': 'delete', 'object': 'garden'}})
        self.req('POST', '/hand/mod/hide', {'object': 'garden', 'reading': 'abusive'}, cookie=f'dt_hand={TOKEN}')
        self.assertEqual((self.host.ops[-1]['object'], self.host.ops[-1]['method']), ('garden', 'hide'))


class Live(HostdCase):
    """The console against a real `serve` (edition 3): the acts are in the journal, marked and public."""
    OPENER = OPENER

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        made = cls.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-tally', 'object': 'tally',
                              'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        assert made['status'] == 'created', made

    def setUp(self):
        self.hand = hand.Hand(self.tmp.name, self.root, who='cli')

    def bump(self, who, intent):
        return self.host.send({'op': 'world-turn', 'principal': who, 'object': 'tally', 'method': 'bump', 'argument': record(), 'identity': intent})

    def test_a_root_set_is_a_marked_public_entry_in_the_objects_history(self):
        got = self.hand.act('root', 'set', {'object': 'tally', 'field': 'state', 'value': json.dumps(record(count=nat(9))), 'reason': 'a test count'})
        self.assertEqual(got['status'], 'root', got)
        seen = self.host.send({'op': 'world-history', 'principal': 'mallory', 'object': 'tally'})['entries'][-1]
        self.assertEqual((seen['root'], seen['reason'], seen['outcome']['kind'], seen['outcome']['after']), (True, 'a test count', 'set', record(count=nat(9))))
        self.assertEqual(hand.root.dump(self.root, OPENER, 'tally')['view']['state'], record(count=nat(9)))

    def test_quiet_refuses_the_quieted_and_the_log_shows_it(self):
        q = self.hand.act('mod', 'quiet', {'who': 'mallory', 'hours': '2', 'reading': 'flooding the tally'})
        self.assertEqual(q['status'], 'moderated', q)
        refused = self.bump('mallory', 'm1')
        self.assertEqual((refused['status'], refused['receipt']['outcome']['class']), ('refused', 'quiet'), refused)
        self.assertIn('flooding the tally', json.dumps(hand.root.modlog(self.root, OPENER)))
        cleared = self.hand.act('root', 'quiet', {'principal': 'mallory', 'hours': '0', 'reason': 'calm again'})  # root's quiet, 0 clears
        self.assertEqual(cleared['status'], 'root', cleared)
        self.assertEqual(self.bump('mallory', 'm2')['status'], 'admitted')

    @unittest.expectedFailure
    def test_unquiet_lifts_a_quiet(self):  # the host answers "no root act unquiet" for a quieted principal (host lane)
        self.hand.act('mod', 'quiet', {'who': 'trudy', 'hours': '2', 'reading': 'a test'})
        self.assertEqual(self.hand.act('mod', 'unquiet', {'who': 'trudy', 'reading': 'calm'})['status'], 'moderated')

    def test_ignore_shadows_and_unignore_restores_and_settings_set_the_quota(self):
        first = self.bump('ember', 'e-ignore')
        got = self.hand.act('root', 'ignore', {'height': str(first['receipt']['height']), 'reason': 'a test'})
        self.assertEqual(got['status'], 'root', got)
        self.assertIn(first['receipt']['height'], self.host.send({'op': 'world-status'}).get('ignored') or [])
        self.hand.act('root', 'unignore', {'height': str(first['receipt']['height']), 'reason': 'a test'})
        s = self.hand.act('mod', 'settings', {'modelQuota': '700', 'reading': 'a quiet week'})
        self.assertEqual(s['status'], 'settings', s)
        self.assertEqual(self.host.send({'op': 'world-status'})['modelQuota']['quota'], 700)

    @unittest.expectedFailure
    def test_expire_a_scratch(self):  # a request error until FEDERATION's scratch worlds are built (HOST-HANDOFF 5.126)
        self.assertEqual(self.hand.act('mod', 'expire', {'scratch': 'junk', 'reading': 'full of junk'})['status'], 'moderated')


if __name__ == '__main__':
    unittest.main()
