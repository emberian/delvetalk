# Codex review of 5db9aa79 (gpt-6.1-sol, six facets, read-only): routing

Review of foundation at `5db9aa79` (the overhauled tree), run 2026-10-12 the way the 2026-10-10 review was: `codex exec -m gpt-6.1-sol -s read-only`, one run per facet, each writing its ranked list to `<facet>.md` here. Rank is the reviewer's order within its facet; P is its stated priority (objects gave none: P1 is assigned here to ranks 1-4, the authority holes). The same defect reached by several facets is listed once per facet: carry forgetting request identities (host 8, docs 1, agent 1), the paint verifier accepting uncredited quotations (host 15, docs 4, agent 14), scratch routes lacking the principal (transport 12, agent 13), hob dropping wants and help pages (docs 6, agent 11), stale worked examples (docs 8, agent 15). Transport 4 (healthcheck) was reported against 5db9aa79; foundation's later merge of lane/deploy10 (d7878aaa, which this branch is cut from) says the healthcheck now reads the new home page, so verify it is already closed before dispatch. The facet's own lane label is used, normalized to the five lanes.

| Facet | Rank | P | file:line | Summary | Lane |
| --- | --- | --- | --- | --- | --- |
| kernel | 1 | P1 | `spec/Delvetalk/Canonical.lean:75` | Canonical Data collisions let grant holders change fixed arguments. | kernel |
| kernel | 2 | P1 | `spec/Delvetalk/Package.lean:102` | Re-exporting a Bend law silently disables its enforcement. | kernel |
| kernel | 3 | P1 | `spec/Delvetalk/Package.lean:265` | A sufficiently long State alias chain removes fixed-field protection. | kernel |
| kernel | 4 | P2 | `spec/Delvetalk/Turn.lean:600` | Saving a continuation materializes unread relations before enforcing checkpoint capacity. | kernel |
| kernel | 5 | P2 | `spec/bend/Compiler/ObjectiveBendElaborate.lean:2946` | A layer elsewhere in the closure supplies metadata for an unrelated entry module. | kernel |
| kernel | 6 | P2 | `spec/Delvetalk/Turn.lean:365` | Diagnosing node exhaustion performs a second, uncharged execution with a trillion-node allowance. | kernel |
| kernel | 7 | P2 | `spec/Delvetalk/Turn.lean:569` | Activity argument conformance performs quadratic work outside the turn tariff. | kernel |
| kernel | 8 | P2 | `spec/bend/Compiler/ObjectiveBendFrontEnd.lean:502` | Top-level laws, rules and wants make a package impossible to extend by layering. | kernel |
| kernel | 9 | P2 | `spec/Delvetalk/Generics.lean:1422` | A handwritten `forms()` can silently erase a form block’s bounds. | kernel |
| host | 1 | P1 | `spec/Delvetalk/Host/Ops.lean:3209` | Placed rules can exfiltrate fields from objects their owner cannot read. | host |
| host | 2 | P1 | `spec/Delvetalk/Host/Law.lean:404` | Raw spell-hole substitution lets writable text redirect a rule owner’s authority. | host |
| host | 3 | P1 | `spec/Delvetalk/Host/TurnLoop.lean:2832` | Direct turns using a grant bypass its fixed arguments and use limit. | host |
| host | 4 | P1 | `spec/Delvetalk/Host/Ops.lean:1828` | Replaying an in-turn creation loses its package’s rules and wants. | host |
| host | 5 | P1 | `spec/Delvetalk/Host/Snapshot.lean:338` | Snapshot validation accepts forged rule ownership and read authority. | host |
| host | 6 | P1 | `spec/Delvetalk/Host/TurnLoop.lean:3267` | Quieting a principal does not prevent writes through the proposal and reprogramming ops. | host |
| host | 7 | P1 | `spec/Delvetalk/Host/Ops.lean:2626` | A locally placed rule can collide with an inherited rule’s delivery identity and suppress it. | host |
| host | 8 | P1 | `spec/Delvetalk/Host/Snapshot.lean:392` | Carry releases previously bound request identities, allowing duplicate effects. | host |
| host | 9 | P1 | `spec/Delvetalk/Host/Carry.lean:299` | Carry can admit suspended writes based on cells changed by a migration. | host |
| host | 10 | P1 | `spec/Delvetalk/Host/Ops.lean:1989` | Nested want dependencies can make a law admit a write it should refuse. | host |
| host | 11 | P1 | `spec/Delvetalk/Host/Ops.lean:2532` | Cross-object constraints judge an atomic commit against other objects’ pre-write states. | host |
| host | 12 | P2 | `spec/Delvetalk/Host/TurnLoop.lean:1859` | `world.judge` reads law dependencies without retaining their roots. | host |
| host | 13 | P2 | `spec/Delvetalk/Host/Law.lean:252` | Relational law and rule evaluation performs quadratic work outside the tick budget. | host |
| host | 14 | P2 | `spec/Delvetalk/Host/Enchant.lean:254` | Historical strokes mix old state with current wants, verbs and rule firings. | host |
| host | 15 | P2 | `spec/Delvetalk/Host/Enchant.lean:465` | The paint verifier accepts truncated resident quotations credited to the wrong writer. | host |
| objects | 1 | P1 | `world/objects/Kind.obend:107` | Kinds without law clauses produce instances that anyone can amend or reprogram. | objects |
| objects | 2 | P1 | `world/bodies/lantern.obend:50` | Reactive receivers mistake a guest’s rule for their intended trigger. | objects |
| objects | 3 | P1 | `world/objects/Avatar.obend:127` | A guest-owned object can add itself to another principal’s holding list. | objects |
| objects | 4 | P1 | `world/objects/Avatar.obend:37` | The Avatar’s principal-only placement restriction never executes. | host |
| objects | 5 | P2 | `world/bodies/bond.obend:31` | A bond silently excludes every party after the fifteenth. | objects |
| objects | 6 | P2 | `world/bodies/errand.obend:58` | An errand can become permanently done without paying its reward. | objects |
| objects | 7 | P2 | `world/bodies/weather.obend:65` | Weather aborts its entire rain when a garden holds 32 eligible bells. | objects |
| objects | 8 | P2 | `world/bodies/front.obend:55` | A front’s clock stops advancing after its retained fill history reaches capacity. | objects |
| objects | 9 | P2 | `world/objects/Record.obend:132` | Retention can suppress a record’s pending-line want while a line remains pending. | objects |
| objects | 10 | P2 | `world/bodies/errand.obend:60` | Reactive objects present themselves as operational when rule installation failed. | objects |
| objects | 11 | P2 | `world/lib/Text.obend:47` | Generated rule names collapse distinct object identities. | objects |
| objects | 12 | P2 | `world/objects/Thing.obend:213` | Copying an extended Thing discards its program. | objects |
| objects | 13 | P2 | `world/objects/Thing.obend:277` | Several renderers exceed the card budget with valid inputs. | objects |
| objects | 14 | P2 | `deploy/genesis.py:123` | The seventh-rain rule counts grown gestures as rains. | objects |
| transport | 1 | P1 | `deploy/backup.sh:35` | Live backups can preserve transport completion markers for turns missing from the backed-up journal. | transport |
| transport | 2 | P1 | `transport/post.py:113` | Concurrent posting of one intent can create two external posts under one reservation. | transport |
| transport | 3 | P1 | `transport/bridge.py:125` | Addressed private offers are copied into public drafts without a host-approved public projection. | transport |
| transport | 4 | P1 | `transport/watch.py:66` | The HTTP healthcheck always rejects the current home-page markup. | transport |
| transport | 5 | P1 | `transport/oauth.py:205` | OAuth credentials remain authoritative after their recorded thirty-day expiry. | transport |
| transport | 6 | P1 | `transport/http.py:577` | The session cookie lacks `Secure`, allowing plaintext disclosure on HTTP requests. | transport |
| transport | 7 | P1 | `transport/identity.py:113` | Unauthenticated verification requests can exhaust another person’s challenge attempts. | transport |
| transport | 8 | P1 | `transport/bridge.py:383` | Multi-spell posts lose usage answers and suspended turns’ eventual replies. | transport |
| transport | 9 | P1 | `deploy/library-update.sh:32` | The library-update command fails after deleting the live library directory because it requires deleted packages. | transport |
| transport | 10 | P1 | `transport/carry.py:67` | Carry overwrites the destination configuration after using it to choose the new host and library. | transport |
| transport | 11 | P2 | `transport/interpret.py:77` | Scratch-world interpretations have no model worker servicing them. | transport |
| transport | 12 | P2 | `transport/http.py:745` | Scratch pending and delivery HTTP routes omit the principal required to select the world. | transport |
| transport | 13 | P2 | `transport/bridge.py:32` | Slot serialization corrupts identities whose intent contains a colon. | transport |
| transport | 14 | P2 | `transport/http.py:170` | Default HTTP and browser act replies discard the host’s revealing lines. | transport |
| transport | 15 | P2 | `transport/repo.py:262` | Repository object and law listings ignore the requested limit and advance the cursor past excess records. | transport |
| docs | 1 | P1 | `docs/FOUNDATION.md:147` | Carry breaks the documented guarantee that retrying an admitted intent cannot repeat its effects. | host |
| docs | 2 | P1 | `capsules/pages/object.txt:23` | The advertised complete coin-jar example is refused by the current compiler. | objects |
| docs | 3 | P2 | `capsules/pages/spells.txt:8` | The documented bare-field completion loses previously supplied fields. | docs |
| docs | 4 | P2 | `docs/OVERHAUL.md:85` | The painter’s contract promises whole, attributed quotations, but the verifier accepts uncredited fragments. | host |
| docs | 5 | P2 | `docs/ROOT.md:32` | ROOT falsely says that setting an unknown pin disables an object’s turns. | docs |
| docs | 6 | P2 | `docs/FOUNDATION.md:486` | Hob is promised the card’s wants and library pages, but Policy discards both before constructing its prompt. | objects |
| docs | 7 | P2 | `docs/DEPLOY.md:759` | Carry can discard suspended work without the explicit leave decision DEPLOY promises. | host |
| docs | 8 | P2 | `docs/AGENTS-EXAMPLES.md:34` | The live examples teach objects and methods that a fresh current town does not have. | docs |
| docs | 9 | P2 | `site/play.html:48` | The play guide’s recovery URL cannot retrieve a receipt by post address. | docs |
| docs | 10 | P2 | `docs/GENESIS.md:107` | The clapper want advertises an exact spell that does not grow its missing verb. | objects |
| docs | 11 | P2 | `docs/GENESIS.md:92` | The welcome’s `me ?` command does not show possessions or notes as promised. | docs |
| docs | 12 | P2 | `docs/FOUNDATION.md:109` | Scratch expiry is renewed by a host restart, contrary to the six-hours-after-last-use contract. | host |
| docs | 13 | P2 | `docs/FEDERATION.md:164` | FEDERATION promises restart-surviving REPL checkpoints that the HTTP implementation explicitly rejects. | docs |
| docs | 14 | P2 | `docs/AGENTS-API.md:55` | The agent guide’s universal 1,400-character card limit is not enforced for programmable cards. | host |
| docs | 15 | P2 | `docs/DEPLOY.md:230` | DEPLOY’s first-start inventory still promises furnished places and seven page drafts that minimal genesis no longer creates. | docs |
| agent | 1 | P1 | `spec/Delvetalk/Host/Snapshot.lean:392` | Carry forgets turn identities, so retrying a committed act performs it again. | host |
| agent | 2 | P1 | `spec/Delvetalk/Host/Spell.lean:357` | Spell splitting casts commands inside fenced examples and literal text blocks. | host |
| agent | 3 | P1 | `spec/Delvetalk/Host/Spell.lean:563` | A misspelled optional field silently discards a kind’s intended law. | host |
| agent | 4 | P1 | `world/objects/Record.obend:257` | Successfully grown verbs cannot be cast by their advertised spells on standard records and things. | host |
| agent | 5 | P1 | `spec/Delvetalk/Host/TurnLoop.lean:3009` | Several acts in one hob reading cannot see each other’s writes. | host |
| agent | 6 | P1 | `world/bodies/bell.obend:75` | Successful town spells with no offer disappear without a receipt reply. | transport |
| agent | 7 | P2 | `spec/Delvetalk/Host/Ops.lean:5016` | HTTP reports carried receipt slugs as nonexistent even when the host resolves them. | transport |
| agent | 8 | P2 | `transport/http.py:163` | Default HTTP refusals discard the spell template needed to recover from a bad form. | transport |
| agent | 9 | P2 | `spec/Delvetalk/Host/TurnLoop.lean:2310` | Default HTTP and play replies conceal fired rules and changed wants. | transport |
| agent | 10 | P2 | `spec/Delvetalk/Host/TurnLoop.lean:2957` | Hob cannot propose the host’s rule, want, or law-adoption spells. | host |
| agent | 11 | P2 | `spec/Delvetalk/Host/TurnLoop.lean:3962` | Hob’s prompt drops the wants and help pages the host assembled for it. | objects |
| agent | 12 | P2 | `world/bodies/commonplace.obend:83` | The commonplace’s “What wants a hand” path always falls back without listing wants. | host |
| agent | 13 | P2 | `transport/http.py:744` | The advertised scratch pending and delivery routes omit the principal needed to select the scratch world. | transport |
| agent | 14 | P2 | `world/lib/Paint.obend:8` | The paint verifier accepts truncated, uncredited resident quotations that reverse their meaning. | host |
| agent | 15 | P2 | `transport/http.py:630` | The served worked sessions teach deleted objects and actions as current onboarding. | docs |
