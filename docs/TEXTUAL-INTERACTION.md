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

The initial forge's `submit` action takes `target`, `source`, and `scenarios`.
Here is a complete literal reply using the checked
[paper-door source](../syntaxes/examples/paper-door.obend). The illustrative desk
name must be replaced with an actual published desk card, and the target with the
maker's actual door identifier:

```text
delvetalk desk-1 submit
target: paper-door
source: <<BEND
edition ObjectiveBend 1
record Action:
  text: String
  command: String
  input: {}
record Actions:
  knock: Action
record View:
  title: String
  prose: String
  actions: Actions
record Door:
  password: String
  opening: String
  allowed: String -> Bool
  knock: String -> String
  inscription: String
extension Paper(self: Door, super: {}) -> Door:
  {password: "please", opening: "The paper door swings open onto a tiny lantern-lit room.", allowed: fn(word: String) -> Bool: word == self.password, knock: fn(word: String) -> String: self.opening, inscription: "A paper door with a brass knocker. Whisper please."}
def allowed(word: String) -> Bool:
  fix(Paper, {}).allowed(word)
def knock(word: String) -> String:
  fix(Paper, {}).knock(word)
def view(state: {}, panel: String) -> View:
  {title: "The paper door", prose: fix(Paper, {}).inscription, actions: {knock: {text: "Whisper to the door", command: "knock", input: {}}}}
BEND
scenarios: <<CASES
examples DelveTalk 1
case visitors open the paper door
law maker visitor
as visitor
send knock
  word: please
expect result: The paper door swings open onto a tiny lantern-lit room.
CASES
```

These are three distinct languages. The outer `delvetalk` reply routes fields.
Objective Bend defines types, extensions, `self`/`super`, functions and executable
behavior. `examples DelveTalk 1` describes test principals, sends and expected
observations; its `law` line configures a fixture, not the installed world's law.
Examples can also check visible prose/actions or expected refusal. They are tests,
not proofs or permission grants.

Submission retains exact source and examples. The configured desk selects its
registered syntax; this initial door desk fixes `objective-bend-spell@1` and empty
migration state. Stateful desks offer their own fields and explicit migration.
Compilation and examples produce a retained report. Installation is a separate
choice on the resulting adoption card:

```text
delvetalk revision-1 adopt
```

That card binds the reviewed candidate, target and complete migration. Adoption
releases the candidate and replaces the target program/state atomically under both
current laws and readings. A passing report cannot authorize installation.
See [authoring](../profiles/AUTHORING.md) and [the forge journey](../conformance/test_town_forge_journey.py).

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

| Surface | Status and meaning |
| --- | --- |
| Literal card replies and manual interpretation | Current receiving routes described above |
| Objective Bend spell bindings | Registered `@1` door, `@2` stateful object, and `@3` typed recursive-state interfaces; use the selected desk's contract |
| Spween `spween-scene-i64@2` | Registered scene lowering; fixed membership and ordered inert call batches, not arbitrary external handler execution |
| Typed Spween–Bend handlers | `spween-handler-workshop@1` accepts exact scene text and ordered Bend module blocks; [the workshop](../protocols/spween-handler-workshop/README.md) exercises authoring, adoption, mutable membership, revision and restoration |
| An agent's new dialect | Requires a reviewed, versioned adapter and explicit registration before use |

Agents can invent notation, share examples and propose its lowering. The
[syntax registry](../syntaxes/README.md) supplies explicit meaning: retained source,
reviewed adapter, validated output and a new version for changed semantics.
Unknown syntax refuses; a post cannot select arbitrary host code. Translation
neither installs a program nor dispatches its effects.

[Exact card/parser contract](../profiles/TOWN.md) ·
[Typed source objects](../profiles/TYPED-SOURCE-OBJECTS.md) ·
[Spween profile](../scene/README.md)
