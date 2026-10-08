#!/usr/bin/env python3
"""Translate and exercise a protocol proposal in disposable local worlds.

No command installs into a live world or grants a principal authority.
"""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


translation = module('proposal_translation', 'scripts/translate.py')
world = module('proposal_world', 'scripts/world.py')
runtime_profile = module('proposal_runtime_profile', 'scripts/runtime_profile.py')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_keys(value, required, optional, label):
    if not isinstance(value, dict) or set(value) - required - optional or required - set(value):
        raise ValueError(f'{label}: missing or unknown fields')


def nonempty_string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label}: expected nonempty string')


def validate_scenarios(scenarios):
    """Validate assertions/selection only; Lean decides every protocol transition."""
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 64:
        raise ValueError('scenarios: expected 1..64 scenarios')
    names = set()
    total = 0
    for scenario in scenarios:
        exact_keys(scenario, {'name', 'law', 'steps'}, set(), 'scenario')
        nonempty_string(scenario['name'], 'scenario.name')
        if scenario['name'] in names:
            raise ValueError('duplicate scenario name')
        names.add(scenario['name'])
        if not isinstance(scenario['law'], list) or any(not isinstance(x, str) for x in scenario['law']):
            raise ValueError('scenario.law: expected string array')
        if not isinstance(scenario['steps'], list) or not scenario['steps']:
            raise ValueError('scenario.steps: expected nonempty array')
        total += len(scenario['steps'])
        if total > 256:
            raise ValueError('scenarios exceed 256 total steps')
        for step in scenario['steps']:
            exact_keys(step, {'principal', 'command', 'input', 'root', 'kind'},
                       {'state', 'error', 'result', 'outbox'}, 'step')
            nonempty_string(step['principal'], 'step.principal')
            nonempty_string(step['command'], 'step.command')
            if not isinstance(step['input'], dict):
                raise ValueError('step.input: expected object')
            if step['root'] not in ('initial', 'current'):
                raise ValueError('step.root: expected initial or current')
            if step['kind'] not in ('committed', 'refused'):
                raise ValueError('step.kind: expected committed or refused')
            if 'error' in step and (step['kind'] != 'refused' or not isinstance(step['error'], str)):
                raise ValueError('step.error: requires refusal and string')
            if any(key in step for key in ('state', 'result', 'outbox')) and step['kind'] != 'committed':
                raise ValueError('step state/result/outbox assertions require committed kind')
            if 'state' in step and not isinstance(step['state'], dict):
                raise ValueError('step.state: expected whole-state object')
            if 'outbox' in step and not isinstance(step['outbox'], list):
                raise ValueError('step.outbox: expected array')


def json_equal(left, right):
    """Structural JSON equality: true is never the number 1."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, (int, Decimal)) and isinstance(right, (int, Decimal)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(value, right[key]) for key, value in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right


def run_scenarios(protocol, scenarios, *, profile='world'):
    """Return deterministic receipts and assertion failures; use fresh worlds only."""
    validate_scenarios(scenarios)
    if profile not in world.PROFILES:
        raise ValueError('unknown local host profile: ' + str(profile))
    binary = world.PROFILES[profile][0]
    if not (ROOT / '.lake/build/bin' / binary).is_file():
        raise ValueError('build ' + binary + ' before checking proposals')
    results = []
    with tempfile.TemporaryDirectory(prefix='delvetalk-proposal-') as temporary:
        for index, scenario in enumerate(scenarios):
            database = Path(temporary) / f'{index}.json'
            installation = world.exchange(database, {
                'op': 'create', 'object': 'candidate', 'principal': 'proposal-fixture',
                'intent': 'install', 'protocol': protocol, 'law': scenario['law']}, profile=profile)
            result = {'name': scenario['name'], 'installation': installation, 'steps': [], 'failures': []}
            results.append(result)
            if installation.get('kind') != 'committed':
                result['failures'].append({'at': 'installation', 'expected': 'committed',
                                           'actual': installation.get('kind')})
                continue
            initial = installation['data']['root']
            for step_index, step in enumerate(scenario['steps']):
                root = initial if step['root'] == 'initial' else world.exchange(database, {
                    'op': 'inspect', 'object': 'candidate', 'principal': 'proposal-fixture'}, profile=profile)
                receipt = world.exchange(database, {
                    'op': 'invoke', 'object': 'candidate', 'principal': step['principal'],
                    'intent': f'step-{step_index}', 'expected': root,
                    'command': step['command'], 'input': step['input']}, profile=profile)
                result['steps'].append({'index': step_index, 'receipt': receipt})
                observed = {'kind': receipt.get('kind'), 'error': receipt.get('data')}
                if receipt.get('kind') == 'committed':
                    data = receipt['data']
                    observed.update(state=data['root']['state'], result=data['result'], outbox=data['outbox'])
                for key in ('kind', 'state', 'error', 'result', 'outbox'):
                    if key in step and (key not in observed or not json_equal(step[key], observed[key])):
                        result['failures'].append({'at': step_index, 'field': key,
                                                  'expected': step[key], 'actual': observed.get(key)})
    return results


def execution_pin(profile='world'):
    # Byte identity is provenance, not a proof that a binary was built from these sources.
    if profile not in world.PROFILES:
        raise ValueError('unknown local host profile: ' + str(profile))
    files = {**runtime_profile.file_hashes(profile),
             'scripts/propose.py': digest(Path(__file__).read_bytes())}
    identity = {'profile': 'delvetalk-local-v1', 'admissionProfile': profile, 'files': files,
                'python': list(sys.version_info[:3])}
    return {**identity, 'sha256': digest(translation.canonical(identity))}


def propose(syntax, source, scenario_source, *, profile='world'):
    if profile not in world.PROFILES:
        raise ValueError('unknown local host profile: ' + str(profile))
    if len(source) > 512 * 1024 or len(scenario_source) > 1024 * 1024:
        raise ValueError('proposal source exceeds 512 KiB or scenarios exceed 1 MiB')
    artifact = translation.translate(syntax, source)
    if artifact['target'] == 'local-protocol-v1':
        protocol, selection = artifact['lowered'], 'lowered'
    elif artifact['target'] == 'spween-protocol-bundle-v1':
        protocol, selection = artifact['lowered']['protocol'], 'lowered.protocol'
    else:
        raise ValueError('proposal syntax must target local-protocol-v1 or spween-protocol-bundle-v1')
    scenarios = translation.load_json(scenario_source.decode('utf-8'))
    validate_scenarios(scenarios)
    candidate = {'format': 'delvetalk-proposal-v1', 'artifact': artifact,
                 'host': {'target': 'local-protocol-v1', 'selection': selection, 'admissionProfile': profile,
                          'protocol_sha256': digest(translation.canonical(protocol))},
                 'scenarios': {'source': scenario_source.decode('utf-8'),
                               'source_sha256': digest(scenario_source), 'value': scenarios,
                               'sha256': digest(translation.canonical(scenarios))}}
    candidate['id'] = digest(translation.canonical(candidate))
    execution = execution_pin(profile)
    outcomes = run_scenarios(protocol, scenarios, profile=profile)
    if execution_pin(profile) != execution:
        raise ValueError('host or proposal runner bytes changed during execution; rerun in a stable checkout')
    report = {'format': 'delvetalk-proposal-report-v1', 'candidate': candidate,
              'execution': execution, 'outcomes': outcomes,
              'passed': all(not result['failures'] for result in outcomes),
              'authority': 'none; isolated local fixture observations only'}
    report['id'] = digest(translation.canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--syntax', required=True, help='explicit reviewed syntax ID/version')
    parser.add_argument('--profile', choices=world.PROFILES, default='world', help='operator-selected host for every scenario')
    parser.add_argument('source', type=Path)
    parser.add_argument('scenarios', type=Path)
    parser.add_argument('-o', '--output', type=Path, help='new report file; existing paths are refused')
    args = parser.parse_args()
    try:
        # Never replace a source, live world, or prior report, including through a symlink.
        if args.output and (args.output.exists() or args.output.is_symlink()):
            raise ValueError('output already exists; select a new report path')
        report = propose(args.syntax, args.source.read_bytes(), args.scenarios.read_bytes(), profile=args.profile)
        output = translation.canonical(report) + b'\n'
        if args.output:
            with args.output.open('xb') as stream:
                stream.write(output)
        else:
            sys.stdout.buffer.write(output)
        return 0 if report['passed'] else 1
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, RecursionError) as error:
        print(f'propose: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
