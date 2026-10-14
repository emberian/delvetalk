"""The mending basket (world/objects/Mending.obend; docs/MENDING.md): residents report what is broken from anywhere, by
`delvetalk report <words>` or the basket's spells, by post, the web's API or the hand; a way in is confided to the
drawer, which only the town's hands read; the town answers, and the answer reaches the reporter's inbox. The hand reads
both, newest first past a cursor (`reports.json`, `hand reports`), and answers each as the town's spell.

The seeds are tonight's real reports (2026-10-14): Kestrel's block fields over HTTP stored raw, the wake that never
noted him, the law hint whose shape is not copyable; Yuè's suspicion of a forged maker, confided.

Refuted by: a report not in its reporter's own name, or one a resident's proposal writes; a status moved by anyone but
the owner; an answer that leaves the reporter's inbox empty; a fifth report in one clock hour admitted, or the sixth
refused after the hour; a confided report's words in its reply, in the public journal, in the feed's draft or readable
by another resident; a drawer that takes a filing from anyone but its basket; `delvetalk report …` read as anything but
the basket's report; a report past 2,000 characters; the poll missing a moved report or repeating one past its cursor;
an answer to a confided report drafted for Post; `report` taken as an object id.

    python3 -W ignore -m tests.run test_mending
"""
import json
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import label, record
from transport import hand, mending
from transport.state import State

OPENER = genesis.OPENER
KESTREL = 'did:plc:kestrelkestrelkestrelkes'
YUE = 'did:plc:yueyueyueyueyueyueyueyue'
MALLORY = 'did:plc:mallorymallorymallorymal'
HANDLES = {KESTREL: 'kestrel.delve.town', YUE: 'yue.delve.town', MALLORY: 'mallory.delve.town'}

BLOCK_FIELDS = ('block fields over HTTP receive stored raw, markers included: my text: <<END … END came back with '
                'the <<END and END in it')
WAKE = 'wake rows on garden/bell/2 armed for count 2; the bell reached 4 rows and my avatar holds no note'
LAW_HINT = "law NAME \"reading\": EXPR, read as a pattern: four refusals before I found the keyword; the hint is right, its shape is not copyable"
FORGED = 'phase/4 shows a maker who never made it; a relay, or a spoof? I can make it happen again'
POST = 'at://did:plc:kestrelkestrelkestrelkes/town.delve.feed.post/3mxtkestrel01'


class Basket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.dir.cleanup)
        cls.town = Town(cls.dir.name, cleanup=cls.addClassCleanup)
        for did, handle in HANDLES.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        cls.st = State(cls.town.state)  # a delve.town world: the hand's drafts wait for ember to post by hand
        cls.hand = hand.Hand(cls.st, cls.town.client, 'token')
        cls.n, cls.minute = 0, 30000000
        cls.later(0)

    @classmethod
    def later(cls, minutes=120):
        """The clock `minutes` on (each test begins in an hour no other test's reports count in); -> the minute."""
        cls.minute += minutes
        got = cls.town.send(op='world-advance', principal='transport', height=cls.minute)
        assert got.get('status') != 'error', got
        return cls.minute

    @classmethod
    def cast(cls, who, text, card=None, post='', intent=None):
        cls.n += 1
        card = card or (cls.town.send(op='spell-parse', text=text).get('spell') or {}).get('card') or text.split()[1]  # a bare card: its own
        return cls.town.send(op='world-turn', principal=who, object=card, method='receive', identity=intent or f'mend-{cls.n}',
                             argument=record(text=label(text), post=label(post)))

    @staticmethod
    def told(got):
        if got['status'] == 'refused':
            return got['receipt']['outcome'].get('reason', '')
        return (got.get('offers') or [{'text': ''}])[-1]['text']

    @staticmethod
    def clause(got):
        return (got.get('receipt') or {}).get('outcome', {}).get('clause')

    def card(self, who, card='mending'):
        return self.town.send(op='world-card', principal=who, object=card)['text']

    def reports(self, card='mending'):
        return {r['n']: r for r in mending.rows_of(self.town.client, OPENER, card)}

    def inbox(self, did):
        from transport import pages
        notes = pages.rows(pages.state_of(self.town.send(op='world-view', principal=did, object=did)).get('inbox'))
        return sorted(notes, key=lambda x: (x['at'], x['n']))

    def number(self, got):
        import re
        m = re.match(r'#(\d+) is in the basket', self.told(got))
        self.assertIsNotNone(m, got)
        return int(m.group(1))

    def test_genesis_places_the_basket_public_and_its_drawer_for_the_opener_alone(self):
        self.assertEqual(self.town.send(op='world-view', principal=KESTREL, object='mending')['status'], 'viewed')
        self.assertEqual(self.town.send(op='world-view', principal=KESTREL, object='mending/drawer')['status'], 'denied')
        self.assertEqual(self.town.send(op='world-view', principal=OPENER, object='mending/drawer')['status'], 'viewed')
        card = self.card(KESTREL)
        self.assertIn('delvetalk report <what happened>', card)
        self.assertNotIn('answer / n:', card)  # the owner's spell is offered to the owner
        self.assertIn('answer / n:', self.card(OPENER))
        self.assertLessEqual(len(card), 1400)

    def test_report_from_anywhere_is_the_baskets_report_in_the_reporters_name(self):
        self.later()
        parsed = self.town.send(op='spell-parse', text='delvetalk report ' + BLOCK_FIELDS)['spell']
        self.assertEqual((parsed['card'], parsed['action']), ('mending', 'report'), parsed)
        got = self.cast(KESTREL, 'delvetalk report ' + BLOCK_FIELDS, post=POST, intent=POST)
        self.assertEqual(got['status'], 'admitted', got)
        self.assertIs(got.get('inPublic'), True, got)
        n = self.number(got)
        r = self.reports()[n]
        self.assertEqual((r['reporter'], r['handle'], r['text'], r['status'], r['post']), (KESTREL, 'kestrel.delve.town', BLOCK_FIELDS, 'open', POST))
        # fields are the report spell's own, inline or below; the words after `/` alone are its text
        got = self.cast(KESTREL, 'delvetalk report / about: garden/bell/2 / text: ' + WAKE)
        r = self.reports()[self.number(got)]
        self.assertEqual((r['about'], r['text']), ('garden/bell/2', WAKE))
        got = self.cast(KESTREL, 'delvetalk mending report\ntext: <<END\n' + LAW_HINT + '\nEND')
        self.assertEqual(self.reports()[self.number(got)]['text'], LAW_HINT)
        self.assertIn(f"#{n} open", self.card(YUE))  # public: another resident reads it
        self.assertIn(BLOCK_FIELDS[:40], self.told(self.cast(YUE, f'delvetalk mending read / n: {n}')))

    def test_a_report_is_bounded_and_written_only_by_its_spell(self):
        self.later()
        longest = 'x' * 2000
        self.assertEqual(self.cast(MALLORY, 'delvetalk mending report\ntext: ' + longest)['status'], 'admitted')
        before = max(self.reports())
        self.assertNotEqual(self.cast(MALLORY, 'delvetalk mending report\ntext: ' + longest + 'x')['status'], 'admitted')
        self.assertEqual(max(self.reports()), before)
        taken = self.town.send(op='world-create', principal=MALLORY, identity='mend-taken', object='report',
                               source='edition ObjectiveBend 1\ndef initial() -> Nat:\n  0n\n', entry='initial', seed={'tag': 'natural', 'value': '0'})
        self.assertNotEqual(taken['status'], 'created', taken)  # `report` is no object's id: the spell reads it as the basket's
        n = max(self.reports())
        record_ = self.town.send(op='world-object', principal=OPENER, object='mending')['record']
        forged = self.town.send(op='world-propose', principal=MALLORY, identity='mend-forge',
                                roots=[{'object': 'mending', 'version': int(record_['version'])}],
                                writes=[{'object': 'mending', 'edits': [record(next={'tag': 'variant', 'label': 'add', 'payload': record(value={'tag': 'natural', 'value': '1'})})]}])
        self.assertNotEqual(forged.get('status'), 'admitted', forged)
        refused = self.cast(MALLORY, f'delvetalk mending answer / n: {n} / status: fixed / text: mine now')
        self.assertEqual((refused['status'], self.clause(refused)), ('refused', 'notOwner'), refused)
        self.assertEqual(self.reports()[n]['status'], 'open')

    def test_four_an_hour_from_one_hand_then_the_next_hour(self):
        start = self.later()
        for i in range(4):
            self.assertEqual(self.cast(YUE, f'delvetalk report the porch lamp flickers, the {i}th time')['status'], 'admitted')
        fifth = self.cast(YUE, 'delvetalk report the porch lamp flickers again')
        self.assertEqual((fifth['status'], self.clause(fifth)), ('refused', 'tooMany'), fifth)
        self.assertIn(f'clock {start + 60}', self.told(fifth))
        self.assertEqual(self.cast(KESTREL, 'delvetalk report another hand is not paced by Yue')['status'], 'admitted')
        self.later(60)
        self.assertEqual(self.cast(YUE, 'delvetalk report the porch lamp flickers after the hour')['status'], 'admitted')

    def test_the_towns_answer_moves_the_status_and_reaches_the_reporters_inbox(self):
        self.later()
        n = self.number(self.cast(KESTREL, 'delvetalk report ' + WAKE, post=POST + 'w', intent=POST + 'w'))
        before = len(self.inbox(KESTREL))
        got = self.hand.answer_report('mending', n, 'fixed', 'the wake counts rows now; your avatar is noted at the count')
        self.assertEqual(got['outcome'], 'admitted', got)
        r = self.reports()[n]
        self.assertEqual((r['status'], r['by'], r['answer']), ('fixed', OPENER, 'the wake counts rows now; your avatar is noted at the count'))
        notes = self.inbox(KESTREL)
        self.assertEqual(len(notes), before + 1, notes)
        self.assertIn(f"basket's #{n} is fixed", notes[-1]['text'])
        # on delve.town the answer waits in the hand's outbox, under the post the report came by, for ember to post by hand
        _, d = self.hand.draft(got['drafted'])
        self.assertEqual((d['replyTo'], d['posted']), (POST + 'w', False), d)
        self.assertIn('kestrel.delve.town: your report', d['text'])
        again = self.hand.answer_report('mending', n, 'fixed', 'the wake counts rows now; your avatar is noted at the count')
        self.assertEqual((again['height'], again['drafted']), (got['height'], got['drafted']))  # one answer, one turn

    def test_a_confidence_is_filed_in_the_drawer_and_said_nowhere_public(self):
        self.later()
        got = self.cast(YUE, 'delvetalk mending confide / about: phase/4 / text: ' + FORGED)
        self.assertEqual(got['status'], 'admitted', got)
        self.assertIs(got.get('inPublic'), False, got)  # so the front drafts nothing of it for the town (http.Front.draft_turn)
        self.assertNotIn('phase/4', self.told(got))
        self.assertNotIn(FORGED[:30], json.dumps(got.get('offers')))  # what any reply shows; the receipt is the reporter's own
        drawer = self.reports('mending/drawer')
        n = max(drawer)
        self.assertEqual((drawer[n]['reporter'], drawer[n]['text'], drawer[n]['about']), (YUE, FORGED, 'phase/4'))
        self.assertNotIn(FORGED[:30], json.dumps(self.town.send(op='world-entries', principal='anonymous', after=0, limit=1000)))
        self.assertNotIn(FORGED[:30], json.dumps(self.town.send(op='world-entries', principal=MALLORY, after=0, limit=1000)))
        self.assertNotIn(FORGED[:30], self.card(MALLORY))
        self.assertIn(FORGED[:30], self.told(self.cast(YUE, 'delvetalk mending mine')))  # the reporter reads their own back
        self.assertNotIn(FORGED[:30], self.told(self.cast(MALLORY, 'delvetalk mending mine')))
        # the drawer takes a filing from its basket alone, and no direct report
        direct = self.cast(MALLORY, 'delvetalk mending/drawer report / text: let me in', card='mending/drawer')
        self.assertNotEqual(direct['status'], 'admitted', direct)
        self.assertEqual(n, max(self.reports('mending/drawer')))
        # answered as a turn, never drafted; the reporter is told without the words
        before = len(self.inbox(YUE))
        answered = self.hand.answer_report('mending/drawer', n, 'answered', 'a relay: the maker field is the creating principal')
        self.assertEqual((answered['outcome'], answered['drafted']), ('admitted', None), answered)
        notes = self.inbox(YUE)
        self.assertEqual(len(notes), before + 1)
        self.assertIn(f'your confided report #{n} is answered', notes[-1]['text'])
        self.assertEqual(self.reports('mending/drawer')[n]['status'], 'answered')

    def test_the_poll_is_newest_first_past_its_cursor_and_the_web_face_serves_it(self):
        self.later()
        first = self.hand.reports()
        cursor = first['cursor']
        self.assertEqual(first['reports'], sorted(first['reports'], key=lambda r: (r['moved'], r['card'], r['n']), reverse=True))
        self.assertEqual(self.hand.reports(cursor)['reports'], [])
        n = self.number(self.cast(KESTREL, 'delvetalk report the station clock stopped at 3:10'))
        moved = self.hand.reports(cursor)
        self.assertEqual([(r['card'], r['n']) for r in moved['reports']], [('mending', n)])
        self.hand.answer_report('mending', n, 'seen')
        seen = self.hand.reports(moved['cursor'])
        self.assertEqual([(r['card'], r['n'], r['status']) for r in seen['reports']], [('mending', n, 'seen')])
        code, body, headers = self.hand.handle('GET', f"/hand/town/reports.json?since={cursor}", given='token')
        self.assertEqual((code, dict(headers).get('Content-Type')), (200, 'application/json'))
        self.assertEqual([r['n'] for r in json.loads(body)['reports']], [n])
        self.assertEqual(self.hand.handle('GET', '/hand/town/reports.json', given='wrong')[0], 404)
        code, page, _ = self.hand.handle('GET', '/hand/town/reports', given='token')
        self.assertEqual(code, 200)
        self.assertIn('the station clock stopped', page)
        code, _, headers = self.hand.handle('POST', '/hand/town/reports/answer', given='token',
                                            form={'card': 'mending', 'n': str(n), 'status': 'wontfix', 'text': 'the station keeps no clock'})
        self.assertEqual(code, 303)
        self.assertEqual(self.reports()[n]['status'], 'wontfix')


if __name__ == '__main__':
    unittest.main()
