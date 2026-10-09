"""Presentation quotas cannot strand a retained native account receipt."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import agent_heaps


class AccountReceiptCustody(unittest.TestCase):
    def test_execute_and_retry_need_no_derived_draft_write(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        alice = {'accountId': 'a' * 32, 'did': 'did:plc:' + 'a' * 24}
        def manager_for():
            return agent_heaps.HeapManager(home / 'accounts', home / 'shared.json', max_active=1)
        with manager_for() as manager:
            card = manager.encounter(alice, 'private', 'notebook')
            initial = manager.inspect(alice, 'private', 'notebook')
            self.assertEqual(initial['law']['read'], [alice['did']])
            self.assertEqual(initial['law']['invoke']['note'], [alice['did']])
            draft = manager.prepare(alice, 'private', {'card': card['card'],
                'action': next(action['id'] for action in card['actions'] if action['command'] == 'note'),
                'fields': {'thought': 'Keep this once.'}})
            files = list(manager.root.glob('*/encounters/private/drafts/' + draft['draft'] + '.json'))
            self.assertEqual(len(files), 1)
            retained_draft = files[0].read_bytes()
            with patch.object(manager, '_save_encounter', side_effect=agent_heaps.HeapLimit('encounter full')):
                first = manager.execute(alice, 'private', {'draft': draft['draft']})
                self.assertEqual(first['kind'], 'committed', first)
                root = manager.inspect(alice, 'private', 'notebook')
                self.assertEqual(manager.execute(alice, 'private', {'draft': draft['draft']}), first)
                self.assertEqual(manager.inspect(alice, 'private', 'notebook'), root)
                self.assertEqual(manager.reading(alice, 'private', 'draft', draft['draft'])['outcome'], 'committed')
                self.assertEqual(files[0].read_bytes(), retained_draft)
        with manager_for() as manager:
            with patch.object(manager, '_seed_law', side_effect=AssertionError('retained seed law rebuilt')), \
                    patch.object(manager, '_save_encounter', side_effect=agent_heaps.HeapLimit('encounter full')):
                self.assertEqual(manager.execute(alice, 'private', {'draft': draft['draft']}), first)
                self.assertEqual(manager.reading(alice, 'private', 'draft', draft['draft'])['outcome'], 'committed')


if __name__ == '__main__':
    unittest.main()
