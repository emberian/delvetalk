"""The standalone core wire retains hosted scans before and after evaluation."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get("DELVETALK_CORE_BINARY", ROOT / ".lake/build/bin/delvetalk"))


class CoreTextWire(unittest.TestCase):
    def test_scan_wire_roundtrip_and_scalar_execution(self):
        cases = [("textSpan", "🌙e\u0301!", "🌙e\u0301", 3),
                 ("textBreak", "🌙e\u0301!", "!", 3)]
        for primitive, text, alphabet, count in cases:
            term = ["binary", primitive, ["label", text], ["label", alphabet]]
            for fuel, expected in [(0, term), (100, ["nat", str(count)])]:
                with self.subTest(primitive=primitive, fuel=fuel):
                    request = {"name": primitive, "term": term, "fuel": fuel}
                    result = subprocess.run([str(BINARY)], input=json.dumps(request) + "\n",
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["term"], expected)


if __name__ == "__main__":
    unittest.main()
