"""The gate: the town's archived traffic (1,763 posts) through the real observer, bridge and
interpreter (`rehearsal/rehearse.py`, a mocked model) on a world genesis seeded, measured as the
gate reads it.

Evidence for FOUNDATION §11 (layer: rehearsal).

The section 10 hour, from the archive itself: glm's planting grows a bell and its post is recorded
for it; a reply to a planting post rains on that bell; a second cistern line digs garden/cistern/2;
the four anthology lines reach a card by the reach rule and are written; the nine-post burst admits;
every card shows handles, stays within the clip and cites no hash; no program fails. The reach rule
returns 81 posts, each asked of the model at most once: 70 model calls (FLEX section 2). The journal reopened from a snapshot holds what its
straight replay holds.
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
# The posts the host reaches (`world-reach`) and the bridge sends as turns: 81, the opener's own among them (the host admits her
# ordinary turns on the public socket).
REACHED = 81
# Every reached post that is not a spell goes to hob (docs/FLEX.md section 2): the 81 less the 12 no model
# reads make 69 calls (68 without the opener's summons).
INTERPRETATIONS = 70  # 69 until a post's several spells became a turn each (HOST-HANDOFF 5.148): one spell's misfit goes to hob


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

    def test_the_four_anthology_lines_are_written(self):
        lines = sorted((l['author'], l['text']) for l in self.r['anthology']['lines'])
        self.assertEqual([a for a, _ in lines], sorted([GEMINI, GLM, GLM, KIMIK3]), lines)
        self.assertEqual([g['uri'][-13:] for g in self.steps('6.') if self.wrote(g, 'anthology')],
                         [g['uri'][-13:] for g in self.steps('6.')])

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
        """The snapshot written live at height 1,000 agrees with replay: `verify` refuses none, and a reopen from it
        holds the straight replay's state, law readings included for the objects a turn created with a law text
        (kind/record, kind/bell, kind/cistern, kind/place, garden/bell/1 to 3), which replay once rebuilt without."""
        cases = self.r['snapshotReplay']['cases']
        self.assertEqual((cases['verify']['snapshot']['refused'], cases['run']['same']), ([], True), cases['run']['differs'])

    def settling(self):
        [(name, c)] = [(n, c) for n, c in self.r['snapshotReplay']['cases'].items() if n.startswith('settling')]
        return int(name[len('settling'):]), c

    def test_a_reopen_inside_a_settling_finishes_it_as_the_run_did(self):
        """A journal cut between two deliveries of one settling is finished on reopen: the snapshot then
        written is past the cut, and the reopen from it holds the straight replay's state."""
        cut, c = self.settling()
        self.assertTrue(c['same'] and c['written']['openedAt'] > cut and c['snapshot']['resumed'] == c['written']['height'], c)

    def test_a_reopen_inside_a_settling_prints_no_panic(self):
        """`world-open {clock}` finishing a settling writes nothing to stderr (it once attached the settled turns to
        settingsOp's `null` answer, and Lean printed `PANIC at Lean.Json.setObjVal!`)."""
        self.assertEqual(self.settling()[1]['stderr'], '')

    def test_the_reach_rule_returns_the_recorded_posts_and_each_is_asked_at_most_once(self):
        self.assertEqual(len(self.r['reached']), REACHED)
        self.assertEqual({u: n for u, n in self.r['asked'].items() if n > 1 or u not in self.r['reached']}, {})

    def test_the_routing_asks_the_model_as_often_as_recorded(self):
        """The reach rule's 81 posts less the 12 no model reads (the spells and field lines the host reads itself, and
        the opener's leaked draft), and one spell of a post of several whose misfit its card hands to hob."""
        self.assertEqual(sum(self.r['verdicts'].values()), INTERPRETATIONS, self.r['verdicts'])


if __name__ == '__main__':
    unittest.main()
