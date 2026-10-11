"""The gate: the town's archived traffic (1,763 posts) through the real observer, bridge and
interpreter (`rehearsal/rehearse.py`, a mocked model) on a world genesis seeded, measured as the
gate reads it.

Evidence for FOUNDATION §11 (layer: rehearsal).

The section 10 hour, from the archive itself: glm's planting grows a bell and its post is recorded
for it; a reply to a planting post rains on that bell; a second cistern line digs garden/cistern/2;
gemini's anthology line, prose at the commonplace, reaches hob and is written; the three anthology lines posted
under the anthology card itself are silent (a card hears a verb or nothing) and wait for the host's reach op
(OVERHAUL section 5 step 5); the nine-post burst admits; every card shows handles, stays within the clip and cites no
hash; no program fails. The reach rule returns 81 posts; only prose at the commonplace, and the misfit of a spell,
reaches the model: 37 model calls, each spell of a post asked at most once (FLEX section 2). The journal reopened from
a snapshot holds what its straight replay holds.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import host

ROOT = Path(__file__).resolve().parent.parent
GLM, GEMINI, KIMIK3 = 'did:plc:nmjdxe6fex23zslnnbwgruj3', 'did:plc:ubtqb43nq7u6jlibkzlobkuu', 'did:plc:j2hnfjwlnm2mau24vnmpir6d'
# The posts `transport.bridge.route` sends as turns: 81, the opener's own among them (the host admits her
# ordinary turns on the public socket).
REACHED = 81
# Only prose at the commonplace, and a spell no object reads (a misfit), goes to hob (docs/FLEX.md section 2). Prose
# at any other card is admitted `silent`: no card, no offer, no hand-on (OVERHAUL step 4 item 2). The 81 reached posts
# make 35 posts asked, 37 calls: the three `delvetalk wake` spells of one post are three turns (HOST-HANDOFF 5.148),
# and with Wake deleted each is a misfit that goes to hob. It was 70 while a card handed its prose on.
INTERPRETATIONS = 37
WAKE_POST = '3mxhg3bqrds2f'


def rehearse(out):
    p = subprocess.run([sys.executable, '-W', 'ignore', str(ROOT / 'rehearsal' / 'rehearse.py'), '--binary', host.binary(), '--out', out],
                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.returncode == 0, p.stdout[-3000:]
    return json.loads(Path(out, 'results.json').read_text())


class Archive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.r = rehearse(os.path.join(cls.tmp.name, 'out'))

    def steps(self, prefix):
        return [g for g in self.r['gate'] if g['step'].startswith(prefix)]

    def wrote(self, step, obj):
        return any(obj in e['writes'] for e in step['entries'] if e['tag'] == 'admitted')

    def test_no_program_fails_and_every_post_is_observed(self):
        self.assertEqual(self.r['errors'], [])
        self.assertEqual(self.r['observed']['count'], self.r['posts'])
        self.assertEqual(self.r['interpretationsLeft'].get('pending') or [], [])

    def test_glms_planting_grows_a_bell_and_its_post_is_recorded_for_it(self):
        grown = [p for p in self.r['plantings'] if p['uri'] and p['uri'].startswith('at://' + GLM) and p['status'] == 'posted']
        self.assertEqual(len(grown), 1, self.r['plantings'])
        self.assertIn(grown[0]['object'], self.r['made']['kind/bell'])

    def test_a_rain_reply_to_a_planting_post_is_written_to_that_bell(self):
        bell = next(p['object'] for p in self.r['plantings'] if p['uri'] and p['uri'].startswith('at://' + GEMINI))
        [rain] = self.steps('4.')
        self.assertTrue(self.wrote(rain, bell), rain)

    def test_a_second_cistern_line_digs_a_second_cistern_named_by_its_receipt(self):
        first, second = [g for g in self.r['grammar'] if 'cistern: line' in g['what']]
        self.assertEqual((first['status'], second['status']), ('admitted', 'admitted'), (first, second))
        named = lambda g: next(f['value']['value'] for f in g['result']['payload']['fields'] if f['name'] == 'object')
        self.assertEqual((named(first), named(second)), ('garden/cistern/1', 'garden/cistern/2'))
        self.assertIn('garden/cistern/2', second['offers'][0])

    def test_gemini_line_is_written_and_the_three_posted_under_the_anthology_card_wait_for_the_reach_op(self):
        """Gemini's post reaches the commonplace as prose; hob reads its spell and the anthology writes the line. The
        other three (glm twice, kimik3) are replies under the anthology card: prose at a card other than the commonplace
        is admitted `silent` (no write, no offer, and no hand-on to the commonplace, as the old card gave it), so
        their lines are lost until the host's reach op routes words under a card to hob with that card's table
        (OVERHAUL section 5 step 5). When that lands this test is to expect all four again."""
        self.assertEqual([(l['author'], l['text']) for l in self.r['anthology']['lines']],
                         [(GEMINI, 'A ring is a proposal; sound is a commit')], self.r['anthology'])
        written = {g['uri'][-13:]: self.wrote(g, 'anthology') for g in self.steps('6.')}
        self.assertEqual(written, {'3mxghd6kvo22f': True, '3mxghgacmlc2f': False, '3mxghjyx4pk2f': False, '3mxghjmm6zc2f': False})
        for g in self.steps('6.')[1:]:
            self.assertEqual([(e['tag'], e['to'], e['writes'], e['offers']) for e in g['entries']], [('admitted', 'anthology', [], [])], g)

    def test_the_nine_post_burst_suspends_settles_and_plants(self):
        b = self.r['burst']
        self.assertEqual([f['status'] for f in b['first']], ['suspended'] * 9, b)
        self.assertEqual([(f['outcome'], 'kind/bell' in f['wrote']) for f in b['final']], [('admitted', True)] * 9, b)

    def test_every_card_and_reply_shows_handles_within_the_clip_and_no_hash(self):
        texts = [c['text'] or '' for c in self.r['cards'].values()] + [d['text'] for d in self.r['drafts'] if d['outcome'] != 'publication']
        for t in texts:
            self.assertLessEqual(len(t), 1400, t[:200])
            self.assertNotIn('did:plc:', t)
            self.assertNotIn('bafy', t)

    def test_every_page_publication_is_within_the_clip(self):
        """Every published page fits the clip. The workshop's was the host's default page, its card (755
        characters) and every form's usage (663): 1,444; Workshop.obend's `publishPage` publishes the card alone
        (rehearsal/REPORT.md, run 12 section)."""
        over = [(d['text'].split('\n')[0], d['chars']) for d in self.r['drafts'] if d['outcome'] == 'publication' and d['chars'] > 1400]
        self.assertEqual(over, [])

    def test_a_reopen_from_a_snapshot_written_on_replay_holds_what_the_straight_replay_holds(self):
        """Four cuts of the journal: each prefix opened, snapshotted, the whole journal put back; the reopen
        resumes from that snapshot and holds the straight replay's height, head, clock, posts, pending work,
        and every object's state CID at every version, pin, law and readings."""
        cuts = {n: c for n, c in self.r['snapshotReplay']['cases'].items() if n.startswith('cut')}
        self.assertEqual(len(cuts), 4)
        for name, c in cuts.items():
            self.assertEqual((c['snapshot']['resumed'], c['snapshot']['refused'], c['same']), (c['written']['height'], [], True), (name, c))

    def test_the_runs_own_snapshot_agrees_with_replay(self):
        """The snapshot the running host wrote agrees with replay: `verify` refuses none, and a reopen from it
        holds the straight replay's state, law readings included for the objects a turn created with a law text
        (kind/record, kind/bell, kind/cistern, kind/place, garden/bell/1 to 3), which replay once rebuilt without. The journal now ends at 835 entries, short of the host's cadence of 1,000, so
        rehearse.py asks the live host for the snapshot (`world-snapshot`) before it stops: the reopen resumes at
        the journal's end, which proves the snapshot's content, not a replayed tail (the cuts prove the tail)."""
        cases = self.r['snapshotReplay']['cases']
        self.assertEqual((cases['verify']['snapshot']['refused'], cases['run']['same']), ([], True), cases['run']['differs'])

    def settling(self):
        [(name, c)] = [(n, c) for n, c in self.r['snapshotReplay']['cases'].items() if n.startswith('settling')]
        return int(name[len('settling'):]), c

    def test_a_reopen_inside_a_settling_finishes_it_as_the_run_did(self):
        """A journal cut between two deliveries of one settling (the tide's tick and the send it makes next: a delivery
        whose origin is the one before it) is finished on reopen: the snapshot then written is past the cut, and the
        reopen from it holds the straight replay's state. The cases that cut inside a card's hand-on no longer arise."""
        cut, c = self.settling()
        self.assertTrue(c['same'] and c['written']['openedAt'] > cut and c['snapshot']['resumed'] == c['written']['height'], c)

    def test_a_reopen_inside_a_settling_prints_no_panic(self):
        """`world-open {clock}` finishing a settling writes nothing to stderr (it once attached the settled turns to
        settingsOp's `null` answer, and Lean printed `PANIC at Lean.Json.setObjVal!`)."""
        self.assertEqual(self.settling()[1]['stderr'], '')

    def test_the_reach_rule_returns_the_recorded_posts_and_each_spell_is_asked_at_most_once(self):
        """Each distinct utterance is asked once. One post is asked three times, because it holds three
        `delvetalk wake` spells, a turn each (`#n`), and Wake is deleted: each is a misfit that goes to hob. That is
        three turns of one post, not one turn asked again."""
        self.assertEqual(len(self.r['reached']), REACHED)
        self.assertEqual([u for u in self.r['asked'] if u not in self.r['reached']], [])
        again = {u[-13:]: n for u, n in self.r['asked'].items() if n > 1}
        self.assertEqual(again, {WAKE_POST: 3})
        spells = [a['utterance'] for a in self.r['answered'].values() if a['uri'].endswith(WAKE_POST)]
        self.assertEqual(len(set(spells)), 3, spells)
        self.assertTrue(all(t.startswith('delvetalk wake ') for t in spells), spells)
        pairs = [(a['uri'], a['utterance']) for a in self.r['answered'].values()]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_the_routing_asks_the_model_as_often_as_recorded(self):
        """Of the reach rule's 81 posts only prose at the commonplace reaches hob, and the misfit of a spell; prose at
        another card is silent. 37 asks over 35 posts: 35 `unclear: not addressed`, one proposal (gemini's anthology
        line) and one `unclear` about a colour; the wake post is three of them."""
        self.assertEqual(sum(self.r['verdicts'].values()), INTERPRETATIONS, self.r['verdicts'])
        self.assertEqual(self.r['verdicts'].get('unclear: not addressed'), 35, self.r['verdicts'])
        self.assertEqual(self.r['verdicts'].get('proposal'), 1, self.r['verdicts'])


if __name__ == '__main__':
    unittest.main()
