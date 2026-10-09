"""Frame repeatable authored-editor turns; Lean owns every editing decision.

A generation's exact requests and receipts survive interruption in local custody.
Candidate allocation, source submission, authentic review and adoption use the
existing governed world and source desks. No object behavior is evaluated here.
"""
import copy
from pathlib import Path

import clerk
import desk


def review_request(editor, candidate, principal, intent, expected_editor, expected_candidate):
    return {'op': 'transaction', 'principal': principal, 'intent': intent,
        'reads': {editor: expected_editor, candidate: expected_candidate},
        'calls': [{'object': candidate, 'command': 'report', 'input': {}},
                  {'object': editor, 'command': 'review', 'inputFrom': 0}]}


def adoption_request(editor, candidate, target, principal, intent,
                     expected_editor, expected_candidate, expected_target):
    return {'op': 'transaction', 'principal': principal, 'intent': intent,
        'reads': {editor: expected_editor, candidate: expected_candidate, target: expected_target},
        'calls': [{'op': 'observe', 'object': target},
                  {'object': editor, 'command': 'approve', 'inputFrom': 0},
                  {'object': candidate, 'command': 'adopt', 'inputFrom': 1},
                  {'op': 'reprogram', 'object': target, 'inputFrom': 2},
                  {'object': editor, 'command': 'finish', 'inputFrom': 3}]}


class Editor:
    def __init__(self, client, custody):
        self.client = client
        self.custody = Path(custody)

    def generation(self, editor, target, factory, name, principal, intent,
                   expected_editor, expected_target, expected_factory, proposal, migration):
        """Allocate and submit one new candidate, recovering each exact admission.

        Exact preimages and complete migration are supplied deliberately. A
        refused step is retained; callers choose a new generation/intent explicitly.
        """
        request = {'op': 'transaction', 'principal': principal, 'intent': intent + ':allocate',
            'reads': {editor: expected_editor, target: expected_target, factory: expected_factory,
                      factory + '/' + name: None},
            'calls': [{'object': editor, 'command': 'draft', 'input': {'name': name}},
                      {'op': 'observe', 'object': target},
                      {'object': editor, 'command': 'plan', 'inputFrom': 1},
                      {'object': factory, 'command': 'make', 'inputFrom': 2}]}
        identity = desk.digest({'principal': principal, 'intent': intent})
        path = self.custody / 'generations' / (identity + '.json')
        inputs = {'request': request, 'proposal': proposal, 'migration': migration}
        if path.exists():
            retained = desk.loads(path.read_bytes())
            if desk.canonical(retained['inputs']) != desk.canonical(inputs):
                raise ValueError('generation identity already binds different exact inputs')
        else:
            retained = {'inputs': copy.deepcopy(inputs), 'phase': 'prepared'}
            clerk.save(path, retained)
        if 'allocation' not in retained:
            retained['allocation'] = self.client.exchange(request)
            retained['phase'] = 'allocated' if retained['allocation']['kind'] == 'committed' else 'refused'
            clerk.save(path, retained)
        allocation = retained['allocation']
        if allocation['kind'] != 'committed':
            return copy.deepcopy(retained)
        # Receiving allocation receipts identify the child. User names do not
        # establish creation; the receipt carries its exact initial root.
        children = list(allocation['data']['allocated'].items())
        if len(children) != 1:
            raise ValueError('editor generation requires exactly one admitted candidate allocation')
        candidate, initial = children[0]
        plan = allocation['data']['results'][2]
        if 'submission' not in retained:
            submitted = {'op': 'invoke', 'object': candidate, 'principal': principal,
                'intent': intent + ':submit', 'expected': initial, 'command': 'submit',
                'input': {'proposal': proposal, 'migration': migration, 'target': target,
                    'editor': plan['editor'], 'generation': plan['generation'],
                    'baselineVersion': plan['baselineVersion']}}
            retained['submission'] = self.client.exchange(submitted)
            retained['phase'] = 'submitted' if retained['submission']['kind'] == 'committed' else 'refused'
            clerk.save(path, retained)
        if retained['submission']['kind'] != 'committed':
            return copy.deepcopy(retained)
        if 'activation' not in retained:
            activation = {'op': 'transaction', 'principal': principal, 'intent': intent + ':activate',
                'reads': {editor: allocation['data']['roots'][editor],
                          candidate: retained['submission']['data']['root']},
                'calls': [{'object': candidate, 'command': 'report', 'input': {}},
                          {'object': editor, 'command': 'review', 'inputFrom': 0}]}
            retained['activation'] = self.client.exchange(activation)
            retained['phase'] = 'retained' if retained['activation']['kind'] == 'committed' else 'refused'
            clerk.save(path, retained)
        retained.update(candidate=candidate, generation=plan['generation'], baseline=expected_target)
        clerk.save(path, retained)
        return copy.deepcopy(retained)

    def review(self, editor, candidate, principal, intent, expected_editor, expected_candidate):
        return self.client.exchange(review_request(editor, candidate, principal, intent,
                                    expected_editor, expected_candidate))

    def adopt(self, editor, candidate, target, principal, intent,
              expected_editor, expected_candidate, expected_target):
        return self.client.exchange(adoption_request(editor, candidate, target, principal, intent,
                                    expected_editor, expected_candidate, expected_target))
