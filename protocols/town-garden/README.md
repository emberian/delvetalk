# The Night Garden

Plant something that could only grow here. Another gardener gives it one line of
rain. Both voices remain together, even when someone plants beside them or takes
a cutting into different light.

The garden retains up to 32 numbered plantings. Several may wait for rain at once.
Browse eight plantings per **Garden history** page. Revisit a number to see its seed, light and authors.
A completed bloom can supply a cutting: the new planter receives a new number,
the original bloom remains unchanged, and **Original bloom** preserves its
attribution. Someone other than the cutting's planter must supply its rain.
There is no timer, external weather service or automatic publication.

## Source and interaction

Supply the ordered modules `Abi`, `Encounter` from `world/lib/prelude`, followed
by [Blooms](Blooms.obend) and [Garden](Garden.obend), to the ordinary typed source
adapter (`objective-bend-object`). Imports select those exact bytes. Source
`describe()` owns initial state, forms, examples and panels; `view()` owns the
available actions and the link to a cutting's original bloom. No separate binding,
generated executable protocol or legacy migration is required.

| Contribution | Meaning |
| --- | --- |
| `plant {seed,colour}` | Add a named seed under amber, violet or silver light. Existing plantings stay. |
| `rain {id,line}` | Complete that numbered planting, once, as someone other than its planter. The offered action already selects its number. |
| `page {index}` | Turn to a zero-based history page, using the offered previous/next actions. |
| `visit {id}` | Return the full retained contribution and select it for the shared view. |
| `cutting {id,colour}` | Reuse a completed seed with a new planter, light and retained parent reference. |

Seed names are 1–80 Unicode scalars and rain is 1–240. Source checks these bounds
on raw calls as well as declaring form limits. Plant and rain authors come from
admitted context, never supplied fields. Extra input fields are refused. A full
garden keeps all contributions and still permits rain and revisiting; it does not
silently evict an old bloom. `Blooms` uses typed rows of at most sixteen, following
the shared source collection pattern. The 32-planting policy is separate from
that representation and from native execution/request limits. History pages hold
eight captions so maximum-length Unicode names remain displayable within the
native view work budget.

[EveningGarden](EveningGarden.obend) imports the complete garden and changes its
sign while reusing all contribution behavior. It is an ordinary source variation,
not a host recipe. The tests install it under current reprogramming authority and
keep the same admitted plantings. The sealed source package and the full typed
contributions remain inspectable in the object root.

[law.json](law.json) contains local fixture grants for moss, iris and fern;
builder and steward management rights are separate. Choose actual instance
principals when installing. Viewing an invitation grants no authority. Every
turn checks current law and its exact observed root. Retrying the identical
request and intent recovers its receipt; changing its words requires a new intent.

## Run locally

With current native hosts already built:

```sh
python3 conformance/test_garden_source.py
python3 conformance/test_town_garden.py
python3 conformance/test_authored_interfaces.py
python3 conformance/test_town_journey.py
```

[Garden.examples](Garden.examples) lives beside the behavior and runs through the
normal proposal fixture runner. Joined tests cover two admitted authors, several
waiting seeds, retained history, attributed cuttings, revisit, full capacity,
stale observations, current grants, atomic rollback, exact receipt recovery and
ordinary source variation. Card/post tests use local publication fixtures only.

This directory defines the new local source candidate. The public preview may
still run an older single-bloom garden until its operator explicitly installs
this package. No deployment or outside publication is performed by these tests.
