"""Pure source-desk adoption request constructor; Lean alone admits it."""
import copy
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('adoption_translate', Path(__file__).with_name('translate.py'))
_translate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_translate)


def request(candidate_id, target_id, principal, intent, expected_candidate, expected_target):
    """Release the candidate then reprogram its target in one exact-read transaction."""
    if candidate_id == target_id and _translate.canonical(expected_candidate) != _translate.canonical(expected_target):
        raise ValueError('one object cannot have two different read roots')
    return copy.deepcopy({
        'op': 'transaction', 'principal': principal, 'intent': intent,
        'reads': {candidate_id: expected_candidate, target_id: expected_target},
        'calls': [{'object': candidate_id, 'command': 'adopt', 'input': {'target': target_id}},
                  {'op': 'reprogram', 'object': target_id, 'inputFrom': 0}]})
