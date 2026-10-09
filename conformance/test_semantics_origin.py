"""Historical attribution does not freeze local semantics; actual closures still bind them."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_semantics
import runtime_profile


class SemanticsOrigin(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.root = Path(home.name)
        for folder in ('spec', 'profiles'):
            for path in (ROOT / folder).rglob('*.lean'):
                target = self.root / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        for name in ('LICENSE', 'lakefile.toml', check_semantics.ORIGIN, runtime_profile.MANIFEST):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def test_actual_origin_and_local_closure(self):
        self.assertGreater(check_semantics.verify(ROOT), 0)
        self.assertNotIn(check_semantics.ORIGIN, runtime_profile.paths('compiled'))

    def test_local_changes_and_new_modules_need_no_baseline_edits(self):
        path = self.root / 'spec/bend/Theory/AxiomPin.lean'
        path.write_text(path.read_text() + '\n-- An ordinary local edit.\n')
        (path.parent / 'LocalExtension.lean').write_text('import Theory.AxiomPin\ndef localExample : Nat := 1\n')
        origin = self.root / check_semantics.ORIGIN
        original = origin.read_bytes()
        check_semantics.verify(self.root)
        self.assertEqual(origin.read_bytes(), original)

    def test_baseline_is_not_a_required_local_inventory(self):
        path = self.root / check_semantics.ORIGIN
        origin = json.loads(path.read_text())
        origin['baseline']['Theory/RetiredInLocalFork.lean'] = '0' * 64
        path.write_text(json.dumps(origin))
        check_semantics.verify(self.root)

    def test_missing_local_runtime_dependency_is_not_hidden_by_origin(self):
        path = self.root / runtime_profile.MANIFEST
        manifest = json.loads(path.read_text())
        manifest['groups']['common'].remove('spec/bend/Theory/AxiomPin.lean')
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'runtime closure omits'):
            check_semantics.verify(self.root)

    def test_invalid_origin_or_changed_license_is_rejected(self):
        path = self.root / check_semantics.ORIGIN
        origin = json.loads(path.read_text())
        origin['baseline']['../escape.lean'] = '0' * 64
        path.write_text(json.dumps(origin))
        with self.assertRaisesRegex(ValueError, 'baseline path'):
            check_semantics.verify(self.root)
        shutil.copy2(ROOT / check_semantics.ORIGIN, path)
        (self.root / 'LICENSE').write_text('different license')
        with self.assertRaisesRegex(ValueError, 'license'):
            check_semantics.verify(self.root)


if __name__ == '__main__':
    unittest.main()
