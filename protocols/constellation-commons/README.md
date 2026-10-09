# A constellation of borrowed light

An ordinary source Bend collaborative art instrument. Place an image and a line
beside other people's lights; read the shared sky as a poem, inspect a numbered
light, and return to revise your own words. Multiple contributions by the same
author remain separate. There are twelve places, with images bounded to 80 and
lines to 240 characters. Filling the sky does not close revision.

[Constellation.obend](Constellation.obend) owns the transitions, description and
offered encounter. [Stars.obend](Stars.obend) uses the shared generic source
`List` library for the attributed collection. Load `Abi`, `List`, `Encounter`,
`Stars`, then `Constellation` through `obend-object@1`; the actual module loader
and receiving tests are in
[test_constellation_source.py](../../conformance/test_constellation_source.py).
No generated protocol or empty migration twin is shipped.

The source methods are:

```text
contribute {image: String, line: String}
revise     {id: Nat, image: String, line: String}
visit      {id: Nat}
```

`context.principal` supplies attribution. Request payloads cannot select an
author. A revision requires that current caller to match the retained author;
other contributors cannot overwrite that light. `visit` selects a light for the
shared encounter; inspection and selection confer no editing authority. The
view offers contribution, numbered inspection, and revision of the selected
light. Its revision invitation says “Author”; admission still checks ownership.
The same caller context applies to every call in a transaction.

[law.json](law.json) is an explicit local source policy: Iris, Moss and Fern can
contribute, revisit and revise their own work; Builder can reprogram and Steward
can manage law. Local names are trusted local caller assertions. This policy is
separate from Commons presence and shared-place stewardship. Current grants,
exact observed roots and retained retry receipts remain host obligations. An
uncertain reply should retry the identical request and intent; a stale refusal
requires a new observation and intent.

Run the dedicated receiving checks against a matching qualified native host:

```sh
python3 -m unittest conformance.test_constellation_source
```

They cover two authors composing and revising through offered forms, retained
inspectable source, unauthorized edits, malformed and forged-author input,
stale roots, exact retries, full capacity and current policy changes. Source
compilation and actual receiving tests are separate evidence; this package does
not establish deployment.
