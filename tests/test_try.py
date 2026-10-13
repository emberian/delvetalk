"""`try` is the commit with the write switched off (docs/POSTING.md §2): `world-try` runs a turn exactly as `world-turn`
does, settling pass and all, answers what it would write (the entry, its roots with their versions, each write's
state CID, the exact cards it would offer, what it would fire and open) and drops the world it leaves. Any act may
carry `if: [{object, version}]`, the roots a try read, and is refused `moved`, unjournaled, when one has moved since.
A post says the same: `delvetalk try` with spells indented under it, and a margin line `if: bell/1 v3` ahead of
the spells.

Evidence for docs/POSTING.md §2 (layer: host).

Refuted by: a try that journals anything or changes a version, a try whose writes' state CIDs differ from the real
act's at the same head, a try whose offer is not the card the act offers, an act with a moved root that runs, or
an indented spell under `try` that casts.
"""
import tempfile
import unittest

from tests.poster import Poster
from tests.host import bounds
from tests.town import Town
from tests.test_heard import HeardCase
from tests.wire import label, record

WHO = 'did:plc:tryer'


class Try(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.host = cls.town.client
        cls.n = 0
        assert cls.host.send({'op': 'world-arrive', 'principal': 'transport', 'did': WHO, 'handle': 'tryer.test'})['status'] == 'arrived'

    def turn(self, text, op='world-turn', post='at://x/p', **more):
        type(self).n += 1
        return self.host.send({'op': op, 'principal': WHO, 'object': 'bell/1', 'method': 'receive', 'identity': f'try-{self.n}',
                               'argument': record(text=label(text), post=label(post)), **more})

    def height(self):
        return self.host.send({'op': 'world-status'})['height']

    def version(self, oid):
        return self.host.send({'op': 'world-view', 'principal': WHO, 'object': oid})['version']

    def test_a_try_answers_the_act_and_writes_nothing_then_the_act_lands_as_shown(self):
        before, v = self.height(), self.version('bell/1')
        tried = self.turn('delvetalk bell/1 rain / text: a first rain', op='world-try', post='at://x/same')
        self.assertTrue(tried.get('tried'), tried)
        self.assertEqual(tried['status'], 'admitted', tried)
        self.assertEqual(tried['against']['height'], before)
        self.assertEqual((self.height(), self.version('bell/1')), (before, v))  # nothing journaled, nothing moved
        writes = tried['receipt']['outcome']['writes']
        self.assertTrue(any(w['object'] == 'bell/1' and w.get('cid') for w in writes), writes)
        roots = tried['receipt']['roots']
        self.assertIn({'object': 'bell/1', 'version': v}, [{'object': r['object'], 'version': r['version']} for r in roots])
        shown = [o['text'] for o in tried.get('offers') or []]
        done = self.turn('delvetalk bell/1 rain / text: a first rain', post='at://x/same',
                         **{'if': [{'object': r['object'], 'version': r['version']} for r in roots]})
        self.assertEqual(done['status'], 'admitted', done)
        self.assertNotIn('tried', done)
        after = self.height()
        self.assertGreater(after, before)
        landed = {w['object']: w.get('cid') for w in done['receipt']['outcome']['writes']}
        self.assertEqual({w['object']: w.get('cid') for w in writes}, landed)  # the bytes shown are the bytes that landed
        self.assertEqual(shown, [o['text'] for o in done.get('offers') or []])
        again = self.turn('delvetalk bell/1 rain / text: a second rain', **{'if': [{'object': 'bell/1', 'version': v}]})
        self.assertEqual((again['status'], again['class']), ('refused', 'moved'), again)
        self.assertEqual(again['moved'], [{'object': 'bell/1', 'was': v, 'now': v + 1}])
        self.assertEqual(again['line'], f'refused moved: bell/1 is at v{v + 1}, not v{v}')
        self.assertEqual(self.height(), after)  # a moved act journals nothing

    def test_a_refusal_is_tried_as_it_would_be_refused(self):
        before = self.height()
        tried = self.turn('delvetalk bell/1 rain / text: ' + 'x' * 5000, op='world-try')
        self.assertNotEqual(tried.get('status'), 'admitted', tried)
        self.assertEqual(self.height(), before)

    def test_a_post_of_spells_indented_under_world_try_is_tried_and_none_of_them_casts(self):
        before, v = self.height(), self.version('bell/1')
        text = 'delvetalk try\n  delvetalk bell/1 rain / text: tried in a post\n  delvetalk bell/1 rain / text: and again'
        tried = self.turn(text)
        self.assertTrue(tried.get('tried'), tried)
        self.assertEqual(tried['status'], 'spells', tried)
        self.assertEqual([t['status'] for t in tried['turns']], ['admitted', 'admitted'])
        self.assertEqual((self.height(), self.version('bell/1')), (before, v))
        self.assertEqual(self.host.send({'op': 'spell-parse', 'text': 'Delvetalk Try'})['spell']['card'], 'try')
        made = self.host.send({'op': 'world-create', 'principal': WHO, 'identity': 'mk-try', 'object': 'try', 'modules': [], 'entry': 'initial'})
        self.assertNotEqual(made.get('status'), 'created', made)  # no object takes the name

    def test_a_plan_under_try_answers_its_whole_outcome_and_makes_nothing(self):
        before = self.height()
        plan = ('delvetalk try\n  delvetalk plan\n  delvetalk kinds make / name: trylamp / of: record\n  delvetalk {made 1} make\n')
        tried = self.turn(plan)
        self.assertTrue(tried.get('tried'), tried)
        self.assertEqual(tried['status'], 'admitted', tried)
        self.assertEqual(self.height(), before)
        self.assertEqual(self.host.send({'op': 'world-view', 'principal': WHO, 'object': 'kind/trylamp'})['status'], 'unknown')

    def test_an_if_line_ahead_of_a_posts_spells_guards_them(self):
        v = self.version('bell/1')
        moved = self.turn(f'if: bell/1 v{v + 7}\ndelvetalk bell/1 rain / text: guarded')
        self.assertEqual(moved.get('class'), 'moved', moved)
        held = self.turn(f'if: bell/1 v{v}, kind/bell v{self.version("kind/bell")}\ndelvetalk bell/1 rain / text: guarded')
        self.assertEqual(held['status'], 'admitted', held)
        self.assertNotIn('if:', ''.join(o['text'] for o in held.get('offers') or []))
        v = self.version('bell/1')
        for bad in ('if: bell/1', 'if: bell/1 version 3', 'IF:'):
            refused = self.turn(f'{bad}\ndelvetalk bell/1 rain / text: guarded badly')
            self.assertEqual(refused.get('class'), 'moved', refused)  # a guard that does not read fails closed
            self.assertTrue(refused['line'].startswith('refused moved: the if: line does not read'), refused)
        self.assertEqual(self.version('bell/1'), v)



class BehaviorGuards(HeardCase):
    def request(self, text, op='world-turn', who='glm', roots=None):
        self.n = getattr(self, 'n', 0) + 1
        return self.host.send(op=op, principal=who, object='bell', method='receive', identity=f'guard-{self.n}',
                              argument=record(text=label(text), post=label('')), **({'if': roots} if roots is not None else {}))

    def preview(self, text='delvetalk bell rain / text: previewed rain'):
        tried = self.request(text, op='world-try')
        self.assertEqual(tried['status'], 'admitted', tried)
        self.assertTrue(tried['tried'], tried)
        return tried['receipt']['roots']

    def place(self, spell, who='kim'):
        placed = self.request('delvetalk bell ' + spell, who=who)
        self.assertEqual(placed['status'], 'admitted', placed)

    def moved(self, roots, text='delvetalk bell rain / text: previewed rain'):
        before = self.host.send(op='world-status')['height']
        ran = self.request(text, roots=roots)
        self.assertEqual((ran.get('status'), ran.get('class')), ('refused', 'moved'), ran)
        self.assertIn('behaviour changed', ran['line'])
        self.assertEqual(self.host.send(op='world-status')['height'], before)
        self.assertEqual((self.value('rains'), self.value('rains', 'square')), ('0', '0'))

    def test_a_guarded_rain_is_refused_after_another_resident_places_a_rule(self):
        roots = self.preview()
        version = self.host.send(op='world-view', principal='glm', object='bell')['version']
        self.place('rule / name: echo / when: request.method == "rain" / then: delvetalk square rain / text: echo')
        self.assertEqual(self.host.send(op='world-view', principal='glm', object='bell')['version'], version)
        self.moved(roots)

    def test_a_guarded_rain_is_refused_after_another_resident_grows_a_verb(self):
        roots = self.preview()
        self.place('grow / name: water / reading: poured on by a hand')
        self.moved(roots)

    def test_a_guarded_rain_is_refused_after_its_rule_is_removed(self):
        self.place('rule / name: echo / when: request.method == "rain" / then: delvetalk square rain / text: echo')
        roots = self.preview()
        self.place('unrule / name: echo')
        self.moved(roots)

    def test_a_guarded_grown_verb_is_refused_after_the_verb_is_removed(self):
        self.place('grow / name: water / reading: poured on by a hand')
        text = 'delvetalk bell water / text: previewed water'
        roots = self.preview(text)
        self.place('ungrow / name: water')
        self.moved(roots, text)
        self.assertEqual(self.value('acts'), '0')

    def test_a_guarded_rain_is_refused_after_its_law_is_amended(self):
        roots = self.preview()
        amended = self.host.send(op='world-amend', principal='ember', identity='amended-guard', object='bell', version=0,
                                 law='law open: request.kind == 0 or request.subject == "ember"')
        self.assertEqual(amended['status'], 'admitted', amended)
        self.moved(roots)

    def test_a_guarded_rain_is_refused_after_a_want_is_placed_or_removed(self):
        for spell in ('want / name: water / when: new.rains == 0 / asks: delvetalk bell rain / text: water',
                      'unwant / name: water'):
            roots = self.preview()
            self.place(spell)
            self.moved(roots)

    def test_an_untouched_object_accepts_its_preview_guards(self):
        text = 'delvetalk bell rain / text: unchanged'
        roots = self.preview(text)
        self.assertEqual(roots[0]['behaviour'], 0)
        ran = self.request(text, roots=roots)
        self.assertEqual(ran['status'], 'admitted', ran)
        self.assertEqual(self.value('rains'), '1')

    def test_an_unchanged_placing_accepts_its_preview_guards(self):
        self.place('grow / name: water / reading: poured on by a hand')
        text = 'delvetalk bell rain / text: unchanged'
        roots = self.preview(text)
        self.assertEqual(roots[0]['behaviour'], 1)
        ran = self.request(text, roots=roots)
        self.assertEqual(ran['status'], 'admitted', ran)

    def test_a_guard_with_behaviour_zero_is_refused_after_the_behaviour_changes(self):
        roots = [{'object': 'bell', 'version': 0, 'behaviour': 0}]
        self.place('grow / name: water / reading: poured on by a hand')
        self.moved(roots)

    def test_a_version_only_guard_still_passes_after_the_objects_behaviour_changes(self):
        roots = [{'object': 'bell', 'version': 0}]
        self.place('grow / name: water / reading: poured on by a hand')
        current = self.preview()
        self.assertEqual(current[0]['behaviour'], 1)
        self.assertEqual(current[0]['version'], 0)
        ran = self.request('delvetalk bell rain / text: version only', roots=roots)
        self.assertEqual(ran['status'], 'admitted', ran)
        self.assertEqual(self.value('rains'), '1')

    def test_an_unplaced_object_accepts_a_guard_without_a_behaviour_field(self):
        ran = self.request('delvetalk bell rain / text: old guard', roots=[{'object': 'bell', 'version': 0}])
        self.assertEqual(ran['status'], 'admitted', ran)

    def test_a_malformed_behaviour_guard_refuses_before_the_act_runs(self):
        for behaviour in (-1, None, True, {}, 'bad'):
            ran = self.request('delvetalk bell rain / text: malformed',
                               roots=[{'object': 'bell', 'version': 0, 'behaviour': behaviour}])
            self.assertEqual((ran.get('status'), ran.get('class')), ('refused', 'moved'), ran)
            self.assertIn('behaviour must be a natural number', ran['line'])
        self.assertEqual(self.value('rains'), '0')

    def test_a_guard_accepts_the_maximum_number_of_roots_and_refuses_one_more(self):
        maximum = bounds()['host']['maxRoots']
        roots = [{'object': 'bell', 'version': 0, 'behaviour': 0}] * maximum
        refused = self.request('delvetalk bell rain / text: too many roots', roots=roots + roots[:1])
        self.assertEqual((refused.get('status'), refused.get('class')), ('refused', 'moved'), refused)
        self.assertIn(f'if names at most {maximum} roots', refused['line'])
        self.assertEqual(self.value('rains'), '0')
        ran = self.request('delvetalk bell rain / text: maximum roots', roots=roots)
        self.assertEqual(ran['status'], 'admitted', ran)

    def test_previewing_a_direct_method_retains_behaviour_without_changing_ordinary_state_roots(self):
        tried = self.host.send(op='world-try', principal='glm', identity='direct-preview', object='bell', method='rain',
                               argument=record(text=label('direct')))
        self.assertEqual(tried['status'], 'admitted', tried)
        self.assertEqual(tried['receipt']['roots'][0]['behaviour'], 0)
        ran = self.turn('bell', 'rain', record(text=label('direct')), principal='glm')
        self.assertEqual(ran['status'], 'admitted', ran)
        self.assertNotIn('behaviour', ran['receipt']['roots'][0])


class ByPost(unittest.TestCase):
    """A resident who only posts previews an act, then sends it guarded by the preview's `if:` line."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.poster = Poster(cls.tmp.name, cls.town.client)

    def test_a_preview_reply_says_nothing_was_done_names_no_receipt_and_its_if_line_guards_the_act(self):
        version = lambda: self.town.client.send({'op': 'world-view', 'principal': 'anonymous', 'object': 'bell/1'})['version']  # noqa: E731
        v = version()
        [preview] = self.poster.say('delvetalk try\n  delvetalk bell/1 tend')
        text = preview['text']
        self.assertTrue(text.startswith('preview, nothing done'), text)
        self.assertIn('would be admitted bell/1 v', text)
        self.assertNotIn('receipt', text)
        self.assertNotIn('●', text)
        self.assertTrue(preview['preview'])
        self.assertEqual(version(), v)  # the preview wrote nothing
        guard = next(line for line in text.splitlines() if line.startswith('if: '))
        [done] = self.poster.say(guard + '\ndelvetalk bell/1 tend')
        self.assertIn('admitted bell/1', done['text'])
        [moved] = self.poster.say(guard + '\ndelvetalk bell/1 tend')
        self.assertTrue(moved['text'].startswith('refused moved: bell/1 is at v'), moved['text'])



class Settled(unittest.TestCase):
    """What a try would settle in the same write, as the live v12 town's settling pass met it (2026-10-12): the tide's
    carried tick delivered 64 times, each answered by the receipt its identity was bound to in v9 (no roots, no
    writes). The preview names the card and says that receipt once; it crashed on `KeyError: 'object'` before."""

    def test_a_delivery_with_no_roots_is_named_by_its_card_and_one_receipt_is_said_once(self):
        from transport import bridge
        bound = {'hash': 'bafyreid5g2', 'height': 3, 'outcome': {'tag': 'admitted'}, 'slug': 'luhuk-mukiz'}
        rain = {'status': 'admitted', 'object': 'bell/2', 'inPublic': True,
                'receipt': {'outcome': {'tag': 'admitted', 'writes': [{'object': 'bell/2', 'version': 8}]}, 'roots': [{'object': 'bell/2', 'version': 7}]}}
        reply = {**rain, 'tried': True, 'against': {'height': 1013}, 'delivered': [{'object': 'tide', 'status': 'admitted', 'receipt': bound}] * 64}
        text = bridge.preview_text(reply)
        self.assertEqual(text.count('then would be admitted tide'), 1, text)
        self.assertTrue(text.startswith('preview, nothing done (as of entry 1013):\nwould be admitted bell/2 v8\n'), text)
        self.assertNotIn('luhuk-mukiz', text)

    def test_sends_answered_already_are_said_as_never_run_again(self):
        from transport import bridge
        reply = {'status': 'admitted', 'object': 'bell/2', 'tried': True, 'against': {'height': 1013},
                 'receipt': {'outcome': {'tag': 'admitted'}, 'roots': [{'object': 'bell/2', 'version': 7}]},
                 'unresolved': {'pending': 6, 'suspended': 0, 'answered': 2}}
        self.assertIn('\nleft for later, not foreseen: 6 sends, 0 waiting on hob\n2 sends answered already by their receipts, never run again\n',
                      bridge.preview_text(reply))


if __name__ == '__main__':
    unittest.main()
