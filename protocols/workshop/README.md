# A shared workshop

**Build a place, change its program, and let another participant use it.**
This seed combines ordinary factories, a presence registry, a work ticket and
the original two-player Automatafl table. Every seed is an ordinary Bend source
object with an explicitly supplied typed initial state and an empty genesis; no
previous world or private participant custody is copied. Places and entity
descriptions are source objects too. The main encounters have explicit public
panel grants; raw object reads and actions remain governed separately.

```sh
python3 scripts/workshop.py /tmp/shared-workshop
python3 scripts/portal.py /tmp/shared-workshop --principal moss --allow-local-actions
```

The default builders are `moss` and `iris`. Choose two explicit principals with
`--builders FIRST SECOND`; `--compiler` and `--steward` name separate grants.
These are local assertions, not authenticated logins. [Clerk attachment](../../profiles/CLERK.md)
and the [operator service](../../profiles/SERVICE.md) supply a separate receiving route.

- Enter the porch through `commons`; follow an offered path to the garden.
  Presence changes no object's law.
- Create an object at `factory:objects`. Both builders may use, reprogram and
  govern it. They can later narrow those grants with an explicit law change.
- Create a candidate at `factory:desks`. Its maker submits/adopts; the configured
  compiler reports checks. Use the portal's [source desk](../../profiles/AUTHORING.md)
  to install a tested program into the shared object.
- Post, claim and review work at `ticket:welcome`. Acceptance acknowledges review.
- Play `table:automatafl` using the [private participant helper](../../game/table/PARTICIPANT.md).
  The first builder owns seat 0, the second seat 1; the table has no management grant.

Copy action tokens from current cards. After a stale refusal, read again and
prepare a new intent. After an uncertain reply, retry the saved draft. Public
continuations preserve revealed history; unrevealed game openings stay in each
participant's private custody.

This is an explicitly configured workshop, not a universal world ontology.
Its objects, rules and grants remain inspectable ordinary programs.

Seed custody retains each exact module closure, the original source lowering,
and the configured initial state. Native decoding checks the retained state
schema, and creation and replay decide whether that state is admissible. A
declared constructor name records provenance supplied by the seed author; it
does not prove that an arbitrary supplied state was produced by executing that
constructor. Export and restoration retain these source and configuration bytes.
