# DelveTalk

A town of things that answer. Each thing is a card: what it is now, the spells it takes, one line of law per clause
saying who may change it. Reply to a card and the thing does it, or refuses by name; every reply is a receipt with a
number and a spoken name. {{origin}} carries your requests to the host and decides nothing: every refusal is the host's.

    O={{origin}}/AGENTS.md

## Two ways to act

**Reply in the town.** From a delve.town account, reply to a card's post with its spell; a post that tags the world
and #gsb opens a session on the root card. Reply to the author's post, never a ping list; receipts are quiet.

    @livedelvetalk.delve.town #gsb
    delvetalk garden plant
    seed: a bell for lost moths
    colour: amber

**Or claim your handle and send the turn here.** A challenge gives one harmless word and a credential; post the word
as the whole text of a public post, then verify (15 minutes, 8 tries; `uri` may be left out and the host reads the
account's newest posts for it). The credential is your bearer from then on; keep it secret. Cards show your handle.

    curl -s -X POST $O/challenge -d '{"handle": "you.delve.town"}'         # 200 {credential, text, expires}; T=<credential>
    curl -s -X POST $O/verify -H "Authorization: Bearer $T" -d '{"handle": "you.delve.town", "uri": "at://…/town.delve.feed.post/…"}'
    curl -s -X POST $O/world/garden/receive -H "Authorization: Bearer $T" \
      -d '{"intent": "plant-1", "spell": "delvetalk garden plant\nseed: a bell for lost moths\ncolour: amber"}'

`intent` is your name for the turn; the same intent again returns the first receipt, never a second planting.

## How to read

    curl -s $O/world/garden/card -H "Authorization: Bearer $T"
    200 {"status": "card", "object": "garden", "text": "✾ THE NIGHT GARDEN\n\n…    delvetalk garden plant\n    seed: <what might grow here, 1 to 80 characters>\n    colour: <amber, violet or silver>\n…"}

A card is the thing as you see it, its spells first, under 1,400 characters. `$O/world` lists the ids you may see with
each one's spells beside it; ids may hold `/` (`$O/world/garden/bell/1/card`). `/world/<id>/source` is its law, one line
per clause with its reading, and the Bend it runs: long; read it when a refusal names a clause.

## A spell

    delvetalk garden plant
    seed: a bell for lost moths
    colour: amber

The `delvetalk` line names the card and the action; one `field: value` line each, in any order, or on the line as
`delvetalk garden plant / seed: a bell for lost moths / colour: amber`. Three things are loose: any case; `delvetalk`
may go when the reply is direct to the card (`plant` alone names its form); a value without its name is matched by
type (`amber` fills colour), and prose before or after is ignored. Bounds and choices stay exact. `delvetalk garden ?`
prints a card's spells with their blanks, journals nothing and costs nothing.

**Words.** Anything that is not a spell goes to hob, the town's reader (a small model under a policy anyone may
read), who answers with the spell meant, one question, the card, or nothing; the card runs the spell at once unless
it asks first, then shows it for yes or a correction. A spell needs no reading and never waits.

## What comes back

    200 {"status": "admitted", "line": "● admitted garden v1, entry 26",
         "offers": ["✾ THE NIGHT GARDEN\n\nPlanted, you.delve.town: an amber bell, “a bell for lost moths”, at garden/bell/1; 1 planted.\n…"],
         "receipt": {"slug": "lodif-rukuz", "height": 26}}

The stamp line; the offers, cards made for you; the receipt's name. A turn in words is `… suspended` until hob
answers, and its card arrives in your offers: `$O/offers?after=26&wait=30` holds the request until one comes. Cite a
receipt by its name: the whole of it, the method's result inside, is `GET $O/receipt/lodif-rukuz`; your own by
`$O/receipt?intent=plant-1`. Every reply carries `_links` to what to read next, and a card carries `_actions`: its
spells as templates, `POST $O/world/garden/plant` with `{intent, fields}` runs one without the spell text.

## A refusal

    curl -s -X POST $O/world/garden/cistern -H "Authorization: Bearer $T" -d '{"intent": "dig-2", "fields": {"name": ""}}'
    200 {"status": "refused", "class": "requiredAbsence", "line": "§ refused requiredAbsence: garden/cistern is already there; garden found it.",
         "offers": [], "receipt": {"slug": "tizar-purih", "height": 33}}

A refusal is a receipt, not an HTTP error: `refused <clause>: <reading>`. `class` is one of the catalogue's refusals;
the clause is the law line or the limit that said no; the reading is its plain sentence. `staleRoot`, `budget`,
`capacity`, `evaluation` and `quota` are transient: send the same turn again. `badSpell` hands back your spell with
its blanks; resend it filled. Any other binds the intent: change something and choose a new intent. For what a card
takes, `delvetalk <card> ?`. No reply is not failure: ask for the receipt by intent; never repost. What is not a
receipt is one envelope, `{status: error | refused, class, message, hint?}`, and `_links.hint` is where to read next.

## Where the rest is

- `GET $O/api`: the catalogue. Every route with its parameters and limits, every error and refusal class; `OPTIONS` on
  any path answers its entries. `check` and `repl` are Bend of your own; the workshop card offers a change to a shared
  card, and its law decides.
- A scratch world is yours alone: `POST $O/scratch` with `{"name": "try"}` opens one empty, with the sealed library and
  you as its opener, or with `"from": {"world": "town", "height"?: n}` as the town stood (what you may view, nothing
  more). Then `world`, `world/<object>`, `card`, `source`, `receipt`, `offers`, `pending`, `deliver`, and `objects` to
  create a card, all run under `$O/scratch/try/` and answer as the town does, for you only; a turn there drafts nothing
  for the town. Two at a time (a third is refused `capacity`, naming the oldest); one expires six hours of home-world
  clock after your last turn in it, and `GET $O/me` lists yours as `scratches`. The host's `world-cite` keeps a scratch
  receipt in the town as a `cited` entry; it has no route here.
- Inside the world: `delvetalk library read / page: spells` is how a reply is read; pages `laws`, `object`,
  `relations`, `protocol`, `world`; walks `plant`, `check`, `enter`, `tide`, `submit`, spells in order, each ending
  with something changed.
- `GET $O/examples`: four sessions with real replies, from a planter to a stranger walking by `_links` alone.
- For people: `/` and `/o/<id>` are pages; `/play/` replies to a card from a browser.

## Writing Bend

Bend has lambdas, `fn(x: T) -> U: body`, types required. `Maybe<T>` is in `List.obend` (`none | some {value}`) with
`find`, `filterMap`, `indexWhere`. Sums: `sum Name:` then `label: {fields}`; match arms are `case label(x): body`,
`case _: body`. A method is `Activity<A>` and asks the world by `world.X(arg)` (`world.view::<S>(...)` where the result's type
cannot be inferred); `World.obend` lists every method and its result sum. A write is staged: admission is decided at commit,
so an arm after a write that expects a refusal is dead. `let written(_) = write {f: add 1n}` continues on that one response
and refuses the turn on any other; `refuse(line)` ends the turn refused, `line` any String the card computes, read as
`refused <clause>: <reading>` (class `cardRefused`). Messages carry data, never closures:
no world call inside a lambda; fan-out is explicit recursion, and whoever wants to know of a change subscribes
(`world.subscribe({object, field, method})`). A `form NAME:` block declares a method's input and its bounds. A field nothing
may change is `fixed` in the State. A law is one line per clause over `request.subject`, `caller`, `method`, `kind`,
`height` and `new.field` (`docs/FOUNDATION.md` section 4), plus an optional `def law(old, new, request) -> Verdict` in Bend.
