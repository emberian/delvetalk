"""Live measurement readers preserve transport evidence and carried wants (FOUNDATION §2, §7).

Refuted by an invalid stored timestamp crashing a read, a manual post disappearing, or a carried want losing its since.
"""
import tempfile
import unittest
from transport import measure, observe
from transport.config import Config
from transport.delve import canonical
from transport.state import State


class Measures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = State(self.tmp.name, config=Config(opener='owner'))

    def log(self, **line):
        self.st.append(self.st.hand_log, canonical({'world': 'town', 'uri': 'at://did:test:a/town.delve.feed.post/r1', **line}))

    def draft(self, name, **fields):
        self.st.write(self.st.outbox / (name + '.json'), {'text': 'rain on bell/1', **fields})

    def test_not_a_date_and_non_string_stored_timestamps_are_skipped_and_counted(self):
        ob = observe.Observer(self.st, None)
        self.addCleanup(ob.db.close)
        for n, stamp in enumerate(('not-a-date', None, 42, '2026-10-12T10:00:00Z')):
            obs = {'uri': f'local:{n}', 'cid': 'c', 'author': {'did': 'resident', 'handle': 'robin'},
                   'createdAt': stamp, 'text': 'delvetalk bell/1 tend', 'kind': 'summon'}
            ob.insert(obs, {})
        entries = [{'height': n + 1, 'identity': {'intent': f'local:{n}'}, 'outcome': {'tag': 'admitted'}} for n in range(4)]
        got = measure.measures(self.st, entries)
        self.assertEqual(got['invalidObservations'], 3)
        self.assertEqual(got['T0'], '2026-10-12T10:00:00Z')
        self.assertEqual(got['noReply'], ['local:3'])
        self.assertIn(('invalid observation timestamps', 3, 'skipped', []), measure.table(got))

    def test_both_confirmed_post_spellings_use_created_at_for_the_invitation_and_prompts(self):
        self.draft('1-invite', speak={'invitation': 0})
        for spelling in ('post', 'posted'):
            with self.subTest(spelling=spelling):
                self.st.hand_log.unlink(missing_ok=True)
                self.log(what='post-failed', draft='1-invite', at=10)
                self.log(what='post', draft='1-invite', at=20, uri=None)
                self.log(what=spelling, draft='1-invite', at=2000, createdAt='1970-01-01T00:16:40Z')
                self.log(what=spelling, world='elsewhere', draft='1-invite', at=1)
                self.assertEqual(measure.t0(self.st), 1000)
                self.assertEqual(measure.hand_posts(self.st), [(1000, 'rain on bell/1')])
                entries = [{'height': 1, 'wanted': [{'object': 'bell/1', 'want': 'rain'}]},
                           {'height': 2, 'identity': {'principal': 'resident', 'intent': 'u'},
                            'unwanted': [{'object': 'bell/1', 'want': 'rain'}]}]
                got = measure.wants(entries, {'u': 1300}, measure.hand_posts(self.st))
                self.assertEqual(len(got['prompted']), 1)
                self.assertEqual(measure.measures(self.st, [])['T0'], '1970-01-01T00:16:40Z')

    def test_a_confirmed_post_without_created_at_uses_its_log_time(self):
        self.draft('1-invite', speak={'invitation': 0})
        self.log(what='posted', draft='1-invite', at=1000)
        self.assertEqual(measure.t0(self.st), 1000)
        self.assertEqual(measure.hand_posts(self.st), [(1000, 'rain on bell/1')])

    def test_a_carried_want_keeps_entry_seven_and_uses_the_carried_clock_when_closed(self):
        entries = [{'height': 101, 'outcome': {'tag': 'carried', 'state': {'clock': 20},
                                             'index': {'wanting': {'bell/1': {'rain': 7, 'ring': 9}}}}}]
        self.assertEqual(measure.measures(self.st, entries)['clock'], 20)
        self.assertEqual(measure.wants(entries, {}, [])['ignored'], [
            {'object': 'bell/1', 'want': 'rain', 'since': 7}, {'object': 'bell/1', 'want': 'ring', 'since': 9}])
        entries += [{'height': 102, 'identity': {'principal': 'resident', 'intent': 'close'},
                     'outcome': {'tag': 'admitted'}, 'unwanted': [{'object': 'bell/1', 'want': 'rain'}]}]
        got = measure.wants(entries, {}, [(1000, 'rain on bell/1')])
        self.assertEqual(got['prompted'], [{'object': 'bell/1', 'want': 'rain', 'since': 7,
                                           'height': 102, 'by': 'resident', 'prompted': True}])
        self.assertEqual(got['ignored'], [{'object': 'bell/1', 'want': 'ring', 'since': 9}])

    def test_a_maximum_object_name_in_a_carried_want_reopens_after_a_staff_close(self):
        obj = 'b' * 128
        entries = [{'height': 101, 'outcome': {'tag': 'carried', 'state': {'clock': 20},
                                             'index': {'wanting': {obj: {'rain': 7}}}}},
                   {'height': 102, 'identity': {'principal': 'owner'}, 'unwanted': [{'object': obj, 'want': 'rain'}]},
                   {'height': 103, 'wanted': [{'object': obj, 'want': 'rain'}]},
                   {'height': 104, 'outcome': {'tag': 'advanced', 'to': 40}},
                   {'height': 105, 'identity': {'principal': 'resident'}, 'unwanted': [{'object': obj, 'want': 'rain'}]}]
        got = measure.wants(entries, {}, [(1000, obj)], lambda p: p == 'resident')
        self.assertEqual(got['prompted'], [])
        self.assertEqual(got['ignored'], [])
        self.assertEqual(got['unprompted'], [{'object': obj, 'want': 'rain', 'since': 103,
                                             'height': 105, 'by': 'resident', 'prompted': False}])
