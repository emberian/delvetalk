# The moth workshop

One author writes a Spween scene and its ordinary Bend handlers. Another changes
the repair from one counted repair to two. The same moth, inventory and passage
survive the revision. Old action cards refuse; restored history retains both
complete source documents and the installed state.

The explicit syntax `spween-handler-workshop@1` accepts one `spween` block and
ordered `obend NAME` blocks, ending in `Handler`. For example:

````text
spween handler workshop 1

```spween
---
id: example
title: A small workshop
---
=== bench
* [Repair]
  ~ repair
  -> bench
```

```obend Handler
...ordinary Objective Bend handler source...
```
````

Use the complete runnable source, including its Handler ABI:

```sh
python3 protocols/spween-handler-workshop/generate.py --source
python3 protocols/spween-handler-workshop/generate.py --source --revision 2
```

[Scene](moth.scene), [first handler](Handler.obend), [revision](Chorus.obend), and
[text examples](moth.examples) are editable source. The compiler supplies a pinned
Kernel and generates Scene; authors cannot replace those reserved modules. Every
other dependency is an explicit ordered module block. The native frontend resolves
and checks those modules. Python neither executes handlers nor searches for imports.

`generate.build(authors, compiler)` supplies ordinary governed factories. Its
initial placeholder state comes from native `describe()`. Each proposal gets a
fresh desk. `submission_offer(candidate, candidate_root, target, target_root)`
creates a writing card bound to both exact observations. The resident fills only
source and examples; the offered migration explicitly preserves the entire
captured target state. If the target changes before submission, Lean refuses the
transaction. Checking examples produces a review card; adoption separately checks
current authority and both reviewed roots. Preservation does not prove that an
arbitrary replacement handler accepts that schema; incompatible migrations remain
a matter for explicit examples and receiving checks.

The source wrapper retains the complete document; the lowered program retains
exact scene and ordered handler strings. Adapter, parser, generated-source helper
and native runtime dependencies are pinned with compiler custody. A source block
confers no authority. Two authors in the demonstration have explicit shared grants.

After the existing native hosts are built:

```sh
python3 conformance/test_spween_handler_authoring.py
```

The journey runs text posts through receiving custody, compiler queue, checked
adoption, two-person play, handler revision, stale refusal, history export and
restoration. Only public record GETs are simulated; nothing is posted externally.
