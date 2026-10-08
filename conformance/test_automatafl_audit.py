#!/usr/bin/env python3
"""Positive/negative checks for the documented Lean-only audit import projection.

Tiny probe modules compile serially; no package rebuild or Mathlib is involved.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AuditorCompatibility(unittest.TestCase):
    def test_auditors_accept_kernel_proofs_and_refuse_axioms_and_sorry(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / "Theory").mkdir()
            for artifact in (ROOT / ".lake/build/lib/lean/Theory").iterdir():
                if artifact.is_file():
                    (temp / "Theory" / artifact.name).symlink_to(artifact)
            env = {**os.environ, 'LEAN_NUM_THREADS': '1',
                   'LEAN_PATH': str(temp) + ':' + str(ROOT / '.lake/build/lib/lean')}

            def lean(module, text):
                source = temp / (module.replace('.', '/') + '.lean')
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(text)
                return subprocess.run(['lean', '-j', '1', '-R', str(temp), str(source),
                                       '-o', str(source.with_suffix('.olean'))], cwd=ROOT,
                                      env=env, capture_output=True, text=True, timeout=30)

            good = lean('Theory.AuditorGood', 'import Theory.AssertAxioms\n'
                        'theorem audit_good : True := True.intro\n#assert_axioms audit_good\n')
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            good_tree = lean('GoodTree', 'import Theory.AuditorGood\n#assert_axioms_tree\n')
            self.assertEqual(good_tree.returncode, 0, good_tree.stdout + good_tree.stderr)
            self.assertIn('none on sorryAx or a declared axiom', good_tree.stdout)
            for suffix, declaration, rejected in [
                ('Declared', 'axiom audit_bad : False', 'audit_bad'),
                ('Sorry', 'theorem audit_bad : False := by sorry', 'sorryAx')]:
                module = 'Theory.Auditor' + suffix
                compiled = lean(module, 'import Theory.AssertAxioms\n' + declaration + '\n')
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                direct = lean('Direct' + suffix, f'import {module}\n#assert_axioms audit_bad\n')
                self.assertNotEqual(direct.returncode, 0)
                self.assertIn(rejected, direct.stdout + direct.stderr)
                tree = lean('Tree' + suffix, f'import {module}\n#assert_axioms_tree\n')
                self.assertNotEqual(tree.returncode, 0)
                self.assertIn(rejected, tree.stdout + tree.stderr)


if __name__ == '__main__':
    unittest.main()
