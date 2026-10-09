# Bend is the implementation home

**Decision.** DelveTalk is an inhabited, metaprogrammed Bend system. Its world,
workflows, scene relation and interaction logic are source programs. Lean supplies
the language implementation and the smallest explicit admission boundary. Python
supplies necessary physical custody, process and platform I/O. This is the target
architecture. Remaining behavioral owners below require consumer cutovers.

Native execution is insufficient: Python which chooses an AST's guards, writes,
phases or action sequences is still the author of those semantics. Moving its
output into a `.obend` file without reusable source definitions preserves the
wrong authoring model. A JSON encoding is unobjectionable as transport; an extra
Python language for deciding what that encoding means is not.

## Current source owners

[ReviewableWork and Ticket](../../protocols/work-ticket/README.md) own ticket
phases, review and encounters. [Agreement and Exhibition](../../protocols/shared-exhibition/README.md)
own arrangements and revision-bound approval. Their package loaders retain exact
modules and explicit configuration; they do not generate behavior.

[Editor, Candidate and Factory](../../protocols/editor/README.md) now own their
lifecycle, preparation, child construction and child law in source. The Editor
client retains native preparation results and admission receipts. Source
preparation returns complete plans, questions or refusals through the native
boundary; `source_offers.py` retains captured invitations and transports those
calls. These paths replace the client recipe interpreter.

[SceneRuntime](../../scene/runtime/README.md) owns guards, effects, entry,
visitation and navigation. `scene/handlers.py` serializes the parsed scene as
typed data and packages explicit handler/runtime/scene modules. Serialization of
that data is not control-flow generation.

Town-forge, stateful and Spween workshops package source factories and writing
participants. Contract release invokes source `prepareContract`; its Python helper
retains compiler observations and receipts. Workshop seeds use source factories.
Their `generate.py` names do not imply behavior generation.

These are current implementation boundaries, not claims of whole-system
qualification or deployment. [TRACKING](../../TRACKING.md) owns integration status.

## Remaining consumer replacements

| Behavioral owner | Source replacement | Cutover obligation |
| --- | --- | --- |
| `protocols/commons/generate.py` | Typed presence/graph relations over configured data | Remove unrolled participant/edge policy; preserve gated origin checks and distinguish presence from containment. |
| `scripts/authoring.py` | Source workshop encounters/preparation | Remove Python selection of application steps as its actual CLI/portal consumers move. |
| `game/table/protocol.py` | `CommitRevealTable` around the existing Bend game | Move commitment/reveal/reset behavior; retain private nonce custody and transport. |

The [repository consumer graph](REPOSITORY.md#cut-over-consumers-then-delete-the-duplicate)
identifies callers that must move together. A new source object does not finish a
cutover while the advertised seed or CLI still installs its generated predecessor.

Automatafl gameplay already lives in Bend; preserve the original two-player
11×11 rules and opening. Its small presentation wrapper is not the substantive
problem. The independent Python/C/JS evaluators remain test oracles, not alternate
world implementations. Test harnesses do not grant permission for application
policy to live in Python.

## Small shared boundaries

**Configuration is checked data.** Explicit source configuration belongs to the
object's retained definition/root. Do not specialize programs using source string
replacement or unroll a configured collection into generated methods. Start with
typed initial state and explicit source constructors; add native configuration
binding only where a concrete source interface needs it.

**Preparation is source evaluation.** An ordinary pure Bend export takes typed
arguments and explicit observations and returns a complete bounded plan or an
authored question/refusal. Root binding and validation belong to one native
boundary. Clients retain invitations and native results; source chooses participants
and ordering. Remaining recipe callers must use that invitation contract. Native
admission checks every effect. A source plan is a proposal, never authority. See
[composition](COMPOSITION.md).

**Environment services are explicit.** Compilation, verified specification
observation, hashing, governed allocation and persistence need a host boundary.
Give source fixed typed requests/results and authenticated provenance. The host
must not choose the applicant's lifecycle, grants, migration strategy, deadlines
or story outcome. A source-produced allocation still faces parent/child law and
exact absence checks. A source-produced law amendment still faces old and new law.

## Parallel implementation

Presence and commit/reveal can progress independently. Qualify source workshops
against native preparation, verified observations, allocation and law boundaries
as one receiving composition.

Each conversion ends by changing its consumers and deleting the old behavioral
owner. Do not accumulate a new Bend object beside a permanently supported Python
twin. Use current positive and refusal journeys to detect changed meaning; add
checks for the new source composition, not tests that merely repeat generated data.

The architectural question in review is: can an inhabitant inspect, reuse and
change this behavior as DelveTalk source, or must a developer edit the harness?
Moving the Python workflow interpreter into Lean also fails this test. The native
boundary should validate and enact explicit effects; the program that chooses and
composes them must remain available to Bend authors.

## Make source sufficient for inhabitants

The replacement requires language ergonomics as well as correct ownership. These
fronts distinguish existing substrate from remaining consumer and design work.

- **One explicit prelude.** [Shared source modules](../../world/lib/prelude/README.md)
  provide context, encounters, preparation and allocation data. Sealed packages
  retain their exact dependencies; no ambient import is supplied. Replace remaining
  repeated declarations at consumers. Domain-specific collections can remain beside
  their behavior rather than pretending to provide polymorphism.
  The [generic sums and functions proposal](GENERICS.md) specifies bounded native
  specialization and two consumer cuts; it is not an implemented language feature.
- **Text computation.** Hosted text operations implement concatenation, decimal
  rendering and Unicode-scalar length/slicing without normalization. The
  [focused checks](../../conformance/test_text_primitives.py) cover types, lazy
  evaluation and work/allocation budgets. Preserve the explicit extension boundary
  and source provenance; qualify receiving consumers with the matching runtime.
- **Collections with explicit bounds.** Use domain collections for mail, consent
  and appointments rather than hand-enumerated slots. Keep capacity,
  per-turn work and causal growth as explicit budgets. Lists alone do not make
  evaluation efficient. Paged encounter collections and 200-entry workloads exist;
  qualify inhabited-room view construction and action preparation before claiming
  that those measurements establish the whole interaction budget.
- **References with precise meaning.** Design a typed distinction between text,
  resolved object identity and authenticated provenance. A host-minted identity
  value can prevent accidental text substitution; it does not automatically
  confer authority or prove that someone observed the object. Specify minting,
  serialization, revalidation and law checks before adding a primitive. Prefer
  an opaque host-profile type if it suffices; a core extension needs justification.
- **One current language boundary.** Remove the tagged JSON expression evaluator
  as its application consumers become Bend programs. Keep structural effect/data
  encodings. Collapse unlaunched profile ladders at their consumers; supported
  semantic distinctions should be expressed deliberately, not as archaeological
  version choices presented to inhabitants.
- **Examples live with behavior.** Put executable domain examples beside source
  and expose them through the same governed inspection interface. Extend the
  source example runner for multiobject behavior where necessary. Keep external
  crash, process, authentication, transport and differential tests: a domain
  example cannot establish those boundary properties by itself.
- **A quick private workshop.** An explicitly installed scratch law can allow
  immediate checked revision by its authorized builder. Shared review is another
  authored policy, not a compulsory host ceremony. Both face current law, exact
  preimages and invariants; promotion to shared governance is an explicit change.

Room-local verb resolution belongs in a revisable Bend library using governed
observations and offered actions. It should return alternatives or a partial
intention when ambiguous, and must not gain unrestricted read access by being a
parser. Model-assisted interpretation can use the same finite set of affordances.
Physical clock drivers and bounded receive-to-send chains connect this library to
the durable collaboration design in [composition](COMPOSITION.md).

### Conditional record updates

A conditional may return an existing record on one branch and `extend(record,
{field: value})` on another. Equivalent record fields may appear in a different
order; both branches must still agree on each field's type. This also works for
an updated record nested inside a decision, and for natural-number and sum
matches whose arms return equivalent rows. An unchosen branch stays lazy.
The checker admits equivalent rows through its existing checked conversion;
the typing rule and restricted-value sharing rules remain unchanged.

A concrete recursive record alias can also be extended. The frontend rebuilds
its declared row around one shared lazy base cell: overridden fields do not
force the base, and retained fields project it only when demanded. Fields can
change type or be added when the enclosing result declares the resulting row.
Open `Self`/`Super` variables keep their abstract tails; their lower bounds are
not aliases. This shared reconstruction refuses affine bases and affine
captures. Consuming record updates need a separate ownership rule.

### Bounded layer composition

Open `Self`/`Super` layers can wrap closed layers whose equivalent record fields
use a different declaration order. Composition still checks every required
member and its type; a lower bound is not permission to replace a rigid type
with that bound. Callable conversions preserve specification metadata, and
restricted values cannot become reusable through row normalization. The
checker constructs the existing composition and fix judgments through checked
conversion; this does not introduce a new typing rule.
