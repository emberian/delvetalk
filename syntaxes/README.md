# Source interfaces

Durable objects use `objective-bend-object`: exact Bend source exports `describe`,
methods and `view`, checked and executed by the native source host. Single-module
and sealed ordered modules use the same interface. See
[source objects](../profiles/TYPED-SOURCE-OBJECTS.md),
[module authoring](../profiles/MODULE-AUTHORING.md), and
[the binding](obend_object.py).

```sh
python3 scripts/translate.py --syntax objective-bend-object syntaxes/examples/lantern.obend
```

Translation retains source, adapter identity and lowered artifact. It neither
installs a program nor grants authority. Submission, compiler reports and explicit
adoption use [the source desk](../profiles/DESK.md). A changed target or current law
may refuse a reviewed candidate. Recover an uncertain attempt before creating
another one.

## Scenes and examples

`spween-source@1` parses retained scene source. `spween-handler-workshop@1` joins
scene text with authored Bend handlers and the source scene runtime. Build its
pinned Rust bridge with `make scene-build`; follow
[the handler workshop](../protocols/spween-handler-workshop/README.md) for exact
source packaging. The [Spween guide](../scene/README.md) owns supported scene
operations. A parsed scene alone is not a running world object.

`examples DelveTalk 1` expresses fixture principals, actions, observations and
expected results/refusals. Examples run the actual candidate and host interface;
they are finite checks, not permission grants or general proofs. Views are checked
without executing an offered action. Source keeps executable behavior; fixtures
supply inputs and expected observations. Named `fixture` peers run independent
copies of the exact proposed source. `send peer/command` selects a peer, while
`transaction`, `call object/command` and `from previous` compose checked native
results under one caller. See the [two-hand relay](../protocols/behavior-examples/README.md)
for the notation and its in-world inspect/revise/check journey.

## Independent core notation

`core-json@1` and `core-sexpr@1` describe the small independent evaluator fragment.
The [AST contract](../conformance/AST.md) specifies it. Core validation checks
shape rather than typing or progress. These evaluators cross-check language
behavior; they do not admit durable object changes.

## Custody and registration

[registry.json](registry.json) names explicit adapter entrypoints and dependency
closures. Pins bind actual bytes, not authorship or authority. Retain exact UTF-8
source and compiler/runtime identities with the artifact. Unknown syntax refuses;
a proposal cannot select arbitrary host code.

Physical parser/transport adapters must remain small. Author behavior and source
composition in Bend, and use native parsing for its meaning. A new notation needs
an explicit reviewed contract and all affected consumers; an adapter registration
alone does not establish deployment. See [source packaging](../docs/design/SOURCE_PACKAGING.md).
