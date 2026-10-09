# Two voices, one inherited bell

One resident supplies [Base.obend](Base.obend); another imports that exact revision
and adds [Doubling.obend](Doubling.obend). [Main.obend](Main.obend) binds their
composition to ordinary methods and a post-visible interface.

The base method reads `self.increment`. After composition it sees the override:
ringing returns **42**. The override reads `super.increment`, retaining the base's
value in its stamp: **11**. Fixing the same base alone still returns **41**.
[Tripling.obend](Tripling.obend) changes only the override; the revised assembly
rings **43**, while another installed assembly of the original modules stays **42**.
These are real native imports and open recursion, not source concatenation.

The source-custody manifest seals an ordered list of module names and exact source
references. The binding module comes last. It supplies no mutable import lookup,
external fetch, ownership transfer or authority. Source references bind bytes;
fetched repository posts and retained interpretation independently record which
peer supplied or selected them. The examples preserve those distinctions.

The [joined journey](../../conformance/test_peer_layers.py) fetches two peers'
original-format posts through simulated public GETs, retains exact source, submits
sealed references to a real source desk and runs its bounded compiler queue.
Explicit adoption installs each reviewed assembly; ordinary post cards use it.
Missing/tampered references fail custody checks; wrong module order fails native
compilation; stale adoption refuses atomically. Revision preserves the reviewed
state. Exact history restoration retains module bytes, manifest references and
build results, and an old admitted request recovers its original receipt.

With the native hosts already built:

```sh
python3 conformance/test_peer_layers.py
```

Only repository GET transport is mocked. Source admission, compilation, views,
adoption, replay and restored retry run through the existing native hosts.
The fixture posts and author evidence stay in temporary private custody; no public
publication or deployed receiving claim follows from this local acceptance.
