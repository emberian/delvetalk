"""Shared submission ordering, exact temporary wire and uncertain-outcome cleanup."""
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import submission
import translate


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.portal = SimpleNamespace(database=self.directory / 'world.json', profile='transactions',
                                      _retained=Mock(return_value=None))
        self.saved = {'request': {'principal': 'author', 'intent': 'retained-intent',
            'op': 'invoke', 'object': 'table:λ', 'expected': {'version': 10 ** 90},
            'input': {'decimal': Decimal('1.2300'), 'escaped': '\n"λ'}}}
        self.pins = Mock()
        self.reply = {'kind': 'committed', 'data': {'root': {'version': 3}}}

    def execute(self, cached=None):
        return submission.execute(self.portal, self.saved, cached, self.directory, self.pins)

    def test_cached_and_world_receipts_precede_pins_and_execution(self):
        self.pins.side_effect = AssertionError('historical reply needs no current runtime')
        with patch.object(submission.worker, 'command', side_effect=AssertionError('must not execute')):
            self.assertEqual(self.execute(self.reply), (self.reply, None))
            self.portal._retained.assert_not_called()
            self.portal._retained.return_value = self.reply
            self.assertEqual(self.execute(), (self.reply, None))
            self.portal._retained.assert_called_once_with(self.saved['request'])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_lookup_and_pin_failures_are_not_submission_uncertainty(self):
        with patch.object(submission.worker, 'command', side_effect=AssertionError('must not execute')):
            self.portal._retained.side_effect = TimeoutError('custody busy')
            with self.assertRaisesRegex(TimeoutError, 'custody busy'):
                self.execute()
            self.pins.assert_not_called()
            self.portal._retained.side_effect = None
            self.pins.side_effect = ValueError('runtime changed')
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                self.execute()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_exact_wire_bounds_and_cleanup(self):
        expected = submission.canonical(self.saved['request'])
        self.assertEqual(expected, translate.canonical(self.saved['request']))

        def command(arguments, timeout):
            self.pins.assert_called_once_with(self.saved)
            self.assertEqual(arguments[:-1], [str(ROOT / 'scripts/world.py'), '--profile',
                                              'transactions', str(self.portal.database)])
            self.assertEqual(timeout, 20)
            path = Path(arguments[-1])
            self.assertEqual(path.parent, self.directory)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_bytes(), expected)
            return self.reply

        with patch.object(submission.worker, 'command', side_effect=command):
            self.assertEqual(self.execute(), (self.reply, None))
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assertEqual(submission.canonical(self.saved['request']), expected)

    def test_uncertain_errors_preserve_request_and_remove_temporary_files(self):
        original = submission.canonical(self.saved)
        for error in (RuntimeError('private details'), ValueError('private details'),
                      OSError('private details'), subprocess.TimeoutExpired('world.py', 20)):
            with self.subTest(error=type(error).__name__):
                with patch.object(submission.worker, 'command', side_effect=error):
                    self.assertEqual(self.execute(), (None, type(error).__name__))
                self.assertEqual(list(self.directory.iterdir()), [])
                self.assertEqual(submission.canonical(self.saved), original)
        with patch.object(submission, 'canonical', side_effect=ValueError('encoding failed')), \
                patch.object(submission.worker, 'command') as command:
            self.assertEqual(self.execute(), (None, 'ValueError'))
            command.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_interrupt_propagates_and_cleans_temporary_request(self):
        with patch.object(submission.worker, 'command', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
