"""Run the whole suite in parallel, one subprocess per test class.

    python3 -W ignore -m tests.run [module ...]     (default: every tests/test_*.py)

The host binary is copied once and the copy shared with the workers. Each class gets its own
process (and so its own host process), preserving class-level sharing and journal isolation.
Slowest classes start first; Maximum classes (wall-clock bounds) run last, three at a time; their measured times persist in tests/.timings.json.
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests import host

HERE = Path(__file__).resolve().parent
TIMINGS = HERE / '.timings.json'


def classes(modules):
    found = {}
    for module in modules:
        suite = unittest.defaultTestLoader.loadTestsFromName('tests.' + module)
        stack = [suite]
        while stack:
            for t in stack.pop():
                if isinstance(t, unittest.TestSuite):
                    stack.append(t)
                else:
                    key = f'tests.{module}.{type(t).__name__}' if type(t).__module__ == 'tests.' + module else f'tests.{module}'
                    found.setdefault(key, 0)
                    found[key] += 1
    return found


def run_one(name, env):
    t0 = time.time()
    p = subprocess.run([sys.executable, '-W', 'ignore', '-m', 'unittest', name], env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return name, p.returncode, time.time() - t0, p.stdout


def main(argv):
    modules = argv or sorted(p.stem for p in HERE.glob('test_*.py'))
    found = classes(modules)
    try:
        known = json.loads(TIMINGS.read_text())
    except (OSError, ValueError):
        known = {}
    order = sorted(found, key=lambda n: -known.get(n, found[n]))
    env = dict(os.environ, DELVETALK_OBEND_COPY=host.binary(), PYTHONPATH=str(HERE.parent))
    t0, failed, took = time.time(), [], {}
    # Classes named Maximum assert wall-clock bounds; they run after the rest, three at a time.
    phases = [([n for n in order if not n.endswith('.Maximum')], os.cpu_count() or 4),
              ([n for n in order if n.endswith('.Maximum')], 3)]
    for names, workers in phases:
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            for name, code, secs, out in pool.map(lambda n: run_one(n, env), names):
                took[name] = secs
                if code:
                    failed.append(name)
                    print(f'--- FAILED {name}\n{out}')
    try:
        TIMINGS.write_text(json.dumps({**known, **{k: round(v, 2) for k, v in took.items()}}, indent=1))
    except OSError:
        pass
    per = {}
    for name, secs in took.items():
        mod = name.split('.')[1]
        per[mod] = max(per.get(mod, 0), secs)
    print('slowest classes: ' + ', '.join(f'{n.split(".", 1)[1]} {took[n]:.1f}s' for n in sorted(took, key=took.get)[-3:]))
    print(f'{sum(found.values())} tests in {len(found)} classes, {time.time() - t0:.1f}s wall, {len(failed)} failed classes')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
