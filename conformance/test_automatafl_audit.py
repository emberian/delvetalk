#!/usr/bin/env python3
"""Positive/negative checks for the documented Lean-only audit import projection.

Tiny probe modules compile serially; no package rebuild or Mathlib is involved.
"""
import json
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
                return subprocess.run(['lean', '--json', '-j', '1', '-R', str(temp), str(source),
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
                # Both commands inspect the same imported environment. Lean
                # continues after an elaboration error, so one compiler process
                # can exercise both refusals without weakening either control.
                both = lean('Both' + suffix, f'import {module}\n'
                            '#assert_axioms audit_bad\n#assert_axioms_tree\n')
                self.assertNotEqual(both.returncode, 0)
                diagnostics = both.stdout + both.stderr
                # Structured diagnostics retain wrapped offender lists inside
                # their own messages rather than matching unrelated output.
                errors = [message['data'] for line in both.stdout.splitlines()
                          if (message := json.loads(line)).get('severity') == 'error']
                direct = [message for message in errors
                          if 'depends on axioms outside the standard three' in message]
                tree = [message for message in errors
                        if '#assert_axioms_tree:' in message
                        and 'rest on axioms outside the standard three' in message]
                self.assertEqual(len(direct), 1, diagnostics)
                self.assertEqual(len(tree), 1, diagnostics)
                self.assertIn(rejected, direct[0])
                self.assertIn(rejected, tree[0])


if __name__ == '__main__':
    unittest.main()
