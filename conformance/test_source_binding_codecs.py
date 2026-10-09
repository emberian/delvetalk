"""Source binder checks codec and allocation schemas against their native ABI."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from syntaxes import obend_object


def modules(name):
    files = [('Preparation', ROOT / 'world/lib/prelude/Preparation.obend')]
    if name == 'Factory': files.append(('Allocation', ROOT / 'world/lib/prelude/Allocation.obend'))
    files.append((name, ROOT / 'protocols/editor' / (name + '.obend')))
    return [{'name': key, 'source': path.read_text()} for key, path in files]


class SourceBindingCodecs(unittest.TestCase):
    def test_actual_candidate_binds_value_codecs_without_form_metadata_leak(self):
        protocol = obend_object.lower_data_modules(modules('Candidate'))
        for name, command in protocol['commands'].items():
            transition = command['transition']
            self.assertEqual(transition['resultCodec'], 'value')
            self.assertEqual(transition.get('inputCodec'), None if name == 'report' else 'value')
            self.assertEqual(set(protocol['affordances'][name]), {'label', 'fields'})
        self.assertNotIn('allocation', protocol)

    def test_actual_factory_binds_allocation_policy_including_disabled_quota(self):
        for limit in (0, 32, 100):
            sources = modules('Factory')
            sources[-1]['source'] = sources[-1]['source'].replace('allocation: {limit: 32n}', f'allocation: {{limit: {limit}n}}')
            protocol = obend_object.lower_data_modules(sources)
            self.assertEqual(protocol['allocation'], {'limit': limit})
            self.assertNotIn('inputCodec', protocol['commands']['make']['transition'])

    def test_codec_requires_canonical_value_not_merely_serializable_record(self):
        sources = modules('Candidate')
        # report's real input is {}, while every result has canonical Value type.
        sources[-1]['source'] = sources[-1]['source'].replace('record ReportMethod:\n  label: String\n  fields: {}\n  resultCodec: String',
            'record ReportMethod:\n  label: String\n  fields: {}\n  inputCodec: String\n  resultCodec: String').replace(
            'report: {label: "Report this candidate", fields: {}, resultCodec: "value"}',
            'report: {label: "Report this candidate", fields: {}, inputCodec: "value", resultCodec: "value"}')
        with self.assertRaisesRegex(ValueError, 'report input codec.*incompatible'):
            obend_object.lower_data_modules(sources)
        sources = modules('Candidate')
        sources[-1]['source'] = sources[-1]['source'].replace('inputCodec: "value"', 'inputCodec: "invented"')
        with self.assertRaisesRegex(ValueError, 'codec must be value'):
            obend_object.lower_data_modules(sources)

    def test_allocations_need_policy_and_canonical_child_description(self):
        sources = modules('Factory')
        sources[-1]['source'] = sources[-1]['source'].replace('  allocation: {limit: Nat}\n', '').replace(', allocation: {limit: 32n}', '')
        with self.assertRaisesRegex(ValueError, 'allocations require a declared allocation policy'):
            obend_object.lower_data_modules(sources)
        sources = modules('Factory')
        sources[1]['source'] = sources[1]['source'].replace('protocol: P.Value', 'protocol: String')
        sources[-1]['source'] = sources[-1]['source'].replace('protocol: state.candidate', 'protocol: "wrong shape"')
        with self.assertRaisesRegex(ValueError, 'make allocations.*incompatible'):
            obend_object.lower_data_modules(sources)


if __name__ == '__main__':
    unittest.main()
