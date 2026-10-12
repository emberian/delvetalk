"""Genesis seeds the town's world once through a real `serve`: every door resolves, the opener's handle
shows, the door pages are published, and the library it shelves answers by a word and only its owner shelves.

Evidence for FOUNDATION §7, §11 (layer: transport).
"""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
import unittest.mock

from deploy import genesis
from tests.town import Town
from tests.wire import cast_refusal, field, label, nat, record, result_label, rows
from transport.config import ORIGIN


class Genesis(unittest.TestCase):
    """One genesis per class: a `serve` opened by the opener with the library sealed, then
    deploy/genesis.py's whole sequence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False, fresh=True)  # genesis itself, run here
        cls.host = cls.town.client  # genesis is the opener's: the root socket
        cls.made, cls.refusal = cls.town.made, cls.town.refusal

    def view(self, obj):
        got = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': obj})
        self.assertEqual(got['status'], 'viewed', got)
        return {f['name']: f['value'] for f in got['state']['fields']}

    def test_the_whole_sequence_is_created_once_and_refused_a_second_time(self):
        host, made, refusal = self.host, self.made, self.refusal
        hands = [dict(fields)['id'] for _, fields, _ in genesis.HANDS]
        # world-create seeds the frame; the town's coinages are then admitted by spell on their kinds, the porch's
        # doors to the two bells and the seeded wants after; then the porch's things are created and laid there
        self.assertEqual((refusal, [(m['object'], m['status']) for m in made]),
                         (None, [(n, 'created') for n, _, _ in genesis.seeds(genesis.OPENER)] + [(id, 'admitted') for id in hands]
                          + [('porch', 'admitted')] * len(genesis.PORCH_DOORS) + [(w[0], 'admitted') for w in genesis.WANTS]
                          + [(t, 'created') for t, _ in genesis.THINGS] + [(dict(f)['id'], 'admitted') for _, f in genesis.MOTION]), made)
        o = genesis.OPENER
        self.assertEqual(sorted(genesis.existing(host, o)), sorted([n for n, _, _ in genesis.seeds(o)] + ['kind/' + k[0] for k in genesis.KINDS] + hands + [t for t, _ in genesis.THINGS] + [dict(f)['id'] for _, f in genesis.MOTION] + [o]))
        self.assertEqual([m.get('laid') for m in made if m['module'] == 'Thing'], ['admitted'] * len(genesis.THINGS))
        # each coinage is a record of its kind whose maker is the opener, made from its coiner's post, which its card credits
        for id, (kind, _, post) in zip(hands, genesis.HANDS):
            thing = self.view(id)
            self.assertEqual((thing['kind']['value'], thing['maker']['value'], thing['owner']['value'], thing['post']['value']), (kind, o, o, post), id)
            self.assertIn('After %s\n' % post, host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': id})['text'])
        avatar = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': o})
        self.assertIn("ember.delve.town's avatar, nowhere yet", json.dumps(avatar))
        again, refusal = genesis.run(host)
        self.assertEqual(again, [])
        self.assertIn('already run', refusal)
        self.assertEqual((len(genesis.DOORS), len(genesis.seeds(genesis.OPENER))), (4, 6))
        ids = set(genesis.existing(host, o))
        self.assertEqual([l for l, to, _ in genesis.DOORS if to not in ids], [])  # every door with an object resolves
        self.assertEqual([d[0] for d in genesis.DOORS] + [genesis.STUDIO[0]], ['KINDS', 'PORCH', 'WORKSHOP', 'TIDE', 'STUDIO'])
        self.assertEqual([(m['object'], m['body']) for m in made if 'body' in m], [('commonplace', 'admitted')])
        said = {}
        for word in ('PORCH', 'STUDIO'):
            got = host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'commonplace', 'method': 'receive',
                             'argument': record(text=label(word), post=label('at://x/p/' + word)),
                             'identity': 'door-' + word})
            self.assertEqual(got['status'], 'admitted', got)
            said[word] = got['offers'][0]['text']
        self.assertTrue(said['PORCH'].startswith("The Bellfounder's Porch"), said)
        # The link door has no object: naming it answers its description.
        self.assertEqual(said['STUDIO'], 'STUDIO\nscratch worlds and REPL: ' + ORIGIN + '/AGENTS.md\n')
        menu = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'commonplace'})['text']
        self.assertIn(ORIGIN + '/AGENTS.md', menu)

    def test_the_seeded_things_want_in_their_own_voice_and_a_want_fades_when_answered(self):
        """The onboarding is wants, never posts: mimo's bell has no clapper, kinds has made only the town's own,
        each porch thing has nothing around it, each bell no door; each reading says what the thing lacks and asks no one."""
        wants = lambda obj: {r['name']: r for r in self.host.send({'op': 'world-wants', 'principal': 'did:plc:stranger', 'object': obj})['rows']}
        clapper = wants('bell/1')['clapper']
        self.assertEqual((clapper['reading'], clapper['asks']), (genesis.WANTS[0][2], genesis.WANTS[0][4]))
        self.assertIn('grow / name: hang', clapper['asks'])  # a clapper is a verb the first hand grows, not a thing to bring
        self.assertEqual(wants('kinds')['made']['reading'], "no kind made here yet but the town's own")
        self.assertNotIn('made', wants('kind/bell'))  # the guard keeps kinds' want off the kinds that follow it
        self.assertEqual(wants('porch/goblet')['claimed']['reading'], 'nothing surrounds it yet')
        for obj in ('bell/1', 'bell/2', 'porch', 'kinds', 'porch/goblet'):
            for row in wants(obj).values():
                self.assertFalse(re.match(r'(please |you |hang |make |inspirit |tend |rain )', row['reading']), row)

    def test_the_tide_ticks_itself_every_hour_with_nobody_posting(self):
        """OFFERING §4: the opener's first tick starts the tide, which then ticks itself every 60 clock minutes;
        a clock jump ticks it once, at the clock it wakes to."""
        tide = next(m for m in self.made if m['object'] == 'tide')
        self.assertEqual(tide['tick'], 'admitted', tide)
        def ticks():
            state = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'tide'})['state']
            return {f['name']: f['value'] for f in state['fields']}['ticks']['value']
        self.assertEqual(ticks(), '1')
        clock = self.host.send({'op': 'world-status'}).get('clock', 0)
        seen = []
        for minutes in (30, 61, 125):
            self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': clock + minutes})
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
            seen.append(ticks())
        self.assertEqual(seen, ['1', '2', '3'])


    def test_the_room_kind_carries_the_record_law_and_the_rooms_body(self):
        from tests.test_objects import run_pure
        # Record declares no law (every kind imports the package it makes); genesis passes it with each record kind
        self.assertEqual(run_pure("Record", "lawText")["value"]["value"], genesis.RECORD_LAW)
        self.assertIn('room', [name for name, *_ in genesis.KINDS])
        state = {f['name']: f['value'] for f in self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'kind/room'})['state']['fields']}
        # the kind's text is its instances' laws, rules and wants: the record's law and the room's want `company`
        self.assertEqual((state['law']['value'], state['body']['value']), (genesis.RECORD_LAW + '\n' + genesis.kind_text('room'), genesis.body_of('room')))
        # a kind's voice is its things' register, on its card and owner-only by the kinds' law
        bell = self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'kind/bell'})['text']
        self.assertIn('Its things speak: %s\n' % genesis.VOICES['bell'], bell)
        self.assertIn('unchanged(voice)', genesis.KIND_LAW)

    def test_every_door_with_an_object_publishes_its_page(self):
        pages = {m['object']: m['page']['status'] for m in self.made if 'page' in m}
        self.assertEqual(sorted(k for k, v in pages.items() if v == 'admitted'), ['kinds', 'porch', 'tide', 'workshop'], pages)

    def library(self, text, n):
        got = self.host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'library', 'method': 'receive', 'identity': 'lib-%d' % n,
                              'argument': record(text=label(text), post=label('at://x/p/%d' % n))})
        if got['status'] == 'refused':  # the card's refusal refuses the turn: its line is the receipt's reason
            cast_refusal(got)
            return got['receipt']['outcome']['reason'] + '\n'
        self.assertEqual(got['status'], 'admitted', got)
        return got['offers'][0]['text']

    def test_the_library_finds_a_page_by_a_word_names_its_pages_on_a_miss_and_shelves_only_for_its_owner(self):
        """LIBRARY (a), (e): genesis shelved capsules/pages/ as the opener; anyone reads a page by a word of what they said."""
        self.assertEqual(self.library('delvetalk library read / page: how do i read laws?', 1), genesis.page_body('laws'))
        miss = self.library('delvetalk library read / page: dragons', 2)
        self.assertEqual(miss, 'refused noPage: No page called dragons. Pages: spells laws object relations protocol world kinds; walks: bell check enter tide kind.\n')
        refused = self.library('delvetalk library shelve / name: mine / kind: page / title: t / body: hob: mine', 3)
        self.assertEqual(refused, 'refused notOwner: Only ember.delve.town shelves a page\n')
        self.assertNotIn('mine', self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'library'})['text'])


    def test_every_page_fits_a_reply_under_the_librarys_receipt_and_names_only_pages_shelved(self):
        """Playtest 2's D8 (69090, 69096: the spells and laws pages drafted at 1,450 and 1,426) and D9 (69090: the spells
        page named a walk `plant` the stacks did not hold). A page is what a reply leaves after the library's receipt
        line (Card.limit: 1,400 less twice the id and 120), opens with hob's line, and every page it names is shelved."""
        names = [name for name, _, _ in genesis.PAGES]
        for name in names:
            with self.subTest(page=name):
                body = genesis.page_body(name)
                self.assertLessEqual(len(body), 1400 - (2 * len('library') + 120), name)
                self.assertTrue(body.startswith('hob: '), body[:40])
                for named in re.findall(r'page: ([a-z]+)', body):
                    self.assertIn(named, names, (name, named))


class Clapper(unittest.TestCase):
    def test_the_clapper_wants_exact_spell_grows_the_verb_whose_use_answers_it(self):
        """Codex docs 10: the clapper want asked `delvetalk bell/1 hang`, a verb nobody seeded, which with no model
        is refused `noAction`. Its spell grows `hang`; cast by its name, it hangs the clapper and the want falls."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        town = Town(tmp.name, cleanup=self.addCleanup, furnished=False)
        say = lambda text, n: town.send(op='world-turn', principal='did:plc:stranger', object='bell/1', method='receive', identity='c%d' % n,
                                        argument=record(text=label(text), post=label('')))
        wants = lambda: [r['name'] for r in town.send(op='world-wants', principal='did:plc:stranger', object='bell/1')['rows']]
        [asks] = [r['asks'] for r in town.send(op='world-wants', principal='did:plc:stranger', object='bell/1')['rows'] if r['name'] == 'clapper']
        grown = say(asks, 1)
        self.assertEqual(grown['status'], 'admitted', grown)
        self.assertIn('clapper', wants())
        hung = say('delvetalk bell/1 hang / text: a brass clapper', 2)
        self.assertEqual(hung['status'], 'admitted', hung)
        self.assertNotIn('clapper', wants())


class NoWipe(unittest.TestCase):
    """FOUNDATION §2: a genesis while a town lives under `--towns` is refused, naming it, and creates nothing;
    with the owner's word it runs, and the word is the town's first line, admitted. Refuted by a genesis that runs
    over a living town without the word, one that creates anything before refusing, or a word not on the commonplace."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.towns = tmp.name
        # A town that lives: another data directory's journal with entries (the guard reads only its chain's lines).
        os.makedirs(os.path.join(self.towns, 'v1', 'state'))
        with open(os.path.join(self.towns, 'v1', 'state', 'town.journal'), 'w') as f:
            f.write('{"height":1}\n{"height":2}\n')
        os.makedirs(os.path.join(self.towns, 'v1', 'state', 'scratch'))
        self.town = Town(os.path.join(self.towns, 'v2'), run_genesis=False, cleanup=self.addCleanup)

    def genesis(self, *more):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = genesis.main(['--root-socket', self.town.process.root, '--towns', self.towns, '--state', self.town.state, *more])
        return code, err.getvalue()

    def test_a_genesis_over_a_living_town_is_refused_by_name_and_runs_only_with_the_owners_word(self):
        code, err = self.genesis()
        self.assertEqual(code, 1, err)
        self.assertIn('v1/state/town.journal (height 2)', err)
        self.assertNotIn(os.path.join(self.towns, 'v2') + os.sep, err)  # its own journal is not a town it would abandon (a path, since the temp dir's random name may hold 'v2')
        self.assertEqual(genesis.existing(self.town.client, genesis.OPENER), [])
        self.assertEqual(self.genesis('--wipe-with-the-owners-word', 'two\nlines')[0], 64)
        word = 'the town begins again by the owner\'s word'
        code, err = self.genesis('--wipe-with-the-owners-word', word)
        self.assertEqual(code, 0, err)
        state = self.town.send(op='world-view', principal=genesis.OPENER, object='commonplace')['state']
        [first] = rows(field(state, 'lines'))
        self.assertEqual((field(first, 'n')['value'], field(first, 'text')['value'], field(first, 'author')['value']),
                         ('1', word, genesis.OPENER))
        self.assertEqual([field(a, 'n')['value'] for a in rows(field(state, 'admitted'))], ['1'])

    @unittest.skipIf(os.geteuid() == 0, 'root reads a mode-0 directory')
    def test_a_directory_the_guard_cannot_read_refuses_and_the_word_is_written_whatever_it_saw(self):
        hidden = os.path.join(self.towns, 'v1')
        os.chmod(hidden, 0)
        self.addCleanup(os.chmod, hidden, 0o755)
        code, err = self.genesis()
        self.assertEqual(code, 1, err)
        self.assertIn('v1 (Permission denied): unreadable', err)
        self.assertEqual(genesis.existing(self.town.client, genesis.OPENER), [])
        word = 'the owner begins again'
        self.assertEqual(self.genesis('--wipe-with-the-owners-word', word)[0], 0)  # the deploy of 5db9aa79 ran so, and dropped the word
        state = self.town.send(op='world-view', principal=genesis.OPENER, object='commonplace')['state']
        self.assertEqual([field(r, 'text')['value'] for r in rows(field(state, 'lines'))], [word])

    def test_without_towns_genesis_refuses_to_guess(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), unittest.mock.patch.dict(os.environ, {'DELVETALK_TOWNS': ''}):
            self.assertEqual(genesis.main(['--root-socket', self.town.process.root]), 64)
        self.assertIn('--towns', err.getvalue())


class Checked(unittest.TestCase):
    """`workshop check / target:` checks what the card runs, its whole source: a bell and the garden are a
    kind's body layered over Record, so the layer alone names a module below it (`world.checkObject`)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        cls.town.send(op='world-arrive', principal='transport', did='did:plc:glm', handle='glm.delve.town')

    def check(self, target, ident):
        got = self.town.send(op='world-turn', principal='did:plc:glm', object='workshop', method='receive',
                             argument=record(text=label('delvetalk workshop check / target: ' + target),
                                             post=label('at://x/p/' + ident)), identity=ident)
        self.assertEqual(got['status'], 'admitted', got)
        return got['offers'][0]['text']

    def test_a_bell_and_the_garden_check_clean_and_a_missing_card_is_named(self):
        for target in ('bell/1', 'garden'):
            with self.subTest(target=target):
                source = self.town.send(op='world-inspect', principal='did:plc:glm', object=target, source=True)['source']
                self.assertTrue(source.startswith('layer over ./'), source[:80])
                self.assertEqual(self.check(target, 'check-' + target.replace('/', '-')), '✾ WORKSHOP\n\nChecked: it compiles.\n')
        # A missing card is the card's own refusal now: the turn is refused, the reason names it (kernel16, rewrite13).
        got = self.town.send(op='world-turn', principal='did:plc:glm', object='workshop', method='receive',
                             argument=record(text=label('delvetalk workshop check / target: ghost'),
                                             post=label('at://x/p/check-ghost')), identity='check-ghost')
        self.assertEqual((got['status'], got['public']['class']), ('refused', 'cardRefused'), got)
        self.assertIn('No object called ghost', json.dumps(got))


class Refresh(unittest.TestCase):
    """`refresh` on a town genesis made with older texts (a record law with no `pending` want, a bell kind with no rules
    or wants, no voices, no kind/front, no weather or lamp), as a carried town keeps them: the opener re-writes each
    slot to genesis's text today, makes the kind it lacks and places the motion, each a journaled turn; a slot another hand changed since is left and named; a
    second refresh finds every slot current."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        old_record = genesis.RECORD_LAW.rsplit('\nwant pending', 1)[0]
        old_kinds = [(n, of, form, head, law.replace(genesis.RECORD_LAW, old_record).split('\nrule seven', 1)[0], body)
                     for n, of, form, head, law, body in genesis.KINDS if n != 'front']  # a kind genesis makes since
        with unittest.mock.patch.multiple(genesis, RECORD_LAW=old_record, KINDS=old_kinds, VOICES={}, MOTION=[]):
            cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.send = cls.town.send
        # Another hand since genesis: kinds' own law gains a clause, kind/door's law field loses its want.
        version = int(cls.send(op='world-object', principal=genesis.OPENER, object='kinds')['record']['version'])
        cls.amended = genesis.KIND_LAW + '\nlaw quiet "nothing after midnight": request.clock >= 0'
        assert cls.send(op='world-amend', principal=genesis.OPENER, identity='hand-kinds', object='kinds', version=version,
                        law=cls.amended)['status'] == 'admitted'
        door = cls.send(op='world-object', principal=genesis.OPENER, object='kind/door')['record']['version']
        cls.door = old_record
        assert cls.send(op='world-propose', principal=genesis.OPENER, identity='hand-door', roots=[{'object': 'kind/door', 'version': int(door)}],
                        writes=[{'object': 'kind/door', 'edits': [record(law={'tag': 'variant', 'label': 'set', 'payload': record(value=label(cls.door))})]}]
                        )['status'] == 'admitted'
        cls.rows = genesis.refresh(cls.town.client, genesis.OPENER, genesis.ancestry(cls.town.journal))

    def status(self, rows, obj, slot):
        [row] = [r for r in rows if (r['object'], r.get('slot')) == (obj, slot)]
        return row['status'], row.get('reading')

    def test_each_slot_genesis_made_is_its_text_today_and_another_hands_change_is_left_and_named(self):
        for obj, slot in (('commonplace', 'law'), ('kind/record', '.law'), ('kind/bell', '.law'), ('kind/bell', '.voice'),
                          ('kind/garden', '.law'), ('kind/porch', '.voice')):
            with self.subTest(obj=obj, slot=slot):
                self.assertEqual(self.status(self.rows, obj, slot), ('refreshed', None))
        self.assertEqual(self.status(self.rows, 'kind/front', '.law'), ('refreshed', 'made'))
        self.assertIn('kind/front', self.send(op='world-objects', principal=genesis.OPENER)['ids'])
        # The town's motion, which the older genesis did not place, is placed after its kinds.
        for obj in ('weather', 'porch/lamp'):
            self.assertEqual(self.status(self.rows, obj, 'placed'), ('refreshed', 'placed'))
        self.assertEqual(sorted(r['name'] for r in self.send(op='world-rules', principal=genesis.OPENER, object='tide')['rows']), ['porch_slamp', 'weather'])
        self.assertEqual(self.status(self.rows, 'kinds', 'law'), ('left', 'changed since genesis gave it'))
        self.assertEqual(self.status(self.rows, 'kind/door', '.law'), ('left', 'changed since genesis gave it'))
        self.assertEqual(self.send(op='world-object', principal=genesis.OPENER, object='commonplace')['record']['law'], genesis.RECORD_LAW)
        self.assertEqual(self.send(op='world-object', principal=genesis.OPENER, object='kinds')['record']['law'], self.amended)
        kind = {f['name']: f['value']['value'] for f in self.send(op='world-view', principal=genesis.OPENER, object='kind/bell')['state']['fields']
                if f['name'] in ('law', 'voice')}
        self.assertEqual(kind, {'law': dict((k[0], k[4]) for k in genesis.KINDS)['bell'], 'voice': genesis.VOICES['bell']})
        door = [f['value']['value'] for f in self.send(op='world-view', principal=genesis.OPENER, object='kind/door')['state']['fields'] if f['name'] == 'law']
        self.assertEqual(door, [self.door])

    def test_the_bell_genesis_placed_carries_the_kinds_rules_now_and_a_second_refresh_changes_nothing(self):
        got = self.send(op='world-rules', principal=genesis.OPENER, object='bell/1')
        self.assertEqual(sorted((r['name'], r['from']) for r in got['rows']), [('rang', 'kind/bell'), ('seven', 'kind/bell')], got)
        height = self.send(op='world-status')['height']
        again = genesis.refresh(self.town.client, genesis.OPENER, genesis.ancestry(self.town.journal))
        self.assertEqual({r['status'] for r in again} - {'current'}, {'left'}, again)
        self.assertEqual(sorted((r['object'], r['slot']) for r in again if r['status'] == 'left'), [('kind/door', '.law'), ('kinds', 'law')])
        self.assertEqual(self.send(op='world-status')['height'], height)


class CarriedRefresh(unittest.TestCase):
    """`refresh` on a carried town whose older journals are not on this disk (a deploy check's backup, a container
    without the old state): the carry keeps each object's making (`made`), so a kind the opener made at the original
    genesis counts as genesis-made and its law, form and voice are refreshed, never left as "its making is in no
    journal read"."""

    def test_a_kind_made_at_the_original_genesis_is_refreshed_through_the_carry(self):
        import shutil
        import subprocess
        from tests.host import binary
        from transport.host import HostProcess
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old_record = genesis.RECORD_LAW.rsplit('\nwant pending', 1)[0]
        old_kinds = [(n, of, form, head, law.replace(genesis.RECORD_LAW, old_record).split('\nrule seven', 1)[0], body)
                     for n, of, form, head, law, body in genesis.KINDS]
        with unittest.mock.patch.multiple(genesis, RECORD_LAW=old_record, KINDS=old_kinds, VOICES={}, MOTION=[]):
            town = Town(os.path.join(tmp.name, 'v1'), cleanup=self.addCleanup, furnished=False)
        self.assertEqual(town.send(op='world-snapshot')['status'], 'snapshot')
        town.close()
        out = os.path.join(tmp.name, 'v2.journal')
        p = subprocess.run([binary(), 'carry', '--from', town.journal, '--out', out, '--reason', 'a newer host'],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        made = {r['object']: r for r in genesis_outcome(out).get('made') or []}
        self.assertEqual((made['kind/bell']['identity']['principal'], made['kind/bell']['identity']['intent']),
                         (genesis.OPENER, 'genesis-kind-bell'), made.get('kind/bell'))
        # A carried genesis of an edition before `made` (the live v9): carried again, the makings are read from the
        # journal it cites while that is on this disk, and kept.
        from tests.wire import cid_of, write_journal
        from transport import journal
        [g] = journal.entries(out)
        g['outcome'].pop('made')
        g.pop('hash')
        g['hash'] = cid_of(g)
        os.remove(out)
        os.remove(out + '.blocks')
        write_journal(out, [g])
        held = HostProcess(binary(), out)
        self.assertEqual(held.send(op='world-snapshot')['status'], 'snapshot')
        held.close()
        again = os.path.join(tmp.name, 'v3.journal')
        p = subprocess.run([binary(), 'carry', '--from', out, '--out', again, '--reason', 'again'], capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual({r['object']: r for r in genesis_outcome(again)['made']}['kind/bell'], made['kind/bell'])
        shutil.rmtree(town.state)  # the worlds before are not on this disk
        os.remove(out)
        out = again
        host = HostProcess(binary(), out)
        self.addCleanup(host.close)
        rows = genesis.refresh(host, genesis.OPENER, genesis.ancestry(out))
        status = {(r['object'], r.get('slot')): (r['status'], r.get('reading')) for r in rows}
        for obj, slot in (('kind/record', '.law'), ('kind/bell', '.law'), ('kind/bell', '.voice')):
            with self.subTest(obj=obj, slot=slot):
                self.assertEqual(status[(obj, slot)], ('refreshed', None))
        kind = {f['name']: f['value']['value'] for f in host.send(op='world-view', principal=genesis.OPENER, object='kind/bell')['state']['fields']
                if f['name'] in ('law', 'voice')}
        self.assertEqual(kind, {'law': dict((k[0], k[4]) for k in genesis.KINDS)['bell'], 'voice': genesis.VOICES['bell']})


def genesis_outcome(path):
    from transport import journal
    return journal.read(path, journal.links(path)[:1])[0]['outcome']


class Weather(unittest.TestCase):
    """docs/METAPHYSICS.md §7.4: the furnished garden's weather (`garden/weather`) rains by its rule on the tide, at
    every twenty-fourth tick while the garden is tended, on every bell the garden holds, and writes the garden's
    weather line, since the garden hangs a door to it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.town = Town(tmp.name, cleanup=self.addCleanup)
        self.host = self.town.client

    def state(self, obj):
        return {f['name']: f['value'] for f in self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': obj})['state']['fields']}

    def deliver(self):
        for _ in range(16):
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
            if not self.host.send({'op': 'world-pending'}).get('count'):
                return

    def test_the_weather_rains_on_a_planted_bell_at_a_tide_tick_and_writes_the_gardens_weather(self):
        glm = 'did:plc:glm'
        self.host.send({'op': 'world-arrive', 'principal': 'transport', 'did': glm, 'handle': 'glm.delve.town'})
        planted = self.host.send({'op': 'world-turn', 'principal': glm, 'object': 'garden', 'method': 'receive', 'identity': 'plant',
                                  'argument': record(text=label('delvetalk garden plant / seed: a bell for the weather / colour: silver'), post=label('at://x/p/plant'))})
        self.assertEqual(planted['status'], 'admitted', planted)
        self.deliver()
        self.assertEqual(self.state('garden/weather')['lines']['payload']['fields'][0]['value']['items'], [])
        self.assertNotIn('Weather:', self.host.send({'op': 'world-card', 'principal': glm, 'object': 'garden'})['text'])
        clock = self.host.send({'op': 'world-status'}).get('clock', 0)
        for hour in range(1, 24):  # a jump ticks once, so the tide is walked through its day: tick 24 is the 23rd hour on
            self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': clock + 61 * hour})
            self.deliver()
        bell = self.host.send({'op': 'world-view', 'principal': glm, 'object': 'garden/bell/1'})['state']
        rains = [next(f['value']['value'] for f in row['fields'] if f['name'] == 'text')
                 for row in next(f['value'] for f in bell['fields'] if f['name'] == 'lines')['payload']['fields'][0]['value']['items']]
        self.assertEqual(len(rains), 1, rains)
        self.assertRegex(rains[0], r"^garden/weather's rain, clock \d+$")
        self.assertRegex(self.host.send({'op': 'world-card', 'principal': glm, 'object': 'garden'})['text'], r'Weather: rain at clock \d+, on 1\n')


class Commonplace(unittest.TestCase):
    """docs/METAPHYSICS.md §5, §7.5: the town's first card is the commonplace, a record the opener keeps. Its
    card says what changed in the town, newest first (World.changed, read when asked: nothing is kept to say
    it), each `<id> v<n> by <handle>, entry N`, then the first spells, then the doors the hand named, each
    with the spells it prints. The owner hangs an arc under a door with `door`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        cls.host = cls.town.client  # genesis is the opener's: the root socket
        cls.made, cls.refusal = cls.town.made, cls.town.refusal

    def say(self, who, obj, text, ident):
        got = self.host.send({'op': 'world-turn', 'principal': who, 'object': obj, 'method': 'receive',
                              'argument': record(text=label(text), post=label('at://x/p/' + ident)), 'identity': ident})
        self.assertEqual(got['status'], 'admitted', got)
        self.deliver()
        return got

    def deliver(self):
        for _ in range(16):
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
            if not self.host.send({'op': 'world-pending'}).get('count'):
                return

    def test_an_arrivals_own_cards_are_not_what_changed(self):
        """Playtest 2 D5: arrival makes a principal's avatar; the commonplace names none of it,
        whatever names the principal (a DID, a Zulip id)."""
        for who, handle in (('did:plc:arriving', 'arriving.delve.town'), ('zulip:tulip.arke.me/77', 'Kestrel')):
            self.host.send({'op': 'world-arrive', 'principal': 'transport', 'did': who, 'handle': handle})
        card = self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'commonplace'})['text']
        self.assertNotIn('arriving', card)
        self.assertNotIn('zulip:', card)

    def owner(self, method, ident, **fields):
        got = self.host.send({'op': 'world-turn', 'principal': genesis.OPENER, 'object': 'commonplace', 'method': method,
                              'identity': ident, 'argument': record(**{k: label(v) for k, v in fields.items()})})
        self.assertIn(got['status'], ('admitted', 'refused'), got)
        return got

    def test_what_wants_a_hand_leads_what_changed_yields_and_the_doors_follow_within_the_clip(self):
        stranger, glm, kimi = 'did:plc:stranger', 'did:plc:glm', 'did:plc:kimi'
        card = self.host.send({'op': 'world-card', 'principal': stranger, 'object': 'commonplace'})['text']
        self.assertTrue(card.startswith('✾ DELVETALK · THE COMMONPLACE\n\nEight doors.'), card)
        self.assertIn('  delvetalk commonplace since / entry: 0\n', card)
        self.assertIn('PORCH\n  delvetalk porch enter\n', card)
        self.assertIn('ROOMS\n', card)  # the furnished town's doors, hung by spell with no example
        for n, colour in enumerate(('silver', 'amber'), 1):
            self.say(glm, 'garden', 'delvetalk garden plant / seed: a bell for the %d / colour: %s' % (n, colour), 'plant-%d' % n)
        rain = self.say(kimi, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: it rained here first', 'rain-1')
        # The owner opens an arc (SEEDING §4): a door to the first bell, with a spell.
        # The commonplace holds eight doors, and the hand's seven with the link door fill them: a ninth is refused, so TIDE makes room.
        self.assertEqual(result_label(self.owner('door', 'arc-full', label='BELL', to='garden/bell/1')), 'refused')
        self.assertEqual(self.owner('undoor', 'arc-room', label='TIDE')['result']['label'], 'done')
        self.assertEqual(self.owner('door', 'arc-door', label='BELL', to='garden/bell/1')['result']['label'], 'done')
        blank = self.say(stranger, 'commonplace', '', 'blank')['offers'][-1]['text']
        self.assertLessEqual(len(blank), 1400, blank)
        # What wants a hand leads (the onboarding); what changed yields it room, and is said only when its first row fits.
        self.assertEqual(blank.split('\n')[3], 'What wants a hand, newest first:', blank)
        self.assertIn('\ngarden/bell/2: a bell nobody has rained on\n  delvetalk garden/bell/2 rain\n', blank)
        # The card itself leads with it (the web's card, and the answer to a question hob reads nothing into, 5.171, are
        # this text): the host hands `renderWanting` the rows, as it hands it the reader.
        shown = self.host.send({'op': 'world-card', 'principal': stranger, 'object': 'commonplace'})['text']
        self.assertEqual(shown.split('\n')[3], 'What wants a hand, newest first:', shown)
        self.assertIn('\ngarden/bell/2: a bell nobody has rained on\n  delvetalk garden/bell/2 rain\n', shown)
        if 'What changed, newest first:\n' in blank:
            changed = blank[blank.index('What changed, newest first:\n'):].split('\n')[1]
            self.assertTrue(changed.startswith('garden/bell/1 v') and changed.endswith(' by kimi, entry %d' % rain['receipt']['height']), changed)
        self.assertNotIn('commonplace v', blank)  # its own doors are not news
        self.assertIn('  delvetalk kinds make / name: lamp / of: record\n  » kind/lamp, a kind anyone makes\n  delvetalk garden/bell/1 ?\n', blank)
        # KINDS and WORKSHOP lead (playtest 2, F1): what is clipped is the places, from the end.
        self.assertIn('\nKINDS\n  delvetalk kinds make / name: lamp / of: record / form: seed: text 1..80\n  » kind/lamp, a kind anyone makes\nPORCH\n', blank)
        self.assertIn('STUDIO · scratch worlds and REPL: ' + ORIGIN + '/AGENTS.md\n', blank)  # a link door is never clipped
        self.assertTrue(blank.endswith('Every reply is a receipt: admitted, or refused <clause>: <reading>. No reply: ask for it; never repost.\n'), blank)
        # since an entry: only what changed after it
        since = self.host.send({'op': 'world-turn', 'principal': stranger, 'object': 'commonplace', 'method': 'since', 'identity': 'since',
                                'argument': record(entry=nat(rain['receipt']['height'] - 1))})
        news = since['offers'][-1]['text']
        self.assertLessEqual(len(news), 1400, news)
        self.assertIn('  delvetalk kinds make / name: lamp / of: record\n  » kind/lamp, a kind anyone makes\n  delvetalk garden/bell/1 ?\n', news)
        if 'What changed, newest first:\n' in news:
            self.assertEqual(news.split('What changed, newest first:\n')[1].split('\n')[0].split(' v')[0], 'garden/bell/1')
        # A stranger hangs no door.
        refused = self.host.send({'op': 'world-turn', 'principal': stranger, 'object': 'commonplace', 'method': 'door', 'identity': 'stranger-door',
                                  'argument': record(label=label('MINE'), to=label('garden'))})
        self.assertEqual(result_label(refused), 'refused', refused)

    def test_a_field_line_goes_to_its_door_and_first_words_get_no_greeting(self):
        reader = 'did:plc:newcomer'
        hello = self.say(reader, 'commonplace', 'hello', 'hello')
        self.assertEqual((hello['status'], hello['result']['label'], hello.get('offers', [])), ('admitted', 'silent', []), hello)
        # A field line that reached the commonplace and names a door's action is the host's to fit (HOST-HANDOFF
        # 5.163): it runs at once, no model, as the reader's turn on the first door taking it (the porch, a room),
        # whose card refuses it by its own clause.
        got = self.host.send({'op': 'world-turn', 'principal': reader, 'object': 'commonplace', 'method': 'receive', 'reach': 'fields',
                              'argument': record(text=label('choose: Open'), post=label('at://x/p/by-field-line')), 'identity': 'by-field-line'})
        out = got['receipt']['outcome']
        self.assertEqual((got['status'], out['class'], out['object'], out['reason']), ('refused', 'cardRefused', 'porch', 'refused notHere: Enter the room first.'), got)
        self.assertEqual(self.host.send({'op': 'world-interpretations'})['pending'], [])


if __name__ == '__main__':
    unittest.main()
