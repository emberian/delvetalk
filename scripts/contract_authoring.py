"""Compiler custody for source-owned ContractCandidate preparation and release."""
from copy import deepcopy
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk

obend = desk.module('contract_obend', 'syntaxes/obend_object.py')
FORMAT = 'delvetalk-contract-release-v1'


def execution_profile():
    return {'profile': 'compiled', 'files': desk.runtime_profile.hash_paths(
        (*desk.execution_paths('compiled'), 'scripts/contract_authoring.py',
         'protocols/contract-workshop/generate.py', 'protocols/contract-workshop/Workshop.obend',
         'protocols/contract-workshop/ContractCandidate.obend'), root=desk.ROOT)}


def source_request(inputs, build, metadata):
    """Supply retained compiler data; the captured source owner chooses the turn."""
    desk.source_store.verify_bound_material(build['sourceBindings'], build['sourceMaterial'])
    invitation = {'format': desk.source_offers.FORMAT, 'object': inputs['candidate'],
        'root': inputs['candidateRoot'], 'entry': 'prepareContract',
        'observations': [{'object': inputs['target'], 'root': inputs['targetRoot'],
                          'inspectState': False, 'inspectLaw': True}],
        'title': 'Source promise', 'label': 'Install this source promise', 'fields': []}
    outcome = desk.source_offers.prepare_value(invitation, inputs['principal'], inputs['intent'],
        {'entry': inputs['entry'], 'metadata': metadata})
    if outcome['kind'] != 'ready':
        raise desk.source_offers.PreparationOutcome(outcome)
    return outcome['request']


def validate(proposal):
    """Validate custody framing, never source types or specification meaning."""
    if not isinstance(proposal, dict) or set(proposal) != {
            'format', 'inputs', 'request', 'executionProfile', 'build', 'sourceBinding', 'metadata'
            } or proposal['format'] != FORMAT:
        raise ValueError('invalid contract release proposal')
    inputs, build = proposal['inputs'], proposal['build']
    if set(inputs) != {'candidate', 'target', 'principal', 'intent', 'candidateRoot', 'targetRoot', 'entry'}:
        raise ValueError('invalid contract release inputs')
    state = desk.candidate_state(inputs['candidateRoot'])
    if (state['target'] != inputs['target']
            or state['proposal'] != build['proposal'] or state['protocol'] != build['protocol']
            or state['artifact'] != desk.digest(build) or build.get('passed') is not True):
        raise ValueError('contract source differs from captured checked candidate')
    binding = proposal['sourceBinding']
    if (not isinstance(binding, dict) or set(binding) != {'entry', 'sourcesSha256', 'packetSha256'}
            or binding['entry'] != inputs['entry']):
        raise ValueError('contract observation differs from selected source export')
    expected = source_request(inputs, build, proposal['metadata'])
    if proposal['request'] != expected:
        raise ValueError('contract release plan differs from its captured source and intent')
    return proposal


class Contracts:
    def __init__(self, client):
        if client.profile != 'compiled':
            raise ValueError('source contracts require the compiled receiving host')
        self.client = client

    def create(self, object_id, principal, intent, law):
        protocol = desk.module('contract_candidate', 'protocols/contract-workshop/generate.py').candidate()
        return self.client.exchange({'op': 'create', 'object': object_id, 'principal': principal,
                                     'intent': intent, 'protocol': protocol, 'law': law})

    def path(self, principal, intent):
        return self.client.artifact_store / 'contract-attempts' / (desk.digest([principal, intent]) + '.json')

    def prepare(self, candidate, target, principal, intent, candidate_root, target_root,
                *, entry='contract'):
        inputs = deepcopy({'candidate': candidate, 'target': target, 'principal': principal,
                           'intent': intent, 'candidateRoot': candidate_root,
                           'targetRoot': target_root, 'entry': entry})
        path = self.path(principal, intent)
        if path.exists():
            retained = desk.loads(path.read_bytes())
            if retained['inputs'] != inputs:
                raise ValueError('contract intent is already bound to another proposal')
            if self.client.retained_reply(retained['request']) is not None:
                return retained
            return validate(retained)
        state = desk.candidate_state(candidate_root)
        if not desk.is_source_desk_protocol(candidate_root['protocol']):
            raise ValueError('contract release requires a reviewed SourceDesk body')
        build = desk.load_artifact(self.client.artifact_store, state['artifact'])
        if (build.get('passed') is not True or build['proposal'] != state['proposal']
                or build['protocol'] != state['protocol'] or build['target'] != target
                or build['migration'] != state['migration']):
            raise ValueError('candidate differs from its retained checked build')
        source, _, bindings = desk.proposal_material(state['proposal'], self.client.artifact_store)
        desk.source_store.verify_bound_material(bindings, build['sourceMaterial'])
        if bindings != build['sourceBindings']:
            raise ValueError('candidate source bindings differ from checked build')
        syntax = bindings['syntax']
        if syntax not in ('objective-bend-spell@2', 'objective-bend-spell@3'):
            raise ValueError('contract requires an explicit Objective Bend source candidate')
        modules = ([{'name': item['name'], 'source': item['source']} for item in source['modules']]
                   if isinstance(source, dict) else [{'name': 'Main', 'source': source.decode('utf-8')}])
        if not isinstance(entry, str) or not entry or len(entry.encode()) > 128:
            raise ValueError('specification export requires a bounded entry name')
        execution = execution_profile()
        deadline = time.monotonic() + 30
        compiled = obend._native({'op': 'compile', 'modules': modules, 'entry': entry,
                                  'limits': obend.LIMITS}, deadline)
        observed = obend._native({'op': 'inspect-spec-v1', 'artifact': compiled['artifact'],
                                  'limits': obend.LIMITS}, deadline)
        request = source_request(inputs, build, observed['value'])
        if execution != execution_profile():
            raise ValueError('contract preparation runtime changed')
        value = {'format': FORMAT, 'inputs': inputs, 'request': request,
                 'executionProfile': execution, 'build': build,
                 'sourceBinding': observed['sourceBinding'], 'metadata': observed['value']}
        retained = desk.immutable(path, value)
        if retained != value:
            raise ValueError('contract intent conflicts with a concurrently retained proposal')
        return retained

    def release(self, proposal, *, before_exchange=None):
        """Recover an exact receipt first; otherwise recheck custody and submit."""
        if proposal.get('format') != FORMAT:
            raise ValueError('unknown contract release proposal')
        request = proposal['request']
        retained = self.client.retained_reply(request)
        if retained is not None:
            return retained
        validate(proposal)
        inputs = proposal['inputs']
        original = desk.loads(self.path(inputs['principal'], inputs['intent']).read_bytes())
        if original != proposal:
            raise ValueError('contract release differs from its immutable reviewed proposal')
        if proposal['executionProfile'] != execution_profile():
            raise ValueError('contract release runtime changed')
        desk.proposal_material(desk.candidate_state(inputs['candidateRoot'])['proposal'], self.client.artifact_store)
        desk.preserve_build_dependencies(self.client.artifact_store, proposal['build'])
        if before_exchange is not None:
            before_exchange()
        return self.client.exchange(request)

    def restore(self, proposal):
        """Check the captured source turn and retain its bytes; this grants no authority."""
        if proposal.get('format') != FORMAT:
            raise ValueError('unknown contract release proposal')
        if self.client.retained_reply(proposal['request']) is None:
            validate(proposal)
        inputs = proposal['inputs']
        existing = desk.immutable(self.path(inputs['principal'], inputs['intent']), proposal)
        if existing != proposal:
            raise ValueError('restored contract intent conflicts with retained attempt')
        return existing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create')
    for name in ('candidate', 'principal', 'intent'):
        create.add_argument('--' + name, required=True)
    create.add_argument('--law', type=Path, required=True)
    prepare = commands.add_parser('prepare')
    for name in ('candidate', 'target', 'principal', 'intent'):
        prepare.add_argument('--' + name, required=True)
    prepare.add_argument('--candidate-root', type=Path, required=True)
    prepare.add_argument('--target-root', type=Path, required=True)
    prepare.add_argument('--entry', default='contract')
    release = commands.add_parser('release')
    release.add_argument('proposal', type=Path)
    args = parser.parse_args()
    authoring = Contracts(desk.Desk(args.database, args.artifacts, profile='compiled'))
    if args.command == 'create':
        result = authoring.create(args.candidate, args.principal, args.intent, desk.loads(args.law.read_bytes()))
    elif args.command == 'prepare':
        result = authoring.prepare(args.candidate, args.target, args.principal, args.intent,
            desk.loads(args.candidate_root.read_bytes()), desk.loads(args.target_root.read_bytes()), entry=args.entry)
    else:
        result = authoring.release(desk.loads(args.proposal.read_bytes()))
    sys.stdout.buffer.write(desk.canonical(result) + b'\n')
    return int(result.get('kind') == 'refused')


if __name__ == '__main__':
    raise SystemExit(main())
