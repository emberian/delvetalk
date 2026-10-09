# Bounded program fingerprints

`program-digest` and the fingerprint returned by `reprogram` share one native
implementation, [ProgramDigest](../../profiles/ProgramDigest.lean). The compiled
turn still has 100,000 work units. This is an explicit host tariff change; older
one-unit-per-byte pricing rejected a useful 122KB source factory before hashing.

**Bytes are unchanged.** FileCustody emits sorted keys, UTF-8 strings and exact
JsonNumber mantissa/scale. It accumulates into one string instead of rendering
intermediate subtrees. `120e-2` remains distinct from `12e-1`. No normalization,
truncated digest or alternative hash is introduced.

**Pay before work.** A bounded preflight counts the exact output bytes without
constructing the output. Its shared turn ledger charges:

| Work | Units |
| --- | --- |
| JSON node or object key | 1 |
| Scanned string bytes, rounded across the whole value | 2 per 64 bytes |
| Two decimal conversions per integer component | 2 × squared 64-bit limb count |
| Canonical rendering | 8 per 64 output bytes |
| SHA-256 compression, including padding | 32 per block |

String scans are prepaid. Integer limb work is prepaid before decimal conversion.
Rendering and hashing are prepaid after the exact size is known. Nesting is capped
at 256; encoded output at 1MiB. Refusal changes no object. Repeated fresh hashes
consume the same ledger; a retained exact retry returns its previous receipt.
Other hash profiles keep their existing, stricter tariffs.

**Measured, not timeless.** Native local calibration used a retained 122,447-byte
SessionFactory: accumulation reduced serialization from 1.87ms to 0.66ms;
SHA-256 took 2.87ms. A recursive Nat workload measured roughly55ns per machine
step. The complete measured digest took4.79ms and costs89,647 units. Block
pricing is a bounded logical model, not a wall-time guarantee across machines.

[Receiving checks](../../conformance/test_program_digest.py) cover canonical
Unicode/escapes/large integers/scale, near-budget success, shared-ledger
exhaustion, output/depth/decimal bounds, rollback/retry, and actual configured
SessionFactory revision. Source representation remains a separate optimization;
this change does not remove its retained checked child program.
