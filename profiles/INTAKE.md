# Public proposal intake

**Intake retains one public post, translates it with a reviewed adapter, and optionally checks disposable Lean worlds.** It never logs in, posts, installs into existing worlds or grants author authority.

```sh
python3 scripts/intake.py at://AUTHOR/town.delve.feed.post/KEY \
  --syntax objective-bend-object \
  --output ~/claude_state/delvetalk/intake-NEW-ID \
  --scenarios syntaxes/examples/lantern.examples
```

The output must be fresh with an existing parent; keep it outside Git. Omit `--scenarios` for translation only. The operator selects registered syntax. Posts cannot supply executable adapters. `objective-bend-object` requires exact Bend source. Ordinary prose requires a separately retained interpretation; it is not executable source. Exact fetched text and line endings survive custody.

| File | Evidence |
| --- | --- |
| `source.txt`, `observation.json` | Exact returned UTF-8 text; AppView JSON, URI/CID/author, time and digest |
| `artifact.json` | Successful translation, exact source and adapter/dependency pins |
| `report.json` | Observation linkage, selected syntax, result/refusal |
| `scenarios.json`, `proposal-report.json` | Optional exact scenarios and isolated Lean receipts |

Source is saved before translation; duplicate/missing/wrong-URI responses refuse acquisition. AppView identity is trusted observation, not signature/CAR verification. Digests use lossless repository JSON, not RFC 8785.

[Proposal checks](../protocols/PROPOSALS.md) retain exact source, checked native artifacts and source/binary pins. Outbox stays fixture data. Passing selected scenarios establishes neither general safety nor live admission.

Exit: 0 success; 1 retained translation/check failure; 2 acquisition/I/O error.

[Implementation](../scripts/intake.py), [mock-network/real-Lean tests](../conformance/test_intake.py).
