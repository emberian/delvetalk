#!/usr/bin/env python3
"""Check fork attribution and local build/runtime closure, without pinning local edits."""
import json
from pathlib import Path, PurePosixPath
import re
import tomllib
import hashlib

import runtime_profile

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'spec/bend/origin.json'


def verify(root=ROOT):
    root = Path(root)
    origin = json.loads((root / ORIGIN).read_text())
    if set(origin) != {'format', 'upstream', 'license', 'scope', 'baseline'} or origin['format'] != 'delvetalk-bend-origin-v1':
        raise ValueError('invalid Bend origin record')
    upstream = origin['upstream']
    if (set(upstream) != {'name', 'repository', 'commit', 'sourceRoot'} or upstream['name'] != 'Mini'
            or upstream['repository'] != 'https://github.com/emberian/minidregg'
            or upstream['sourceRoot'] != '.'
            or not re.fullmatch(r'[0-9a-f]{40}', upstream['commit'])):
        raise ValueError('invalid upstream attribution')
    license = origin['license']
    if (set(license) != {'file', 'sha256'} or license['file'] != 'LICENSE'
            or hashlib.sha256((root / 'LICENSE').read_bytes()).hexdigest() != license['sha256']):
        raise ValueError('attributed license differs from retained license')
    if not isinstance(origin['scope'], str) or not origin['scope'] or not isinstance(origin['baseline'], dict):
        raise ValueError('invalid documentary baseline')
    for name, digest in origin['baseline'].items():
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or '..' in path.parts or str(path) != name
                or '\\' in name or path.suffix != '.lean' or not isinstance(digest, str)
                or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ValueError('invalid baseline path or hash')
    # Baseline hashes describe the original Mini commit. They do not constrain
    # the bytes or inventory of this fork: local modules may change or disappear.
    lake = tomllib.loads((root / 'lakefile.toml').read_text())
    libraries = {item['name']: item.get('srcDir', '.') for item in lake.get('lean_lib', [])}
    if any(libraries.get(name) != 'spec/bend' for name in ('Theory', 'Compiler', 'Pred')):
        raise ValueError('Bend libraries must build the local fork')
    directories = sorted(set(libraries.values()) | {item.get('srcDir', '.') for item in lake.get('lean_exe', [])})

    def imports(path):
        for declaration in re.findall(r'^import\s+([^\n]+)', (root / path).read_text(), re.M):
            for module in declaration.split():
                if module.split('.')[0] in ('Lean', 'Std', 'Init'):
                    continue
                relative = Path(*module.split('.')).with_suffix('.lean')
                matches = [str(Path(folder) / relative) for folder in directories if (root / folder / relative).is_file()]
                if len(matches) != 1:
                    raise ValueError(f'{path}: cannot resolve local import {module}')
                yield matches[0]

    for path in (root / 'spec/bend').rglob('*.lean'):
        list(imports(str(path.relative_to(root))))
    for profile in runtime_profile.load_manifest(root=root)['profiles']:
        selected = set(runtime_profile.paths(profile, root=root))
        if any(path.startswith(('spec/upstream/', 'spec/original/')) or path in ('spec/upstream.json', ORIGIN) for path in selected):
            raise ValueError('runtime closure must bind local source, not origin/replacement records')
        for path in sorted(selected):
            if not path.endswith('.lean'):
                continue
            for dependency in imports(path):
                if dependency not in selected:
                    raise ValueError(f'{profile}: runtime closure omits {dependency}')
    return len(origin['baseline'])


if __name__ == '__main__':
    verify()
    print('Bend origin and local source closures checked; no upstream byte equality or semantic conformance claimed.')
