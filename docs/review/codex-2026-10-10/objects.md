Read-only review of `foundation` at `a3e1fb2`; no edits, builds or tests. Generic-edit examples below use the host’s [`world-propose` admission path](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Session.lean:281).

1. **Owner clauses allow a stranger to take ownership through a reprogram migration.**  
   Evidence: [Garden:56](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:56), [Directory:43](/Users/ember/dev/delvetalk2/world/objects/Directory.obend:43), [Policy:26](/Users/ember/dev/delvetalk2/world/objects/Policy.obend:26), [host judgment:1941](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1941).  
   A stranger’s Workshop proposal can supply a compatible migration that sets `owner` to that stranger, making `request.subject == new.owner` true. The current law judges the migrated state, so writing the authority field supplies the authority needed to reprogram.  
   Smallest fix: add an unconditional `unchanged(owner)` clause to these owner laws. **Lane: objects.**

2. **Any stranger can reprogram or amend a Deal or Tide.**  
   Evidence: [Deal:38](/Users/ember/dev/delvetalk2/world/objects/Deal.obend:38), [Tide:27](/Users/ember/dev/delvetalk2/world/objects/Tide.obend:27), [predicate dispatch:1946](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:1946).  
   A non-party can amend a Deal to a law authorizing themselves because `members` constrains only kind-0 writes and the remaining clauses admit unchanged state. Tide likewise admits state-preserving reprogramming and amendment because its text has no authority clause and its predicate runs only for kind-0 changes.  
   Smallest fix: guard Deal’s non-write changes by party membership; give Tide a fixed owner and guard its non-write changes. **Lane: objects.**

3. **A stranger can replace a held Workshop proposal before its owner adopts it.**  
   Evidence: [Workshop State:22](/Users/ember/dev/delvetalk2/world/objects/Workshop.obend:22), [adoption:124](/Users/ember/dev/delvetalk2/world/objects/Workshop.obend:124), [default law:2273](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/Ops.lean:2273).  
   A `world-propose` upsert can replace an existing held row’s `package`, `migration` and proposer metadata because Workshop declares no state-write law. The target’s owner subsequently adopting that number executes the replacement source under their own authority.  
   Smallest fix: add a Bend predicate refusing unnamed generic writes, preserving the existing guarded methods and default reprogram authority. **Lane: objects.**

4. **Avatar’s owner checks do not protect its state against generic proposals.**  
   Evidence: [Avatar State:33](/Users/ember/dev/delvetalk2/world/objects/Avatar.obend:33), [send guard:99](/Users/ember/dev/delvetalk2/world/objects/Avatar.obend:99), [mail delivery:145](/Users/ember/dev/delvetalk2/world/objects/Avatar.obend:145).  
   A stranger can insert a forged letter into another Avatar’s `outbox` through `world-propose`, bypassing `mine(context)`. Its followers then receive that letter as mail from the victim Avatar, including the attacker-supplied handle and text.  
   Smallest fix: add a predicate rejecting unnamed generic writes to Avatar state. **Lane: objects.**

5. **A stranger can overwrite a Table’s outcome or a Seat’s commitment.**  
   Evidence: [Table:25](/Users/ember/dev/delvetalk2/world/objects/Table.obend:25), [mutable Seat fields:13](/Users/ember/dev/delvetalk2/world/lib/game/Seats.obend:13), [Seat commit guard:28](/Users/ember/dev/delvetalk2/world/objects/Seat.obend:28).  
   A generic proposal setting `Table.game.winner` to South is admitted while preserving the round and fixed fields, after which `resolve` reports the match finished. Seat similarly admits replacement of its mutable digest, opening and move fields without the player’s commit/reveal checks.  
   Smallest fix: reject unnamed generic writes in both objects’ predicates. **Lane: objects.**

6. **Thing’s custody law admits unauthorized release and pickup.**  
   Evidence: [Thing owner law:29](/Users/ember/dev/delvetalk2/world/objects/Thing.obend:29), [custody predicate:35](/Users/ember/dev/delvetalk2/world/objects/Thing.obend:35).  
   A stranger can propose `holder = nobody` for someone else’s held Thing, then propose themselves as holder on the next turn. Both changes pass the predicate’s unconditional empty-holder exceptions and bypass the offer, Place and Avatar custody protocol.  
   Smallest fix: reject unnamed generic writes that change custody fields. **Lane: objects.**

7. **A Deal party can forge another party’s countersignature.**  
   Evidence: [Deal laws:38](/Users/ember/dev/delvetalk2/world/objects/Deal.obend:38), [signature construction:83](/Users/ember/dev/delvetalk2/world/objects/Deal.obend:83), [last-signature amendment:86](/Users/ember/dev/delvetalk2/world/objects/Deal.obend:86).  
   Alice, listed as a party, can generically insert a signature whose principal is Bob because membership checks Alice while `insertOnly` checks only preservation of existing rows. Alice’s subsequent genuine countersignature can then apply the amendment without Bob ever signing.  
   Smallest fix: add a predicate requiring newly inserted signatures to belong to the requester and originate from `countersign`. **Lane: objects.**

8. **Scene’s law permits entering forbidden passages without satisfying requirements or choices.**  
   Evidence: [Scene laws and predicate:54](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:54), [entry requirements:92](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:92), [choice guards:115](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:115).  
   With cooldown zero, a generic proposal inserting the requester into `presence` at a secret passage is admitted even when the scene’s requirements fail. The law checks fixed configuration and cooldown, leaving passage selection, choice guards and variable effects protected only inside methods.  
   Smallest fix: reject unnamed generic writes through the Scene predicate. **Lane: objects.**

9. **Unrelated departures can erase an active Scene cooldown.**  
   Evidence: [Scene retention:53](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:53), [cooldown lookup:62](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:62), [departure recording:174](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:174).  
   After Alice leaves a scene with a long cooldown, 64 newer departures can evict Alice’s row from the bounded `left` relation. Her next `enter` is then admitted early because a missing departure means `cooling` returns false.  
   Smallest fix: retain unexpired cooldown records and refuse capacity growth that would evict one. **Lane: objects.**

10. **Thirty-three due Tide subscribers make the whole tick fail.**  
    Evidence: [Tide capacity:56](/Users/ember/dev/delvetalk2/world/objects/Tide.obend:56), [fan-out:102](/Users/ember/dev/delvetalk2/world/objects/Tide.obend:102), [host send limit:1500](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:1500).  
    Thirty-three subscriptions with `every = 1` are accepted, but the next sufficiently budgeted tick aborts on its thirty-third send. The tick and all its staged notes are discarded, so successful subscriptions can collectively disable delivery.  
    Smallest fix: reduce `subsMax` to 32, or continue fan-out across separate turns. **Lane: objects.**

11. **Garden’s completion path can plant seeds exceeding its declared 80-character limit.**  
    Evidence: [plant form:87](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:87), [field detection:213](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:213), [completion:225](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:225), [host bare routing:948](/Users/ember/dev/delvetalk2/spec/Delvetalk/Host/TurnLoop.lean:948).  
    A reply beginning with an unrelated field, followed by `colour: silver` and an 81-character `seed`, reaches `receive` because its first field names no form. Garden then detects the planting fields and grows the seed without checking its length.  
    Smallest fix: validate completed seed length in `fromFields` before holding or planting it. **Lane: objects.**

12. **Completed and confirmed plantings lose the post that their Bell should await.**  
    Evidence: [Garden named planting:230](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:230), [confirmation:240](/Users/ember/dev/delvetalk2/world/objects/Garden.obend:240), [Bell strike:50](/Users/ember/dev/delvetalk2/world/objects/Bell.obend:50).  
    Completing a held planting with `colour: silver`, or answering a confirmation with `yes`, reaches `named`, which passes an empty planting post to `settled`. The resulting Bell’s `strike` immediately returns its current state instead of awaiting a reply to the planting post.  
    Smallest fix: pass the completing or confirming turn’s `context.inputOrigin.post` into `settled`. **Lane: objects.**

13. **Anthology retention changes what an existing line number identifies.**  
    Evidence: [Anthology retention:28](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:28), [admit by index:43](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:43), [numbering:59](/Users/ember/dev/delvetalk2/world/objects/Anthology.obend:59).  
    After 1,024 short submissions, another submission drops the first row and renumbers every survivor from one. An owner copying `admit / number: 1` from the preceding card consequently admits the former second line.  
    Smallest fix: assign a durable submission number and look up admission by that number. **Lane: objects.**

14. **Composite cards can exceed the character budget by thousands of characters.**  
    Evidence: [Bell rendering:105](/Users/ember/dev/delvetalk2/world/objects/Bell.obend:105), [unclipped door lines:147](/Users/ember/dev/delvetalk2/world/lib/Card.obend:147), [Scene rendering:216](/Users/ember/dev/delvetalk2/world/objects/Scene.obend:216).  
    A Bell accepts eight maximum-length doors and appends all their lines after a separately clipped rain section, producing a card well beyond 1,400 characters. Scene similarly allocates independent budgets to choices and variables before adding its passage header, so section clipping does not bound the combined card.  
    Smallest fix: allocate one remaining-character budget across each entire renderer. **Lane: objects.**

15. **`Card.clipped` can exceed its own 1,200-character allowance.**  
    Evidence: [Card clipping:117](/Users/ember/dev/delvetalk2/world/lib/Card.obend:117).  
    Given two 600-character documents and a third document, the helper keeps the first 1,200 characters and then appends `… and 1 more\n`. The overflow footer is emitted without charging or reserving its characters.  
    Smallest fix: reserve footer space whenever undisplayed rows remain. **Lane: objects.**