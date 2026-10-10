#!/usr/bin/env python3
"""A world's repository signing key (docs/REPO.md "The key"), made once, at first start.

  python3 -m deploy.repokey --dir /repo --world town [--curve secp256k1]

Writes <dir>/<world>.key, a PKCS#8 PEM, created mode 0400 by the running user (10425 in the ops container, so
the front's uid owns it) and never overwritten; prints the did:key it names and nothing secret. Refuses if the
file exists: a new key re-signs every commit, so replacing one is a deliberate act (docs/REPO.md, rotation).
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transport.atproto.sign import CURVES, Key  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog='deploy.repokey')
    ap.add_argument('--dir', required=True, help='the key directory, /etc/delvetalk/repo on the box')
    ap.add_argument('--world', default='town')
    ap.add_argument('--curve', default='secp256k1', choices=sorted(CURVES))
    a = ap.parse_args(argv)
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', a.world):
        ap.error('a world name is [a-z][a-z0-9-]{0,31}')
    key, path = Key.generate(a.curve), Path(a.dir) / f'{a.world}.key'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    except FileExistsError:
        print(f'{path} exists; not replaced', file=sys.stderr)
        return 1
    with os.fdopen(fd, 'wb') as f:
        f.write(key.pem())
        f.flush()
        os.fsync(f.fileno())
    print(f'{path}: {key.did_key}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
