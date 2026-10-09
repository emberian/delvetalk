# Source Candidate custody

For the explicit `compiled` profile, `Desk.create` loads the ordinary
`protocols/editor/Candidate.obend` through its source `ordinary()` constructor. Editor
factories use the same source with editor approval enabled. The object owns
submission, compiler-report acceptance and release; custody code does not decide
these transitions. Historical plain Candidate roots remain readable, and the
`transactions` profile retains its earlier body for compatibility.

`desk.candidate_state(root)` is a structural projection for compiler custody.
It reads the typed model's scalar fields and asks the native shared Preparation
codec to decode proposal, migration, protocol, diagnostics and roomArtifact.
Requests, exact-read roots, build identities and retained receipts continue to
carry the original complete root. The projection never replaces that root.

`source_object.value(json)` encodes a configuration as `Preparation.Value`.
The bounded pure compiled request is `{op:"value-codec",direction,values}`,
where direction is `encode`, `decode` or `digest`. The response contains a status
and an equally sized values array. Native conversion reuses Preparation's
64-depth, 100000-work codec, with at most 64 values and a 1 MiB request. The
physical runner captures and rechecks the compiled runtime closure. It does not
write a world, resolve source imports or choose workflow policy.

Successful typed Candidate compiler completion includes the native digest of
the actual checked protocol. This is the same FileCustody representation used
by the host's program identity; Python's JSON hashing does not substitute for it.
The reviewed-service recognizer compares the complete source package and method
body with the reviewed Candidate, allowing its explicit initial configuration.
This selection grants no authority; every actual operation faces current law.

Numeric conversion follows the native JSON representation. Decimal value and
scale are retained without Python floats; native integer mantissas normalize
negative zero to zero. Original request custody still retains its original
framing. This codec does not claim preservation of the sign of zero.
