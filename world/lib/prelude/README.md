# Shared Bend source

Supply these modules before the consumer in one compile job; imports are
`import ./Name.obend as Name` and name an earlier module of the same job.

- `Abi.obend`: the one `Context {world, object, principal, handle, caller, intent, height,
  clock, inputOrigin}` the host fills for every turn, and the law predicate's `Request` and
  `Verdict`.
- `List.obend`: rank-1 generic `List<T>` and its traversals.
