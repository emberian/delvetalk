#!/usr/bin/env python3
"""Local durable transport; the selected Lean profile owns semantic decisions.

Input: one request JSON file, or '-' for stdin. Output: Lean's reply JSON.
Principal strings are assertions by the local caller, NOT authenticated identities.
The database and lock must be on a local filesystem supporting flock/atomic rename.
"""
import argparse
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# Lean Nat is unbounded. Do not impose Python's decimal conversion cap on
# otherwise admitted finite results; Lean owns the request/frame envelopes.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'world': ('delvetalk-world', 'World.lean'),
    'transactions': ('delvetalk-transactions', 'Transactions.lean'),
    'compiled': ('delvetalk-compiled', 'Compiled.lean'),
}


def wire_loads(text):
    def invalid(value):
        raise ValueError('non-JSON number: ' + value)
    return json.loads(text, parse_float=Decimal, parse_constant=invalid)


def _needs_decimal_encoding(value):
    """Check object keys before native JSON can silently coerce them."""
    if isinstance(value, dict):
        decimal = False
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('JSON object keys must be strings')
            # Visit every child: short-circuiting would miss invalid later keys.
            decimal = _needs_decimal_encoding(item) or decimal
        return decimal
    if isinstance(value, (list, tuple)):
        decimal = False
        for item in value:
            decimal = _needs_decimal_encoding(item) or decimal
        return decimal
    return isinstance(value, Decimal)


def _decimal_dumps(value):
    # Preserve exact decimal preimages: binary float roundtrips can merge roots.
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('non-JSON decimal')
        return str(value)
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(key, ensure_ascii=False) + ':' + _decimal_dumps(item)
                              for key, item in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(_decimal_dumps(item) for item in value) + ']'
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def wire_dumps(value):
    if _needs_decimal_encoding(value):
        return _decimal_dumps(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def exchange(database, request, *, profile='world'):
    try:
        binary, source = PROFILES[profile]
    except KeyError:
        raise ValueError('unknown local host profile: ' + str(profile)) from None
    database = Path(database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    # The lock has stable identity across replacing the database file.
    with open(str(database) + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        world = wire_loads(database.read_text()) if database.exists() else {
            'objects': {}, 'receipts': []}
        executable = ROOT / '.lake/build/bin' / binary
        command = ([str(executable)] if executable.exists() else
                   ['lake', 'env', 'lean', '--run', 'profiles/' + source])
        proc = subprocess.run(command, cwd=ROOT,
                              input=wire_dumps({'world': world, 'request': request}) + '\n',
                              text=True, capture_output=True,
                              env={**os.environ, 'LEAN_NUM_THREADS': '1'})
        if proc.returncode:
            raise RuntimeError(proc.stderr + proc.stdout)
        response = wire_loads(proc.stdout)
        if 'error' in response:
            raise ValueError(response['error'])
        updated = response['world']
        if updated != world:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=database.parent,
                                                 prefix=database.name + '.', delete=False) as f:
                    temporary = f.name
                    f.write(wire_dumps(updated))
                    f.write('\n')
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, database)
                temporary = None
                directory = os.open(database.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if temporary is not None:
                    os.unlink(temporary)
        return response['reply']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, default='world',
                        help='opt-in Lean host admission profile (default: world)')
    parser.add_argument('database', type=Path)
    parser.add_argument('request', help="request JSON path, or '-' for stdin")
    args = parser.parse_args()
    request = wire_loads(sys.stdin.read() if args.request == '-' else Path(args.request).read_text())
    try:
        print(wire_dumps(exchange(args.database, request, profile=args.profile)))
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({'transport_error': str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
