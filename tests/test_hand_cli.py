"""`python3 -m transport hand <verb> [sub-verb ...]`: every verb parses to itself and dispatches.

`hand requests` and `hand reports` each named their positional sub-verb `verb`, the dest the hand's own subparsers
write the command into, so the sub-verb (or its absence, None) replaced the command and dispatch raised `KeyError:
None` (found on both towns at the edition-20 carry, 2026-10-14). These parse every hand verb through the real parser
and run each sub-verb's dispatch against a stand-in Hand, so a positional that shadows the command fails here first."""
import argparse
import io
import unittest
from unittest import mock

from transport import hand
from transport.__main__ import parser

CLAIMED = {'command', 'verb', 'rverb', 'state', 'world', 'json'}  # the dests the command line itself fills


def subparsers(p):
    return next(a for a in p._actions if isinstance(a, argparse._SubParsersAction)).choices


def hand_verbs():
    """{verb: its parser}, `root`'s verbs as `root <verb>`."""
    verbs = dict(subparsers(subparsers(parser())['hand']))
    for name, p in subparsers(verbs.pop('root')).items():
        verbs['root ' + name] = p
    return verbs


class Dests(unittest.TestCase):

    def test_no_verb_has_an_argument_writing_a_dest_the_command_line_fills(self):
        for verb, p in hand_verbs().items():
            own = [a.dest for a in p._actions if a.dest in CLAIMED - {'json', 'state', 'world'}]
            self.assertEqual(own, [], f'hand {verb}: an argument writes {own}, which names the verb')


class Dispatch(unittest.TestCase):
    """Each sub-verb, parsed by the real parser, reaches the Hand method it names."""

    def run_hand(self, *argv):
        a = parser().parse_args(['hand', *argv, '--state', '/nonexistent'])
        fake = mock.MagicMock(name='Hand')
        for method in ('requests', 'request', 'reports', 'answer_report', 'automod', 'automod_review', 'slow'):
            getattr(fake, method).return_value = {'ok': method}
        with mock.patch.object(hand, 'Hand', return_value=fake):
            code = hand.command(mock.MagicMock(name='State'), a, io.StringIO(), host=mock.MagicMock(name='host'))
        self.assertEqual(code, 0, argv)
        return a, fake

    def test_requests_alone_lists_what_waits(self):
        a, h = self.run_hand('requests')
        self.assertEqual(a.verb, 'requests')
        h.requests.assert_called_once_with()
        h.request.assert_not_called()

    def test_each_requests_sub_verb_acts_on_its_line(self):
        for sub, kind, obj in (('admit', 'line', 'register'), ('decline', 'line', 'register'), ('adopt', 'proposal', 'workshop'),
                               ('repair', 'stranded', 'kinds')):
            a, h = self.run_hand('requests', sub, obj, '3', '--kind', kind, '--reading', 'why')
            self.assertEqual(a.verb, 'requests')
            h.request.assert_called_once_with(kind, sub, obj, 3, 'why')

    def test_reports_alone_reads_since_the_cursor(self):
        a, h = self.run_hand('reports', '--since', '7')
        self.assertEqual(a.verb, 'reports')
        h.reports.assert_called_once_with(7, None, 200)

    def test_reports_answer_answers_one_report(self):
        a, h = self.run_hand('reports', 'answer', 'mending', '2', '--status', 'fixed', '--text', 'mended')
        self.assertEqual(a.verb, 'reports')
        h.answer_report.assert_called_once_with('mending', 2, 'fixed', 'mended')

    def test_automod_alone_lists_and_with_a_verdict_reviews(self):
        _, h = self.run_hand('automod')
        h.automod.assert_called_once_with(None)
        for verdict in ('restore', 'confirm', 'hide'):
            a, h = self.run_hand('automod', verdict, 'k1', '--reading', 'r')
            self.assertEqual(a.verb, 'automod')
            h.automod_review.assert_called_once_with('k1', verdict, 'r')

    def test_slow_on_and_off(self):
        for switch, on in (('on', True), ('off', False)):
            a, h = self.run_hand('slow', switch, '--reading', 'r')
            self.assertEqual(a.verb, 'slow')
            h.slow.assert_called_once_with(on, 'r')


if __name__ == '__main__':
    unittest.main()
