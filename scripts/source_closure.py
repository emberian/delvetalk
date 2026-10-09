"""Confined physical assembly of explicit sources, using native parsed imports.

The compiler still receives a sealed in-memory table and owns all source meaning.
No filesystem search, source rewriting, inferred types or import grammar lives here.
"""
import hashlib
from pathlib import Path

import process_custody
import source_packages
import source_store

ROOT = Path(__file__).resolve().parents[1]
# An explicit shared allowlist, selected by callers; never compiler ambient imports.
LIBRARY = tuple((name, path) for name, path in (
    ('Abi', 'world/lib/prelude/Abi.obend'),
    ('Allocation', 'world/lib/prelude/Allocation.obend'),
    ('Emissions', 'world/lib/prelude/Emissions.obend'),
    ('Encounter', 'world/lib/prelude/Encounter.obend'),
    ('EncounterPages', 'world/lib/prelude/EncounterPages.obend'),
    ('List', 'world/lib/prelude/List.obend'),
    ('Preparation', 'world/lib/prelude/Preparation.obend'),
    ('Reflection', 'world/lib/prelude/Reflection.obend'),
    ('Document', 'world/lib/document/Document.obend'),
))


def native_imports(modules, *, runner=None):
    runner = Path(runner or ROOT / '.lake/build/bin/delvetalk-obend')
    def binary_hash():
        with runner.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    pin = binary_hash()
    done = process_custody.run_native([str(runner)],
        input=source_store.canonical({'op': 'source-imports-v1', 'modules': modules}) + b'\n',
        cwd=ROOT, timeout=15, cpu_seconds=10, stdout_limit=8 * 1024 * 1024,
        stderr_limit=1024 * 1024, file_limit=8 * 1024 * 1024)
    if done.returncode:
        raise ValueError('native source import parser failed')
    reply = source_store.loads(done.stdout)
    if binary_hash() != pin:
        raise ValueError('native source import parser changed during assembly')
    if not isinstance(reply, dict) or reply.get('status') != 'parsed-imports':
        raise ValueError('native source import parser refused: ' + str(reply))
    edges = reply.get('modules')
    if (not isinstance(edges, list) or len(edges) != len(modules)
            or any(not isinstance(entry, dict) or set(entry) != {'name', 'imports'}
                   or entry['name'] != module['name'] or not isinstance(entry['imports'], list)
                   for entry, module in zip(edges, modules))):
        raise ValueError('invalid native source import transcript')
    return {entry['name']: entry['imports'] for entry in edges}


def order(roots, modules, *, parser=native_imports):
    """Order exact supplied in-memory material by native parsed imports.

    Performs no filesystem loading or source rewriting. Unreachable supplied
    modules are omitted; the last named root remains the entry module.
    """
    roots = list(roots)
    if not roots or len(set(roots)) != len(roots):
        raise ValueError('source closure requires distinct ordered roots')
    modules = source_packages.table(modules)['modules']
    names = [module['name'] for module in modules]
    if len(set(names)) != len(names):
        raise ValueError('source material has duplicate module identity')
    if any(name not in names for name in roots):
        raise ValueError('source root missing from explicit module material')
    imports = parser(modules)
    by_name = {module['name']: module for module in modules}
    by_import = {'./' + name + '.obend': name for name in names}
    ordered, visiting, visited = [], [], set()

    def visit(name):
        if name in visiting:
            raise ValueError('source import cycle: ' + ' -> '.join(visiting + [name]))
        if name in visited:
            return
        visiting.append(name)
        for edge in imports[name]:
            path = edge.get('path') if isinstance(edge, dict) else None
            dependency = by_import.get(path) if isinstance(path, str) else None
            if dependency is None:
                raise ValueError(f'{name}: import {path!r} missing from explicit allowlist or outside package path ABI')
            visit(dependency)
        visiting.pop()
        visited.add(name)
        ordered.append(by_name[name])

    for name in roots:
        visit(name)
    if ordered[-1]['name'] != roots[-1]:
        raise ValueError('last source root must be the entry module, not its dependency')
    return ordered


def assemble(roots, allowed, *, root=ROOT, parser=native_imports):
    """Read an allowlist once; return dependency-first exact bytes and manifest.

    Names are module identities, independent of filesystem basenames. Import paths
    must match the native package ABI ./NAME.obend. Multiple aliases retain the
    same module identity. Root order and native edge order determine stable output;
    the last root is the package's selected entry module.
    """
    root = Path(root).resolve()
    roots = list(roots)
    if not roots or len(set(roots)) != len(roots):
        raise ValueError('source closure requires distinct ordered roots')
    paths, identities = {}, {}
    for name, supplied in allowed:
        if not isinstance(name, str) or not name or name in paths:
            raise ValueError('source allowlist has duplicate or invalid module name: ' + str(name))
        path = Path(supplied)
        path = (root / path if not path.is_absolute() else path).resolve()
        if not path.is_relative_to(root):
            raise ValueError('source allowlist escapes custody root: ' + str(supplied))
        if path in identities:
            raise ValueError('source allowlist path has ambiguous module identity: ' + str(path))
        paths[name], identities[path] = path, name
    if any(name not in paths for name in roots):
        raise ValueError('source root missing from explicit allowlist')
    # Validation of every path precedes every source read (including symlinks).
    modules = [{'name': name, 'source': source_store._read(path, source_store.limit('source')).decode('utf-8')}
               for name, path in paths.items()]
    ordered = order(roots, modules, parser=parser)
    manifest = source_store.seal_modules([
        {'name': module['name'], 'sourceRef': source_store.reference(module['source'].encode('utf-8'), kind='source')}
        for module in ordered])
    return {'modules': ordered, 'manifest': manifest}


def read(roots, allowed, *, root=ROOT, parser=native_imports):
    return assemble(roots, allowed, root=root, parser=parser)['modules']
