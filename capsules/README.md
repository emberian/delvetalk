# Capsules

One-screen references for a model with little context, each about 2,500 characters and checked against the code. They are reading material; the library's pages under [pages/](pages/) are runtime inputs, shelved by genesis (`deploy/genesis.py` `PAGES`) and read in the world with `delvetalk library read / page: <name>`. The world at a glance is the page [pages/world.txt](pages/world.txt), the same text a resident reads.

- [spells.txt](spells.txt): the spell grammar as the host reads it: the cast rule, fields, misfits, `badSpell`, prose.
- [object.txt](object.txt): how to write an object (message dialect), with one complete example.
- [protocol.txt](protocol.txt): the world's methods, their results, `changed`, receipts.
- [laws.txt](laws.txt): the law fragment (counts, `changed … by`, membership, `under`), readings, the metarule, the Bend predicate, classes.
- [relations.txt](relations.txt): `Relation<T>`, keys, edits and which commute, order, queries.

For current behavior, read [docs/INDEX.md](../docs/INDEX.md) and the source.
