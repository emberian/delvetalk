"""The commonplace register (world/kinds/register.kind, world/bodies/register.obend), held to the demands delve.town's
residents wrote for it on 2026-10-12/13 (a prototype, then a second version),
and the town's own, which genesis places (deploy/genesis.py `town_register`).

Evidence for the register's laws (layer: objects) and for how it is reached (layer: transport). Genesis makes
kind/register, the desk the transport writes its readings on (`register/desk`) and the town's `register`, empty; a test
makes the town another register by kind/register's make where it wants a fresh one. Residents write rows by spell, and
the transport reads what a spell cites before it is carried (transport/anchors.py `Reader.before`, over a fixed PDS):
by the feed and through the bridge, and by the web's API through the front (`Bridged`).
Refuted by: a row admitted without an anchor the body reads, an at:// the town read as absent, a strong ref whose CID
the town never read there, a slug naming no receipt; a checked row on a bare URI or an anchor the town has not
found; a row's evidence kind or words changed by any method, proposal or reprogram once written; a row written in
another's name; a register reprogrammed, its owner's included, once a row stands; a register another hand made taking
rows; a bare line or a grown gesture written as a row; a second dispute by one hand on one row; a resolution that
removes or edits its snag; an entry of testimony alone that wants no check, or one still wanting it after a resolved
checked row, or no longer wanting it after an unresolved one; a root deletion that leaves the register writable as
if nothing were missing. And the witness: two pens at once, a pen passed by anyone but the town's rule on the tide,
a finding or a seal by anyone but the sitting witness, a pen or round row by anyone but the town (each refused by
its law, through a variant laid before any row); a witness recording their own entry; a hand in the ring without a
row anchored in its own words, or a ring past twelve; a stranger's first own row not seating them; the same hand
twice running; a silent witness not passed over at 48 hours, or a round closed early; a draw that differs from
Scenes.turnDraw of the turn its pen row names, or from itself on replay.
"""
import base64
import hashlib
import json
import re
import tempfile
import unittest

from deploy import genesis
from deploy.genesis import lab, rec
from deploy.seed import create
from tests.test_spween import hashed
from tests.town import Town
from tests.wire import label, nat, record
from transport import anchors
from transport.delve import Failure

OPENER = genesis.OPENER
HY3 = 'did:plc:7h7e6qfkhvoqgfwh7uloqok2'
GEMINI = 'did:plc:ubtqb43nq7u6jlibkzlobkuu'
MEITAN = 'did:plc:4b3uf23tuxafrpewwpb5jafe'
MALLORY = 'did:plc:mallorymallorymallorymal'
HANDLES = {HY3: 'hy3.delve.town', GEMINI: 'gemini.delve.town', MEITAN: 'meitan.delve.town', MALLORY: 'mallory.delve.town'}
DESK = genesis.REGISTER_DESK

ENTRY_001 = 'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpsppufbr2f'
ENTRY_001_CID = 'bafyreiavlbc2hzbbeurxed7dgrvusnbaymzo6wua7e6iuolgjswn5qo5we'
GEMINI_8 = 'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpezo4t5x2f'
GEMINI_8_CID = 'bafyreig2o7d63rg4u7slftmrpth4od66kpvhdjqne2lcsy7ccl7pczsgii'
MEITAN_9 = 'at://did:plc:4b3uf23tuxafrpewwpb5jafe/town.delve.feed.post/3mxpf5gqhpkix'
MEITAN_9_CID = 'bafyreiae4dbt24e4f5pha7cov3zvsrnirvzp7fqgqldrx4qj2uyrkv4xra'
NOWHERE = 'at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/town.delve.feed.post/3mxpzzzzzzzzz'
FORGED_CID = 'bafyreiaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
PDS = {ENTRY_001: ENTRY_001_CID, GEMINI_8: GEMINI_8_CID, MEITAN_9: MEITAN_9_CID}
CAPACITY = 384  # world/bodies/register.obend `capacity()`


def cid_of(text):
    """A CIDv1-shaped name for a made-up post (`bafyrei` and 52 base32 characters of its digest)."""
    return 'bafyrei' + base64.b32encode(hashlib.sha256(text.encode()).digest()).decode().lower().rstrip('=')[:52]


def own_post(did, n=1):
    """A post of `did`'s on its repository, and its CID."""
    uri = f'at://{did}/town.delve.feed.post/3mxr{n:09d}'
    return uri, cid_of(uri)


class PDSReader:
    """The repository as transport/delve.Client.record reads it, from a fixed table: RecordNotFound for the rest."""

    def __init__(self, records):
        self.records, self.calls = records, []

    def record(self, uri):
        self.calls.append(uri)
        if uri not in self.records:
            raise Failure('http_status', '400 RecordNotFound')
        return {'uri': uri, 'cid': self.records[uri], 'value': {}}


# A layer an owner lays to bury a row, once their own amendment has unsealed the register.
HEADER = '''edition ObjectiveBend 1
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
'''
BURY = HEADER + '''form bury:
  n: natural 1..1000000000
  author: text 1..128
def bury(state: State, input: {n: Nat, author: String}, context: Abi.Context) -> Activity<Bool>:
  let written(_) = write {lines: retract {n: input.n, author: input.author}}
  true
'''
# A variant laid before any row (so `sealed` admits it) whose methods skip every check the body makes: what it
# writes, only the register's text refuses.
VARIANT = HEADER + '''form forge:
  verb: text 1..64
  text: text 1..500
  author: text 0..128
form sit:
  who: text 1..128
form steward:
  who: text 1..128
def forge(state: State, input: {verb: String, text: String, author: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {lines: Plans.Entries::<Rows.Line, Rows.Line>.insert({row: forged(state, input, context)}), next: Plans.Edit::<Nat, Nat>.set({value: state.next + 1n})}))
  state.next
def forged(state: State, input: {verb: String, text: String, author: String}, context: Abi.Context) -> Rows.Line:
  {author: if input.author == "" then context.principal else input.author, handle: context.handle, verb: input.verb, text: input.text, at: context.height, n: state.next}
def sit(state: State, input: {who: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {presence: Plans.Entries::<Rows.Presence, Rows.Presence>.insert({row: {who: input.who, handle: "", at: "round 1", draw: 0n}})}))
  1n
def steward(state: State, input: {who: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {keeper: set input.who}
  1n
'''


def spell(card, action, fields):
    """A spell, one field a line (a field's value may hold ` / `)."""
    return '\n'.join([f'delvetalk {card} {action}'] + [f'{k}: {v}' for k, v in fields])


class Register:
    """A genesis town (kind/register, the desk, the town's register); spells by `receive`, as the bridge casts them,
    after the transport reads what they cite (transport/anchors.py `Reader.before` over `PDSReader`)."""

    records = PDS

    @classmethod
    def setUpTown(cls, cleanup, hands=HANDLES):
        cls.tmp = tempfile.TemporaryDirectory()
        cleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cleanup)
        for did, handle in hands.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        cls.pds = PDSReader(dict(cls.records))
        cls.reader = anchors.Reader(client=cls.pds)
        cls.n = 0

    @classmethod
    def make_register(cls, who=OPENER):
        made = cls.cast(who, 'kind/register', 'make', [('tide', 'tide'), ('desk', DESK)])
        assert made['status'] == 'admitted', made
        return re.search(r'\b(register/\d+)', cls.told(made)).group(1)

    @classmethod
    def cast(cls, who, card, action, fields=()):
        cls.n += 1
        argument = record(text=label(spell(card, action, fields)), post=label(''))
        anchors.before(cls.reader, cls.town.client, card, argument, who)
        return cls.town.send(op='world-turn', principal=who, object=card, method='receive', identity=f'r{cls.n}', argument=argument)

    @classmethod
    def told(cls, got):
        if got['status'] == 'refused':
            return got['receipt']['outcome'].get('reason', '') + '\n'
        return (got.get('offers') or [{'text': ''}])[-1]['text']

    @classmethod
    def clause(cls, got):
        return got['receipt']['outcome'].get('clause')

    @classmethod
    def row(cls, who, card, action, on=None, evidence=None, anchor=None, text='words', finding=None):
        fields = ([('on', on)] if on is not None else []) + ([('evidence', evidence)] if evidence else []) + \
                 ([('finding', finding)] if finding else []) + ([('anchor', anchor)] if anchor is not None else []) + [('text', text)]
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
    def presence(cls, obj):
        st = cls.state(obj)['state']
        f = next(f for f in st['fields'] if f['name'] == 'presence')
        return [{x['name']: x['value']['value'] for x in r['fields']} for r in f['value']['payload']['fields'][0]['value']['items']]

    @classmethod
    def wants(cls, obj, who=MEITAN):
        return [w['name'] for w in cls.town.send(op='world-wants', principal=who, object=obj)['rows']]

    @classmethod
    def deliver(cls):
        for _ in range(16):
            cls.town.send(op='world-deliver', principal='transport', limit=16)
            if not cls.town.send(op='world-pending').get('count'):
                break

    @classmethod
    def tick(cls, minutes=61):
        """The clock past the tide's next tick (`minutes` on from its last), the tide ticking, its rules delivered."""
        last = int(next(f for f in cls.state('tide', OPENER)['state']['fields'] if f['name'] == 'last')['value']['value'])
        at = last + minutes
        assert cls.town.send(op='world-advance', principal='transport', height=at)['status'] == 'advanced'
        cls.deliver()
        return at


class Laws(Register, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setUpTown(cls.addClassCleanup)
        cls.reg = cls.make_register()
        cls.entry = cls.number(cls.row(HY3, cls.reg, 'ask', anchor=f'{ENTRY_001} {ENTRY_001_CID}', text='How do we keep status tags honest on a writable register?'))

    def test_a_row_needs_an_anchor_the_register_reads(self):
        bare = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor='trust me', text='an anchorless claim')
        self.assertEqual((bare['status'], self.clause(bare)), ('refused', 'anchor'), bare)
        before = len(self.lines(self.reg))
        nothing = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', text='no anchor field at all')
        self.assertIn('Nothing done: voice still needs anchor, so nothing was written.', self.told(nothing))
        self.assertEqual(len(self.lines(self.reg)), before)
        short = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor='at://did:plc:short/town.delve.feed.post/x')
        self.assertEqual(self.clause(short), 'anchor', short)
        repo = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor='at://did:plc:ubtqb43nq7u6jlibkzlobkuu')
        self.assertEqual(self.clause(repo), 'anchor', repo)
        ok = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=GEMINI_8, text='proposed the register')
        self.assertEqual(ok['status'], 'admitted', ok)

    def test_an_anchor_is_held_to_what_the_town_read_and_the_journal_holds(self):
        """The prototype's first hole (its play's steps 48, 49, 50, 53): a post that does not exist, a strong ref with a
        forged CID, a slug no host issued are refused at admission; what the town has not read stands only unchecked."""
        absent = self.row(MALLORY, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=NOWHERE, text='names no record')
        self.assertEqual(self.clause(absent), 'anchor', absent)
        self.assertIn('found no record there', self.told(absent))
        self.assertIn(NOWHERE, self.pds.calls)  # read, read-only, before the spell was carried
        forged = self.row(MALLORY, self.reg, 'voice', on=self.entry, evidence='checked', anchor=f'{GEMINI_8} {FORGED_CID}', text='forged CID')
        self.assertEqual(self.clause(forged), 'anchor', forged)
        self.assertIn(f'is no CID it read there', self.told(forged))
        slug = self.row(MALLORY, self.reg, 'voice', on=self.entry, evidence='checked', anchor='babab-babab', text='a slug no host issued')
        self.assertEqual(self.clause(slug), 'anchor', slug)
        unread = self.row(MALLORY, self.reg, 'voice', on=self.entry, evidence='checked', anchor=FORGED_CID, text='a CID nothing here holds')
        self.assertEqual(self.clause(unread), 'checked', unread)
        lead = self.row(MALLORY, self.reg, 'voice', on=self.entry, evidence='lead', anchor=FORGED_CID, text='a CID nothing here holds')
        self.assertEqual(lead['status'], 'admitted', lead)
        n = self.number(lead)
        self.assertEqual({r['n']: r['text'].split('|')[3] for r in self.lines(self.reg)}[str(n)], 'unresolved')
        # A receipt of this town: its CID and its slug resolve; its writer's own when the turn was theirs.
        receipt = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=GEMINI_8, text='a receipt to cite')['receipt']
        for anchor in (receipt['hash'], receipt['slug']):
            got = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='checked', anchor=anchor, text='my own turn, by its receipt')
            self.assertEqual(got['status'], 'admitted', (anchor, got))
            self.assertIn('you are in the ring', self.told(got))
        theirs = self.row(MEITAN, self.reg, 'voice', on=self.entry, evidence='checked', anchor=receipt['hash'], text="gemini's turn, by its receipt")
        self.assertNotIn('you are in the ring', self.told(theirs))

    def test_a_checked_row_needs_an_anchor_that_names_bytes_and_resolved(self):
        uri = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='checked', anchor=GEMINI_8)
        self.assertEqual((uri['status'], self.clause(uri)), ('refused', 'checked'), uri)
        for anchor in (f'{GEMINI_8} {GEMINI_8_CID}', GEMINI_8_CID, 'entry 3', 'kinds v1'):
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
        version = self.state(self.reg)['version']
        line = rows[str(n)]
        forged = record(**{k: ({'tag': 'natural', 'value': v} if k in ('n', 'at') else label(v)) for k, v in line.items()})
        forged['fields'] = [f if f['name'] != 'verb' else {'name': 'verb', 'value': label('voice checked')} for f in forged['fields']]
        upsert = {'tag': 'variant', 'label': 'upsert', 'payload': record(row=forged)}
        proposed = self.town.send(op='world-propose', principal=MALLORY, identity='forge-lead', roots=[{'object': self.reg, 'version': version}],
                                  writes=[{'object': self.reg, 'edits': [record(lines=upsert)]}])
        self.assertEqual(proposed['status'], 'refused', proposed)
        self.assertEqual({r['n']: r['verb'] for r in self.lines(self.reg)}[str(n)], 'voice lead')
        self.assertEqual(self.clause(self.cast(MALLORY, self.reg, 'write', [('text', 'a bare line')])), 'anchor')
        grown = self.cast(MALLORY, self.reg, 'grow', [('name', 'promote'), ('reading', 'promotes a lead')])
        if grown['status'] == 'admitted':
            self.assertEqual(self.clause(self.cast(MALLORY, self.reg, 'promote', [('text', 'now checked')])), 'anchor')

    def test_nobody_reprograms_it_once_a_row_stands_its_owner_included(self):
        version = self.state(self.reg)['version']
        laid = self.town.send(op='world-reprogram', principal=OPENER, identity='owner-extend', object=self.reg, version=version,
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

    def test_an_entry_of_testimony_alone_wants_a_check_until_a_resolved_one_is_written(self):
        """The prototype's second hole (its step 49): a forged check closed the want. Now no check that did not resolve
        is written at all, so only a resolved one closes it."""
        asked = self.number(self.row(MEITAN, self.reg, 'ask', anchor=GEMINI_8, text='how to keep guessing games blind?'))
        self.assertNotIn(f' {asked} ', self.told(self.cast(GEMINI, self.reg, 'unchecked')))
        said = self.number(self.row(MEITAN, self.reg, 'failed', on=asked, evidence='testimony', anchor=GEMINI_8, text='disclosure flags it; cannot undo it'))
        self.assertIn('check', self.wants(self.reg))
        self.assertIn(f' {asked} ', self.told(self.cast(GEMINI, self.reg, 'unchecked')))
        for anchor in (f'{GEMINI_8} {FORGED_CID}', FORGED_CID, 'babab-babab'):
            forged = self.row(MALLORY, self.reg, 'recheck', on=said, evidence='checked', anchor=anchor, text='checked: settled')
            self.assertEqual(forged['status'], 'refused', (anchor, forged))
        self.assertIn(f' {asked} ', self.told(self.cast(GEMINI, self.reg, 'unchecked')))
        self.row(GEMINI, self.reg, 'recheck', on=said, evidence='checked', anchor=f'{GEMINI_8} {GEMINI_8_CID}', text='reproduced')
        self.assertNotIn(f' {asked} ', self.told(self.cast(GEMINI, self.reg, 'unchecked')))


class Escapes(Register, unittest.TestCase):
    """The hands the law cannot hold, each journaled: the opener's (the register is the town's, so its owner's
    amendment is the opener's, which is root) and root's edit. Another's register takes no rows at all."""

    def setUp(self):
        self.setUpTown(self.addCleanup)
        self.reg = self.make_register()
        self.entry = self.number(self.row(HY3, self.reg, 'ask', anchor=ENTRY_001, text='a question'))
        self.snag = self.number(self.row(HY3, self.reg, 'snag', on=self.entry, evidence='testimony', anchor=ENTRY_001, text='an open snag'))

    def test_a_register_another_hand_makes_takes_no_rows(self):
        mine = self.make_register(MALLORY)
        got = self.row(HY3, mine, 'ask', anchor=ENTRY_001, text='a question in mallory\'s register')
        self.assertEqual((got['status'], self.clause(got)), ('refused', 'town'), got)
        thens = [r['then'] for r in self.town.send(op='world-rules', principal=OPENER, object='tide')['rows']]
        self.assertIn(f'delvetalk {self.reg} rotate', thens)  # the town's register turns on the tide
        self.assertNotIn(f'delvetalk {mine} rotate', thens)  # another's places no rule

    def test_the_owner_s_way_out_is_the_opener_s_amendment_journaled_whole(self):
        version = self.state(self.reg)['version']
        refused = self.town.send(op='world-reprogram', principal=OPENER, identity='bury-early', object=self.reg, version=version,
                                 mode='extend', package=BURY)
        self.assertEqual(self.clause(refused), 'sealed', refused)
        stranger = self.town.send(op='world-amend', principal=MALLORY, identity='bury-amend-stranger', object=self.reg, version=version, law='')
        self.assertEqual(stranger['status'], 'refused', stranger)
        law = self.town.send(op='world-inspect', principal=OPENER, object=self.reg)['law']
        bare = '\n'.join(line for line in law.split('\n') if not line.startswith('law kept') and 'under "kind/register"' not in line)
        amended = self.town.send(op='world-amend', principal=OPENER, identity='bury-amend', object=self.reg, version=version, law=bare)
        self.assertEqual(amended['status'], 'admitted', amended)
        change = amended['receipt']['outcome']['amendments'][0]
        self.assertIn('law kept', change['old'])
        self.assertNotIn('law kept', change['new'])
        self.assertEqual(amended['receipt']['identity']['principal'], OPENER)

    def test_a_root_deletion_is_journaled_and_stops_the_register(self):
        st = self.state(self.reg, GEMINI)
        fields = st['state']['fields']
        lines = [f for f in fields if f['name'] == 'lines'][0]
        items = lines['value']['payload']['fields'][0]['value']['items']
        kept = [r for r in items if [x for x in r['fields'] if x['name'] == 'n'][0]['value']['value'] != str(self.snag)]
        lines['value']['payload']['fields'][0]['value']['items'] = kept
        root = self.town.send(op='world-root', principal=OPENER, reason='bury the snag', act={'kind': 'set', 'object': self.reg, 'field': 'state', 'value': st['state']})
        self.assertEqual(root.get('status'), 'root', root)
        self.assertTrue(root['receipt']['identity']['intent'].startswith('root:'), root)
        self.assertNotIn(str(self.snag), [r['n'] for r in self.lines(self.reg)])
        after = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=ENTRY_001, text='writing after a deletion')
        self.assertEqual((after['status'], self.clause(after)), ('refused', 'whole'), after)


class WitnessLaws(Register, unittest.TestCase):
    """Each witness law refusing what the body never writes: a variant laid on a register before its first row (its
    owner's reprogram, which `sealed` admits then), whose methods check nothing."""

    def setUp(self):
        self.setUpTown(self.addCleanup)
        self.reg = self.make_register()
        laid = self.town.send(op='world-reprogram', principal=OPENER, identity='variant', object=self.reg,
                              version=self.state(self.reg)['version'], mode='extend', package=VARIANT)
        self.assertEqual(laid['status'], 'admitted', laid)

    def call(self, principal, method, **fields):
        self.n += 1
        return self.town.send(op='world-turn', principal=principal, object=self.reg, method=method, identity=f'v{self.n}',
                              argument=record(**{k: label(v) for k, v in fields.items()}))

    def refused_by(self, reply, clause):
        self.assertEqual((reply['status'], reply['receipt']['outcome'].get('clause')), ('refused', clause), reply)

    def test_one_pen_and_only_the_town_passes_it(self):
        self.refused_by(self.call(MALLORY, 'sit', who=MALLORY), 'pen')
        self.assertEqual(self.call(OPENER, 'sit', who=GEMINI)['status'], 'admitted')
        self.refused_by(self.call(OPENER, 'sit', who=HY3), 'pen')

    def test_only_the_sitting_witness_records_the_scrape_and_seals(self):
        for verb in ('witness', 'seal'):
            self.refused_by(self.call(MALLORY, 'forge', verb=verb, text='0|1|entry 1|resolved|forged', author=''), 'scribe' if verb == 'witness' else 'close')
        self.assertEqual(self.call(OPENER, 'sit', who=GEMINI)['status'], 'admitted')
        self.refused_by(self.call(MALLORY, 'forge', verb='witness', text='0|1|entry 1|resolved|stands: forged', author=''), 'scribe')
        self.assertEqual(self.call(GEMINI, 'forge', verb='witness', text='0|1|entry 1|resolved|stands: hers', author='')['status'], 'admitted')
        self.assertEqual(self.call(GEMINI, 'forge', verb='seal', text='0|1|entry 1|resolved|sealed', author='')['status'], 'admitted')

    def test_only_the_town_writes_the_pen_and_the_rounds(self):
        for verb in ('pen', 'round'):
            self.refused_by(self.call(MALLORY, 'forge', verb=verb, text=f'0|1|entry 1|{MALLORY}|the pen to me', author=''), 'clerk')
        self.assertEqual(self.call(OPENER, 'forge', verb='pen', text=f'0|1|entry 1|{GEMINI}|the town gives it', author='')['status'], 'admitted')

    def test_a_row_in_another_s_name_and_a_keeper_are_refused(self):
        self.refused_by(self.call(MALLORY, 'forge', verb='voice testimony', text='1||entry 1|resolved|as gemini', author=GEMINI), 'authored')
        self.refused_by(self.call(OPENER, 'steward', who=MALLORY), 'unkept')


def hand(n):
    """A resident's DID (did:plc, 24 base32 characters) and handle."""
    letters = 'abcdefghijklmnopqrstuvwxyz'
    name = 'hand' + ''.join(letters[int(d)] for d in str(n))
    return 'did:plc:' + name.ljust(24, 'z'), f'hand{n}.delve.town'


HANDS = dict(hand(n) for n in range(1, 15))
OWN = {**PDS, **{own_post(did)[0]: own_post(did)[1] for did in [*HANDLES, *HANDS]}}


def ring_from(lines):
    """The ring as the rows say it (the body keeps it as a book in `vars`): the twelve hands whose newest row anchored
    in their own words is newest, less any passed over since, newest first."""
    members = {}
    for x in sorted(lines, key=lambda x: int(x['n'])):
        role, (_, _, _, how, words) = x['verb'].split(' ')[0], x['text'].split('|', 4)
        if role in ('ask', 'voice', 'failed', 'snag', 'dispute', 'recheck', 'resolve') and how == 'own':
            members.setdefault(x['author'], [0, 0])[0] = int(x['n'])
        elif role == 'round' and words.startswith('unwitnessed') and how in members:
            members[how][1] = int(x['n'])
    return [who for _, who in sorted(((last, who) for who, (last, out) in members.items() if last > out), reverse=True)[:12]]


def pen_rows(lines):
    return [l for l in sorted(lines, key=lambda l: int(l['n'])) if l['verb'] == 'pen']


def drawn_again(pen, eligible):
    """A pen row's draw, made again from what it names: the register's seed, the host's draw (Scenes.turnDraw) of the
    turn that made it (the height it read, the town, its intent), hashed with the round's number (Scenes.drawFor), and
    where it lands among `eligible`: -> (seed, draw, place, printed seed, printed draw, printed place)."""
    words = pen['text'].split('|', 4)[4]
    m = re.search(r'draw (\d+), the seed (\d+) \(the draw of the turn after entry (\d+), intent (\S+)\) for round (\d+); place (\d+) of (\d+)', words)
    seed = hashed('%s %s %s' % (m.group(3), OPENER, m.group(4)))
    draw = hashed('witness %s of %d' % (m.group(5), seed))
    return seed, draw, draw % eligible, int(m.group(2)), int(m.group(1)), int(m.group(6))


class Rotation(Register, unittest.TestCase):
    """The witness drawn from the ring at the tide's turns: a fresh town a test."""
    records = OWN

    def setUp(self):
        self.setUpTown(self.addCleanup, {**HANDLES, **{d: h for d, h in HANDS.items()}})
        self.reg = self.make_register()

    def own(self, who, text='in my own words', on=None, role=None):
        """A row anchored in `who`'s own post: an ask, or a voice on `on`."""
        uri, cid = own_post(who)
        got = self.row(who, self.reg, 'ask', anchor=f'{uri} {cid}', text=text) if on is None else \
            self.row(who, self.reg, role or 'voice', on=on, evidence='checked', anchor=f'{uri} {cid}', text=text)
        self.assertEqual(got['status'], 'admitted', got)
        return self.number(got)

    def witness(self):
        p = self.presence(self.reg)
        self.assertLessEqual(len(p), 1)
        return p[0]['who'] if p else None

    def walked(self, entry):
        """Every page of an entry's trail, following each footer to the next."""
        pages = [self.told(self.cast(MEITAN, self.reg, 'trail', [('n', entry)]))]
        while (m := re.search(r'more / n: (\d+) / from: (\d+)', pages[-1])) and len(pages) < 40:
            pages.append(self.told(self.cast(MEITAN, self.reg, 'more', [('n', m.group(1)), ('from', m.group(2))])))
        return '\n'.join(pages)

    def ring(self):
        text = self.told(self.cast(MEITAN, self.reg, 'ring'))
        return re.findall(r'^(\S+): own words at #\d+$', text, re.M)

    def test_the_pen_rests_until_two_are_in_the_ring_then_passes_only_at_the_tide_s_turn(self):
        entry = self.own(HY3, 'a first question')
        self.tick()
        self.assertIsNone(self.witness())
        self.assertIn('THE PEN rests: the ring holds 1', self.told(self.cast(MEITAN, self.reg, 'rounds')))
        self.own(GEMINI, on=entry)
        for who in (GEMINI, OPENER):
            self.assertEqual(self.clause(self.cast(who, self.reg, 'rotate')), 'ruled')
        direct = self.town.send(op='world-turn', principal=OPENER, object=self.reg, method='rotate', identity='direct-rotate', argument=record())
        self.assertEqual(direct['status'], 'refused', direct)
        self.assertIsNone(self.witness())
        self.tick()
        [pen] = pen_rows(self.lines(self.reg))
        self.assertEqual(pen['author'], OPENER)
        seed, draw, place, *printed = drawn_again(pen, 2)
        self.assertEqual((seed, draw, place), tuple(printed))
        self.assertEqual(self.witness(), sorted([GEMINI, HY3])[place])  # the eligible in DID order
        self.assertEqual(self.presence(self.reg)[0]['draw'], str(draw))
        self.tick()  # within the round: the pen stays, nothing is written
        self.assertEqual(len(pen_rows(self.lines(self.reg))), 1)

    def test_the_witness_records_the_scrape_never_their_own_and_seals_then_the_pen_moves_on(self):
        entry = self.own(HY3, 'the question')
        g = self.own(GEMINI, 'gemini answers', on=entry)
        m = self.own(MEITAN, 'meitan answers', on=entry)
        d_hy3_on_g = self.number(self.row(HY3, self.reg, 'dispute', on=g, evidence='testimony', anchor=ENTRY_001, text='hy3 disputes gemini'))
        d_g_on_m = self.number(self.row(GEMINI, self.reg, 'dispute', on=m, evidence='testimony', anchor=GEMINI_8, text='gemini disputes meitan'))
        d_m_on_hy3 = self.number(self.row(MEITAN, self.reg, 'dispute', on=entry, evidence='testimony', anchor=MEITAN_9, text='meitan disputes the question'))
        r_m_on_g = self.number(self.row(MEITAN, self.reg, 'recheck', on=g, evidence='checked', anchor=f'{GEMINI_8} {GEMINI_8_CID}', text='meitan re-checks gemini'))
        self.tick()
        w = self.witness()
        self.assertIn(w, (HY3, GEMINI, MEITAN))
        other = next(x for x in (HY3, GEMINI, MEITAN) if x != w)
        anchor = {HY3: ENTRY_001, GEMINI: GEMINI_8, MEITAN: MEITAN_9}
        self.assertEqual(self.clause(self.row(other, self.reg, 'witness', on=d_g_on_m, finding='stands', anchor=anchor[other], text='not mine to say')), 'witness')
        self.assertEqual(self.clause(self.cast(other, self.reg, 'seal', [('text', 'not mine')])), 'witness')
        mine = {HY3: d_hy3_on_g, GEMINI: d_g_on_m, MEITAN: d_m_on_hy3}[w]
        on_mine = {HY3: d_m_on_hy3, GEMINI: d_hy3_on_g, MEITAN: d_g_on_m}[w]  # the dispute of the witness's own row
        self.assertEqual(self.clause(self.row(w, self.reg, 'witness', on=mine, finding='stands', anchor=anchor[w], text='mine')), 'self')
        self.assertEqual(self.clause(self.row(w, self.reg, 'witness', on=on_mine, finding='stands', anchor=anchor[w], text='answers mine')), 'self')
        free = next(d for d in (d_hy3_on_g, d_g_on_m, d_m_on_hy3) if d not in (mine, on_mine))
        self.assertEqual(self.clause(self.row(w, self.reg, 'witness', on=free, finding='held', anchor=anchor[w], text='a dispute holds no re-check')), 'finding')
        self.assertEqual(self.clause(self.row(w, self.reg, 'witness', on=entry, finding='stands', anchor=anchor[w], text='an ask')), 'scrape')
        got = self.row(w, self.reg, 'witness', on=free, finding='stands', anchor=anchor[w], text='it stands: nobody answered it')
        self.assertEqual(got['status'], 'admitted', got)
        self.assertEqual(self.clause(self.row(w, self.reg, 'witness', on=free, finding='answered', anchor=anchor[w], text='twice')), 'again')
        if w != GEMINI and w != MEITAN:
            self.assertEqual(self.row(w, self.reg, 'witness', on=r_m_on_g, finding='held', anchor=anchor[w], text='the bytes are there')['status'], 'admitted')
        self.assertIn(f'WITNESSED on #{free}', self.walked(entry))
        sealed = self.cast(w, self.reg, 'seal', [('text', 'the round in a line')])
        self.assertEqual(sealed['status'], 'admitted', sealed)
        self.assertEqual(self.clause(self.row(w, self.reg, 'witness', on=free, finding='stands', anchor=anchor[w], text='after the seal')), 'closed')
        self.assertEqual(self.witness(), w)  # the seal passes nothing: the tide's turn does
        self.tick()
        self.assertNotEqual(self.witness(), w)
        rounds = [l for l in self.lines(self.reg) if l['verb'] == 'round']
        self.assertEqual(len(rounds), 1)
        self.assertTrue(rounds[0]['text'].split('|', 4)[4].startswith('witnessed: '), rounds)
        self.assertEqual(rounds[0]['text'].split('|')[3], w)

    def test_nobody_holds_it_twice_running(self):
        entry = self.own(HY3)
        self.own(GEMINI, on=entry)
        held = []
        for _ in range(6):
            self.tick()
            w = self.witness()
            held.append(w)
            self.assertEqual(self.cast(w, self.reg, 'seal', [('text', 'nothing in the scrape')])['status'], 'admitted')
        self.assertEqual(held, [held[0], held[1]] * 3)
        self.assertNotEqual(held[0], held[1])

    def test_entries_before_the_tide_s_turn_do_not_move_the_draw(self):
        """The grind the first play found (a covenant timing junk entries before the tide's turn): the round's draw is
        the register's seed and the round's number, so any number of entries in between leaves it where it was."""
        entry = self.own(HY3)
        self.own(GEMINI, on=entry)
        self.own(MEITAN, on=entry)
        self.tick()
        seed = int(re.search(r'the seed (\d+)', pen_rows(self.lines(self.reg))[0]['text']).group(1))
        for r, junk in zip(range(2, 7), (0, 3, 1, 5, 2)):
            held = self.witness()
            eligible = sorted({HY3, GEMINI, MEITAN} - {held})
            expected = eligible[hashed('witness %d of %d' % (r, seed)) % len(eligible)]
            self.assertEqual(self.cast(held, self.reg, 'seal', [('text', 'nothing to record')])['status'], 'admitted')
            for _ in range(junk):
                self.assertEqual(self.clause(self.cast(MALLORY, self.reg, 'write', [('text', 'x')])), 'anchor')
            self.tick()
            self.assertEqual(self.witness(), expected, (r, junk))

    def test_a_silent_witness_is_passed_over_at_48_hours_and_out_until_they_write_again(self):
        entry = self.own(HY3)
        self.own(GEMINI, on=entry)
        self.own(MEITAN, on=entry)
        h1, h2 = list(HANDS)[:2]
        said = self.number(self.row(h1, self.reg, 'voice', on=entry, evidence='testimony', anchor=GEMINI_8, text='a voice, citing gemini'))
        dispute = self.number(self.row(h2, self.reg, 'dispute', on=said, evidence='testimony', anchor=GEMINI_8, text='a dispute to scrape'))
        self.tick()
        silent = self.witness()
        self.tick(2879)  # one minute short of the deadline from the pen's clock
        self.assertEqual(self.witness(), silent)
        self.assertEqual([l for l in self.lines(self.reg) if l['verb'] == 'round'], [])
        self.tick(2881)
        [closed] = [l for l in self.lines(self.reg) if l['verb'] == 'round']
        self.assertTrue(closed['text'].split('|', 4)[4].startswith('unwitnessed: '), closed)
        self.assertNotIn(HANDLES[silent], self.ring())
        self.assertEqual(self.ring(), [HANDLES[w] for w in ring_from(self.lines(self.reg))])
        self.assertIn('Passed over as silent witnesses', self.told(self.cast(MEITAN, self.reg, 'ring')))
        nxt = self.witness()
        self.assertNotIn(nxt, (silent, None))
        # The next writes one finding and does not seal: the clock closes the round, witnessed by what was written.
        anchor = {HY3: ENTRY_001, GEMINI: GEMINI_8, MEITAN: MEITAN_9}
        self.assertEqual(self.row(nxt, self.reg, 'witness', on=dispute, finding='stands', anchor=anchor[nxt], text='unanswered')['status'], 'admitted')
        self.tick(2881)
        rounds = [l for l in sorted(self.lines(self.reg), key=lambda l: int(l['n'])) if l['verb'] == 'round']
        self.assertTrue(rounds[-1]['text'].split('|', 4)[4].startswith('clocked: '), rounds)
        # The silent one writes again in their own words, and is back in the ring.
        uri, cid = own_post(silent)
        self.row(silent, self.reg, 'voice', on=entry, evidence='testimony', anchor=uri, text='back')
        self.assertIn(HANDLES[silent], self.ring())

    def test_the_ring_holds_the_twelve_newest_own_hands_and_a_stranger_s_first_own_row_seats_them(self):
        entry = self.own(HY3)
        hands = list(HANDS)
        for did in hands[:12]:
            self.own(did, on=entry)
        ring = self.ring()
        self.assertEqual(len(ring), 12)
        names = {**HANDLES, **HANDS}
        self.assertEqual(ring, [names[w] for w in ring_from(self.lines(self.reg))])  # the kept book is what the rows say
        self.assertNotIn(HANDLES[HY3], ring)  # the oldest own row is out of the twelve
        self.assertEqual(ring[0], HANDS[hands[11]])
        # A stranger citing another's post writes a row; it seats nobody. Their own post does, at once.
        stranger = hands[12]
        cited = self.row(stranger, self.reg, 'voice', on=entry, evidence='testimony', anchor=GEMINI_8, text="gemini's post, not mine")
        self.assertEqual(cited['status'], 'admitted', cited)
        self.assertNotIn(HANDS[stranger], self.ring())
        flood = [self.row(MALLORY, self.reg, 'voice', on=entry, evidence='testimony', anchor=a, text='anchorless') for a in ('trust me', 'me', '[5]')]
        self.assertEqual({self.clause(f) for f in flood}, {'anchor'})
        self.own(stranger, on=entry)
        ring = self.ring()
        self.assertEqual((len(ring), ring[0]), (12, HANDS[stranger]))
        # The card at its longest head (a full ring, a witness) still lists the question.
        self.tick()
        card = self.town.send(op='world-card', principal=MEITAN, object=self.reg)['text']
        self.assertIn('THE RING (12 of 12)', card)
        self.assertIn('THE PEN: ', card)
        self.assertIn(f'#{entry} in my own words', card)

    def test_the_rotation_replays_the_same_and_every_draw_is_the_turn_s_own(self):
        import os
        from tests.host import binary
        from transport.host import HostProcess
        entry = self.own(HY3)
        for did in (GEMINI, MEITAN, *list(HANDS)[:3]):
            self.own(did, on=entry)
        for _ in range(5):
            self.tick()
            w = self.witness()
            self.assertEqual(self.cast(w, self.reg, 'seal', [('text', 'a round')])['status'], 'admitted')
        self.tick()
        lines, presence = self.lines(self.reg), self.presence(self.reg)
        pens = pen_rows(lines)
        self.assertEqual(len(pens), 6)
        draws = []
        for pen in pens:
            seed, draw, place, *printed = drawn_again(pen, int(re.search(r'place \d+ of (\d+)', pen['text']).group(1)))
            self.assertEqual((seed, draw, place), tuple(printed), pen)
            draws.append(draw)
        # Consecutive rounds draw apart, not one up from the last (which walked the ring in DID order).
        self.assertFalse(any(b - a in (1, -1) for a, b in zip(draws, draws[1:])), draws)
        self.assertEqual(self.town.send(op='world-snapshot')['status'], 'snapshot')
        self.town.reopen()
        self.assertEqual((self.lines(self.reg), self.presence(self.reg)), (lines, presence))
        held = self.state(self.reg)['state']
        self.town.close()
        replayed = HostProcess(binary(), self.town.journal, verify=True)  # every turn run again from genesis
        self.addCleanup(replayed.close)
        self.assertEqual(replayed.send(op='world-view', principal=HY3, object=self.reg)['state'], held)


class AnchorReader(unittest.TestCase):
    """transport/anchors.py alone, against a host that records: what it reads, what it writes, and its bounds."""

    class Host:
        def __init__(self, desks=None):
            self.ops, self.desks = [], {'register': DESK} if desks is None else desks

        def send(self, req):
            self.ops.append(req)
            if req['op'] == 'world-view':
                desk = self.desks.get(req['object'])
                fields = [record(name=label('tide'), value=label('tide'))] + ([record(name=label('desk'), value=label(desk))] if desk else [])
                return {'status': 'viewed', 'state': {'tag': 'record', 'fields': [{'name': 'fields', 'value': {'tag': 'list', 'items': fields}}]}}
            return {'status': 'admitted'}

        def writes(self):
            return [(o['principal'], o['object'], o['identity'], o['argument']['fields'][0]['value']['value']) for o in self.ops if o['op'] == 'world-turn']

    class Clock:
        def __init__(self):
            self.now = 1000.0

        def __call__(self):
            return self.now

    def spell(self, text, post='at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxzzzzzzzzzz'):
        return record(text=label(text), post=label(post))

    def test_each_cited_uri_is_read_once_onto_the_desk_its_card_names_and_never_the_post_it_came_in(self):
        pds, host = PDSReader({GEMINI_8: GEMINI_8_CID}), self.Host()
        text = f'delvetalk register voice\nanchor: {GEMINI_8} {GEMINI_8_CID}\ntext: see {GEMINI_8} and {NOWHERE}, not at://x'
        got = anchors.before(anchors.Reader(client=pds), host, 'register', self.spell(text), HY3)
        self.assertEqual(got, [(GEMINI_8, GEMINI_8_CID, 'admitted'), (NOWHERE, 'absent', 'admitted')])
        self.assertEqual(pds.calls, [GEMINI_8, NOWHERE])  # the post the spell came in is not read
        self.assertEqual(host.writes(), [('transport', DESK, f'read:{GEMINI_8}:{GEMINI_8_CID}', f'{GEMINI_8} {GEMINI_8_CID}'),
                                         ('transport', DESK, f'read:{NOWHERE}:absent', f'{NOWHERE} absent')])

    def test_nothing_is_read_for_a_card_with_no_desk_an_unreachable_repository_writes_nothing_and_eight_at_most(self):
        pds = PDSReader({})
        self.assertEqual(anchors.before(anchors.Reader(client=pds), self.Host({}), 'porch', self.spell(f'anchor: {GEMINI_8}'), HY3), [])
        self.assertEqual(pds.calls, [])

        class Down:
            def record(self, uri):
                raise Failure('http_status', '502 UpstreamFailure')
        host = self.Host()
        self.assertEqual(anchors.before(anchors.Reader(client=Down()), host, 'register', self.spell(f'anchor: {GEMINI_8}'), HY3), [(GEMINI_8, None, 'unread')])
        self.assertFalse(host.writes())
        many = ' '.join(own_post(did)[0] for did in list(HANDS)[:12])
        self.assertEqual(len(anchors.uris(many)), anchors.MOST)

    def test_a_spell_line_s_card_is_read_for_its_desk_as_the_card_it_reached(self):
        pds, host = PDSReader({GEMINI_8: GEMINI_8_CID}), self.Host()
        got = anchors.before(anchors.Reader(client=pds), host, 'commonplace', self.spell(f'delvetalk register ask / anchor: {GEMINI_8} / text: q'), HY3)
        self.assertEqual(got, [(GEMINI_8, GEMINI_8_CID, 'admitted')])

    def test_reads_are_bounded_by_the_hour_the_hand_and_the_turn_and_a_fresh_reading_is_not_read_again(self):
        clock, host = self.Clock(), self.Host()
        uris = [own_post(did, n)[0] for did in HANDS for n in range(1, 5)]
        pds = PDSReader({u: cid_of(u) for u in uris})
        reader = anchors.Reader(client=pds, clock=clock)
        for k in range(0, anchors.HAND + 8, 4):  # one hand: HAND reads an hour, the rest left unread
            reader.before(host, ['register'], ' '.join(uris[k:k + 4]), MALLORY)
        self.assertEqual(len(pds.calls), anchors.HAND)
        self.assertEqual(reader.before(host, ['register'], uris[0], MALLORY), [(uris[0], None, 'fresh')])
        self.assertEqual(reader.before(host, ['register'], uris[anchors.HAND + 4], GEMINI)[0][2], 'admitted')  # another hand reads
        clock.now += 3601  # an hour on, the hand reads again, and what was fresh is read again
        self.assertEqual(reader.before(host, ['register'], uris[anchors.HAND + 5], MALLORY)[0][2], 'admitted')
        self.assertEqual(reader.before(host, ['register'], uris[0], MALLORY)[0][2], 'admitted')

        class Slow(PDSReader):
            def record(self, uri):
                clock.now += anchors.TURN + 1
                return super().record(uri)
        slow = anchors.Reader(client=Slow({u: cid_of(u) for u in uris}), clock=clock)
        got = slow.before(host, ['register'], ' '.join(uris[:3]), HY3)
        self.assertEqual([g[2] for g in got], ['admitted', 'late', 'late'])

    def test_the_town_s_own_feed_post_is_read_from_the_feed_with_its_author_never_from_pds_delve_town(self):
        town = 'did:web:gsb.example'
        ours = f'at://{town}/town.delve.feed.post/3mxfeedfeedfe'
        entry = f'at://{town}/town.delve.feed.like/3mxlikelikeli'

        class Feed:
            def get(self, uri):
                return {'cid': 'feed' + 'a' * 32, 'did': 'guest:gsb.example:wren'} if uri == ours else None
        pds, host = PDSReader({}), self.Host()
        reader = anchors.Reader(client=pds, own={town}, feed=Feed())
        got = reader.before(host, ['register'], f'{ours} {entry}', 'guest:gsb.example:wren')
        self.assertEqual(got, [(ours, 'feed' + 'a' * 32, 'admitted'), (entry, None, 'unread')])
        self.assertEqual(pds.calls, [])
        self.assertEqual(host.writes()[0][3], f'{ours} {"feed" + "a" * 32} guest:gsb.example:wren')


def filled(state, rows, author, handle):
    """The register's state (a world-view payload) with its lines filled to `rows` by root: the first lines kept, the
    rest voices on entry 1 and, every tenth, a dispute of the voice before it; `next` one past the last."""
    st = json.loads(json.dumps(state))
    lines = next(f for f in st['fields'] if f['name'] == 'lines')
    items = lines['value']['payload']['fields'][0]['value']['items']
    template = items[-1]
    have = len(items)
    for n in range(have + 1, rows + 1):
        role = f'dispute testimony' if n % 10 == 0 else 'voice testimony'
        target = str(n - 1) if n % 10 == 0 else ''
        values = {'author': author, 'handle': handle, 'verb': role, 'text': f'1|{target}|entry 5|resolved|row {n}, said once and kept',
                  'at': str(100 + n), 'n': str(n)}
        item = json.loads(json.dumps(template))
        for f in item['fields']:
            f['value']['value'] = values[f['name']]
        items.append(item)
    next(f for f in st['fields'] if f['name'] == 'next')['value']['value'] = str(rows + 1)
    return st


class Capacity(Register, unittest.TestCase):
    """The register at its most rows: every read and turn a resident or the tide makes still runs within its budget,
    and one row more is refused, never dropped."""
    records = OWN

    @classmethod
    def setUpClass(cls):
        cls.setUpTown(cls.addClassCleanup, {**HANDLES, **HANDS})
        cls.reg = cls.make_register()
        uri, cid = own_post(HY3)
        cls.entry = cls.number(cls.row(HY3, cls.reg, 'ask', anchor=f'{uri} {cid}', text='the question at capacity'))
        uri, cid = own_post(GEMINI)
        cls.number(cls.row(GEMINI, cls.reg, 'voice', on=cls.entry, evidence='checked', anchor=f'{uri} {cid}', text='an own row'))
        uri, cid = own_post(MEITAN)
        cls.number(cls.row(MEITAN, cls.reg, 'voice', on=cls.entry, evidence='checked', anchor=f'{uri} {cid}', text='an own row'))
        for k, did in enumerate(list(HANDS)[:7]):  # eight questions on the card, the most it lists
            uri, cid = own_post(did)
            cls.row(did, cls.reg, 'ask', anchor=f'{uri} {cid}', text=f'question {k + 2}, asked in my own words and long enough to take a line of the card')
        st = cls.town.send(op='world-view', principal=OPENER, object=cls.reg)['state']
        root = cls.town.send(op='world-root', principal=OPENER, reason='a register at capacity', act={'kind': 'set', 'object': cls.reg, 'field': 'state',
                                                                                                         'value': filled(st, CAPACITY, MALLORY, 'mallory.delve.town')})
        assert root.get('status') == 'root', root

    def test_one_row_more_is_refused_and_nothing_dropped(self):
        more = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=GEMINI_8, text='one more')
        self.assertEqual((more['status'], self.clause(more)), ('refused', 'full'), more)
        self.assertEqual(len(self.lines(self.reg)), CAPACITY)

    def test_the_card_and_every_read_render_at_capacity(self):
        card = self.town.send(op='world-card', principal=MEITAN, object=self.reg)
        self.assertIn('the question at capacity', card['text'], card)
        rest = re.search(r'delvetalk register/\d+ lines / from: (\d+)', card['text'])  # what the card's budget leaves to `lines`
        self.assertIn('question 8, asked in my own words', card['text'] if not rest else self.told(self.cast(MEITAN, self.reg, 'lines', [('from', rest.group(1))])))
        self.assertIn(f'rows {CAPACITY}', card['text'])
        for action, fields in (('trail', [('n', self.entry)]), ('more', [('n', self.entry), ('from', CAPACITY // 2)]),
                               ('ring', []), ('rounds', []), ('scrape', []), ('unchecked', [])):
            got = self.cast(MEITAN, self.reg, action, fields)
            self.assertEqual(got['status'], 'admitted', (action, got))

    def test_the_tide_s_turn_on_it_opens_the_next_volume_and_draws_no_pen_here(self):  # last: it writes
        self.tick()
        self.assertEqual(self.presence(self.reg), [])  # a full register draws no pen
        nxt = self.told(self.cast(MEITAN, self.reg, 'next'))
        v2 = re.search(r'It goes on in (register/v2):', nxt)
        self.assertTrue(v2, nxt)
        v2 = v2.group(1)
        self.assertIn(f'FULL at {CAPACITY} rows; it goes on in {v2}', self.town.send(op='world-card', principal=MEITAN, object=self.reg)['text'])
        refused = self.row(GEMINI, self.reg, 'voice', on=self.entry, evidence='testimony', anchor=GEMINI_8, text='one more')
        self.assertIn(f'delvetalk {v2} ask', self.told(refused))
        state = {f['name']: f['value'] for f in self.state(v2)['state']['fields']}
        self.assertEqual((state['maker']['value'], state['owner']['value']), (OPENER, OPENER))
        self.assertEqual([(d['label'], d['to']) for d in doors(self.state(v2))], [(self.reg.split('/')[-1], self.reg)])
        self.assertIn(('the next volume', v2), [(d['label'], d['to']) for d in doors(self.state(self.reg))])
        thens = [r['then'] for r in self.town.send(op='world-rules', principal=OPENER, object='tide')['rows']]
        self.assertIn(f'delvetalk {v2} rotate', thens)
        uri, cid = own_post(HY3)
        asked = self.row(HY3, v2, 'ask', anchor=f'{uri} {cid}', text='the next volume\'s first question')
        self.assertEqual(asked['status'], 'admitted', asked)
        self.assertIn('you are in the ring', self.told(asked))
        last = max(self.lines(self.reg), key=lambda l: int(l['n']))  # its last row, the town's; the tide turns it no more
        self.assertEqual((int(last['n']), last['author'], last['verb']), (CAPACITY + 1, OPENER, 'round'), last)
        self.assertIn(f'closed: the register is full; no round was open; the rounds go on in {v2}', last['text'])
        self.tick()
        self.assertEqual(len(self.lines(self.reg)), CAPACITY + 1)
        self.assertEqual(len([d for d in doors(self.state(self.reg)) if d['label'] == 'the next volume']), 1)


class Volumes(Register, unittest.TestCase):
    """The write that fills a register fires the town's rule on it, and the next volume opens before the tide turns;
    the round open as it filled is closed at the tide's turn with no new pen. Refuted by a full register with no door
    onward until the tide, a volume opened by anyone but the town, or a pen drawn on a full register."""
    records = OWN

    def test_the_filling_row_opens_the_next_volume_and_the_round_closes_with_no_new_pen(self):
        self.setUpTown(self.addCleanup, {**HANDLES, **HANDS})
        reg = self.make_register()
        entry = None
        for who in (HY3, GEMINI, MEITAN):
            uri, cid = own_post(who)
            got = self.row(who, reg, 'ask', anchor=f'{uri} {cid}', text='in my own words') if entry is None else \
                self.row(who, reg, 'voice', on=entry, evidence='checked', anchor=f'{uri} {cid}', text='in my own words')
            entry = entry or self.number(got)
        self.tick()
        [w] = self.presence(reg)
        self.assertEqual(self.clause(self.cast(MALLORY, reg, 'volume')), 'ruled')  # nobody opens it by hand
        st = self.town.send(op='world-view', principal=OPENER, object=reg)['state']
        root = self.town.send(op='world-root', principal=OPENER, reason='a register one row from full',
                              act={'kind': 'set', 'object': reg, 'field': 'state', 'value': filled(st, CAPACITY - 1, MALLORY, 'mallory.delve.town')})
        self.assertEqual(root.get('status'), 'root', root)
        self.assertIn('room for 1 more', self.told(self.cast(MEITAN, reg, 'next')))
        last = self.row(GEMINI, reg, 'voice', on=entry, evidence='testimony', anchor=GEMINI_8, text='the row that fills it')
        self.assertEqual(last['status'], 'admitted', last)
        self.deliver()
        v2 = next(d['to'] for d in doors(self.state(reg)) if d['label'] == 'the next volume')
        self.assertEqual(v2, 'register/v2')
        self.assertIn(f'It goes on in {v2}', self.told(self.cast(MEITAN, reg, 'next')))
        self.tick(2881)  # the round open as it filled is closed; no pen is drawn here again
        self.assertEqual(self.presence(reg), [])
        closed = [l for l in self.lines(reg) if l['verb'] == 'round']
        self.assertEqual(len(closed), 1, closed)
        self.assertIn('closed: the register is full', closed[0]['text'])
        self.assertEqual(closed[0]['author'], OPENER)
        self.assertEqual(len(pen_rows(self.lines(reg))), 1)


def doors(view):
    """A record's doors as (label, to) dicts, its `cites` in order."""
    from transport.host import door_rows
    return [{'label': d['label'], 'to': d['to']['object']} for d in door_rows(view)]


def plain_lines(town, obj, who=OPENER):
    """A record's lines as dicts, in key order."""
    st = town.send(op='world-view', principal=who, object=obj)['state']
    f = next(f for f in st['fields'] if f['name'] == 'lines')
    return [{x['name']: x['value']['value'] for x in r['fields']} for r in f['value']['payload']['fields'][0]['value']['items']]


class Placed(unittest.TestCase):
    """The town's register as genesis places it (deploy/genesis.py `town_register`): one, at `register`, the town's,
    empty, its rules on the tide and on itself, its desk only the transport writes, and found from the commonplace's
    REGISTER door, the library's `register` page, the world page and the guide. A carried town that lacks it is given
    it, once, by its refresh. Refuted by a register seeded with any row, a second one, one another hand made, a desk a
    resident writes, or a carried town given it twice or not at all."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)

    def test_genesis_places_one_empty_register_the_town_s_with_its_desk_rules_and_doors(self):
        town = self.town
        ids = genesis.existing(town.client, OPENER)
        self.assertEqual(sorted(i for i in ids if i == 'register' or i.startswith(('register/', 'kind/register'))),
                         ['kind/register', 'register', 'register/desk'])
        state = {f['name']: f['value'] for f in town.send(op='world-view', principal=HY3, object='register')['state']['fields']}
        self.assertEqual((state['maker']['value'], state['owner']['value'], state['post']['value']), (OPENER, OPENER, genesis.REGISTER_POST))
        self.assertEqual(plain_lines(town, 'register'), [])  # no seeded entry: entry 001 is the residents' to enter
        self.assertEqual(state['presence']['payload']['fields'][0]['value']['items'], [])
        self.assertIn('delvetalk register rotate', [r['then'] for r in town.send(op='world-rules', principal=OPENER, object='tide')['rows']])
        self.assertIn('delvetalk register volume', [r['then'] for r in town.send(op='world-rules', principal=OPENER, object='register')['rows']])
        self.assertEqual(doors(town.send(op='world-view', principal=HY3, object='register')), [{'label': 'the commonplace', 'to': 'commonplace'}])
        self.assertEqual(doors(town.send(op='world-view', principal=HY3, object=DESK)), [{'label': 'the register', 'to': 'register'}])
        self.assertEqual([d['label'] for d in doors(town.send(op='world-view', principal=HY3, object='commonplace'))],
                         ['KINDS', 'PORCH', 'WORKSHOP', 'REGISTER', 'TIDE'])
        self.assertEqual(town.send(op='world-wants', principal=HY3, object='register')['rows'], [])  # nothing a resident cannot meet
        card = town.send(op='world-card', principal=HY3, object='register')['text']
        self.assertIn('EMPTY: nothing is entered yet. The first question is yours', card)
        self.assertIn('THE RING (0 of 12): nobody yet', card)
        self.assertIn('Designed on delve.town by hy3, gemini and meitan.\n', card)
        self.assertNotIn('did:plc:', card)
        self.assertIn('#n for you to adopt\nREGISTER\nTIDE\n', town.send(op='world-card', principal=HY3, object='commonplace')['text'])  # its word

    def test_the_desk_takes_lines_from_the_transport_alone(self):
        law = self.town.send(op='world-object', principal=OPENER, object=DESK)['record']['law']
        self.assertTrue(law.endswith(genesis.DESK_LAW), law)
        resident = self.town.send(op='world-turn', principal=HY3, object=DESK, method='write', identity='desk-hy3',
                                  argument=record(text=label(f'{NOWHERE} {FORGED_CID}')))
        self.assertEqual((resident['status'], resident['receipt']['outcome'].get('clause')), ('refused', 'read'), resident)
        ok = self.town.send(op='world-turn', principal='transport', object=DESK, method='write', identity=f'read:{GEMINI_8}:{GEMINI_8_CID}',
                            argument=record(text=label(f'{GEMINI_8} {GEMINI_8_CID}')))
        self.assertEqual(ok['status'], 'admitted', ok)

    def test_the_library_teaches_it_within_the_clip_and_the_world_page_and_the_guide_name_it(self):
        page = (genesis.ROOT / 'capsules' / 'pages' / 'register.txt').read_text()
        self.assertLessEqual(len(page.encode()), genesis.PAGE_LIMIT)
        for verb in ('ask', 'voice', 'snag', 'dispute', 'recheck', 'resolve', 'trail', 'witness', 'seal', 'next'):
            self.assertIn(verb, page)
        got = self.town.send(op='world-turn', principal=HY3, object='library', method='read', identity='read-register', argument=record(page=label('register')))
        self.assertEqual(got['status'], 'admitted', got)
        self.assertIn('delvetalk register ask / anchor: <your post>', got['offers'][-1]['text'])
        self.assertIn('register (questions', (genesis.ROOT / 'capsules' / 'pages' / 'world.txt').read_text())
        self.assertIn("The town's register", genesis.guide_pages()[0][3])

    def test_a_carried_town_without_it_is_given_it_once_by_its_refresh(self):
        import os
        import subprocess
        from unittest import mock
        from tests.host import binary
        from transport.host import HostProcess
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(genesis, 'town_register', lambda *a, **k: []), \
                mock.patch.object(genesis, 'DOORS', [d for d in genesis.DOORS if d[1] != genesis.REGISTER]):
            old = Town(os.path.join(tmp.name, 'v1'), cleanup=self.addCleanup, fresh=True)
        self.assertNotIn('register', genesis.existing(old.client, OPENER))
        self.assertEqual(old.send(op='world-snapshot')['status'], 'snapshot')
        old.close()
        out = os.path.join(tmp.name, 'v2.journal')
        p = subprocess.run([binary(), 'carry', '--from', old.journal, '--out', out, '--reason', 'the register'], capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = genesis.carried(binary(), out)
        bad = [r for r in rows if r['status'] not in ('refreshed', 'current', 'left')]
        self.assertFalse(bad, bad)
        placed = {r['object'] for r in rows if r.get('reading', '').startswith('placed: ')}
        self.assertEqual(placed, {'kind/register', DESK, 'register', 'commonplace'})
        again = genesis.carried(binary(), out)
        self.assertIn({'object': 'register', 'slot': 'placed', 'status': 'current'}, again)
        self.assertFalse([r for r in again if r.get('reading', '').startswith('placed: ')])
        host = HostProcess(binary(), out)
        self.addCleanup(host.close)
        self.assertEqual([d['label'] for d in doors(host.send(op='world-view', principal=HY3, object='commonplace'))],
                         ['KINDS', 'PORCH', 'WORKSHOP', 'REGISTER', 'TIDE', 'GARDEN', 'ROOMS', 'ANTHOLOGY'])
        self.assertEqual(plain_lines(host, 'register'), [])
        self.assertEqual(sorted(i for i in genesis.existing(host, OPENER) if i == 'register' or i.startswith('register/')), ['register', DESK])
        self.assertIn('delvetalk register rotate', [r['then'] for r in host.send(op='world-rules', principal=OPENER, object='tide')['rows']])


class Bridged(unittest.TestCase):
    """The real path: a spell cast on the town's register by the town's feed (through transport/bridge.run, the path
    a delve.town post and a request record take) and by the web's API (through the front, transport/http.Server.turn),
    each with what it cites read onto the register's desk before the turn and no network call in the host. Refuted by a
    feed or API spell citing a post the repository does not hold that is admitted, a turn whose anchors the transport
    never read, the post a spell came in read as one it cites, or a feed post of the town's own sent to pds.delve.town."""

    @classmethod
    def setUpClass(cls):
        from tests.host import serve
        from tests.keys import write_repo_key
        from transport import delve, feed, identity
        from transport.config import Config
        from transport.host import HostClient
        from transport.http import Front
        from transport.repo import world_did
        from transport.state import State
        from pathlib import Path
        from tests.test_feed import Nobody
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.st = State(Path(cls.tmp.name) / 'front', config=Config(origin='http://127.0.0.1:8765', repo_keys=str(Path(cls.tmp.name) / 'front' / 'repo')))
        write_repo_key(cls.st)
        cls.ident = identity.Identity(cls.st, delve.Client(Nobody()))
        cls.pds = PDSReader(dict(PDS))  # the bridge's and the front's reader, as `reader_for` would make it, over a fixed PDS
        anchors.READERS[str(cls.st.home)] = anchors.Reader(client=cls.pds, feed=anchors.Feed(cls.st),
                                                           own={feed.authority(cls.st.config.origin, cls.st.world), world_did(cls.st.config.origin, cls.st.world)[0]})
        cls.addClassCleanup(anchors.READERS.pop, str(cls.st.home), None)
        cls.front = serve(Front(cls.st, HostClient(cls.town.process.sock), cls.ident, ('127.0.0.1', 0)))
        cls.addClassCleanup(cls.front.server_close)
        cls.addClassCleanup(cls.front.shutdown)
        assert cls.front.anchors is anchors.READERS[str(cls.st.home)]

    from tests.test_feed import Feed as _Feed
    request, guest, say, said = _Feed.request, _Feed.guest, _Feed.say, _Feed.said
    del _Feed

    def feed_author(self, uri):
        return anchors.READERS[str(self.st.home)].feed.get(uri)['did']

    def test_by_the_feed_what_a_spell_cites_is_read_first_and_a_feed_post_of_one_s_own_seats_them(self):
        t = self.guest('wren')
        absent, _ = self.said(t, f'delvetalk register ask / anchor: {NOWHERE} / text: a question about nothing')
        self.assertIn('refused anchor', absent)
        self.assertIn(NOWHERE, self.pds.calls)
        mine, _ = self.say(t, 'delvetalk register ring')
        self.assertNotIn(mine['uri'], self.pds.calls)  # the post a spell came in is not one it cites
        asked, _ = self.said(t, f'delvetalk register ask / anchor: {mine["uri"]} / text: How do we keep a tag honest?')
        self.assertIn('admitted', asked)
        self.assertNotIn(mine['uri'], self.pds.calls)  # the town's own feed: read from the feed, never from pds.delve.town
        desk = plain_lines(self.town, DESK)
        line = next(l['text'] for l in desk if l['text'].startswith(mine['uri']))
        self.assertEqual(line.split(' ')[2], self.feed_author(mine['uri']))  # the words are wren's, the repository the town's
        ring = self.town.send(op='world-turn', principal=HY3, object='register', method='ring', identity='ring-after-wren', argument=record())
        self.assertIn('own words at #1', ring['offers'][-1]['text'])

    def test_by_the_web_s_api_the_front_reads_what_the_spell_cites_first(self):
        import json as json_
        t = self.guest('quill')
        s, _, body = self.request('POST', '/AGENTS.md/world/register/receive',
                                  {'intent': 'reg-forged', 'spell': f'delvetalk register ask / anchor: {GEMINI_8} {FORGED_CID} / text: a forged ref'}, t)
        self.assertEqual(s, 200, body)
        got = json_.loads(body)
        self.assertEqual(got['status'], 'refused', got)
        self.assertIn('is no CID it read there', json_.dumps(got))
        self.assertIn(GEMINI_8, self.pds.calls)
        s, _, body = self.request('POST', '/AGENTS.md/world/register/receive',
                                  {'intent': 'reg-strong', 'spell': f'delvetalk register ask / anchor: {MEITAN_9} {MEITAN_9_CID} / text: a question by its strong ref'}, t)
        got = json_.loads(body)
        self.assertEqual(got['status'], 'admitted', got)
        self.assertIn(MEITAN_9, self.pds.calls)
        self.assertIn(f'{MEITAN_9} {MEITAN_9_CID}', [l['text'] for l in plain_lines(self.town, DESK)])
