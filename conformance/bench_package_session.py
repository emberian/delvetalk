#!/usr/bin/env python3
"""Compare identical native source REPL/view requests with fresh or warm custody.

No changed fuel or receiving-world simulation. The view is the
actual PageGallery.view source function; counters exclude frontend verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from package_session import PackageSession
from process_custody import run_native
import runtime_profile
from bench_source_collections import pages as page_entries, record, natural, text


def wire(value): return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()+b'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--binary', type=Path, default=ROOT / '.lake/build/bin/delvetalk-obend')
    parser.add_argument('--repeats', type=int, default=10)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 30: parser.error('repeats must be 2..30')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frozen = args.output.with_suffix('.binary')
    if frozen.exists(): parser.error('choose a new output path; snapshot already exists')
    digest = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    shutil.copy2(args.binary, frozen)
    if hashlib.sha256(frozen.read_bytes()).hexdigest() != digest: raise RuntimeError('binary changed during copy')
    sources = [('Abi', 'world/lib/prelude/Abi.obend'), ('List', 'world/lib/prelude/List.obend'), ('Encounter', 'world/lib/prelude/Encounter.obend'),
               ('EncounterPages', 'world/lib/prelude/EncounterPages.obend'),
               ('Gallery', 'world/lib/prelude/examples/PageGallery.obend')]
    modules = [{'name': name, 'source': (ROOT/path).read_text()} for name,path in sources]
    simple = [{'name': 'Main', 'source': 'edition ObjectiveBend 1\ndef answer() -> Nat:\n  6n * 7n\n'}]
    report = {'binarySha256': digest, 'sources': modules, 'scope': __doc__, 'results': []}
    pin_times = []
    for _ in range(3):
        begin = time.perf_counter()
        runtime_profile.file_hashes('compiled')
        hashlib.sha256(frozen.read_bytes()).hexdigest()
        pin_times.append((time.perf_counter()-begin)*1000)
    report['oneRuntimeCaptureMedianMs'] = statistics.median(pin_times)
    report['runtimeCaptureScope'] = 'HeapManager still captures/checks identities before and after evaluation; transport samples below exclude those reads.'
    def fresh(frame):
        result = run_native([str(frozen)], input=frame, cwd=ROOT, timeout=10, cpu_seconds=10,
                            stdout_limit=8*1024*1024, stderr_limit=64*1024)
        result.check_returncode()
        return result.stdout
    for name, source, entry, arguments in [
            ('repl42', simple, 'answer', []),
            ('gallery-view-32', modules, 'view', [record(pages=page_entries(32), current=natural(0)), text('main')]),
            ('gallery-view-200', modules, 'view', [record(pages=page_entries(200), current=natural(0)), text('main')])]:
        compile_frame = wire({'op': 'compile', 'modules': source, 'entry': entry})
        compiled = json.loads(fresh(compile_frame))
        if compiled.get('status') != 'compiled': raise RuntimeError(compiled)
        run_frame = wire({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': arguments})
        expected = fresh(run_frame)
        if json.loads(expected).get('status') != 'finished': raise RuntimeError(expected)
        for mode in ('fresh', 'session'):
            with PackageSession([str(frozen)], cwd=ROOT) as session:
                call = fresh if mode == 'fresh' else lambda frame: session.exchange(frame, timeout=10, identity=digest)
                # Establish the exact successful artifact in this process before
                # repeated views; both binaries receive the identical primer.
                if mode == 'session':
                    assert json.loads(call(compile_frame)) == compiled
                # Measure actual compile+evaluate REPL flow as well as repeated
                # view execution; cold first session sample is retained separately.
                times = []
                for _ in range(args.repeats):
                    begin = time.perf_counter()
                    if name == 'repl42':
                        assert json.loads(call(compile_frame)) == compiled
                    actual = call(run_frame)
                    elapsed = (time.perf_counter()-begin)*1000
                    assert actual == expected, 'native result/counters changed'
                    times.append(elapsed)
                result = json.loads(expected)
                report['results'].append({'case': name, 'mode': mode, 'coldMs': times[0],
                    'warmMedianMs': statistics.median(times[1:]), 'allMs': times,
                    'counters': {key: result[key] for key in ('ticksUsed','conversionNodes','heapCells','nodesUsed')}})
                print(json.dumps(report['results'][-1]), flush=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
