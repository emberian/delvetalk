"""Exact custody wire contract; no Lean process or build is needed."""
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import world


class WorldWire(unittest.TestCase):
    def test_native_json_keeps_exact_bytes_and_key_order(self):
        vectors = [
            (None, 'null'), (True, 'true'), (False, 'false'),
            (0, '0'), (-17, '-17'), (1.0, '1.0'), (-0.0, '-0.0'),
            (1e-8, '1e-08'), ([], '[]'), ({}, '{}'),
            (('a', True, None), '["a",true,null]'),
            ({'z': 2, 'a': [1, {'b': False}]}, '{"z":2,"a":[1,{"b":false}]}'),
            ('é🜉✾\n\t\b\f\r\\"', '"é🜉✾\\n\\t\\b\\f\\r\\\\\\""'),
        ]
        for value, expected in vectors:
            with self.subTest(value=value):
                self.assertEqual(world.wire_dumps(value), expected)

    def test_unbounded_integers_never_round_through_float(self):
        digits = '9' * 5000
        value = int(digits)
        self.assertEqual(world.wire_dumps({'n': value, 'small': 9007199254740993}),
                         '{"n":' + digits + ',"small":9007199254740993}')
        self.assertEqual(world.wire_loads(world.wire_dumps(value)), value)

    def test_decimal_fallback_retains_spelling_precision_and_native_values(self):
        value = {'precise': Decimal('0.100000000000000000000000000000000001'),
                 'scaled': Decimal('1.2300'), 'exponent': Decimal('1E+1000'),
                 'negativeZero': Decimal('-0.00'), 'native': [True, 1.0, -0.0, ('é', 7)]}
        expected = ('{"precise":0.100000000000000000000000000000000001,"scaled":1.2300,'
                    '"exponent":1E+1000,"negativeZero":-0.00,"native":[true,1.0,-0.0,["é",7]]}')
        self.assertEqual(world.wire_dumps(value), expected)
        parsed = world.wire_loads(expected)
        self.assertEqual(str(parsed['scaled']), '1.2300')
        self.assertEqual(str(parsed['negativeZero']), '-0.00')
        self.assertEqual(parsed['precise'], value['precise'])

    def test_nonstring_keys_refuse_at_every_depth_even_after_decimal(self):
        invalid = [{1: 'a'}, {True: 'a'}, {None: 'a'}, [('tuple', {2: 'x'})],
                   {'decimal': Decimal('1.0'), 'later': {'nested': {3: 'x'}}},
                   [Decimal('1.0'), {'nested': {4: 'x'}}]]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'keys must be strings'):
                    world.wire_dumps(value)

    def test_nonfinite_numbers_refuse_in_native_and_decimal_branches(self):
        for bad in (float('nan'), float('inf'), float('-inf'),
                    Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'), Decimal('-Infinity')):
            for value in (bad, {'nested': [bad]}, [Decimal('1.0'), bad]):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        world.wire_dumps(value)

    def test_unsupported_values_are_not_coerced(self):
        for value in (b'bytes', {1, 2}, object(), {'nested': b'bytes'}, [Decimal('1.0'), b'bytes']):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    world.wire_dumps(value)


if __name__ == '__main__':
    unittest.main()
