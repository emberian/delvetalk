#!/usr/bin/env python3
"""Differential native exact-cache qualification against the uncached boundary.

The binary is explicit so stale shared builds cannot establish this claim.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from package_session import PackageSession
from process_custody import run_native


def frame(request):
    return json.dumps(request, separators=(',', ':')).encode() + b'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--baseline', type=Path, help='uncached predecessor for cross-version reply comparison')
    args = parser.parse_args()
    binary = args.binary.resolve()
    reference = args.baseline.resolve() if args.baseline else binary
    def fresh(request):
        result = run_native([str(reference)], input=frame(request), cwd=ROOT, timeout=10, cpu_seconds=10,
                            stdout_limit=8*1024*1024, stderr_limit=64*1024)
        result.check_returncode()
        return json.loads(result.stdout)
    def compile_request(n):
        return {'op': 'compile', 'modules': [{'name': 'Main', 'source':
                f'edition ObjectiveBend 1\ndef answer() -> Nat:\n  {n}n\n'}], 'entry': 'answer'}
    checks = 0
    with PackageSession([str(binary)], cwd=ROOT) as session:
        def same(request):
            nonlocal checks
            expected = fresh(request)
            actual = json.loads(session.exchange(frame(request), timeout=10, identity=str(binary)))
            assert actual == expected, (request, expected, actual)
            checks += 1
            return actual
        original = compile_request(42)
        artifact = same(original)['artifact']
        same(original)
        run = {'op': 'run-data-v1', 'artifact': artifact, 'arguments': []}
        assert same(run)['value'] == {'tag': 'natural', 'value': '42'}
        for limit in ({'ticks': 0}, {'work': 1}, {'bytes': 1}):
            same({**run, 'limits': limit})
        same({**run, 'arguments': [{'tag': 'natural', 'value': 1}]})
        # Neither changed source nor changed packet can inherit prior verification.
        for key in ('modules', 'packet', 'limits'):
            forged = copy.deepcopy(artifact)
            if key == 'modules': forged[key][0]['source'] = compile_request(43)['modules'][0]['source']
            elif key == 'packet': forged[key] = {}
            else: forged[key] = {'fuel': 1}
            assert same({**run, 'artifact': forged})['status'] == 'error'
        changed = same(compile_request(43))['artifact']
        assert same({**run, 'artifact': changed})['value']['value'] == '43'
        invalid = {**original, 'entry': 'missing'}
        assert same(invalid)['status'] == 'error'
        same(invalid)
        # Exceed the entry ceiling, then revisit evicted artifact and source.
        for number in range(50, 60): same(compile_request(number))
        same(run)
        same(original)
        same({'op': 'unknown', 'artifact': artifact})
    print(f'{checks} cached/fresh native replies and counters identical')


if __name__ == '__main__': main()
