"""Actual source Candidate checks and retained receiving recovery."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from conformance.source_custody_fixture import counter_source, counter_protocol, count
spec = importlib.util.spec_from_file_location('source_desk', ROOT / 'scripts/desk.py')
desk_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk_module)

def scoped(invoke=None, reprogram=None, law=None):
    return {'profile': 'delvetalk-scoped-law', 'invoke': invoke or {},
            'reprogram': reprogram or [], 'law': law or [], 'read': 'public'}

class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.desk = desk_module.Desk(self.path / 'world.json', self.path / 'artifacts')
        self.source = counter_source()
        self.scenarios = desk_module.canonical([{'name':'actual-source-add','law':['player'],'steps':[
            {'principal':'player','command':'add','input':{'amount':3},'root':'initial','kind':'committed','result':3}]}])
        self.law = scoped({'submit':['author'],'compiled':['compiler'],'failed':['compiler'],'adopt':['reviewer'],
                           'requestCheck':['compiler']}, law=['owner'])
        self.candidate = self.desk.create('candidate','owner','create-candidate',self.law)['data']['root']
        self.target = self.desk.exchange({'op':'create','object':'target','principal':'owner','intent':'create-target',
            'protocol':counter_protocol(),'law':scoped({'add':['player']},reprogram=['reviewer'],law=['owner'])})['data']['root']

    def submit(self, **changes):
        migration = {'model': desk_module.source_object.compact_state(self.target['protocol'],
            desk_module.source_object.data({'count':41}), entry='describe', path=[{'field':'initial'}])}
        values = dict(object_id='candidate',principal='author',intent='submit',expected=self.candidate,
                      syntax='objective-bend-object',source=self.source,scenarios=self.scenarios,
                      migration=migration,target='target')
        values.update(changes)
        return self.desk.submit(**values)

    def requested(self, pending):
        view = desk_module.projection.project(pending, 'candidate')
        receipt = self.desk.exchange(desk_module.projection.request(view, 'check', 'compiler', 'request-check'))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        root = self.desk.inspect('candidate', principal='compiler')
        work = desk_module.compiler_work(root, 'candidate', 'compiler', self.desk.database)
        return root, work['intent']

    def ready(self):
        pending, intent = self.requested(self.submit()['data']['root'])
        return self.desk.check('candidate', 'compiler', intent, pending)['data']['root']

    def test_source_compile_release_and_exact_retry(self):
        pending, intent = self.requested(self.submit()['data']['root'])
        compiled = self.desk.check('candidate','compiler',intent,pending)
        self.assertEqual(compiled['kind'],'committed',compiled)
        ready = compiled['data']['root']
        self.assertEqual(desk_module.candidate_state(ready)['status'],'ready')
        with patch.object(desk_module,'bounded_compile',side_effect=AssertionError('recompiled')):
            self.assertEqual(self.desk.check('candidate','compiler',intent,pending),compiled)
        admitted = self.desk.adopt('candidate','target','reviewer','release',ready,self.target)
        self.assertEqual(admitted['kind'],'committed',admitted)
        self.assertEqual(desk_module.source_object.plain(desk_module.source_object.state_data(self.desk.inspect('target')))['count'],41)
        self.assertEqual(self.desk.inspect('target')['law'],self.target['law'])
        self.assertEqual(self.desk.adopt('candidate','target','reviewer','release',ready,self.target),admitted)

    def test_failed_source_check_retains_diagnostics_and_cannot_release(self):
        pending, intent = self.requested(self.submit(source=b'edition ObjectiveBend 1\ndef broken(')['data']['root'])
        receipt = self.desk.check('candidate','compiler',intent,pending)
        self.assertEqual(receipt['kind'],'committed',receipt)
        failed = receipt['data']['root']
        self.assertEqual(desk_module.candidate_state(failed)['status'],'failed')
        self.assertTrue(desk_module.candidate_state(failed)['diagnostics'])
        self.assertEqual(self.desk.check('candidate','compiler',intent,pending),receipt)
        with self.assertRaises(ValueError):
            self.desk.adopt('candidate','target','reviewer','cannot-release',failed,self.target)
        self.assertEqual(self.desk.inspect('target'),self.target)

if __name__ == '__main__': unittest.main()
