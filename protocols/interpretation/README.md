# Source-owned interpretation and retained model activities

`Interpretation.obend` owns the literal language, local offer selection, typed
partial bindings, questions, prompt instructions, vocabulary, examples and
escalation policy. `WorkshopPolicy.obend` demonstrates ordinary source
specialization. Policies are ordinary values and functions; the host has no
noun/verb router. Editing a policy produces another revision and exact source
capture. The default economical model is `claude-haiku-5-5`.

Physical opt-in accepts `ANTHROPIC_API_KEY` or an explicitly selected
`--tokeman-account NAME` with `--anthropic` (`--agent-anthropic` for account
portals). The selector reads tokeman's private credential file without changing
it or refreshing credentials. OAuth uses bearer authentication to the fixed
Anthropic endpoint; API keys use `x-api-key`. Credentials never enter a source
prompt or retained job. A confirmed HTTP refusal retains `rejected`, its status
code and an allowlisted error category; a lost response remains `uncertain`.
Both recover their original receipt on exact replay and never spend again.
An input that cannot fit the physical request frame is retained as `unsupported`
before network I/O; it does not become an uncertain paid attempt.

`scripts/interpret.py` transports the existing public-card consumer through
native compiled source. Its compatibility literal syntax is `do CARD ACTION
JSON`; the source `route` function owns that syntax. Literal input bypasses the
provider. Both literal and model input can return `partial` with retained fields
and `unresolved` names. Complete fields return a proposal for the captured offer.
Preparation and current authority still belong to the receiving source/native
path; a proposal does not select a principal or execute anything.

Authored conversations construct `Schema`, `Shape`, `Offer` and `Card` directly
as checked source values. Text and natural bounds, booleans and enumerated
reference choices are distinct Shape arms; a proposal carries typed `P.Fields`.
`ConversationModel` does not construct a JSON card or decode a JSON schema.
Only copied public cards and provider replies use the heterogeneous Value
boundary. The external-card decoder returns explicit invalid/found outcomes:
wrong arrays, availability flags, option types and bounds refuse. Missing
optional minimum lengths and inspection flags have declared defaults; malformed
values never acquire those defaults. Reply fields are checked against the typed
offer before entering the typed conversation envelope.

Prompts retain a structured `Document`: authored instructions and explicitly
quoted selected context. Provider content contains only the supplied public card
and original contribution. The conversational source helper selects an explicit local document excerpt using the policy’s `contextScalars` budget (8192 by default). No heap, private observation, credential store or
ambient account context is fetched. `Encounter.obend` supplies the shared
`Conversation.Interpretation` constructor for explicit authorized observations,
exact capture, original text, policy revision, bindings and questions. The
receiving conversation rechecks its revision/capture and authenticates actor
separately.

`Encounter.obend` also owns an explicit generative section's pending/received/
uncertain/error state, regeneration generation, request identity, template
revision, authorized context and retained output. `render` only reads this state.
It cannot make a provider request. It refuses a receipt for another request or a
second receipt, and regeneration requires a new key and increasing generation.
The section receipt describes model I/O, never an admission receipt.

`scripts/model_service.py` supplies bounded Anthropic Messages I/O and durable
exact job/receipt custody. Before crossing the network it fsyncs a pending job;
exact retries recover the retained receipt. If a response is lost, the job stays
uncertain and replay does not charge again. Explicitly creating another
generation is a new activity. No implicit supervisor calls, retries or provider
tools are enabled. Bare JSON and one complete `json` or unlabelled JSON code fence are supported transport formats. Surrounding prose, multiple fences, duplicate members and incomplete output produce an explicit retained `provider-error`; replay reads the same receipt instead of making another call. Provider failures retain no diagnostic strings that might
expose credentials. A configured API key and explicit private custody directory are required for the real provider;
controlled providers permit deterministic boundary tests. Physical custody defaults to 32 jobs and 4 MiB per explicitly selected account/realm directory, reserving bounded receipt space before the call. A nonblocking service lock permits one provider call at a time; busy/quota outcomes cause no spend. Account identity is included in the retained exact job.

The existing portal interpretation API retains card, utterance and result. Real
provider results additionally identify the exact retained request, policy
revision, module digest and selected context references. The shared `ConversationModel.obend` joins source request construction and source preparation to the governed Notebook `retain` method. Its request retains an opaque, typed source-produced `C.Interpretation` envelope; preparation validates the returned proposal against the local source schema, exact offer meaning and selected policy, then emits a typed native invocation. The captured `contributionCodec: data` invitation and receiving `inputCodec: data` method use the native declared types; no hand-written envelope shape checker or JSON-to-envelope coercion remains. The receiving method rechecks current policy and capture and derives actor from the authenticated context. The independent generative section API describes retained output; its receipt remains model I/O, never authority to act.

Run `python3 protocols/interpretation/test_interpretation.py` and
`python3 -m unittest conformance.test_interpret`. These run real native source
compilation/evaluation with a controlled provider, covering partial fields,
stale captures, model authority attempts, changed prompts, malformed/missing
replies, bounded quotas/concurrency, exact retry custody and pure retained rendering. The source request → controlled provider → source preparation → actual native Resident admission test checks the joined receiving path, actor attribution, partial intention, wrong-policy refusal and both model/admission receipt recovery. No network is required.

Notebook interpreters now retain their policy in typed conversation state. Open
“Prompt and conventions” to inspect the actual revision, model, prompt sections,
response/context bounds and offered field schema. Its ordinary
`reviseInterpretation` form asks for a new revision, a section and replacement
text. Sections are instructions, vocabulary, examples, escalation and model;
empty vocabulary/examples/escalation explicitly clears that section. Numeric
limits and the rich Document templates remain ordinary editable source in the
same retained package, inspected and revised through the source workspace.

A successful edit rotates the captured meaning, resets active field bindings,
and retains an attributed outcome containing both policies. The next source
request uses the new policy; a previously prepared envelope fails its old
capture/revision check. Each notebook retains at most 32 such revisions before
source revision is needed. Native current law governs the editing method just
as it governs retaining a contribution; editing a prompt grants no action
permission and cannot forge an actual operation result.
