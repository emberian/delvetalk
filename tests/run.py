"""Run the whole suite in parallel, one subprocess per test class.

    python3 -W ignore -m tests.run [--profile] [module ...]     (default: every tests/test_*.py)

--profile counts, per class, the host processes spawned (every exec of the binary, including the
ones hostd starts) and the hostd daemons started, and prints the twenty slowest classes with both.

The host binary is copied once and the copy shared with the workers. Each class gets its own
process (and so its own host process), preserving class-level sharing and journal isolation; a
class declaring `independent = True` measured over SPLIT seconds is dealt into chunks instead.
Slowest classes start first (measured times persist in tests/.timings.json). A class runs in
the module that defines it, never again where it is imported. The run ends with the tests per
layer (each module's docstring names its layer) and the five slowest classes.
"""
import concurrent.futures
import importlib
import json
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests import host

HERE = Path(__file__).resolve().parent
TIMINGS = HERE / '.timings.json'


LAYERS = ['kernel', 'host', 'objects', 'transport', 'rehearsal']  # each module's docstring names its own
SPLIT = 8.0  # seconds: a fresh-world class measured slower than this runs in that many parallel chunks


def classes(modules):
    """{'tests.module.Class': [test names]} for every class defined in the named modules."""
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
                    if type(t).__module__ != mod.__name__:
                        continue  # imported from another module: it runs there, once
                    assert getattr(mod, type(t).__name__, None) is type(t), f'{module}.{type(t).__name__} is not importable by name'
                    found.setdefault(f'tests.{module}.{type(t).__name__}', []).append(t._testMethodName)
    return found


def jobs(found, known):
    """One job per class, except that a class declaring `independent = True` (its tests share
    nothing but a process: HostCase's fresh world per test, TurnCase's stateless checker) known to
    take longer than SPLIT is dealt into chunks run side by side."""
    out = {}
    for key, names in found.items():
        module, cls = key.rsplit('.', 1)
        independent = getattr(getattr(importlib.import_module(module), cls), 'independent', False)
        n = min(len(names), max(1, round(known.get(key, 0) / SPLIT))) if independent else 1
        if n == 1:
            out[key] = [key]
        else:
            for i in range(n):
                out[f'{key}#{i + 1}/{n}'] = [f'{key}.{name}' for name in names[i::n]]
    return out


def run_one(name, targets, env, spawns=None):
    t0 = time.time()
    if spawns:
        env = dict(env, DELVETALK_SPAWN_LOG=os.path.join(spawns, name.replace('/', '-')))
    p = subprocess.run([sys.executable, '-W', 'ignore', '-m', 'unittest', *targets], env=env,
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
        lines = Path(spawns, name.replace('/', '-')).read_text().split()
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
    work = jobs(found, known)
    estimate = lambda job: known.get(job.split('#')[0], len(found[job.split('#')[0]])) / int(job.rpartition('/')[2] if '#' in job else 1)
    order = sorted(work, key=lambda job: -estimate(job))
    env = dict(os.environ, DELVETALK_OBEND_COPY=host.binary(), PYTHONPATH=str(HERE.parent))
    spawns = None
    if profile:
        import tempfile
        spawns = tempfile.mkdtemp(prefix='dt-spawns-')
        env['DELVETALK_OBEND_COPY'] = counting_wrapper(host.binary(), spawns)
    t0, failed, took = time.time(), [], {}
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as pool:
        for name, code, secs, out in pool.map(lambda job: run_one(job, work[job], env, spawns), order):
            took[name] = secs
            if code:
                failed.append(name)
                print(f'--- FAILED {name}\n{out}')
    try:
        per_class = {}
        for job, secs in took.items():
            per_class[job.split('#')[0]] = per_class.get(job.split('#')[0], 0) + secs
        TIMINGS.write_text(json.dumps({**known, **{k: round(v, 2) for k, v in per_class.items()}}, indent=1))
    except OSError:
        pass
    counts = {}
    for key, names in found.items():
        layer = re.search(r'\(layer: (\w+)\)', importlib.import_module(key.rsplit('.', 1)[0]).__doc__ or '')
        counts[layer.group(1) if layer else 'unlayered'] = counts.get(layer.group(1) if layer else 'unlayered', 0) + len(names)
    print('by layer: ' + ', '.join(f'{layer} {counts[layer]}' for layer in LAYERS + ['unlayered'] if layer in counts))
    print('slowest classes: ' + ', '.join(f'{n.split(".", 1)[1]} {took[n]:.1f}s' for n in sorted(took, key=took.get, reverse=True)[:5]))
    if profile:
        print(f'{"class":52} {"tests":>5} {"secs":>6} {"hosts":>5} {"hostd":>5}')
        table = {n: (len(work[n]) if '#' in n else len(found[n]), round(took[n], 1), *spawn_counts(spawns, n)) for n in took}
        (HERE / '.profile.json').write_text(json.dumps(table, indent=0))
        for n in sorted(took, key=took.get, reverse=True)[:20]:
            h, d = table[n][2:]
            print(f'{n.split(".", 1)[1]:52} {table[n][0]:5} {took[n]:6.1f} {h:5} {d:5}')
    print(f'{sum(map(len, found.values()))} tests in {len(found)} classes, {time.time() - t0:.1f}s wall, {len(failed)} failed classes')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
