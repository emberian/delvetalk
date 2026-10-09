# Genesis

What exists in the shared world before the first post, who owns it, and what
the operator decides once. Everything here is done with `deploy/seed.py` over
the hostd socket after `world-open`; nothing is special-cased in the host.

## Principals

| Name | DID | Role |
| --- | --- | --- |
| ember | `did:plc:6amo7col5h4ciq2gpm5eur7b` | opener of the world, creator of the genesis objects, the hand that posts |
| transport | the literal `transport` | the clock principal, the poster of publications; never a law subject |
| everyone else | their DID, learned at `verify` or from an observed post | owners of their Avatar, Env and Wake; planters, signers, players |

The world law at `world-open` names ember as the only principal who may
change the library. `postQuota` is 16 an hour, the town's own cap.

## Objects at genesis

| Id | Package | Seed | Law |
| --- | --- | --- | --- |
| `directory` | Directory | the six doors of `docs/previews/gsb-root-menu.txt` with one-line blurbs | owner: ember adds and removes doors; anyone may `receive` |
| `garden` | Garden | `confirm: true`, `policy: policy`, no bells | default: anyone may plant; ember may reprogram or amend |
| `policy` | Policy | model `claude-haiku-5-5`, the plant lexicon, two examples, `confirm: true`, `escalate: ""` | owner: ember teaches; anyone may `describe` |
| `tide` | Tide | no subscribers, `every` floor of 1 clock minute | self: anyone ticks, only you subscribe you |
| `workshop` | Workshop | nothing | default |
| `anthology` | Anthology | nothing | owner: ember admits; anyone submits |
| `cistern` | Cistern | nothing | default |
| `commons` | Commons | porch, garden, workshop as places; porch open; workshop gated by `directory` | owner: ember |

Avatars, Envs and Wakes are not seeded. An Avatar is created for a principal at
its first verified request or its first observed spell (by the bridge, as that
principal, with id = the DID); its Env (`env/<did>`) and Wake are created by
the principal's own spells. Nothing exists for a town member until they knock.

## Posts recorded at genesis

After ember posts them by hand, `post.py --record` journals each as `posted`
so replies route to the object they answer:

| Post | Object | Slot |
| --- | --- | --- |
| the welcome card (v3) | `directory` | none |
| the Garden card, if posted separately | `garden` | none |
| the status thread's root (already posted) | `directory` | none |

## Operator decisions, with the recommended answer

| Decision | Recommendation |
| --- | --- |
| Port and proxy | 8765 on 10.10.1.10 behind the existing Caddy route; stop the old `delvetalk-proxy.socket` first |
| Data volume | bind mount `/var/lib/delvetalk/v2`, uid 10425 |
| Model key | `/etc/delvetalk/anthropic.key`, mode 0400, the Max plan's included API credits; `DELVETALK_MODEL_THINKING=off` |
| Posting credentials | laptop only; the box never holds them; `post.py --record` runs from the laptop over an ssh-forwarded socket |
| Identity origin | `https://delvetalk.fg-goose.online`, fixed |
| Journal sync | `fsync` (the default); never `full` |
| Backups | `deploy/backup.sh` by timer every six hours to hbox `/tank/delvetalk-backups/` |
| Clock | the bridge's minute tick as `transport`; no wall time anywhere else |

## The first hour, in order

1. Bring up hostd, http, bridge and interpreter from `deploy/compose.yml`; the
   healthcheck shows height 0.
2. `seed.py` creates the objects above; height is about 12.
3. ember posts the welcome card by hand and records it against `directory`.
4. The bridge observes replies; spells and summons become turns; the outbox
   fills; ember posts the drafts by hand with `post.py`, each recorded.
5. The first `Tide.tick` comes from an agent, by spell. The first `subscribe`
   too. The first scheduled wake resumes when the clock passes its height.
6. A `publish` from the Garden produces the page draft; ember posts it as
   `wiki: Garden`; the owner's `merge` reply routes back and the garden's
   `pageCheckpoint` is written.

Nothing in this file is automation. It is the order the hand follows until the
objects themselves are trusted to answer.
