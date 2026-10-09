"""Compiler custody recognizes complete reviewed source bodies, never a service name."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk


class CandidateReview(unittest.TestCase):
    def test_explicit_base_and_composed_contract_bodies_are_reviewed_exactly(self):
        base = desk.module('review_base', 'protocols/source-desk/package.py').candidate()
        contract = desk.module('review_contract', 'protocols/contract-workshop/generate.py').candidate()
        self.assertTrue(desk.is_source_desk_protocol(base))
        self.assertTrue(desk.is_source_desk_protocol(contract))
        spoof = deepcopy(base)
        spoof['name'] = contract['name']
        self.assertFalse(desk.is_source_desk_protocol(spoof))
        tampered = deepcopy(contract)
        tampered['sourcePackages']['resident']['modules'][-1]['source'] += '\n# different exact source\n'
        self.assertFalse(desk.is_source_desk_protocol(tampered))


if __name__ == '__main__':
    unittest.main()
