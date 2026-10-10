"""Run the whole suite in parallel, one subprocess per test class.

    python3 -W ignore -m tests.run [--profile] [module ...]     (default: every tests/test_*.py)

--profile counts, per class, the host processes spawned (every exec of the binary, including the
ones hostd starts) and the hostd daemons started, and prints the twenty slowest classes with both.

The host binary is copied once and the copy shared with the workers. Each class gets its own
process (and so its own host process), preserving class-level sharing and journal isolation.
Slowest classes start first; Maximum classes (wall-clock bounds) run last, three at a time; their measured times persist in tests/.timings.json.
"""
import concurrent.futures
import importlib
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
                    mod = importlib.import_module('tests.' + module)
                    named = type(t).__module__ == mod.__name__ and getattr(mod, type(t).__name__, None) is type(t)
                    key = f'tests.{module}.{type(t).__name__}' if named else f'tests.{module}'  # not importable by name: run with the module
                    found.setdefault(key, 0)
                    found[key] += 1
    return found


def run_one(name, env, spawns=None):
    t0 = time.time()
    if spawns:
        env = dict(env, DELVETALK_SPAWN_LOG=os.path.join(spawns, name))
    p = subprocess.run([sys.executable, '-W', 'ignore', '-m', 'unittest', name], env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return name, p.returncode, time.time() - t0, p.stdout


def counting_wrapper(real, directory):
    """An executable that logs each exec of the host binary to $DELVETALK_SPAWN_LOG, then becomes it."""
    path = os.path.join(directory, 'delvetalk-obend')
    with open(path, 'w') as f:
        f.write('#!/bin/sh\n[ -n "$DELVETALK_SPAWN_LOG" ] && echo host >> "$DELVETALK_SPAWN_LOG"\n'
                f'exec {real} "$@"\n')
    os.chmod(path, 0o755)
    return path


def spawn_counts(spawns, name):
    try:
        lines = Path(spawns, name).read_text().split()
    except OSError:
        return 0, 0
    return lines.count('host'), lines.count('hostd')


def main(argv):
    profile = '--profile' in argv
    argv = [a for a in argv if a != '--profile']
    modules = argv or sorted(p.stem for p in HERE.glob('test_*.py'))
    found = classes(modules)
    try:
        known = json.loads(TIMINGS.read_text())
    except (OSError, ValueError):
        known = {}
    order = sorted(found, key=lambda n: -known.get(n, found[n]))
    env = dict(os.environ, DELVETALK_OBEND_COPY=host.binary(), PYTHONPATH=str(HERE.parent))
    spawns = None
    if profile:
        import tempfile
        spawns = tempfile.mkdtemp(prefix='dt-spawns-')
        env['DELVETALK_OBEND_COPY'] = counting_wrapper(host.binary(), spawns)
    t0, failed, took = time.time(), [], {}
    # Classes named Maximum assert wall-clock bounds; they run after the rest, three at a time.
    phases = [([n for n in order if not n.endswith('.Maximum')], os.cpu_count() or 4),
              ([n for n in order if n.endswith('.Maximum')], 3)]
    for names, workers in phases:
        with concurrent.futures.ThreadPoolExecutor(workers) as pool:
            for name, code, secs, out in pool.map(lambda n: run_one(n, env, spawns), names):
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
    if profile:
        print(f'{"class":52} {"tests":>5} {"secs":>6} {"hosts":>5} {"hostd":>5}')
        table = {n: (found[n], round(took[n], 1), *spawn_counts(spawns, n)) for n in took}
        (HERE / '.profile.json').write_text(json.dumps(table, indent=0))
        for n in sorted(took, key=took.get, reverse=True)[:20]:
            h, d = table[n][2:]
            print(f'{n.split(".", 1)[1]:52} {found[n]:5} {took[n]:6.1f} {h:5} {d:5}')
    print(f'{sum(found.values())} tests in {len(found)} classes, {time.time() - t0:.1f}s wall, {len(failed)} failed classes')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
