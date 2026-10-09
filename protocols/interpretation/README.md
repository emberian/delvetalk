# Source-owned interpretation and retained model activities

`Interpretation.obend` owns the literal language, local offer selection, typed
partial bindings, questions, prompt instructions, vocabulary, examples and
escalation policy. `WorkshopPolicy.obend` demonstrates ordinary source
specialization. Policies are ordinary values and functions; the host has no
noun/verb router. Editing a policy produces another revision and exact source
capture. The default economical model is `claude-haiku-5-5`.

`scripts/interpret.py` transports the existing public-card consumer through
native compiled source. Its compatibility literal syntax is `do CARD ACTION
JSON`; the source `route` function owns that syntax. Literal input bypasses the
provider. Both literal and model input can return `partial` with retained fields
and `unresolved` names. Complete fields return a proposal for the captured offer.
Preparation and current authority still belong to the receiving source/native
path; a proposal does not select a principal or execute anything.

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
tools are enabled. Provider failures retain no diagnostic strings that might
expose credentials. A configured API key and explicit private custody directory are required for the real provider;
controlled providers permit deterministic boundary tests. Physical custody defaults to 32 jobs and 4 MiB per explicitly selected account/realm directory, reserving bounded receipt space before the call. A nonblocking service lock permits one provider call at a time; busy/quota outcomes cause no spend. Account identity is included in the retained exact job.

The existing portal interpretation API retains card, utterance and result. Real
provider results additionally identify the exact retained request, policy
revision, module digest and selected context references. The shared `ConversationModel.obend` joins source request construction and source preparation to the governed Notebook `retain` method. Its request retains an opaque source-produced interpretation envelope; preparation validates the returned proposal against the local source schema, exact offer meaning and selected policy, then emits the ordinary native invocation. The receiving method rechecks current policy and capture and derives actor from the authenticated context. The independent generative section API describes retained output; its receipt remains model I/O, never authority to act.

Run `python3 protocols/interpretation/test_interpretation.py` and
`python3 -m unittest conformance.test_interpret`. These run real native source
compilation/evaluation with a controlled provider, covering partial fields,
stale captures, model authority attempts, changed prompts, malformed/missing
replies, bounded quotas/concurrency, exact retry custody and pure retained rendering. The source request → controlled provider → source preparation → actual native Resident admission test checks the joined receiving path, actor attribution, partial intention, wrong-policy refusal and both model/admission receipt recovery. No network is required.
