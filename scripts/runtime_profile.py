"""Reviewed local runtime custody closures; hashes identify bytes, never authority.

Keep runtime_profiles.json current when a host's Lean imports change. Standard Lean
and Std modules belong to the pinned toolchain. This is not a Lean module loader
or a build/refinement claim, and never executes a compiler or bundled binary.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'scripts/runtime_profiles.json'


def relative_path(name):
    if (not isinstance(name, str) or not name or name == '.' or '\\' in name or '\x00' in name
            or PurePosixPath(name).is_absolute() or '..' in name.split('/')
            or str(PurePosixPath(name)) != name):
        raise ValueError('runtime dependency must be a normalized repository path')
    return name


def validate_manifest(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'groups', 'profiles'}
            or value['format'] != 'delvetalk-runtime-closure-v1'
            or not isinstance(value['groups'], dict) or not isinstance(value['profiles'], dict)):
        raise ValueError('invalid runtime closure manifest')
    for group, names in value['groups'].items():
        if not isinstance(group, str) or not group or not isinstance(names, list):
            raise ValueError('invalid runtime closure group')
        for name in names:
            relative_path(name)
    for profile, entry in value['profiles'].items():
        if (not isinstance(profile, str) or not profile or not isinstance(entry, dict)
                or set(entry) != {'binary', 'source', 'groups'} or not isinstance(entry['groups'], list)
                or any(not isinstance(group, str) or group not in value['groups'] for group in entry['groups'])):
            raise ValueError('invalid runtime closure profile')
        relative_path(entry['source'])
        if '/' in relative_path(entry['binary']):
            raise ValueError('runtime binary must be a basename')
    return value


def load_manifest(*, root=ROOT):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate runtime manifest key')
            result[key] = value
        return result
    return validate_manifest(json.loads((Path(root) / MANIFEST).read_bytes(), object_pairs_hook=pairs))


PROFILES = {name: (entry['binary'], entry['source'])
            for name, entry in load_manifest()['profiles'].items()}


def paths(profile, *, manifest=None, root=ROOT):
    """Resolve current or retained declarative data without executing retained code."""
    manifest = load_manifest(root=root) if manifest is None else validate_manifest(manifest)
    if not isinstance(profile, str) or profile not in manifest['profiles']:
        raise ValueError('unknown runtime profile: ' + str(profile))
    entry = manifest['profiles'][profile]
    selected = [MANIFEST, 'scripts/runtime_profile.py', entry['source'], '.lake/build/bin/' + entry['binary']]
    for group in entry['groups']:
        selected.extend(manifest['groups'][group])
    return tuple(sorted(set(selected)))


def hash_paths(names, *, root=ROOT):
    """Stream each named dependency once for this capture; retain no cache."""
    root = Path(root).resolve()
    result = {}
    for name in sorted(set(relative_path(name) for name in names)):
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('runtime dependency escapes repository: ' + name)
        with path.open('rb') as stream:
            result[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def file_hashes(profile, *, root=ROOT):
    """Read pinned files only; refuse missing paths and escaping symlinks."""
    return hash_paths(paths(profile, root=root), root=root)
