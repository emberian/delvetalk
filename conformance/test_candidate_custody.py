"""Native shared Value framing and typed Candidate custody preserve exact roots."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import source_object


class CandidateCustody(unittest.TestCase):
    def test_native_value_codec_preserves_numbers_null_and_arrays(self):
        original = desk.loads(b'{"decimal":-12.3400e-2,"zero":-0.00,"nested":[null,true,{"value":123456789012345678901234567890}]}')
        encoded = source_object.value(original)
        decoded = source_object.values('decode', [encoded])[0]
        native = desk.loads(b'{"decimal":-12.3400e-2,"zero":0.00,"nested":[null,true,{"value":123456789012345678901234567890}]}')
        self.assertEqual(desk.canonical(decoded), desk.canonical(native))
        self.assertEqual(desk.canonical(original['zero']), b'-0.00')
        self.assertEqual(desk.canonical(decoded['zero']), b'0.00')
        self.assertEqual(source_object.values('digest', [original]), source_object.values('digest', [decoded]))
        with self.assertRaises(ValueError):
            source_object.values('decode', [{'tag': 'variant', 'label': 'number',
                'payload': source_object.data({'encoded': 'null'})}])

    def test_candidate_projection_preserves_exact_root_and_legacy_state(self):
        raw = desk.loads(b'{"proposal":{"syntax":"example","source":null},"migration":{"items":[null,-1.20]},"protocol":{"number":1.00},"diagnostics":[],"roomArtifact":null}')
        names = tuple(raw)
        values = source_object.values('encode', list(raw.values()))
        fields = [dict(name=name, value=value) for name, value in zip(names, values)]
        fields.extend([dict(name='status', value=source_object.data('pending')),
                       dict(name='generation', value=source_object.data(2))])
        root = {'state': {'model': {'tag': 'record', 'fields': fields}}, 'version': 7}
        exact = desk.canonical(root)
        decoded = desk.candidate_state(root)
        self.assertEqual(desk.canonical({name: decoded[name] for name in names}), desk.canonical(raw))
        self.assertEqual(decoded['generation'], 2)
        self.assertEqual(desk.canonical(root), exact)
        malformed = deepcopy(root)
        malformed['state']['model']['fields'].append(fields[0])
        with self.assertRaises(ValueError): desk.candidate_state(malformed)
        legacy = {'state': {'proposal': raw['proposal'], 'status': 'pending'}}
        self.assertIs(desk.candidate_state(legacy), legacy['state'])


if __name__ == '__main__':
    unittest.main()
