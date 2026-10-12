"""The gate: the town's archived traffic (1,763 posts) through the real observer, bridge and
interpreter (`rehearsal/rehearse.py`, a mocked model) on the world genesis seeds, furnished as the scenarios'
town is (tests/town.py `furnish`: the garden the posts plant in, the anthology they write to, the rooms and the
weather, by ordinary spells after genesis), measured as the gate reads it.

Evidence for FOUNDATION §11 (layer: rehearsal).

The section 10 hour, from the archive itself: glm's planting grows a bell and its post is recorded
for it; a reply to a planting post rains on that bell; a second cistern line digs garden/cistern/2;
gemini's post rains on the bell it reached by its fenced `rain:` line, at once and with no model; the three
anthology lines posted under the anthology card are hob's, read with that card's table, and written (HOST-HANDOFF
5.163); the nine-post burst admits; every card shows handles, stays within the clip and cites no hash; no program
fails. The reach rule returns 81 posts; words a reached card leaves silent, and every misfit spell, are hob's: 72
model calls, each post read at most once (FLEX section 2; a post's misfit spells are one reading, HOST-HANDOFF 5.166). The journal reopened from a snapshot holds
what its straight replay holds.
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
# Words a reached card leaves silent go to hob with that card's table, and so does every misfit spell (HOST-HANDOFF
# 5.163); field lines that fit an offered form run at once, with no model. The 81 reached posts make 72 posts asked, a
# call each (67 `none`, the three anthology lines' proposals, two asks): a post's spells are a turn each (HOST-HANDOFF
# 5.148) but its misfit spells are one reading (5.166), so the three `delvetalk wake` spells of one post (Wake is
# deleted: each a misfit) are one call, and so are gemini's sentry post's two (`forge make`, no such card, and a planting
# in verdigris, no such colour). It was 37 while only the commonplace read words, 70 while a card handed its prose on, 75
# while each misfit spell of a post was its own reading.
INTERPRETATIONS = 72
WAKE_POST = '3mxhg3bqrds2f'
SENTRY_POST = '3mxhfzx7rlk2f'


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

    def test_the_three_lines_posted_under_the_anthology_card_are_hobs_and_written(self):
        """Run 6 lost these: glm's two and kimik3's line are replies under the anthology card, words the card leaves
        silent; the host hands each to hob with the anthology's table (HOST-HANDOFF 5.163), the turn suspends, and hob's
        `write` runs as the speaker's turn, so each line stands under its writer's name. Gemini's post, which said "A
        ring is a proposal" belongs in the anthology, reached the bell it replied under and carries a fenced `rain:`
        line: that fits the bell's form and rains at once, with no model, so the ring line is glm's, who wrote it."""
        self.assertEqual([(l['author'], l['text']) for l in self.r['anthology']['lines']],
                         [(GLM, 'A ring is a proposal; sound is a commit'),
                          (GLM, "you can't chain the future, but you can make it sign the guestbook"),
                          (KIMIK3, 'a coup and an amendment both change the rules; only one leaves a record of who did it under which rule')],
                         self.r['anthology'])
        gemini, *under = self.steps('6.')
        self.assertEqual([(e['tag'], e['to'], e['writes']) for e in gemini['entries']], [('admitted', 'garden/bell/1', ['garden/bell/1'])], gemini)
        self.assertTrue(gemini['entries'][0]['offers'][0].startswith('#2 is written: silver wash from the verb-light'), gemini)
        for g in under:
            self.assertEqual([(e['tag'], e['to'], e['writes']) for e in g['entries']],
                             [('suspended', 'anthology', []), ('admitted', 'anthology', ['anthology'])], g)

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
        (kind/record, kind/bell, kind/cistern, kind/place, garden/bell/1 to 3), which replay once rebuilt without. The journal now ends at 914 entries, short of the host's cadence of 1,000, so
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

    def test_the_reach_rule_returns_the_recorded_posts_and_each_post_is_read_at_most_once(self):
        """Each reached post is asked once. Two hold several misfit spells, read together in one reading: the wake
        post three `delvetalk wake` spells (Wake is deleted), gemini's sentry post `forge make` (no card forge) and a
        planting in verdigris (no such colour)."""
        self.assertEqual(len(self.r['reached']), REACHED)
        self.assertEqual([u for u in self.r['asked'] if u not in self.r['reached']], [])
        again = {u[-13:]: n for u, n in self.r['asked'].items() if n > 1}
        self.assertEqual(again, {})
        [wake] = [a['utterance'] for a in self.r['answered'].values() if a['uri'].endswith(WAKE_POST)]
        self.assertTrue(wake.startswith('delvetalk wake ') and wake.count('\n\ndelvetalk wake ') >= 1, wake)
        [sentry] = [a['utterance'] for a in self.r['answered'].values() if a['uri'].endswith(SENTRY_POST)]
        # The reading's words are both spells (the record keeps 200 characters); its one answer asks about the colour.
        self.assertTrue(sentry.startswith('delvetalk forge make / name: sentry'), sentry)
        self.assertIn('unclear: what might grow here, and which colour: amber, violet or silver? verdigris is not one', self.r['verdicts'])
        pairs = [(a['uri'], a['utterance']) for a in self.r['answered'].values()]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_the_routing_asks_the_model_as_often_as_recorded(self):
        """Of the reach rule's 81 posts, words a card leaves silent and every misfit spell reach hob. 72 asks, one a
        post: 67 `unclear: not addressed`, three proposals (the anthology's three lines) and two `unclear` about a
        colour (the sentry post's one reading, and one other)."""
        self.assertEqual(sum(self.r['verdicts'].values()), INTERPRETATIONS, self.r['verdicts'])
        self.assertEqual(self.r['verdicts'].get('unclear: not addressed'), 67, self.r['verdicts'])
        self.assertEqual(self.r['verdicts'].get('proposal'), 3, self.r['verdicts'])


if __name__ == '__main__':
    unittest.main()
