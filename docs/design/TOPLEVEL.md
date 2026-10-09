# The living conversational document

**Working design, 2026-10-09.** Ember selected this as the default top level.
Syntax sketches below are design material, not an installed grammar. Authentication,
private heaps, native admission and source encounters remain the implementation
substrate; this design joins their presentation and authoring rather than adding
another executor.

## One encounter, several contributions

A document is a governed source object presenting an ongoing encounter. It can
contain prose, named references, offered actions, incomplete intentions, examples,
source cells, results and continuations. Private studios, shared places and
workshops specialize this construction. A document need not monopolize its
participants' objects: it refers to independently governed things.

A contribution arrives with authenticated actor, document/conversation identity,
reply context, original content and explicit attachments. It may answer an offered
field, speak naturally, submit a small local notation or evaluate source. These
are entry methods on the same encounter. They share captured references, partial
bindings, unanswered questions and outcomes. The REPL does not become a separate
operator identity; literal forms need no model call.

A small outer envelope addresses a document and optionally selects an offer or
language. Replies normally inherit that context. Frontmatter can expose the
address when useful, but its presence is not compulsory and its strings confer
no authority. The body belongs to the selected source interpretation. Avoid a
universal growing list of host-defined verbs.

A smaller model should be able to pick an offered token, fill one field and make
a useful contribution. A stronger model can inspect the offer's meaning, compose
it with another operation, or revise the interpreter. Both refer to the same
underlying operation and receive the same admission semantics.

## Rich templates are document constructors

The intermediate value is a structured document, not an HTML string. Its small
vocabulary includes text, sequences, quotations, references, fields, choices,
actions, source/results, inclusions and pending continuations. Browser and Town
renderers preserve the selected meaning and named targets while adapting layout.
A rendered action label remains attached to a captured typed offer; concatenating
similar text does not manufacture an action.

A template is an ordinary pure Bend function over explicit context which returns
that document. Low-ceremony syntax should lower to this function. Support literal
text, interpolation, iteration, conditionals, pattern matching, lexical locals,
partials, named slots, inclusion and specialization. Retain Unicode/whitespace
where requested; support literal quoting without elaborate escaping. Templates
may return templates and accept document fragments/functions as arguments.

Self/Super composition should apply to document sections, phrasebooks and prompt
construction, not merely to object methods. For example, a workshop can inherit
a common review invitation and specialize its examples, vocabulary and escalation
policy. A reusable component carries its selected module revisions and contracts.

A useful context contains the subject, authorized observations, participant,
current intention, prior outcomes, offered operations and chosen presentation
style. It contains no ambient entire-world or private-heap dump. Including another
object's view requires its actual authorized observation; copying code is a
separate operation.

## Model-assisted interpretation is programmable

A room or participant selects an interpretation policy: examples, vocabulary,
prompt template, permitted context, model preference, result schema and escalation
behavior. Haiku 5.5 is the intended initial economical service. Its network adapter
supplies bounded provider I/O; prompt construction and interaction policy belong
in Bend. API credits are physical service funding, not mandatory object payers.

Haiku can select an offered operation, extract partial arguments, identify
unresolved references, explain a refusal or suggest a protocol revision. Its
output is a typed interpretation proposal retaining original utterance, prompt
revision, actual context references and proposed bindings. Native/source checking
then prepares the same operation that a literal form would select. A well-formed
model response is neither evidence of user intent nor authority to commit.

Templates and model requests need distinct execution semantics. Pure rendering
does not silently invoke a model, send a message or charge a service on every
refresh. A generative section requests an explicit bounded activity and retains
its result for reuse. Source chooses when to regenerate, ask, act within delegated
scope or escalate. No global confirmation ritual is imposed on every action.

Prompt quotation and data/instruction boundaries are explicit document structure.
They improve interpretation; actual authority remains in the receiving host.
Private context is supplied deliberately according to the participant's policy,
not automatically bundled with a public room's prompt. Model/provider failure
becomes a retained pending/error outcome, never fictional execution.

## Live state and authorship

A document can render current state and retain earlier contributions. Old posts,
questions and action captures keep their exact references; a live region obtains
a new explicit capture. Source-cell output records the source that actually ran.
Changing a template or parser is an ordinary governed revision, with scratch
examples and replayable interactions before adoption.

A reusable intention retains focus, selected offer, partial answers, unresolved
choices and lifecycle status. It can accept contributions from multiple actors
without merging their identities. Save/restore, receipt recovery, browser controls,
Town replies and the native REPL all encounter that same object.

## Next design exercise

Prototype one document in three forms: a Delve post, browser view and agent API
response. A visitor asks to lend a moth, answers one ambiguity, inspects the exact
offer, and receives its actual outcome. Then another participant changes the
prompt/template and repeats the exchange. Show source and template expansion;
prove literal input still works with the model unavailable.

Use this to choose the first template notation and intention ABI. Do not invent
three unrelated front ends or hardcode the demonstration's nouns into the host.
