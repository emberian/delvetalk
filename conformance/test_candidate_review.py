"""Authored compiler consent replaces repository source-body approval."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk


class CandidateReview(unittest.TestCase):
    def test_compatible_source_revision_offers_exact_work_under_current_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            client = desk.Desk(home / 'world.json', home / 'artifacts')
            modules = desk.source_object.read_closure([('Candidate', 'protocols/editor/Candidate.obend')])
            modules[-1]['source'] = modules[-1]['source'].replace(
                'Compiler check requested.', 'This authored resident requests its check.')
            protocol = desk.source_object.load(modules, syntax='objective-bend-object', constructor='initial',
                arguments=[desk.source_object.data({'editorMode': False})])
            law = {'profile': 'delvetalk-scoped-law', 'invoke': {'submit': ['maker'],
                'requestCheck': ['maker'], 'compiled': ['compiler'], 'failed': ['compiler']},
                'law': ['maker'], 'reprogram': [], 'read': ['maker', 'compiler']}
            root = client.exchange({'op': 'create', 'object': 'candidate', 'principal': 'maker',
                'intent': 'make', 'protocol': protocol, 'law': law})['data']['root']
            self.assertIsNone(desk.compiler_work(root, 'candidate', 'compiler', client.database))
            proposal = {'syntax': 'objective-bend-object', 'source': 'retained source', 'scenarios': 'retained examples'}
            root = client.exchange({'op': 'invoke', 'object': 'candidate', 'principal': 'maker',
                'intent': 'submit', 'expected': root, 'command': 'submit',
                'input': {'proposal': proposal, 'migration': {'model': {}}, 'target': 'target'}})['data']['root']
            view = desk.projection.project(root, 'candidate')
            receipt = client.exchange(desk.projection.request(view, 'check', 'maker', 'check'))
            self.assertEqual(receipt['kind'], 'committed', receipt)
            requested = client.inspect('candidate', principal='maker')
            work = desk.compiler_work(requested, 'candidate', 'compiler', client.database)
            self.assertEqual(work['proposal'], proposal)
            self.assertEqual(work['intent'], 'source-compile:candidate:1')
            self.assertEqual(work['reports'], {'passed': 'compiled', 'failed': 'failed'})
            with self.assertRaises(ValueError):
                desk.compiler_work(requested, 'candidate', 'stranger', client.database)
            self.assertIsNone(desk.compiler_work(root, 'candidate', 'compiler', client.database))


if __name__ == '__main__': unittest.main()
