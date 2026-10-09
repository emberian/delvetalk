#!/usr/bin/env python3
"""Explicit, versioned syntax lowering. Translation grants no authority."""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_json(source):
    """Lossless JSON loading for artifact consumers (decimal values stay exact)."""
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f'duplicate JSON member: {key}')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError(f'non-JSON constant: {value}')
    return json.loads(source, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


def canonical(value):
    # Repository profile, not RFC 8785; preserve exact decimal arithmetic data.
    def emit(item):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError('nonfinite decimal')
            return str(item)
        if isinstance(item, float):
            raise ValueError('binary floats are not lossless JSON; use load_json')
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError('JSON object keys must be strings')
            return '{' + ','.join(emit(key) + ':' + emit(item[key]) for key in sorted(item)) + '}'
        if isinstance(item, list):
            return '[' + ','.join(emit(child) for child in item) + ']'
        return json.dumps(item, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return emit(value).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def closure_paths(registry, adapter, validator, *, root=ROOT, runtime_manifest=None):
    """Reviewed syntax paths; opt-in runtime profiles share host closure ownership."""
    root = Path(root).resolve()
    paths = set(registry['closure'] + adapter.get('closure', []) +
                validator.get('closure', []) + ['scripts/translate.py'])
    if 'runtimeProfile' in adapter:
        spec = importlib.util.spec_from_file_location('syntax_runtime_profile', root / 'scripts/runtime_profile.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        paths.update(runtime.paths(adapter['runtimeProfile'], root=root, manifest=runtime_manifest))
    return tuple(sorted(paths))


def closure_files(registry, adapter, validator, *, root=ROOT):
    """Hash the shared closure, refusing dependencies outside the repository."""
    root = Path(root).resolve()
    spec = importlib.util.spec_from_file_location('closure_runtime_profile', root / 'scripts/runtime_profile.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    return runtime.hash_paths(closure_paths(registry, adapter, validator, root=root), root=root)


def translate(syntax, raw, registry_path=None):
    source = raw.decode('utf-8')  # No newline normalization, including CRLF/BOM.
    return _translate(syntax, source, {'encoding': 'utf-8', 'text': source, 'sha256': digest(raw)}, registry_path)


def translate_modules(syntax, material, registry_path=None):
    """Explicit sealed assembly path; raw text never selects this variant."""
    import source_store
    source_store.validate_module_material(material)
    if syntax not in ('objective-bend-spell@2', 'objective-bend-spell@3'):
        raise ValueError('sealed modules require explicit spell@2 or spell@3')
    modules = [{'name': entry['name'], 'source': entry['source']} for entry in material['modules']]
    return _translate(syntax, modules, material, registry_path, modules=True)


def _translate(syntax, source, source_identity, registry_path=None, *, modules=False):
    registry_path = registry_path or ROOT / 'syntaxes/registry.json'
    registry_bytes = Path(registry_path).read_bytes()
    registry = load_json(registry_bytes)
    if registry.get('format') != 'delvetalk-syntax-registry-v1':
        raise ValueError('unsupported syntax registry format')
    adapter = registry['syntaxes'].get(syntax)
    if adapter is None:
        raise ValueError(f'unknown syntax {syntax!r}; register a reviewed versioned adapter')
    if adapter.get('reviewed') is not True:
        raise ValueError('adapter must be explicitly reviewed before execution')
    validator = registry['targets'][adapter['target']]
    files = closure_files(registry, adapter, validator)
    def invoke(entry, value):
        if entry['module'] not in files:
            raise ValueError('adapter/validator module missing from declared closure')
        spec = importlib.util.spec_from_file_location('delvetalk_syntax_module', ROOT / entry['module'])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, entry['entry'])(value)
    selected = adapter
    if modules:
        if not isinstance(adapter.get('modulesEntry'), str):
            raise ValueError('adapter has no reviewed ordered-module entry')
        selected = {**adapter, 'entry': adapter['modulesEntry']}
    lowered = invoke(selected, source)
    invoke(validator, lowered)
    lowered_bytes = canonical(lowered)  # Also rejects nonfinite/surrogate output.
    if 'runtimeProfile' in adapter and (Path(registry_path).read_bytes() != registry_bytes
            or closure_files(registry, adapter, validator) != files):
        raise ValueError('adapter runtime or registry changed during translation; retry with stable dependencies')
    identity = {'syntax': syntax, 'adapter': adapter, 'validator': validator,
                'registry_sha256': digest(registry_bytes), 'files': files}
    return {'format': 'delvetalk-lowered-v1', 'syntax': syntax,
            'source': load_json(canonical(source_identity)),
            'translation': {**identity, 'pin': digest(canonical(identity))},
            'target': adapter['target'], 'lowered': lowered,
            'lowered_sha256': digest(lowered_bytes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--syntax', required=True)
    parser.add_argument('input', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    try:
        if args.output and args.output.resolve() == args.input.resolve():
            raise ValueError('output must not overwrite original source')
        result = translate(args.syntax, args.input.read_bytes())
        data = canonical(result) + b'\n'
        if args.output:
            args.output.write_bytes(data)
        else:
            sys.stdout.buffer.write(data)
    except (ValueError, KeyError, TypeError, OSError, RecursionError) as error:
        print(f'translate: {error}; original source retained at {args.input}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
