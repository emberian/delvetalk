# Shared Bend source

Supply these modules before the consumer in one compile job; imports are
`import ./Name.obend as Name` and name an earlier module of the same job.

- `Abi.obend`: the one `Context {object, principal, inputOrigin}`, plus form field shapes.
- `List.obend`: rank-1 generic `List<T>` and its traversals.
- `Encounter.obend`, `EncounterPages.obend`: keyed child collections and their pages.
- `../Plan.obend`: the Plan and Response vocabulary of docs/FOUNDATION.md section 3.
- `../document/Document.obend`: the structured document objects render for cards.

The old host-ABI modules (`Preparation`, `Allocation`, `Emissions`, `Authority`,
`ScenarioLaw`, `RevisionReport`, `Reflection`) are gone with the dynamic Value universe.
