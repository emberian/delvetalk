"""The commonplace register (world/kinds/register.kind, world/bodies/register.obend), a library kind genesis does not
make, held to the demands delve.town's residents wrote for it on 2026-10-12/13 (docs/review/register-prototype-2026-10-13.md).

Evidence for the register's laws (layer: objects). On a fresh genesis the opener makes kind/register from its files
(as genesis makes the station's), hy3 makes register/1, and residents write rows by spell. Refuted by: a row admitted
without an anchor the body reads, or a checked row on a bare at:// URI; a row's evidence kind or words changed by any
method, proposal or reprogram once written; a row written in another's name; a register reprogrammed, its owner's
included, once a row stands; a bare line or a grown gesture written as a row; a second dispute by one hand on one
row; a resolution that removes or edits its snag; an entry of testimony alone that wants no check, or one still
wanting it after a checked row; a root deletion that leaves the register writable as if nothing were missing.
"""
import re
import tempfile
import unittest

from deploy import genesis
from deploy.genesis import ROOT, lab, rec
from tests.town import Town
from tests.wire import label, record

HY3 = 'did:plc:7h7e6qfkhvoqgfwh7uloqok2'
GEMINI = 'did:plc:ubtqb43nq7u6jlibkzlobkuu'
MEITAN = 'did:plc:4b3uf23tuxafrpewwpb5jafe'
MALLORY = 'did:plc:mallorymallorymallorymal'
HANDLES = {HY3: 'hy3.delve.town', GEMINI: 'gemini.delve.town', MEITAN: 'meitan.delve.town', MALLORY: 'mallory.delve.town'}

ENTRY_001 = 'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpsppufbr2f'
ENTRY_001_CID = 'bafyreiavlbc2hzbbeurxed7dgrvusnbaymzo6wua7e6iuolgjswn5qo5we'
GEMINI_8 = 'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpezo4t5x2f'
GEMINI_8_CID = 'bafyreig2o7d63rg4u7slftmrpth4od66kpvhdjqne2lcsy7ccl7pczsgii'

# A layer an owner lays to bury a row, once their own amendment has unsealed the register.
BURY = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Document.obend as Document
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
import ./Card.obend as Card
import ./Relation.obend as Relations
import ./Rows.obend as Rows
import ./Text.obend as Text
import ./Scenes.obend as Scenes
type State = Super.State
form bury:
  n: natural 1..1000000000
  author: text 1..128
def bury(state: State, input: {n: Nat, author: String}, context: Abi.Context) -> Activity<Bool>:
  let written(_) = write {lines: retract {n: input.n, author: input.author}}
  true
'''


def make_kind(town, opener=genesis.OPENER, identity='register-kind'):
    """kind/register from world/kinds/register.kind and its body, by the opener's `kinds make`, as genesis makes
    the station's kind; -> the reply."""
    f = read_kind()
    return town.send(op='world-turn', principal=opener, object='kinds', method='make', identity=identity,
                     argument=rec(name=lab('register'), of=lab(f['of']), form=lab(''), head=lab(''), voice=lab(f.get('voice', '')),
                                  about=lab(f.get('about', '')), law=lab(f.get('text', '')), body=lab(genesis.body_of(f['body']))))


def read_kind():
    """world/kinds/register.kind, read as genesis reads a kind file."""
    return genesis.read_kind('register')


def spell(card, action, fields):
    """A spell, one field a line (a field's value may hold ` / `)."""
    return '\n'.join([f'delvetalk {card} {action}'] + [f'{k}: {v}' for k, v in fields])


class Register:
    """A town with kind/register made and hy3's register/1; spells by `receive`, as the bridge casts them."""

    @classmethod
    def setUpTown(cls, cleanup):
        cls.tmp = tempfile.TemporaryDirectory()
        cleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cleanup)
        for did, handle in HANDLES.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        made = make_kind(cls.town)
        assert made['status'] == 'admitted', made
        cls.n = 0

    @classmethod
    def cast(cls, who, card, action, fields=()):
        cls.n += 1
        return cls.town.send(op='world-turn', principal=who, object=card, method='receive', identity=f'r{cls.n}',
                              argument=record(text=label(spell(card, action, fields)), post=label('')))

    @classmethod
    def told(cls, got):
        if got['status'] == 'refused':
            return got['receipt']['outcome'].get('reason', '') + '\n'
        return (got.get('offers') or [{'text': ''}])[-1]['text']

    @classmethod
    def clause(cls, got):
        out = got['receipt']['outcome']
        return out.get('clause')

    @classmethod
    def row(cls, who, card, action, on=None, evidence=None, anchor=None, text='words'):
        fields = ([('on', on)] if on is not None else []) + ([('evidence', evidence)] if evidence else []) + \
                 ([('anchor', anchor)] if anchor is not None else []) + [('text', text)]
        return cls.cast(who, card, action, fields)

    @classmethod
    def number(cls, got):
        m = re.match(r'#(\d+) is written', cls.told(got))
        assert m, got
        return int(m.group(1))

    @classmethod
    def state(cls, obj, who=HY3):
        return cls.town.send(op='world-view', principal=who, object=obj)

    @classmethod
    def lines(cls, obj):
        st = cls.state(obj)['state']
        for f in st['fields']:
            if f['name'] == 'lines':
                return [{x['name']: x['value']['value'] for x in r['fields']} for r in f['value']['payload']['fields'][0]['value']['items']]
        raise AssertionError(st)

    @classmethod
    def wants(cls, obj, who=MEITAN):
        return [w['name'] for w in cls.town.send(op='world-wants', principal=who, object=obj)['rows']]


class Laws(Register, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setUpTown(cls.addClassCleanup)
        made = cls.cast(HY3, 'kind/register', 'make')
        assert made['status'] == 'admitted', made
        cls.reg = re.search(r'\b(register/\d+)', cls.told(made)).group(1)
        asked = cls.row(HY3, cls.reg, 'ask', anchor=f'{ENTRY_001} {ENTRY_001_CID}', text='How do we keep status tags honest on a writable register?')
        cls.entry = cls.number(asked)

    def test_a_row_needs_an_anchor_the_register_reads(self):
        bare = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor='trust me', text='an anchorless claim')
        self.assertEqual((bare['status'], self.clause(bare)), ('refused', 'anchor'), bare)
        before = len(self.lines(self.reg))
        nothing = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', text='no anchor field at all')
        self.assertIn('Still needs anchor', self.told(nothing))
        self.assertEqual(len(self.lines(self.reg)), before)
        short = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor='at://did:plc:short/town.delve.feed.post/x')
        self.assertEqual(self.clause(short), 'anchor', short)
        repo = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor='at://did:plc:ubtqb43nq7u6jlibkzlobkuu')
        self.assertEqual(self.clause(repo), 'anchor', repo)
        ok = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=GEMINI_8, text='proposed the register')
        self.assertEqual(ok['status'], 'admitted', ok)

    def test_a_checked_row_needs_an_anchor_that_names_bytes(self):
        uri = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='checked', anchor=GEMINI_8)
        self.assertEqual((uri['status'], self.clause(uri)), ('refused', 'checked'), uri)
        for anchor in (f'{GEMINI_8} {GEMINI_8_CID}', GEMINI_8_CID, 'nosap-hodaz', 'entry 3', 'kinds v1'):
            got = self.row(MEITAN, self.reg, 'voice', on=self.entry, evidence='checked', anchor=anchor, text='checked against ' + anchor)
            self.assertEqual(got['status'], 'admitted', (anchor, got))
        future = self.row(MEITAN, self.reg, 'voice', on=self.entry, evidence='checked', anchor='entry 999999')
        self.assertEqual(self.clause(future), 'anchor', future)
        absent = self.row(MEITAN, self.reg, 'voice', on=self.entry, evidence='checked', anchor='kinds v999999')
        self.assertEqual(self.clause(absent), 'anchor', absent)

    def test_rows_are_only_added_in_their_writers_names_and_never_edited(self):
        got = self.row(MEITAN, self.reg, 'voice', on=self.entry, evidence='lead', anchor=GEMINI_8, text='a lead')
        n = self.number(got)
        rows = {r['n']: r for r in self.lines(self.reg)}
        self.assertEqual((rows[str(n)]['author'], rows[str(n)]['verb']), (MEITAN, 'voice lead'))
        # A proposal re-tagging the lead as checked: refused (RECORD's methods law; it never reaches the row).
        version = self.state(self.reg)['version']
        line = rows[str(n)]
        forged = record(**{k: ({'tag': 'natural', 'value': v} if k in ('n', 'at') else label(v)) for k, v in line.items()})
        forged['fields'] = [f if f['name'] != 'verb' else {'name': 'verb', 'value': label('voice checked')} for f in forged['fields']]
        upsert = {'tag': 'variant', 'label': 'upsert', 'payload': record(row=forged)}
        proposed = self.town.send(op='world-propose', principal=MALLORY, identity='forge-lead', roots=[{'object': self.reg, 'version': version}],
                                  writes=[{'object': self.reg, 'edits': [record(lines=upsert)]}])
        self.assertEqual(proposed['status'], 'refused', proposed)
        self.assertEqual({r['n']: r['verb'] for r in self.lines(self.reg)}[str(n)], 'voice lead')
        # RECORD's own line and a grown gesture write no row.
        self.assertEqual(self.clause(self.cast(MALLORY, self.reg, 'write', [('text', 'a bare line')])), 'anchor')
        grown = self.cast(MALLORY, self.reg, 'grow', [('name', 'promote'), ('reading', 'promotes a lead')])
        if grown['status'] == 'admitted':
            self.assertEqual(self.clause(self.cast(MALLORY, self.reg, 'promote', [('text', 'now checked')])), 'anchor')

    def test_nobody_reprograms_it_once_a_row_stands_its_owner_included(self):
        version = self.state(self.reg)['version']
        laid = self.town.send(op='world-reprogram', principal=HY3, identity='owner-extend', object=self.reg, version=version,
                              mode='extend', package=BURY)
        self.assertEqual((laid['status'], self.clause(laid)), ('refused', 'sealed'), laid)

    def test_one_dispute_a_hand_a_row_each_with_its_own_anchor(self):
        target = self.number(self.row(HY3, self.reg, 'snag', on=self.entry, evidence='testimony', anchor=ENTRY_001, text='who keeps the tag honest?'))
        first = self.row(MALLORY, self.reg, 'dispute', on=target, evidence='lead', anchor=GEMINI_8, text='it is solved already')
        self.assertEqual(first['status'], 'admitted', first)
        again = self.row(MALLORY, self.reg, 'dispute', on=target, evidence='lead', anchor=GEMINI_8, text='solved, I said')
        self.assertEqual((again['status'], self.clause(again)), ('refused', 'again'), again)
        bare = self.row(GEMINI, self.reg, 'dispute', on=target, evidence='testimony', anchor='no', text='a dispute without anchor')
        self.assertEqual(self.clause(bare), 'anchor', bare)

    def test_a_resolution_links_to_its_snag_and_the_snag_stays(self):
        snag = self.number(self.row(HY3, self.reg, 'snag', on=self.entry, evidence='testimony', anchor=ENTRY_001, text='does resolved shrink the archive?'))
        voice = self.number(self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=GEMINI_8, text='a voice'))
        self.assertEqual(self.clause(self.row(GEMINI, self.reg, 'resolve', on=voice, evidence='testimony', anchor=GEMINI_8)), 'notSnag')
        offered = self.row(GEMINI, self.reg, 'resolve', on=snag, evidence='testimony', anchor=GEMINI_8, text='agreed: link, never erase')
        self.assertEqual(offered['status'], 'admitted', offered)
        page = lambda: self.told(self.cast(MEITAN, self.reg, 'more', [('n', self.entry), ('from', snag)]))
        self.assertIn(f'#{snag} SNAG testimony (a resolution offered, unchecked; open)', page())
        closed = self.row(HY3, self.reg, 'resolve', on=snag, evidence='checked', anchor=f'{ENTRY_001} {ENTRY_001_CID}', text='premise')
        self.assertEqual(closed['status'], 'admitted', closed)
        page = page()
        self.assertIn(f'#{snag} SNAG testimony (resolved by a checked row; it stays)', page)
        self.assertIn('does resolved shrink the archive?', page)

    def test_an_entry_of_testimony_alone_wants_a_check_until_one_is_written(self):
        asked = self.number(self.row(MEITAN, self.reg, 'ask', anchor=GEMINI_8, text='how to keep guessing games blind?'))
        self.assertNotIn('check', self.wants(self.reg))
        said = self.number(self.row(MEITAN, self.reg, 'failed', on=asked, evidence='testimony', anchor=GEMINI_8, text='disclosure flags it; cannot undo it'))
        self.assertIn('check', self.wants(self.reg))
        self.assertIn(f' {asked} ', self.told(self.cast(GEMINI, self.reg, 'unchecked')))
        self.row(GEMINI, self.reg, 'recheck', on=said, evidence='checked', anchor=f'{GEMINI_8} {GEMINI_8_CID}', text='reproduced')
        self.assertNotIn(f' {asked} ', self.told(self.cast(GEMINI, self.reg, 'unchecked')))


class Escapes(Register, unittest.TestCase):
    """The two hands the law cannot hold, each journaled: the owner's amendment of their own register's law (the
    metarule: a law admits its owner's amendment, docs/LAW.md section 1) and the opener's root edit."""

    def setUp(self):
        self.setUpTown(self.addCleanup)
        made = self.cast(MALLORY, 'kind/register', 'make')
        self.reg = re.search(r'\b(register/\d+)', self.told(made)).group(1)
        self.entry = self.number(self.row(HY3, self.reg, 'ask', anchor=ENTRY_001, text='a question'))
        self.snag = self.number(self.row(HY3, self.reg, 'snag', on=self.entry, evidence='testimony', anchor=ENTRY_001, text='an open snag'))

    def test_the_owners_amendment_is_admitted_and_journaled(self):
        """The owner's way out, whole: amend the law (admitted by the metarule), then lay code that retracts a row (no
        longer sealed), then bury the snag. Each step is an entry of its own; the amendment's receipt holds the old
        law and the new."""
        version = self.state(self.reg)['version']
        refused = self.town.send(op='world-reprogram', principal=MALLORY, identity='bury-early', object=self.reg, version=version,
                                 mode='extend', package=BURY)
        self.assertEqual(self.clause(refused), 'sealed', refused)
        law = self.town.send(op='world-inspect', principal=MALLORY, object=self.reg)['law']
        bare = '\n'.join(line for line in law.split('\n') if not line.startswith('law kept') and 'under "kind/register"' not in line)
        amended = self.town.send(op='world-amend', principal=MALLORY, identity='bury-amend', object=self.reg, version=version, law=bare)
        self.assertEqual(amended['status'], 'admitted', amended)
        change = amended['receipt']['outcome']['amendments'][0]
        self.assertIn('law kept', change['old'])
        self.assertNotIn('law kept', change['new'])
        version = self.state(self.reg)['version']
        laid = self.town.send(op='world-reprogram', principal=MALLORY, identity='bury-lay', object=self.reg, version=version,
                              mode='extend', package=BURY)
        self.assertEqual(laid['status'], 'admitted', laid)
        buried = self.town.send(op='world-turn', principal=MALLORY, object=self.reg, method='bury', identity='bury',
                                argument=record(n={'tag': 'natural', 'value': str(self.snag)}, author=label(HY3)))
        self.assertEqual(buried['status'], 'admitted', buried)
        self.assertNotIn(str(self.snag), [r['n'] for r in self.lines(self.reg)])

    def test_a_root_deletion_is_journaled_and_stops_the_register(self):
        st = self.state(self.reg, GEMINI)
        fields = st['state']['fields']
        lines = [f for f in fields if f['name'] == 'lines'][0]
        items = lines['value']['payload']['fields'][0]['value']['items']
        kept = [r for r in items if [x for x in r['fields'] if x['name'] == 'n'][0]['value']['value'] != str(self.snag)]
        lines['value']['payload']['fields'][0]['value']['items'] = kept
        root = self.town.send(op='world-root', principal=genesis.OPENER, reason='bury the snag', act={'kind': 'set', 'object': self.reg, 'field': 'state', 'value': st['state']})
        self.assertEqual(root.get('status'), 'root', root)
        self.assertEqual(root['receipt']['identity']['intent'], 'root:1', root)
        self.assertNotIn(str(self.snag), [r['n'] for r in self.lines(self.reg)])
        after = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=ENTRY_001, text='writing after a deletion')
        self.assertEqual((after['status'], self.clause(after)), ('refused', 'whole'), after)


if __name__ == '__main__':
    unittest.main()
