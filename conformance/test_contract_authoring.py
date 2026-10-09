"""Textual specifications reach current law through actual checked source desks."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import contract_authoring
import desk
import source_store

SOURCE = (ROOT / 'protocols/contract-workshop/Counter.obend').read_bytes()
EXAMPLES = (ROOT / 'protocols/contract-workshop/counter.examples').read_bytes()


class ContractAuthoring(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory(prefix='contract-authoring-')
        self.addCleanup(home.cleanup)
        self.home = Path(home.name)
        self.client = desk.Desk(self.home / 'world.json', self.home / 'artifacts', profile='compiled')
        self.contracts = contract_authoring.Contracts(self.client)
        self.serial = 0
        self.names = {}
        self.target_law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'add': ['visitor']},
                           'reprogram': ['maker'], 'law': ['steward']}
        self.candidate_law = {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'submit': ['maker'], 'compiled': ['compiler'], 'failed': ['compiler'],
                       'adopt': ['steward']}, 'reprogram': [], 'law': ['owner']}

    def call(self, request):
        self.serial += 1
        return self.client.exchange({'principal': 'owner', 'intent': 'call-' + str(self.serial), **request})

    def candidate(self, name, source=SOURCE, *, syntax='objective-bend-spell@2', migration=None):
        if isinstance(source, list):
            manifest = source_store.seal_modules([{'name': item['name'],
                'sourceRef': source_store.store_bytes(self.client.artifact_store, item['source'].encode())}
                for item in source])
            proposal = source_store.prepare_module_proposal(self.client.artifact_store, manifest, EXAMPLES, syntax=syntax)
        else:
            proposal = source_store.prepare_proposal(self.client.artifact_store, syntax, source, EXAMPLES)
        made = self.contracts.create(name, 'owner', 'create-' + name, self.candidate_law)
        self.assertEqual(made['kind'], 'committed', made)
        submitted = self.client.submit_refs(name, 'maker', 'submit-' + name, made['data']['root'],
                                           proposal, {'count': 0} if migration is None else migration, 'counter')
        self.assertEqual(submitted['kind'], 'committed', submitted)
        checked = self.client.check(name, 'compiler', 'check-' + name, submitted['data']['root'])
        self.assertEqual(checked['kind'], 'committed', checked)
        root = self.client.inspect(name)
        self.assertEqual(desk.candidate_state(root)['status'], 'ready', desk.candidate_state(root)['diagnostics'])
        self.names[desk.digest(root)] = name
        return root

    def target(self, candidate):
        made = self.call({'op': 'create', 'object': 'counter', 'protocol': desk.candidate_state(candidate)['protocol'],
                          'law': self.target_law})
        self.assertEqual(made['kind'], 'committed', made)
        return made['data']['root']

    def prepare(self, candidate, root, intent='promise', entry='contract'):
        return self.contracts.prepare(self.names[desk.digest(candidate)], 'counter', 'steward', intent,
                                      candidate, root, entry=entry)

    def test_source_owned_export_two_people_and_exact_restore_retry(self):
        candidate = self.candidate('proposal')
        root = self.target(candidate)
        with self.assertRaisesRegex(ValueError, 'Specification|specification'):
            self.prepare(candidate, root, intent='ordinary-method-is-not-contract', entry='add')
        proposal = self.prepare(candidate, root)
        self.assertEqual(proposal['request']['calls'][1]['law']['invoke'], root['law']['invoke'])
        denied = deepcopy(proposal['request'])
        denied.update(principal='maker', intent='maker-cannot-install-law')
        self.assertEqual(self.call(denied)['kind'], 'refused')
        self.assertEqual(self.client.inspect('proposal'), candidate)
        tampered = deepcopy(proposal)
        tampered['request']['calls'][1]['law']['law'] = ['maker']
        with self.assertRaisesRegex(ValueError, 'plan differs'):
            self.contracts.release(tampered)
        # The actual receiving host commits; the transport loses its reply.
        native_exchange = self.client.exchange
        outcomes = []
        def lose_reply(request):
            outcomes.append(native_exchange(request))
            raise OSError('reply lost after receiving admission')
        with patch.object(self.client, 'exchange', side_effect=lose_reply):
            with self.assertRaises(OSError): self.contracts.release(proposal)
        committed = self.contracts.release(proposal)
        self.assertEqual(committed, outcomes[0])
        self.assertEqual(committed['kind'], 'committed', committed)
        with patch.object(contract_authoring, 'source_request', side_effect=AssertionError('must recover receipt first')):
            self.assertEqual(self.prepare(candidate, root), proposal)
            self.assertEqual(self.contracts.restore(proposal), proposal)
        governed = self.client.inspect('counter')
        self.assertEqual(governed['law']['contract']['metadata'], proposal['metadata'])
        self.assertEqual(governed['protocol'], root['protocol'])
        self.assertEqual(governed['state'], root['state'])
        # Native receipt recovery precedes missing source custody and current law.
        locked = self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
            'expected': governed, 'law': {**governed['law'], 'law': []}})
        self.assertEqual(locked['kind'], 'committed', locked)
        # Export/replay the real admitted history, including exact source bytes
        # and the source-derived release journal, then recover from a fresh client.
        attachments = {}
        build_path = self.client.artifact_store / 'builds' / (desk.candidate_state(candidate)['artifact'] + '.json')
        for receipt in desk.world.snapshot(self.client.database)['receipts']:
            refs = source_store.collect_references(receipt['request'])
            if refs:
                attachments[desk.digest(receipt['request'])] = [build_path, *[
                    source_store.blob_path(self.client.artifact_store, item['sha256']) for item in refs]]
        bundle = self.home / 'history'
        manifest = desk.history.export_history(self.client.database, bundle, profile='compiled',
            attachments=attachments, journals=self.client.artifact_store / 'contract-attempts',
            inline_reprogram=True)
        restored_db = self.home / 'restored.json'
        desk.history.replay(desk.loads((bundle / 'manifest.json').read_bytes()), bundle, restored_db,
            expected_genesis=manifest['genesis'], expected_head=manifest['head'])
        restored = contract_authoring.Contracts(desk.Desk(restored_db, self.home / 'restored-artifacts',
                                                         profile='compiled'))
        self.assertEqual(restored.release(proposal), committed)
        self.assertEqual(restored.client.inspect('counter'), locked['data']['root'])
        ref = desk.candidate_state(candidate)['proposal']['sourceRef']
        source_store.blob_path(self.client.artifact_store, ref['sha256']).unlink()
        self.contracts.path('steward', 'promise').unlink()
        self.assertEqual(self.contracts.release(proposal), committed)
        self.contracts.restore(proposal)
        self.assertEqual(self.contracts.release(proposal), committed)
        with self.assertRaises(ValueError): self.prepare(candidate, root, entry='add')

    def test_missing_tampered_source_stale_root_and_revoked_management(self):
        candidate = self.candidate('proposal')
        root = self.target(candidate)
        proposal = self.prepare(candidate, root)
        ref = desk.candidate_state(candidate)['proposal']['sourceRef']
        path = source_store.blob_path(self.client.artifact_store, ref['sha256'])
        raw = path.read_bytes()
        path.write_bytes(raw + b'\n')
        with self.assertRaises(ValueError): self.contracts.release(proposal)
        path.write_bytes(raw)
        changed = self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
                            'expected': root, 'law': {**root['law'], 'law': []}})
        self.assertEqual(changed['kind'], 'committed', changed)
        stale = self.contracts.release(proposal)
        self.assertEqual(stale['kind'], 'refused', stale)
        self.assertEqual(self.client.inspect('proposal'), candidate)
        revoked = self.prepare(candidate, changed['data']['root'], intent='revoked')
        reply = self.contracts.release(revoked)
        self.assertEqual(reply['kind'], 'refused', reply)
        self.assertIn('unauthorized', str(reply))
        self.assertEqual(self.client.inspect('proposal'), candidate)

    def test_candidate_release_revocation_blocks_management_even_with_target_grant(self):
        candidate = self.candidate('proposal')
        root = self.target(candidate)
        revoked_law = deepcopy(candidate['law'])
        revoked_law['invoke']['adopt'] = []
        revoked = self.call({'op': 'law', 'object': 'proposal', 'principal': 'owner',
                             'expected': candidate, 'law': revoked_law})
        self.assertEqual(revoked['kind'], 'committed', revoked)
        candidate = revoked['data']['root']
        self.names[desk.digest(candidate)] = 'proposal'
        proposal = self.prepare(candidate, root)
        refused = self.contracts.release(proposal)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('unauthorized', str(refused))
        self.assertEqual(self.client.inspect('counter'), root)
        self.assertEqual(self.client.inspect('proposal'), candidate)

    def test_model_contract_reads_large_source_from_retained_candidate(self):
        typed = SOURCE.decode().replace('record View:',
            'record Child:\n  key: String\n  label: String\n  object: String\n  panel: String\n'
            'sum Children:\n  nil: {}\n  cons: {head: Child, tail: Children}\nrecord View:')
        typed = typed.replace('record Context:\n  object: String\n  principal: String',
            'record Origin:\n  kind: String\n  object: String\n  command: String\n'
            '  immediatelyPrevious: Bool\nrecord Context:\n  object: String\n  principal: String\n'
            '  inputOrigin: Origin')
        typed = typed.replace('  actions: {add: Action}', '  children: Children\n  actions: {add: Action}')
        typed = typed.replace('prose: "Its method promise belongs to the current law.", actions:',
            'prose: "Its method promise belongs to the current law.", children: Children.nil(), actions:')
        padding = '# Retained source is not an authored form contribution.\n' * 650
        typed += '\n' + padding
        modules = [{'name': 'Notes', 'source': 'edition ObjectiveBend 1\n' + padding + 'def value() -> Nat:\n  0n\n'},
                   {'name': 'Main', 'source': typed}]
        self.assertGreater(sum(len(item['source'].encode()) for item in modules), 65536)
        model = {'model': desk.source_object.data({'count': 0})}
        candidate = self.candidate('typed', modules, syntax='objective-bend-spell@3', migration=model)
        root = self.target(candidate)
        proposal = self.prepare(candidate, root)
        contract = proposal['request']['calls'][1]['law']['contract']
        self.assertEqual(contract['stateProfile'], 'model')
        self.assertEqual(contract['package']['modules'], modules)
        result = self.contracts.release(proposal)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(self.client.inspect('counter')['state'], root['state'])

    def test_source_workshop_requires_projected_law_and_preserves_v4_guard(self):
        source = """edition ObjectiveBend 1
import ./Preparation.obend as P
record Context:
  object: String
  principal: String
  currentLaw: P.Value
  nextLaw: P.Value
def amend(context: Context) -> Bool:
  (context.principal == "owner" || context.principal == "steward") && P.text(P.get(P.get(context.currentLaw, "amendment"), "config")) == "keep" && P.text(P.get(P.get(context.nextLaw, "amendment"), "config")) == "keep"
"""
        self.target_law.update(profile='delvetalk-scoped-law-v4',
            predicate=['lam', ['boolean', True]], invariant=['lam', ['boolean', True]],
            amendment={'profile': 'delvetalk-source-amendment-v1', 'config': 'keep',
                'package': {'modules': [
                    {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
                    {'name': 'Amendment', 'source': source}], 'entry': 'amend'}})
        candidate = self.candidate('promise-source')
        root = self.target(candidate)
        proposal = self.prepare(candidate, root)
        revised = proposal['request']['calls'][1]['law']
        self.assertEqual({key: value for key, value in revised.items() if key != 'contract'}, root['law'])
        native_prepare = desk.source_offers.prepare_value
        def without_law(invitation, *args, **kwargs):
            invitation = deepcopy(invitation)
            invitation['observations'][0]['inspectLaw'] = False
            return native_prepare(invitation, *args, **kwargs)
        with patch.object(desk.source_offers, 'prepare_value', without_law):
            with self.assertRaisesRegex(ValueError, 'explicit scoped law'):
                contract_authoring.source_request(proposal['inputs'], proposal['build'], proposal['metadata'])
        result = self.contracts.release(proposal)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(self.client.inspect('counter')['law'], revised)

    def test_checked_extra_method_upgrade_then_incompatible_contract_refuses(self):
        candidate = self.candidate('first')
        root = self.target(candidate)
        installed = self.contracts.release(self.prepare(candidate, root))
        self.assertEqual(installed['kind'], 'committed', installed)
        root = self.client.inspect('counter')
        # The old promise allows an additional method; strengthening the promise
        # happens after the compatible implementation upgrade.
        source = SOURCE.decode().replace('  add(state: State, input: Input, context: Context) -> Decision\n',
            '  add(state: State, input: Input, context: Context) -> Decision\n'
            '  reset(state: State, input: {}, context: Context) -> Decision\n')
        source = source.replace('  claim preservesCount',
            '  def reset(state: State, input: {}, context: Context) -> Decision:\n'
            '    {accepted: true, reason: "", state: {count: 0}, result: 0}\n  claim preservesCount')
        source += '\ndef reset(state: State, input: {}, context: Context) -> Decision:\n'
        source += '  {accepted: true, reason: "", state: {count: 0}, result: 0}\n'
        source = source.replace('methods: {add: Method}', 'methods: {add: Method, reset: {label: String, fields: {}}}')
        source = source.replace('methods: {add: {label: "Add to the counter", fields: {amount: {type: "nat", maximum: 100}}}}',
            'methods: {add: {label: "Add to the counter", fields: {amount: {type: "nat", maximum: 100}}}, reset: {label: "Reset", fields: {}}}')
        upgraded = self.candidate('broader', source.encode())
        replaced = self.call({'op': 'reprogram', 'object': 'counter', 'principal': 'maker', 'expected': root,
            'protocol': desk.candidate_state(upgraded)['protocol'], 'state': root['state']})
        self.assertEqual(replaced['kind'], 'committed', replaced)
        strengthened = self.contracts.release(self.prepare(upgraded, replaced['data']['root'], intent='broader'))
        self.assertEqual(strengthened['kind'], 'committed', strengthened)
        root = self.client.inspect('counter')
        # Keep the candidate's ordinary implementation intact and export a
        # separate incompatible specification instead, so its scenarios still run.
        bad = SOURCE.decode().replace('def contract() -> Specification<Counter>:',
            'record NarrowInput:\n  amount: String\nrecord Narrow:\n'
            '  add(state: State, input: NarrowInput, context: Context) -> Decision\n'
            'spec NarrowContract for Narrow:\n'
            '  def add(state: State, input: NarrowInput, context: Context) -> Decision:\n'
            '    {accepted: true, reason: "", state: state, result: state.count}\n'
            'def incompatible() -> Specification<Narrow>:\n  NarrowContract\n\n'
            'def contract() -> Specification<Counter>:')
        narrow = self.candidate('narrow', bad.encode())
        attempt = self.prepare(narrow, root, intent='narrow', entry='incompatible')
        refused = self.contracts.release(attempt)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('signature mismatch', str(refused))
        self.assertEqual(self.client.inspect('counter'), root)
        self.assertEqual(self.client.inspect('narrow'), narrow)


if __name__ == '__main__': unittest.main()
