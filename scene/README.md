# Spween scenes

Spween supplies prose, passages, choices, guards and ordered effects. Bend supplies
authored handler behavior and the source scene runtime. The native source host
admits the resulting decisions under exact roots and current law.

```sh
make build scene-build
```

Use [the handler workshop](../protocols/spween-handler-workshop/README.md) to submit
scene text and ordered Bend modules, inspect compiler results and explicitly
adopt. [Runtime source](runtime/) and [handler definitions](../protocols/spween-handlers/)
are the behavior owners; physical packaging retains exact source and parsed data.
[UPSTREAM](UPSTREAM.md) describes parser provenance and interchange.

Effects thread one handler state in authored order. A call sees prior assignments;
subsequent effects see its returned state. A late refusal or budget overflow rolls
back the admitted turn. Looking at a view does not execute passage entry effects.
Choices bind captured state, so concurrent changes refuse stale requests instead
of silently redirecting them. Recover uncertain choices using their original
attempt.

Scene scalar operations use explicit Null, Boolean, signed i64 and text semantics.
Float execution and string ordering are unsupported in the handler profile.
Membership may query authored handler state; it grants no ambient object reads.
Handler sends use the shared bounded source emissions collection and later
recipient admission. Source requests determine clock/scheduling behavior;
physical timers do not become history by themselves.

Scenes and handlers retain exact modules with explicit migration on revision.
Copying a scene or object reference grants no authority. Current source/runtime
changes require matching receiving qualification; see [BACKLOG](../BACKLOG.md).
