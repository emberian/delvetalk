"""Reviewed local runtime custody closures; hashes identify bytes, never authority.

Keep the explicit closures here when a host's Lean imports change. Standard Lean
and Std modules belong to the pinned toolchain. This is not a Lean module loader
or a build/refinement claim, and never executes a compiler or bundled binary.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'world': ('delvetalk-world', 'profiles/World.lean'),
    'transactions': ('delvetalk-transactions', 'profiles/Transactions.lean'),
    'compiled': ('delvetalk-compiled', 'profiles/Compiled.lean'),
}
COMMON = ('scripts/runtime_profile.py', 'scripts/world.py', 'lean-toolchain',
          'lakefile.toml', 'spec/upstream.json', 'profiles/WorldCore.lean',
          'spec/Delvetalk/Core.lean', 'spec/upstream/Theory/AxiomPin.lean',
          'spec/upstream/Theory/ObjectiveBendOpenRecursion.lean')
# Transitive project-local Package/frontend dependencies, including compatibility
# originals as provenance alongside the actual adapted sources and manifest.
PACKAGE_MODULES = '''
Compiler/ObjectiveBendC4 Compiler/ObjectiveBendContract Compiler/ObjectiveBendDataWire
Compiler/ObjectiveBendElaborate Compiler/ObjectiveBendFrontEnd Compiler/ObjectiveBendLaw
Compiler/ObjectiveBendParse Compiler/ObjectiveBendTermWire Compiler/Sha256
Pred/Core Pred/HashEqDigest
Theory/AssertAxioms Theory/AssertCompiled Theory/HashBytes
Theory/ObjectiveBendDemandData Theory/ObjectiveBendDemandMachine Theory/ObjectiveBendDemandMachineFast
Theory/ObjectiveBendTypes Theory/ObjectiveBendTyping
Theory/Sp800185Cshake256Core Theory/Sp800185Cshake256Fast Theory/Sp800185Cshake256Spec
'''.split()
PACKAGE = ('spec/Delvetalk/Package.lean',
           'spec/original/Theory/AssertAxioms.lean.txt',
           'spec/original/Compiler/ObjectiveBendTermWire.lean.txt',
           *(f'spec/upstream/{name}.lean' for name in PACKAGE_MODULES))


def paths(profile):
    """Return one allowlisted profile's complete reviewed repository paths."""
    if profile not in PROFILES:
        raise ValueError('unknown runtime profile: ' + str(profile))
    binary, source = PROFILES[profile]
    selected = [*COMMON, source, '.lake/build/bin/' + binary]
    if profile in ('transactions', 'compiled'):
        selected.append('profiles/TransactionsCore.lean')
    if profile == 'compiled':
        selected.extend(PACKAGE)
    return tuple(sorted(set(selected)))


def file_hashes(profile, *, root=ROOT):
    """Read pinned files only; refuse missing paths and escaping symlinks."""
    root = Path(root).resolve()
    result = {}
    for name in paths(profile):
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('runtime dependency escapes repository: ' + name)
        with path.open('rb') as stream:
            result[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result
