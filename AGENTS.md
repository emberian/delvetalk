# Working on DelveTalk

Read [docs/FOUNDATION.md](docs/FOUNDATION.md) first. It is the design; a change
that contradicts it changes the document in the same commit.

- World behaviour is Objective Bend. Every effect is a Plan an activity
  performs. The host is one Lean process per world. Python carries bytes and
  credentials and decides nothing.
- Files come from `main` by `git checkout main -- path` when a milestone uses
  them, with the reason in the commit message. Nothing comes across because it
  exists.
- Commit named files. Never `git add -A` with other agents in the tree, never
  stash, never reset another lane's work.
- `lake build` builds one executable. Keep local Lean compilation to two
  processes.
- A test names the input that would refute it. Every surface has a
  maximum-length case and an adversarial case.
- Repository authorization does not authorize posting to delve.town, editing
  agentwiki or messaging its participants. Keep credentials, transcripts,
  databases and personal files out of Git.
