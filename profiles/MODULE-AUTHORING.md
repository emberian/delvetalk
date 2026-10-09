# Sealed resident modules

A resident can reuse another resident's exact retained Bend module and supply an
extension of their own. The existing Objective Bend package compiler resolves
only explicitly supplied earlier modules. The final module exports `describe`,
methods and `view` using the current `objective-bend-object` host binding. All
exports compile the same ordered package; no Python code interprets imports or
Bend behavior.

Posts carry source and requests. An operator can retain exact UTF-8 source from
an authenticated post with `source_store.store_bytes(artifacts, raw)`; ordinary
speech can name the intended revision through retained manual interpretation.
Source references identify bytes, not authors, rights or live receiving routes.
Authorship evidence belongs to original post URI/CID, fetched record and retained
operator/receiving custody. No manifest grants authority or fetches a foreign
world, filesystem path or network URL.

## Explicit custody API

```python
base_ref = source_store.store_bytes(artifacts, base_bytes)
override_ref = source_store.store_bytes(artifacts, override_bytes)
main_ref = source_store.store_bytes(artifacts, main_bytes)
manifest = source_store.seal_modules([
    {'name': 'Base', 'sourceRef': base_ref},
    {'name': 'Override', 'sourceRef': override_ref},
    {'name': 'Main', 'sourceRef': main_ref},
])
proposal = source_store.prepare_module_proposal(artifacts, manifest, scenario_bytes)
```

Submit the proposal through the existing desk command with its explicit target
and complete migration. The compiler queue retains the exact candidate root,
manifest, examples reference and adapter pin. Checking grants no installation
right. Installation still requires explicit adoption and current target authority.

The proposal is a strict opt-in envelope:

```text
{format: delvetalk-module-proposal-v1,
 syntax: objective-bend-object,
 manifest: {format: delvetalk-module-manifest-v1,
            modules: ordered [{name, sourceRef}, ...],
            sha256: SHA256(canonical({format, modules}))},
 scenariosRef: existing bounded UTF-8 source reference,
 adapterPin: existing reviewed adapter pin}
```

A manifest has 1–64 distinct bounded names, existing source blobs of at most
512 KiB each, and at most 1 MiB aggregate source. Native compilation owns module
name/import validity. Binding definitions come from the final supplied module.
No mutable “latest” reference or implicit import discovery exists. Changing a
name, order or reference without resealing refuses; resealing does not make an
invalid import order compile or install a new revision.

The resolved material has a distinct tag `delvetalk-module-material-v1`, the
sealed manifest and ordered `{name, sourceRef, source}` records. Each `source`
is the exact decoded UTF-8 text; CRLF/BOM are never normalized. This material
binds lowering, scenarios, queued checks and retained builds. The installed
protocol retains the ordered `{name, source}` modules once in its
object-local `sourcePackages` table; method/view selectors use that same exact table.
Reference identity, adapter dependency closure and host runtime identity remain
separate.

## Recovery and evidence

Missing, tampered or metadata-mismatched source blobs refuse before compilation.
The queue binds complete ordered manifests; later changed candidates/pins refuse
rather than refreshing them. History and continuation export preserve module
refs and exact blobs, original proposals, builds and installed packages. Restore
checks source hashes and sealed material before replaying/rehousing custody.
As with other source forms, this is local exact source custody and receiving
admission, not a proof of arbitrary behavior, authenticated authorship from a
hash alone, or permission to publish externally.
