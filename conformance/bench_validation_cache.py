#!/usr/bin/env python3
"""Exact source creation/reprogram admission on explicit frozen receiving hosts."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from process_custody import run_native
from conformance.test_current_source_contract import SOURCE, package, record, nat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'binary', 'package-binary', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 10: parser.error('repeats must be 2..10')
    def call(binary, frame):
        result = run_native([str(binary.resolve())], input=json.dumps(frame, separators=(',', ':')).encode()+b'\n',
            cwd=ROOT, timeout=30, cpu_seconds=30, stdout_limit=8*1024*1024, stderr_limit=64*1024)
        result.check_returncode(); return json.loads(result.stdout)
    artifact = call(args.package_binary, {'op': 'compile', **package('contractMetadata')})['artifact']
    metadata = call(args.package_binary, {'op': 'run-data-v1', 'artifact': artifact, 'arguments': []})['value']
    protocol = {'profile': 'delvetalk-local-v1', 'initial': {'model': record(count=nat(0))},
        'commands': {name: {'transition': {'profile': 'delvetalk-source-transition',
            'package': package(name), 'inputCodec': 'data'}} for name in ('add', 'damage')}}
    law = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker'], 'damage': ['maker']},
        'reprogram': ['maker'], 'law': ['maker'], 'contract': {'profile': 'delvetalk-source-contract-v1',
        'package': package('contract'), 'stateProfile': 'model', 'metadata': metadata}}
    create = {'world': {'objects': {}, 'receipts': []}, 'request': {'op': 'create', 'object': 'counter',
        'principal': 'maker', 'intent': 'new-counter', 'protocol': protocol, 'law': law}}
    made = call(args.baseline, create); assert made['reply']['kind'] == 'committed', made
    assert call(args.binary, create) == made
    root = made['world']['objects']['counter']
    revised = copy.deepcopy(protocol)
    for command in revised['commands'].values():
        command['transition']['package']['modules'][0]['source'] = SOURCE.replace(
            'state.count + input.amount', 'state.count + input.amount + 1n')
    reprogram = {'world': made['world'], 'request': {'op': 'reprogram', 'object': 'counter',
        'principal': 'maker', 'intent': 'changed-source', 'expected': root, 'protocol': revised, 'state': root['state']}}
    cases = [('source-create', create, 'committed'), ('changed-source-reprogram', reprogram, 'committed')]
    invalid_create = copy.deepcopy(create); invalid_create['request']['protocol']['commands']['add']['transition']['package']['modules'][0]['source'] = 'invalid source'
    cases.append(('invalid-source-create', invalid_create, 'refused'))
    invalid_reprogram = copy.deepcopy(reprogram); invalid_reprogram['request']['protocol']['commands']['add']['transition']['package']['modules'][0]['source'] = 'invalid source'
    cases.append(('invalid-source-reprogram', invalid_reprogram, 'refused'))
    forged = copy.deepcopy(create); forged['request']['law']['contract']['metadata'] = {'tag': 'boolean', 'value': False}
    cases.append(('forged-contract-metadata', forged, 'refused'))
    missing = copy.deepcopy(create); del missing['request']['protocol']['commands']['add']
    cases.append(('missing-current-contract-method', missing, 'refused'))
    unauthorized = copy.deepcopy(reprogram); unauthorized['request']['principal'] = 'outsider'
    cases.append(('current-law-reprogram-refusal', unauthorized, 'refused'))
    twice = {'world': made['world'], 'request': {'op': 'transaction', 'principal': 'maker', 'intent': 'twice',
        'reads': {'counter': root}, 'calls': [
            {'op': 'reprogram', 'object': 'counter', 'protocol': revised, 'state': root['state']},
            {'op': 'reprogram', 'object': 'counter', 'protocol': revised, 'state': root['state']}]}}
    cases.append(('two-reprograms-in-one-turn', twice, 'committed'))
    lockout = copy.deepcopy(twice); lockout['request']['calls'].insert(1,
        {'op': 'law', 'object': 'counter', 'law': {**law, 'reprogram': []}})
    cases.append(('current-law-changes-during-reprogram-turn', lockout, 'refused'))
    args.output.with_suffix('.counter-frames.json').write_text(json.dumps([frame for _, frame, _ in cases if frame['request']['op'] != 'transaction'])+'\n')
    report = {'scope': __doc__, 'sourceSha256': hashlib.sha256(SOURCE.encode()).hexdigest(),
        'binarySha256': {label: hashlib.sha256(binary.read_bytes()).hexdigest() for label,binary in [('baseline', args.baseline),('cachedValidation', args.binary)]}, 'results': []}
    for name, frame, status in cases:
        expected = call(args.baseline, frame); assert expected['reply']['kind'] == status, expected
        assert call(args.binary, frame) == expected, name
        assert call(args.binary, {'world': expected['world'], 'request': frame['request']}) == call(args.baseline, {'world': expected['world'], 'request': frame['request']})
        if status == 'refused': assert expected['world']['objects'] == frame['world']['objects']
        times = {'baseline': [], 'cachedValidation': []}
        for _ in range(args.repeats):
            for mode, binary in [('baseline', args.baseline), ('cachedValidation', args.binary)]:
                begin = time.perf_counter(); assert call(binary, frame) == expected
                times[mode].append((time.perf_counter()-begin)*1000)
        row = {'case': name, 'status': status, 'completeRepliesEqual': True,
            'medianMs': {mode:statistics.median(values) for mode,values in times.items()}, 'allMs':times}
        report['results'].append(row); print(json.dumps(row), flush=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')

if __name__ == '__main__': main()
