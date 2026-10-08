#!/usr/bin/env python3
"""One Lean authority engine for legacy and scoped laws, including transactions."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('authority_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def scoped(invoke=None, reprogram=None, law=None, predicate=None):
    value = {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'play': ['player'], 'review': ['reviewer']} if invoke is None else invoke,
            'reprogram': ['programmer'] if reprogram is None else reprogram,
            'law': ['steward'] if law is None else law}
    if predicate is not None:
        value['predicate'] = predicate
    return value


def protocol():
    command = {'require': [], 'set': {'last': ['principal']},
               'result': ['record', {'by': ['principal']}],
               'outbox': [['record', {'by': ['principal']}]]}
    return {'profile': 'delvetalk-local-v1', 'initial': {'last': 'initial'},
            'commands': {name: copy.deepcopy(command)
                         for name in ['play', 'review', 'reprogram', '*']}}


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for profile in ('world', 'transactions'):
            self.assertTrue((ROOT / '.lake/build/bin' / world.PROFILES[profile][0]).exists(),
                            'Build both Lean host profiles before testing')

    def seed(self, profile='world', authority=None):
        self.profile = profile
        self.db = Path(self.tmp.name) / (profile + '.json')
        self.root = self.create('room', scoped() if authority is None else authority)

    def call(self, request):
        return world.exchange(self.db, request, profile=self.profile)

    def create(self, name, authority):
        reply = self.call({'op': 'create', 'object': name, 'principal': 'creator',
            'intent': 'create-' + name, 'protocol': protocol(), 'law': authority})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def inspect(self, name='room'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'public-observer'})

    def invoke(self, principal='player', command='play', intent='invoke', root=None):
        return {'op': 'invoke', 'object': 'room', 'principal': principal, 'intent': intent,
                'expected': self.root if root is None else root, 'command': command, 'input': {}}

    def reprogram(self, principal='programmer', intent='program', root=None):
        candidate = protocol()
        candidate['initial'] = {'last': 'unused initial'}
        return {'op': 'reprogram', 'object': 'room', 'principal': principal, 'intent': intent,
                'expected': self.root if root is None else root, 'protocol': candidate,
                'state': {'last': 'explicit replacement'}}

    def change_law(self, authority, principal='steward', intent='law', root=None):
        return {'op': 'law', 'object': 'room', 'principal': principal, 'intent': intent,
                'expected': self.root if root is None else root, 'law': authority}

    def test_per_command_and_management_grants_are_separate(self):
        for profile in ('world', 'transactions'):
            with self.subTest(profile=profile):
                self.seed(profile)
                for principal, command in [('player', 'review'), ('reviewer', 'play'),
                                            ('programmer', 'play'), ('steward', 'play'),
                                            ('creator', 'play')]:
                    reply = self.call(self.invoke(principal, command, principal + command))
                    self.assertEqual(reply['data'], 'unauthorized')
                self.assertEqual(self.call(self.reprogram('player'))['data'], 'unauthorized')
                self.assertEqual(self.call(self.change_law(['player'], 'player'))['data'], 'unauthorized')
                self.assertEqual(self.call(self.change_law(['programmer'], 'programmer'))['data'], 'unauthorized')
                self.assertEqual(self.call(self.reprogram('steward'))['data'], 'unauthorized')
                self.assertEqual(self.inspect(), self.root)
                played = self.call(self.invoke())
                self.assertEqual(played['kind'], 'committed')
                self.assertEqual(played['data']['result'], {'by': 'player'})
                programmed = self.call(self.reprogram(root=played['data']['root']))
                self.assertEqual(programmed['kind'], 'committed')
                self.assertEqual(programmed['data']['root']['law'], self.root['law'])

    def test_missing_command_denies_and_star_is_only_a_literal_command(self):
        self.seed(authority=scoped(invoke={'*': ['player'], 'reprogram': ['player']}))
        self.assertEqual(self.call(self.invoke())['data'], 'unauthorized')
        star = self.call(self.invoke(command='*', intent='literal-star'))
        self.assertEqual(star['kind'], 'committed')
        same_name = self.call(self.invoke(command='reprogram', intent='named-command', root=star['data']['root']))
        self.assertEqual(same_name['kind'], 'committed')
        denied = self.call(self.reprogram('player', root=same_name['data']['root']))
        self.assertEqual(denied['data'], 'unauthorized')

    def test_old_law_authorizes_replacement_not_proposed_self_grant(self):
        self.seed()
        requested = scoped(invoke={'play': ['player']}, reprogram=['player'], law=['player'])
        forged = copy.deepcopy(self.root)
        forged['law'] = requested
        denied = self.call(self.change_law(requested, 'player', root=forged))
        self.assertEqual(denied['data'], 'unauthorized')
        self.assertEqual(self.inspect(), self.root)
        authorized = self.call(self.change_law(requested))
        self.assertEqual(authorized['kind'], 'committed')
        self.assertEqual(authorized['data']['root']['version'], 1)
        self.assertEqual(self.call(self.reprogram('player', root=authorized['data']['root']))['kind'], 'committed')

    def test_empty_scoped_law_locks_out_creator_and_every_previous_role(self):
        self.seed()
        empty = scoped(invoke={}, reprogram=[], law=[])
        locked = self.call(self.change_law(empty))['data']['root']
        for principal in ['creator', 'player', 'programmer', 'steward']:
            with self.subTest(principal=principal):
                self.assertEqual(self.call(self.invoke(principal, intent='invoke-' + principal, root=locked))['data'],
                                 'unauthorized')
                self.assertEqual(self.call(self.reprogram(principal, intent='program-' + principal, root=locked))['data'],
                                 'unauthorized')
                self.assertEqual(self.call(self.change_law([principal], principal,
                    intent='recover-' + principal, root=locked))['data'], 'unauthorized')
        self.assertEqual(self.inspect(), locked)

    def test_legacy_upgrade_downgrade_and_exact_roots(self):
        for profile in ('world', 'transactions'):
            with self.subTest(profile=profile):
                self.seed(profile, ['legacy'])
                played = self.call(self.invoke('legacy'))['data']['root']
                programmed = self.call(self.reprogram('legacy', root=played))['data']['root']
                new_law = scoped()
                stale = self.call(self.change_law(new_law, 'legacy', intent='stale'))
                self.assertEqual(stale['data'], 'stale read root')
                migrated = self.call(self.change_law(new_law, 'legacy', intent='migrate', root=programmed))['data']['root']
                self.assertEqual(self.call(self.invoke('legacy', intent='no-longer', root=migrated))['data'], 'unauthorized')
                restored = self.call(self.change_law(['legacy'], intent='restore', root=migrated))['data']['root']
                self.assertEqual(self.call(self.invoke('legacy', intent='legacy-again', root=restored))['kind'], 'committed')

    def test_current_command_grant_and_historical_receipts(self):
        self.seed()
        original = self.invoke()
        original_receipt = self.call(original)
        denied_request = self.invoke(command='review', intent='denied', root=original_receipt['data']['root'])
        refusal = self.call(denied_request)
        self.assertEqual(refusal['data'], 'unauthorized')
        changed = self.call(self.change_law(scoped(invoke={'review': ['player']}),
                    root=original_receipt['data']['root']))['data']['root']
        self.assertEqual(self.call(original), original_receipt)
        self.assertEqual(self.call(denied_request), refusal)
        self.assertEqual(self.call({**denied_request, 'expected': changed})['data'],
                         'intent reused for different request')
        self.assertEqual(self.call(self.invoke(intent='revoked', root=changed))['data'], 'unauthorized')
        self.assertEqual(self.call(self.invoke(command='review', intent='fresh', root=changed))['kind'], 'committed')

    def test_malformed_scoped_law_refuses_atomically_at_create_and_replacement(self):
        self.seed()
        candidates = []
        for key in ['profile', 'invoke', 'reprogram', 'law']:
            value = scoped()
            del value[key]
            candidates.append(value)
        candidates += [scoped() | {'owner': 'creator'}, scoped() | {'profile': 'unknown'},
                       scoped(invoke=['player']), scoped(invoke={'play': 'player'}),
                       scoped(invoke={'play': [4]}), scoped(reprogram='programmer'),
                       scoped(law=[True]), None, 4, 'player']
        for index, candidate in enumerate(candidates):
            with self.subTest(candidate=candidate):
                creation = self.call({'op': 'create', 'object': 'bad-' + str(index), 'principal': 'creator',
                    'intent': 'bad-create-' + str(index), 'protocol': protocol(), 'law': candidate})
                self.assertEqual(creation['kind'], 'refused')
                replacement = self.call(self.change_law(candidate, intent='bad-law-' + str(index)))
                self.assertEqual(replacement['kind'], 'refused')
                self.assertEqual(self.inspect(), self.root)
        self.assertEqual(list(world.wire_loads(self.db.read_text())['objects']), ['room'])

    def test_transaction_checks_each_callee_actual_command_and_rolls_back(self):
        self.seed('transactions')
        second = self.create('second', scoped(invoke={'review': ['player']}))
        request = {'op': 'transaction', 'principal': 'player', 'intent': 'transaction',
                   'reads': {'room': self.root, 'second': second}, 'calls': [
                       {'object': 'room', 'command': 'play', 'input': {}},
                       {'object': 'second', 'command': 'play', 'inputFrom': 0}]}
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'unauthorized')
        self.assertEqual(self.inspect(), self.root)
        self.assertEqual(self.inspect('second'), second)
        self.assertIsInstance(refusal['data'], str)  # no staged result/outbox escaped
        request['intent'] = 'allowed-commands'
        request['calls'][1]['command'] = 'review'
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data']['results'], [{'by': 'player'}] * 2)
        self.assertEqual(len(receipt['data']['outbox']), 2)

    def test_transaction_repeated_object_cannot_reuse_first_command_permission(self):
        self.seed('transactions')
        request = {'op': 'transaction', 'principal': 'player', 'intent': 'repeat',
                   'reads': {'room': self.root}, 'calls': [
                       {'object': 'room', 'command': 'play', 'input': {}},
                       {'object': 'room', 'command': 'review', 'input': {}}]}
        self.assertEqual(self.call(request)['data'], 'unauthorized')
        self.assertEqual(self.inspect(), self.root)
        # Neither metadata nor a command named like a management op changes admission kind.
        request['intent'] = 'smuggled-op'
        request['calls'][1] = {'object': 'room', 'command': 'play', 'input': {}, 'op': 'law'}
        self.assertEqual(self.call(request)['data'], 'unsupported transaction operation')
        self.assertEqual(self.inspect(), self.root)

    def desk(self):
        self.seed('transactions', scoped(invoke={'play': ['player'], 'publish': ['adopter']},
                                         reprogram=['adopter']))
        candidate = {'protocol': {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'publish': {'require': [], 'set': {'body': ['literal', 'published']},
                        'result': ['state', 'body'], 'outbox': []}}},
                     'state': {'body': 'migrated'}}
        desk_protocol = {'profile': 'delvetalk-local-v1',
                         'initial': {'adopted': False, 'candidate': candidate}, 'commands': {
            'adopt': {'require': [[['state', 'adopted'], ['literal', False]]],
                      'set': {'adopted': ['literal', True]}, 'result': ['state', 'candidate'],
                      'outbox': [['literal', 'adopted']]}}}
        desk = self.call({'op': 'create', 'object': 'desk', 'principal': 'creator',
                         'intent': 'desk-create', 'protocol': desk_protocol,
                         'law': scoped(invoke={'adopt': ['adopter', 'player']})})['data']['root']
        request = {'op': 'transaction', 'principal': 'adopter', 'intent': 'adopt-program',
                   'reads': {'desk': desk, 'room': self.root}, 'calls': [
                       {'op': 'invoke', 'object': 'desk', 'command': 'adopt', 'input': {}},
                       {'op': 'reprogram', 'object': 'room', 'inputFrom': 0}]}
        return candidate, desk, request

    def test_atomic_desk_adoption_installs_exact_prior_result_then_new_command_runs(self):
        candidate, desk, request = self.desk()
        request['calls'].append({'object': 'room', 'command': 'publish', 'input': {}})
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['results'], [candidate, None, 'migrated'])
        self.assertEqual(receipt['data']['roots']['room']['protocol'], candidate['protocol'])
        self.assertEqual(receipt['data']['roots']['room']['state'], {'body': 'published'})
        self.assertEqual(receipt['data']['roots']['room']['law'], self.root['law'])
        self.assertEqual(receipt['data']['roots']['room']['version'], 2)
        self.assertEqual(self.inspect('desk')['state']['adopted'], True)
        self.assertEqual(receipt['data']['outbox'], [{'object': 'desk', 'step': 0, 'payload': 'adopted'}])
        self.assertEqual(self.call(request), receipt)

    def test_adoption_result_does_not_delegate_target_programming_authority(self):
        _, desk, request = self.desk()
        request['principal'] = 'player'
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'unauthorized')
        self.assertEqual(self.inspect('desk'), desk)
        self.assertEqual(self.inspect(), self.root)

    def test_stale_candidate_guard_and_late_failure_do_not_consume_or_reprogram(self):
        _, desk, request = self.desk()
        stale = copy.deepcopy(request)
        stale['reads']['desk']['state']['candidate']['state'] = {'body': 'substituted'}
        self.assertEqual(self.call(stale)['data'], 'stale read root')
        request['intent'] = 'later-failure'
        request['calls'].append({'object': 'room', 'command': 'play', 'input': {}})
        self.assertEqual(self.call(request)['data'], 'unauthorized')
        self.assertEqual(self.inspect('desk'), desk)
        self.assertEqual(self.inspect(), self.root)

    def test_direct_transaction_reprogram_and_strict_candidate_shape(self):
        candidate, desk, request = self.desk()
        conflicting = copy.deepcopy(request)
        conflicting['calls'][1]['state'] = {'body': 'substituted'}
        self.assertEqual(self.call(conflicting)['data'], 'unsupported transaction reprogram field')
        self.assertEqual(self.inspect('desk'), desk)
        self.assertEqual(self.inspect(), self.root)
        direct = {**request, 'intent': 'direct', 'calls': [
            {'op': 'reprogram', 'object': 'room', **candidate}]}
        receipt = self.call(direct)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data']['results'], [None])
        self.assertEqual(receipt['data']['roots']['room']['state'], candidate['state'])
        self.assertEqual(self.inspect('desk'), desk)

    def test_referenced_candidate_must_be_exact_complete_valid_record(self):
        candidate, _, _ = self.desk()
        for index, invalid in enumerate([candidate | {'law': ['adopter']}, None,
                {'protocol': candidate['protocol']}, candidate | {'state': []},
                candidate | {'protocol': {'profile': 'unknown'}}]):
            with self.subTest(candidate=invalid):
                name = 'producer-' + str(index)
                producer = {'profile': 'delvetalk-local-v1', 'initial': {'used': False},
                            'commands': {'emit': {'require': [], 'set': {'used': ['literal', True]},
                                'result': ['literal', invalid], 'outbox': [['literal', 'would emit']]}}}
                root = self.call({'op': 'create', 'object': name, 'principal': 'creator',
                    'intent': 'create-' + name, 'protocol': producer,
                    'law': scoped(invoke={'emit': ['adopter']})})['data']['root']
                request = {'op': 'transaction', 'principal': 'adopter', 'intent': name,
                    'reads': {name: root, 'room': self.root}, 'calls': [
                        {'object': name, 'command': 'emit', 'input': {}},
                        {'op': 'reprogram', 'object': 'room', 'inputFrom': 0}]}
                self.assertEqual(self.call(request)['kind'], 'refused')
                self.assertEqual(self.inspect(name), root)
                self.assertEqual(self.inspect(), self.root)

    def policy_counter(self, profile='world'):
        self.profile = profile
        self.db = Path(self.tmp.name) / (profile + '.json')
        context = ['bound', 0]
        amount = ['get', ['get', context, 'input'], 'amount']
        count = ['get', ['get', context, 'state'], 'count']
        predicate = ['lam', ['ifBool', ['binary', 'labelEqual', ['get', context, 'op'], ['label', 'invoke']],
            ['binary', 'lessEqual', ['binary', 'add', count, amount], ['nat', '3']], ['boolean', True]]]
        p = {'profile': 'delvetalk-local-v1', 'initial': {'count': 0}, 'commands': {
            'add': {'require': [], 'set': {'count': ['bend',
                ['lam', ['lam', ['binary', 'add', ['bound', 1], ['bound', 0]]]],
                [['state', 'count'], ['input', 'amount']]]},
                'result': ['record', {'amount': ['input', 'amount']}], 'outbox': [['literal', 'added']]}}}
        self.root = self.call({'op': 'create', 'object': 'room', 'principal': 'creator', 'intent': 'counter',
            'protocol': p, 'law': scoped(invoke={'add': ['player']}, predicate=predicate)})['data']['root']

    def test_pure_policy_bounds_counter_using_current_state_and_actual_input(self):
        for profile in ('world', 'transactions'):
            with self.subTest(profile=profile):
                self.policy_counter(profile)
                first = {**self.invoke(command='add'), 'input': {'amount': 2}}
                committed = self.call(first)
                self.assertEqual(committed['kind'], 'committed')
                self.assertEqual(committed['data']['root']['state'], {'count': 2})
                second = {**first, 'intent': 'over-bound', 'expected': committed['data']['root']}
                refusal = self.call(second)
                self.assertEqual(refusal['data'], 'authority predicate refused')
                self.assertEqual(self.inspect(), committed['data']['root'])
                self.assertEqual(self.call(first), committed)
                self.assertEqual(self.call(second), refusal)

    def test_transaction_policy_uses_staged_state_and_resolved_prior_input(self):
        self.policy_counter('transactions')
        request = {'op': 'transaction', 'principal': 'player', 'intent': 'over-bound',
            'reads': {'room': self.root}, 'calls': [
                {'object': 'room', 'command': 'add', 'input': {'amount': 2}},
                {'object': 'room', 'command': 'add', 'inputFrom': 0}]}
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'authority predicate refused')
        self.assertEqual(self.inspect(), self.root)
        request['intent'] = 'within-bound'
        request['calls'][0]['input']['amount'] = 1
        self.assertEqual(self.call(request)['kind'], 'committed')
        self.assertEqual(self.inspect()['state'], {'count': 2})

    def test_policy_never_expands_grants_and_uses_host_principal_command(self):
        context = ['bound', 0]
        predicate = ['lam', ['binary', 'conjunction',
            ['binary', 'labelEqual', ['get', context, 'principal'], ['label', 'player']],
            ['binary', 'labelEqual', ['get', context, 'command'], ['label', 'play']]]]
        self.seed(authority=scoped(invoke={'play': ['player', 'reviewer'], 'review': ['player']}, predicate=predicate))
        self.assertEqual(self.call(self.invoke('outsider', intent='not-granted'))['data'], 'unauthorized')
        spoofed = self.invoke('reviewer', intent='spoofed')
        spoofed['input'] = {'principal': 'player', 'command': 'play'}
        self.assertEqual(self.call(spoofed)['data'], 'authority predicate refused')
        self.assertEqual(self.call(self.invoke(command='review', intent='other-command'))['data'], 'authority predicate refused')
        self.assertEqual(self.call(self.invoke())['kind'], 'committed')

    def test_policy_is_old_law_management_gate_and_empty_management_context(self):
        context = ['bound', 0]
        predicate = ['lam', ['binary', 'conjunction',
            ['binary', 'labelEqual', ['get', context, 'op'], ['label', 'law']],
            ['binary', 'labelEqual', ['get', context, 'command'], ['label', '']]]]
        self.seed(authority=scoped(predicate=predicate))
        # A new permissive protocol/predicate cannot authorize its own replacement.
        self.assertEqual(self.call(self.reprogram())['data'], 'authority predicate refused')
        revised = self.call(self.change_law(scoped(predicate=['lam', ['boolean', True]])))
        self.assertEqual(revised['kind'], 'committed')
        self.assertEqual(self.call(self.reprogram(intent='now-program', root=revised['data']['root']))['kind'], 'committed')

    def test_policy_false_wrong_kind_stuck_effect_and_unsupported_data_refuse(self):
        examples = [(['lam', ['boolean', False]], 'authority predicate refused'),
                    (['lam', ['nat', '1']], 'authority predicate must return Bool'),
                    (['lam', ['bound', 9]], 'Bend expression stuck'),
                    (['lam', ['perform', ['label', 'escape']]], 'Bend effects are forbidden')]
        for index, (predicate, error) in enumerate(examples):
            with self.subTest(predicate=predicate):
                self.profile = 'world'
                self.db = Path(self.tmp.name) / ('policy-' + str(index) + '.json')
                self.root = self.create('room', scoped(predicate=predicate))
                refusal = self.call(self.invoke())
                self.assertEqual(refusal['kind'], 'refused')
                self.assertIn(error, refusal['data'])
                self.assertEqual(self.inspect(), self.root)
        self.seed(authority=scoped(predicate=['lam', ['boolean', True]]))
        for index, bad in enumerate([None, [], -1, 0.25]):
            request = self.invoke(intent='unsupported-' + str(index))
            request['input'] = {'bad': bad}
            self.assertEqual(self.call(request)['kind'], 'refused')
            self.assertEqual(self.inspect(), self.root)

    def test_policy_and_body_and_transaction_share_one_budget(self):
        def burn(base):
            return ['fix', ['lam', ['lam', ['lam', ['ifZero', ['bound', 0], base,
                    ['app', ['bound', 3], ['bound', 0]]]]]], ['record', []]]
        predicate = ['lam', ['app', burn(['boolean', True]), ['nat', '1000']]]
        self.seed('transactions', scoped(predicate=predicate))
        # One bounded predicate plus cheap body fits.
        one = self.call(self.invoke(intent='one'))
        self.assertEqual(one['kind'], 'committed')
        current = one['data']['root']
        request = {'op': 'transaction', 'principal': 'player', 'intent': 'two-policies',
            'reads': {'room': current}, 'calls': [
                {'object': 'room', 'command': 'play', 'input': {}},
                {'object': 'room', 'command': 'play', 'input': {}}]}
        self.assertEqual(self.call(request)['data'], 'invocation budget exhausted')
        self.assertEqual(self.inspect(), current)
        # Programming also pays its predicate cost in the same transaction budget.
        request.update(principal='programmer', intent='two-management-policies', calls=[
            {'op': 'reprogram', 'object': 'room', 'protocol': protocol(), 'state': {'last': 'a'}},
            {'op': 'reprogram', 'object': 'room', 'protocol': protocol(), 'state': {'last': 'b'}}])
        self.assertEqual(self.call(request)['data'], 'invocation budget exhausted')
        self.assertEqual(self.inspect(), current)
        # A policy cannot each obtain 10,000 ticks independently from its own body.
        expensive = protocol()
        expensive['commands']['play']['set']['last'] = ['bend', burn(['nat', '0']), [['literal', 1000]]]
        replaced = self.call({**self.reprogram(root=current), 'protocol': expensive})
        self.assertEqual(replaced['kind'], 'committed')
        self.assertEqual(self.call(self.invoke(intent='policy-plus-body', root=replaced['data']['root']))['data'],
                         'invocation budget exhausted')
        self.assertEqual(self.inspect(), replaced['data']['root'])

    def test_diverging_predicate_is_bounded_and_its_refusal_is_retained(self):
        omega = ['lam', ['app', ['bound', 0], ['bound', 0]]]
        self.seed(authority=scoped(predicate=['lam', ['app', omega, omega]]))
        request = self.invoke()
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'invocation budget exhausted')
        self.assertEqual(self.call(request), refusal)
        self.assertEqual(self.inspect(), self.root)


if __name__ == '__main__':
    unittest.main()
