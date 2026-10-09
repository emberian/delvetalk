# Appointments

**Book work against explicit logical time.** [Clock](Clock.obend) owns scheduling;
[Appointments](Appointments.obend) implements its typed queue. Independently
governed [tasks](Task.obend) receive native messages. Use the `compiled` host and
initialize its message registry.

Supply sealed modules in order: shared `Abi`, shared `Encounter`, `Appointments`,
then `Clock` or `Task`. The `objective-bend-spell@3` adapter binds authored menus.
Evaluate `configured({capacity: 16})` or `configured({owner: "moss", clock: "clock"})`
for typed initial state; configuration never rewrites source. Grant participants
`request`, `cancel`, `page`; grant the named driver `tick`, and a relay task `wake`.

| Command | Input |
|---|---|
| `request` | `id`, `generation`, `due`, `deadline`, `to`, `recipientProgram`, `topic` |
| `cancel` | `id`, `generation` |
| `tick` | `now` |
| `page` | `offset` |

Booking requires a unique active id, the clock's `nextGeneration`, `due >= now`,
and `deadline >= due`. The global generation increases only on admitted booking.
Send, expiry and owner cancellation remove entries and reclaim capacity. Reusing
an id requires a later generation: old cancellations cannot affect new work.
The last terminal summary remains in state; full outcomes remain in receipts.

Capacity is configured from 1–24, default 16. Actual text/source still face native
byte and fuel limits. Each tick inspects at most four
original entries, rotating future work behind existing entries. New bookings
join the tail. Four emission descriptors bound a turn, not storage. With no new
work, admitted ticks visit every queued entry within `ceil(size/4)` turns.
Queue reversal and inspection cost linear work. Menus display four entries per
page; exact state remains inspectable.

Time cannot decrease. Sends require `due <= now <= deadline`; later work expires.
Deadlines bound sending, not relay delivery. An admitted send cannot be recalled.
Current recipient authority and captured program still govern delivery. Invalid
recipients, changed programs or message capacity refuse the whole tick, preserving
time and queue. The retained refusal explains the blocker; owners may cancel it.

```sh
python3 protocols/appointments/clock_driver.py WORLD PRIVATE_ATTEMPT \
  --principal driver --intent tick-5 --now 5
```

The driver persists this exact tick before submission and retries without refreshing
its root. It never reads wall time or chooses due work. See [menu examples](menu-examples.md)
and [receiving tests](../../conformance/test_appointments.py).
