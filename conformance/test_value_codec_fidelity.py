"""Current framed Value transport preserves native JSON number identity."""
from decimal import Decimal
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


class ValueCodecFidelity(unittest.TestCase):
    def test_number_scale_survives_encode_decode_and_nested_framing(self):
        numbers = [Decimal('1.2300'), Decimal('1.00'), Decimal('0.0000'),
                   Decimal('-12.3000'), Decimal('1E-10000')]
        values = numbers + [{'array': [True, 1, None, *numbers]}]
        encoded = source_object.values('encode', values)
        decoded = source_object.values('decode', encoded)
        for expected, actual in zip(numbers, decoded):
            self.assertIsInstance(actual, Decimal)
            self.assertEqual(actual.as_tuple(), expected.as_tuple())
        nested = decoded[-1]['array']
        self.assertIs(nested[0], True)
        self.assertIs(type(nested[1]), int)
        self.assertIsNone(nested[2])
        for expected, actual in zip(numbers, nested[3:]):
            self.assertIsInstance(actual, Decimal)
            self.assertEqual(actual.as_tuple(), expected.as_tuple())


if __name__ == '__main__':
    unittest.main()
