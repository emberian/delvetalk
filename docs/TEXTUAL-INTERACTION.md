# Speaking and writing in DelveTalk

**Reply to an offered card, or speak normally and have your meaning interpreted.**
The text below is post content, not shell commands or a global command language.
Example card names illustrate the grammar; use the actual name and offered words
on the published card you are answering. No v1 has launched; hosted worlds are
[disposable previews](../TRACKING.md).

## A reply addresses an invitation

A garden card offering `plant` with `seed` and `colour` fields accepts:

```text
delvetalk garden-1 plant
seed: fern
colour: silver
```

`garden-1` identifies a captured invitation, not an object to look up anywhere.
`plant` is that card's unique actual command. When a command cannot be a unique
word, the card supplies an action selector such as `a1`; use what it offers.
Labels such as “Plant something” are presentation, not alternate command names.
Fields with unsuitable names receive offered aliases such as `f1`.

Reply to the **exact published post carrying the card**. The receiver verifies its
URI/CID, the reply's parent and authenticated repository author, and the retained
card. Pasting a card elsewhere does not establish another invitation. The author
becomes the caller; a name typed into a field cannot impersonate someone else.
The card carries an exact reading of the object and its offered actions. Neither
knowing a card name nor copying source grants a capability or changes current law.

## Literal fields

Supply every offered field exactly once, with no extra fields. After `field:` one
separator space is removed; the remaining text, spaces and Unicode are literal.
Quotes and backslash escapes have no special meaning. `field:` is an empty string.
The captured field schema decides the type:

| Offered type | Literal spelling |
| --- | --- |
| String | Unquoted text, preserving spaces |
| Natural | ASCII `0` or decimal digits without a leading zero; within the offered bounds |
| Boolean | Exactly `true` or `false` |
| Enum | One of the offered string values, without JSON quotes |

Multiline strings use an exact closing delimiter:

```text
delvetalk garden-1 plant
seed: <<SEED
A fern whose leaves remember
last night's rain.
SEED
colour: silver
```

The value contains the newline between those two content lines, but none after
“rain.” The newline after the opening marker and before the closing marker frames
the block; to retain a final newline, insert a blank content line before `SEED`.
Choose a delimiter absent as an entire content line. It starts with an ASCII letter
and contains at most 32 letters, digits, underscores or hyphens. A string starting
with `<<` also needs a block. Blank framing lines outside the reply are ignored;
extra commentary belongs in the interpretation route, not inside a literal spell.

Legacy `delvetalk garden-1 a1 {"seed":"fern","colour":"silver"}` remains accepted
when `a1` is the corresponding offered action. JSON is optional.

## Ordinary language and outcomes

“Could we plant a silver fern whose leaves remember last night's rain?” is a
reasonable reply. An operator retains the original post and separately attests an
explicit interpretation: selected action, exact inputs and reading, and its basis.
Missing material choices require clarification. This is
[manual interpretation](../profiles/MANUAL-INTAKE.md), not an autonomous natural
language authority. Lean still checks the authenticated author's current permissions
and the exact reading. The attestation does not make an interpretation infallible.

If the world changed and the action was refused, ask for a fresh card before a new
action. **If no result arrived, link the original reply and ask for recovery. Do not
edit or repost it.** Its retained attempt may already have committed. A new post is
a new attempt. Current grants, program guards and law decide admission even when a
card offers a choice; an offer is not a promise that every caller can execute it.

## Source is another offered field

Inspect a writing card's installed definition, then use its **Revise** form:
`module` selects one captured module; `source` replaces its text; `scenarios`
supplies its examples. The card carries the remaining dependencies and captured
state into the proposal. Its Candidate offers **Check source and examples**, then
**Release** after a successful report. These forms are Bend source and can
themselves be revised under current law.

For a new definition, use the offered **Submit source and examples** form.
[Typed objects](../profiles/TYPED-SOURCE-OBJECTS.md) and
[sealed modules](../profiles/MODULE-AUTHORING.md) describe the source interface.

Compilation and examples produce a retained report. They grant no installation
right. Adoption binds the reviewed candidate, target, complete migration and exact
reading, then releases and replaces the target under current law. Recover an
uncertain submission or adoption using its original attempt before preparing a
replacement. See [authoring](../profiles/AUTHORING.md) and
[source desks](../profiles/DESK.md).

## Scenes and new dialects

Spween writes encounters: prose, passages, choices, guards and ordered effects.
For example, this exact excerpt from [door.scene](../scene/examples/door.scene)
spends a token and changes passage; it is source inside a proposal, not a town reply:

```text
* [Take the tour] { tokens >= 1 }
  ~ tokens -= 1
  ~ visits += 1
  ~ announce "tour accepted"
  -> gallery
```

Scene execution uses authored Bend handlers and the source runtime. Follow
[the handler workshop](../protocols/spween-handler-workshop/README.md) for its
actual package interface and [Spween](../scene/README.md) for scene behavior.
An adapter must preserve exact source and explicit meaning; translation does not
install a program or grant authority. Current source and consumer changes require
qualification against the matching native host before deployment.

[Exact card/parser contract](../profiles/TOWN.md) ·
[Typed source objects](../profiles/TYPED-SOURCE-OBJECTS.md) ·
[Spween profile](../scene/README.md)
