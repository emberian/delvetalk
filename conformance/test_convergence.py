#!/usr/bin/env python3
"""Independent check that custody pins cover the actual local Lean import graph.

Read-only: no builds, binary execution, artifact mutation or network access.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('convergence_runtime_profile', ROOT / 'scripts/runtime_profile.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeClosure(unittest.TestCase):
    def test_every_selected_host_covers_its_transitive_project_imports(self):
        for profile, (_, entry) in runtime.PROFILES.items():
            with self.subTest(profile=profile):
                pending, seen = [entry], set()
                while pending:
                    path = pending.pop()
                    if path in seen:
                        continue
                    seen.add(path)
                    for line in (ROOT / path).read_text().splitlines():
                        if not line.startswith('import '):
                            continue
                        for name in line.removeprefix('import ').split():
                            if name.split('.')[0] in ('Lean', 'Std', 'Init'):
                                continue  # Explicit pinned-toolchain boundary.
                            relative = Path(*name.split('.')).with_suffix('.lean')
                            matches = [str(Path(directory) / relative)
                                       for directory in ('profiles', 'spec', 'spec/upstream')
                                       if (ROOT / directory / relative).is_file()]
                            self.assertEqual(len(matches), 1,
                                f'{path}: cannot resolve project import {name}: {matches}')
                            pending.append(matches[0])
                missing = seen - set(runtime.paths(profile))
                self.assertFalse(missing, f'{profile} leaves source dependencies unpinned: {sorted(missing)}')


if __name__ == '__main__':
    unittest.main()
