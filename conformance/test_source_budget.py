"""Source policy and body spend one receiving ledger, not independent allowances."""
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from test_authority import ROOT, law, source_object, world
import opaque_offers

FIXTURES = ROOT / 'conformance/fixtures/source-budget'
WORK = {'name': 'Work', 'source': (FIXTURES / 'Work.obend').read_text()}
BODY = {'name': 'Counter', 'source': (FIXTURES / 'Counter.obend').read_text()}
GUARD = {'name': 'Guard', 'source': (FIXTURES / 'Guard.obend').read_text()}
POLICY_MODULES = [{'name': name, 'source': (ROOT / ('world/lib/prelude/' + name + '.obend')).read_text()}
                  for name in ['List', 'Preparation']] + [WORK, GUARD]


def native(request):
    reply = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-obend')],
        input=json.dumps(request) + '\n', text=True, capture_output=True, timeout=20, check=True)
    return json.loads(reply.stdout)


class SourceBudget(unittest.TestCase):
    def test_source_derived_preparation_input_stays_private(self):
        modules = source_object.read_closure([
            ('SecretInvitation', FIXTURES / 'SecretInvitation.obend')])
        protocol = source_object.load(modules, syntax='objective-bend-object')
        authority = {'profile': 'delvetalk-scoped-law', 'read': ['owner'],
            'invoke': {'accept': ['player']}, 'reprogram': ['owner'],
            'law': ['owner'], 'view': {'main': 'public'}}
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'world.json'
            created = world.exchange(db, {'op': 'create', 'object': 'counter',
                'principal': 'owner', 'intent': 'create', 'protocol': protocol,
                'law': authority}, profile='compiled')
            self.assertEqual(created['kind'], 'committed', created)
            visible = world.opaque_view(db, 'counter', principal='player', audience='public')
            invitation = opaque_offers.capture(db, 'counter', visible, 'player')['accept']
            request = opaque_offers.prepare(db, invitation, 'player', 'private-input', {})
            receipt = world.exchange(db, request, profile='compiled')
            self.assertEqual(receipt['kind'], 'committed', receipt)
            self.assertEqual(receipt['data']['results'], [True])
            for value in (visible, invitation, request, receipt):
                encoded = world.wire_dumps(value)
                self.assertNotIn('private-derived-input-secret', encoded)
                self.assertNotIn('"protocol"', encoded)
                self.assertNotIn('"state"', encoded)
            self.assertEqual(world.exchange(db, request, profile='compiled'), receipt)
            self.assertIn('private-derived-input-secret', world.wire_dumps(world.snapshot(db)['opaqueCustody']))

    def test_invitation_preparation_and_body_share_receiving_budget(self):
        modules = source_object.read_closure([
            ('Work', FIXTURES / 'Work.obend'), ('Invitation', FIXTURES / 'Invitation.obend')])
        protocol = source_object.load(modules, syntax='objective-bend-object')
        authority = {'profile': 'delvetalk-scoped-law', 'read': ['owner'],
            'invoke': {'add': ['owner', 'player']}, 'reprogram': ['owner'],
            'law': ['owner'], 'view': {'main': 'public'}}
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'world.json'
            created = world.exchange(db, {'op': 'create', 'object': 'counter',
                'principal': 'owner', 'intent': 'create', 'protocol': protocol,
                'law': authority}, profile='compiled')
            self.assertEqual(created['kind'], 'committed', created)
            # The body fits independently in the declared receiving allowance.
            body = world.exchange(db, {'op': 'invoke', 'object': 'counter',
                'principal': 'owner', 'intent': 'body-only', 'expected': created['data']['root'],
                'command': 'add', 'input': {}}, profile='compiled')
            self.assertEqual(body['kind'], 'committed', body)
            before = body['data']['root']
            visible = world.opaque_view(db, 'counter', principal='player', audience='public')
            invitation = opaque_offers.capture(db, 'counter', visible, 'player')['add']
            # Standalone bounded source preparation also fits. Its private plan
            # and the body together exceed the same fresh receiving allowance.
            request = opaque_offers.prepare(db, invitation, 'player', 'joint-budget', {})
            refused = world.exchange(db, request, profile='compiled')
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertEqual(world.exchange(db, request, profile='compiled'), refused)
            self.assertEqual(world.query(db, {'op': 'inspect', 'object': 'counter',
                'principal': 'owner'}), before)

    def test_guard_and_body_individually_fit_but_combined_refuse_atomically(self):
        count = 3000
        state = source_object.data({'count': 0})
        context = source_object.data({'object': 'counter', 'principal': 'player', 'inputOrigin': {
            'kind': 'literal', 'object': '', 'command': '', 'program': '', 'immediatelyPrevious': False}})
        cases = [([WORK, BODY], 'add', [state, source_object.data({'amount': count}), context]),
                 (POLICY_MODULES, 'predicate', [source_object.data({'object': 'counter', 'principal': 'player', 'op': 'create', 'command': '', 'state': {'count': 0}, 'input': {}}), source_object.value(count)])]
        cases[1][2][0]['fields'][-1]['value'] = {'tag': 'variant', 'label': 'none', 'payload': source_object.data({})}
        costs = []
        for modules, entry, arguments in cases:
            compiled = native({'op': 'compile', 'modules': modules, 'entry': entry})
            self.assertEqual(compiled['status'], 'compiled', compiled)
            result = native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': arguments})
            self.assertEqual(result['status'], 'finished', result)
            costs.append(result['ticksUsed'] + result['conversionNodes'])
        self.assertTrue(all(0 < cost < 100000 for cost in costs), costs)
        self.assertGreater(sum(costs), 100000, costs)
        program = {'profile': 'delvetalk-local-v1', 'initial': {'model': state}, 'commands': {
            'add': {'transition': {'profile': 'delvetalk-source-transition',
                                 'package': {'modules': [WORK, BODY], 'entry': 'add'}}}}}
        policy = {'package': {'modules': POLICY_MODULES, 'entry': 'predicate'}, 'config': count}
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'world.json'
            serial = 0
            def call(request):
                nonlocal serial
                serial += 1
                return world.exchange(db, {'principal': 'player', 'intent': str(serial), **request}, profile='compiled')
            roots = {}
            for name, authority in [('body', law()), ('guard', law(predicate=policy)), ('both', law(predicate=policy))]:
                created = call({'op': 'create', 'object': name, 'protocol': program, 'law': authority})
                self.assertEqual(created['kind'], 'committed', created)
                roots[name] = created['data']['root']
            for name, amount in [('body', count), ('guard', 0)]:
                receipt = call({'op': 'invoke', 'object': name, 'command': 'add',
                                'expected': roots[name], 'input': {'amount': amount}})
                self.assertEqual(receipt['kind'], 'committed', receipt)
            request = {'intent': 'combined', 'op': 'invoke', 'object': 'both', 'command': 'add',
                       'expected': roots['both'], 'input': {'amount': count}}
            refusal = call(request)
            self.assertEqual(refusal['kind'], 'refused', refusal)
            self.assertIn('tickExhausted', refusal['data'])
            self.assertEqual(call(request), refusal)
            self.assertEqual(world.query(db, {'op': 'inspect', 'object': 'both', 'principal': 'reader'}), roots['both'])
            transaction = {'intent': 'two-guards', 'op': 'transaction', 'reads': {'both': roots['both']},
                           'calls': [{'object': 'both', 'command': 'add', 'input': {'amount': 0}},
                                     {'object': 'both', 'command': 'add', 'input': {'amount': 0}}]}
            refusal = call(transaction)
            self.assertEqual(refusal['kind'], 'refused', refusal)
            self.assertIn('tickExhausted', refusal['data'])
            self.assertEqual(call(transaction), refusal)
            self.assertEqual(world.query(db, {'op': 'inspect', 'object': 'both', 'principal': 'reader'}), roots['both'])


if __name__ == '__main__':
    unittest.main()
