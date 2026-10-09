"""Presentation quotas cannot strand a retained native account receipt."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from conformance import test_agent_heaps as fixture
import agent_heaps


class AccountReceiptCustody(unittest.TestCase):
    def test_execute_and_retry_need_no_derived_draft_write(self):
        setup = fixture.AccountHeaps(methodName='runTest')
        setup.setUp()
        self.addCleanup(setup.doCleanups)
        with setup.manager() as manager:
            card = manager.encounter(fixture.ALICE, 'private', 'notebook')
            draft = manager.prepare(fixture.ALICE, 'private', {'card': card['card'],
                'action': next(action['id'] for action in card['actions'] if action['command'] == 'note'),
                'fields': {'thought': 'Keep this once.'}})
            files = list(manager.root.glob('*/encounters/private/drafts/' + draft['draft'] + '.json'))
            self.assertEqual(len(files), 1)
            retained_draft = files[0].read_bytes()
            with patch.object(manager, '_save_encounter', side_effect=agent_heaps.HeapLimit('encounter full')):
                first = manager.execute(fixture.ALICE, 'private', {'draft': draft['draft']})
                self.assertEqual(first['kind'], 'committed', first)
                root = manager.inspect(fixture.ALICE, 'private', 'notebook')
                self.assertEqual(manager.execute(fixture.ALICE, 'private', {'draft': draft['draft']}), first)
                self.assertEqual(manager.inspect(fixture.ALICE, 'private', 'notebook'), root)
                self.assertEqual(manager.reading(fixture.ALICE, 'private', 'draft', draft['draft'])['outcome'], 'committed')
                self.assertEqual(files[0].read_bytes(), retained_draft)
        with setup.manager() as manager:
            with patch.object(manager, '_save_encounter', side_effect=agent_heaps.HeapLimit('encounter full')):
                self.assertEqual(manager.execute(fixture.ALICE, 'private', {'draft': draft['draft']}), first)
                self.assertEqual(manager.reading(fixture.ALICE, 'private', 'draft', draft['draft'])['outcome'], 'committed')


if __name__ == '__main__':
    unittest.main()
