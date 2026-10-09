# Bend is the implementation home

**Decision.** DelveTalk is an inhabited, metaprogrammed Bend system. Its world,
workflows, scene relation and interaction logic are source programs. Lean supplies
the language implementation and the smallest explicit admission boundary. Python
supplies necessary physical custody, process and platform I/O. This is the target
architecture; the audit below identifies current violations, not accepted layers.

Native execution is insufficient: Python which chooses an AST's guards, writes,
phases or action sequences is still the author of those semantics. Moving its
output into a `.obend` file without reusable source definitions preserves the
wrong authoring model. A JSON encoding is unobjectionable as transport; an extra
Python language for deciding what that encoding means is not.

## Concrete replacements

| Current owner | Source owner to build | Removal |
| --- | --- | --- |
| `protocols/work-ticket/generate.py` | `ReviewableWork` and a ticket object: phase, participants, submission, review, encounter | Guard/write/view generator and generated scenario authoring |
| `protocols/shared-exhibition/generate.py` | Arrangement plus approvals bound to that arrangement; independently authored exhibition | Parallel role, consent and menu construction |
| `protocols/commons/generate.py` | Typed presence/graph relations over configured data | Unrolled participant/edge code and copied place descriptions |
| `protocols/editor/offers.py`, `scripts/editor.py` | Editor's actual source lifecycle and reusable preparation functions | Source-writing DSL and editor-specific orchestration |
| Town-forge and Editor factory generators | Source `CandidateDesk` and `Factory` specializations | Python-generated phases, child policy and scalar migration language |
| `scripts/contract_authoring.py` | Source `ContractWorkshop` composing verified observations and law proposals | Python's eligibility, law-amendment policy and release choreography |
| `scene/handlers.py` control-flow generation | `SceneRuntime` over typed scene data, importing the selected Handler | Python definitions of guards, entry, effects, visitation and navigation |
| `game/table/protocol.py` | `CommitRevealTable` around the existing qualified Bend game | Commitment/reveal/reset behavior authored as Python AST |

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
boundary. Retire `source_offers.py`'s alias environment, dotted substitutions,
result registers and captures as an operational Python language. Source chooses
participants and ordering; native admission checks every actual effect. A source
plan is a proposal, never authority. See [composition](COMPOSITION.md).

**Environment services are explicit.** Compilation, verified specification
observation, hashing, governed allocation and persistence need a host boundary.
Give source fixed typed requests/results and authenticated provenance. The host
must not choose the applicant's lifecycle, grants, migration strategy, deadlines
or story outcome. A source-produced allocation still faces parent/child law and
exact absence checks. A source-produced law amendment still faces old and new law.

## Parallel implementation

Ticket, agreement, presence and scene-runtime conversions can proceed independently
on the existing typed source substrate. Preparation and source-allocation are
separate native/source seams. Contract workshop and reusable candidate/factory
objects consume those seams as they become available. Commit/reveal can progress
against the existing game kernel without waiting for any of them.

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
fronts extend the decision above; they are not claims of completed implementation.

- **One explicit prelude.** Share Context, Origin, encounters, effect data and
  collection definitions through the sealed module mechanism. A convenient
  implicit import must still resolve to a retained dependency, never ambient
  mutable source. Reuse existing collection modules before inventing another List.
- **Text computation.** Add deliberate, tested text construction and inspection
  semantics, including concatenation and numeric rendering. Decide Unicode
  length/slicing and resource charging before installing primitives. Check the
  upstream language boundary; distinguish a declared extension from the pinned
  normative core. Objects must be able to describe their own changing contents.
- **Collections with explicit bounds.** Replace hand-enumerated mail, consent and
  appointment slots with collection algorithms where supported. Keep capacity,
  per-turn work and causal growth as explicit budgets. Lists alone do not make
  evaluation efficient: measure an inhabited room with 200 objects, including
  view construction and action preparation, before choosing representation or
  evaluator improvements.
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
