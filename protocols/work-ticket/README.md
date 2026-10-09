# Reviewable work

[ReviewableWork.obend](ReviewableWork.obend) owns participants, phase transitions,
submission/review decisions and encounters. [Ticket.obend](Ticket.obend) is a small
ordinary object using those definitions; it supplies its declared forms and
exports the methods. Both import the explicit shared Abi and Encounter modules.
There is no behavioral Python generator or generated protocol twin.

A requester posts work; a participant claims and submits it; the requester
accepts or rejects the submission. The typed phase is one of draft, open,
claimed, submitted, accepted and rejected. Actual Context.principal stamps the
caller. Only the claimant submits and only the configured requester posts or
reviews. Terminal review cannot be overwritten. Acceptance acknowledges review;
it neither changes a target nor certifies an external effect.

The source view shows the task before submission, the submitted result before
review, and the review afterward. It offers the applicable phase actions. The
source also declares the forms: task/result text up to 2,048 scalars, review up to
1,024. Form bounds help input preparation; raw source guards require nonempty
text and the host's bounded input still applies. A visible action is not a grant.

Configuration is explicit typed data, retained in the root. `initial(config)`
constructs the complete state in Bend. The default [configuration.json](configuration.json)
names the requester and three optional references: context, about and replyTo.
Each is an absent/present variant; present holds a fixed
`{format,world,object}` reference record. [package.py](package.py) only loads exact
source/configuration bytes and invokes the native compiler. It does not produce
methods, guards, menus or migrations. Physical reference encoding is validated
by the existing reference boundary. A reference establishes no existence,
observation, foreign lookup or permission.

[law.json](law.json) is explicit fixture grant data: requester post/review,
Moss/Iris claim/submit and steward management. Native receiving checks current law
independently of the source's participant rules. Law revision does not bypass
those source rules. There is no scheduler, timeout, reassignment or external
execution hidden in a ticket.

The named host is `compiled`; source uses the typed object bridge with model state.
Ordinary exact-read transactions compose an authorized target change with a ticket
review. Failure of either call rolls back both; standalone acceptance is also
legal. Historical retries recover the retained outcome after grant revocation.

[ticket.examples](ticket.examples) is executable domain source beside the object:
wrong requester, wrong claimant, submission, acceptance, terminal refusal and
rejected encounter. [Tests](../../conformance/test_work_ticket.py) also retain the
physical/concurrency boundaries: claim races, current law, stale roots, typed
cards, optional references, composition rollback and lost-response recovery.
They install two independently configured tickets sharing the exact module table.

```sh
python3 conformance/test_work_ticket.py
```

The shared workshop now loads this source object through the same small physical
packaging helper. Inspecting its retained sourcePackages reveals the reusable
modules, not an expanded JSON implementation.
