#!/usr/bin/env python3
"""Compare actual law-owned composed source turns on two explicit native hosts.

Physical fixture framing only; source behavior is the authored Counter fixture.
Both hosts receive identical full world/request frames and must return identical
worlds and receipts, including deterministic refusal and retained retry.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
from process_custody import run_native
from conformance.test_current_source_contract import SOURCE, package, record, nat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--package-binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 10: parser.error('repeats must be 2..10')
    def call(binary, request):
        result = run_native([str(binary.resolve())], input=json.dumps(request, separators=(',', ':')).encode()+b'\n',
                            cwd=ROOT, timeout=30, cpu_seconds=30,
                            stdout_limit=8*1024*1024, stderr_limit=64*1024)
        result.check_returncode()
        return json.loads(result.stdout)
    artifact = call(args.package_binary, {'op': 'compile', **package('contractMetadata')})['artifact']
    metadata = call(args.package_binary, {'op': 'run-data-v1', 'artifact': artifact, 'arguments': []})['value']
    protocol = {'profile': 'delvetalk-local-v1', 'initial': {'model': record(count=nat(0))},
                'commands': {name: {'transition': {'profile': 'delvetalk-source-transition',
                    'package': package(name), 'inputCodec': 'data'}} for name in ('add', 'damage')}}
    law = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker'], 'damage': ['maker']},
           'reprogram': ['maker'], 'law': ['maker'], 'contract': {
               'profile': 'delvetalk-source-contract-v1', 'package': package('contract'),
               'stateProfile': 'model', 'metadata': metadata}}
    initial = {'world': {'objects': {}, 'receipts': []}, 'request': {'op': 'create', 'object': 'counter',
               'principal': 'maker', 'intent': 'new-counter', 'protocol': protocol, 'law': law}}
    made = call(args.baseline, initial)
    assert call(args.binary, initial) == made
    assert made['reply']['kind'] == 'committed', made
    world = made['world']; root = world['objects']['counter']
    args.output.with_suffix('.counter-frame.json').write_text(json.dumps({'world': world, 'request': {
        'op': 'invoke', 'object': 'counter', 'command': 'add', 'expected': root,
        'input': record(amount=nat(1)), 'principal': 'maker', 'intent': 'budget-probe'}})+'\n')
    report = {'scope': __doc__, 'sourceSha256': hashlib.sha256(SOURCE.encode()).hexdigest(),
              'binarySha256': {name: hashlib.sha256(binary.read_bytes()).hexdigest()
                  for name, binary in [('baseline', args.baseline), ('cached', args.binary)]}, 'results': []}
    cases = [(f'{count}-source-calls', [{'object': 'counter', 'command': 'add', 'input': record(amount=nat(1))}]
             * count, 'committed') for count in (1, 4, 8)]
    cases += [('atomic-refusal', [{'object': 'counter', 'command': name, 'input': record(amount=nat(1))}
                                for name in ('add', 'damage')], 'refused')]
    revised = copy.deepcopy(protocol)
    for command in revised['commands'].values():
        command['transition']['package']['modules'][0]['source'] = SOURCE.replace(
            'state.count + input.amount', 'state.count + input.amount + 1n')
    cases += [('reprogram-within-turn', [
        {'object': 'counter', 'command': 'add', 'input': record(amount=nat(1))},
        {'op': 'reprogram', 'object': 'counter', 'protocol': revised, 'state': root['state']},
        {'object': 'counter', 'command': 'add', 'input': record(amount=nat(1))}], 'committed')]
    locked = {**law, 'invoke': {'add': [], 'damage': []}}
    cases += [('current-law-lockout', [
        {'object': 'counter', 'command': 'add', 'input': record(amount=nat(1))},
        {'op': 'law', 'object': 'counter', 'law': locked},
        {'object': 'counter', 'command': 'add', 'input': record(amount=nat(1))}], 'refused')]
    frames = [(name, calls, status, world, root) for name, calls, status in cases]
    # Build compact framing only through the same verified native codec.
    add_artifact = call(args.package_binary, {'op': 'compile', **package('add')})['artifact']
    def compact(path, value):
        return call(args.package_binary, {'op': 'encode-compact',
            'selection': {'artifact': add_artifact, 'path': path}, 'value': value})['value']
    compact_protocol = copy.deepcopy(protocol)
    compact_protocol['commands']['add']['transition']['inputCodec'] = 'compact'
    compact_protocol['initial']['model'] = {'format': 'delvetalk-compact-state',
        'value': compact(['domain'], record(count=nat(0))), 'schema': {
            'package': package('add'), 'path': ['domain'],
            'packetSha256': add_artifact['packetSha256'], 'sourcesSha256': add_artifact['sourcesSha256']}}
    compact_initial = copy.deepcopy(initial)
    compact_initial['request']['protocol'] = compact_protocol
    compact_made = call(args.baseline, compact_initial)
    assert compact_made['reply']['kind'] == 'committed', compact_made
    assert call(args.binary, compact_initial) == compact_made
    compact_world = compact_made['world']; compact_root = compact_world['objects']['counter']
    compact_input = {'schemaPacketSha256': add_artifact['packetSha256'],
                     'value': compact(['codomain', 'domain'], record(amount=nat(1)))}
    compact_call = {'object': 'counter', 'command': 'add', 'input': compact_input}
    frames += [('4-compact-source-calls', [compact_call]*4, 'committed', compact_world, compact_root),
               ('compact-schema-forgery', [compact_call, {**compact_call,
                   'input': {**compact_input, 'schemaPacketSha256': 'forged'}}], 'refused', compact_world, compact_root)]
    for name, calls, status, case_world, case_root in frames:
        request = {'op': 'transaction', 'principal': 'maker', 'intent': name,
                   'reads': {'counter': case_root}, 'calls': calls}
        frame = {'world': case_world, 'request': request}
        expected = call(args.baseline, frame)
        assert expected['reply']['kind'] == status, expected
        assert call(args.binary, frame) == expected
        retry = {'world': expected['world'], 'request': request}
        assert call(args.binary, retry) == call(args.baseline, retry)
        if status == 'refused': assert expected['world']['objects'] == case_world['objects']
        times = {'baseline': [], 'cached': []}
        # Alternate hosts to limit drift from load or temperature.
        for _ in range(args.repeats):
            for mode, binary in [('baseline', args.baseline), ('cached', args.binary)]:
                begin = time.perf_counter()
                assert call(binary, frame) == expected
                times[mode].append((time.perf_counter()-begin)*1000)
        row = {'case': name, 'status': status, 'completeRepliesEqual': True,
               'medianMs': {key: statistics.median(value) for key, value in times.items()}, 'allMs': times}
        report['results'].append(row)
        print(json.dumps(row), flush=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
