# Appointments

**Book work against explicit logical time.** [Clock](Clock.obend) owns scheduling;
[Appointments](Appointments.obend) implements its typed queue. Independently
governed [tasks](Task.obend) receive native messages. Use the `compiled` host and
initialize its message registry.

Supply sealed modules in order: shared `Abi`, shared `Encounter`, `Preparation`, `Emissions`, `Appointments`,
then `Clock` or `Task`. The `objective-bend-object` adapter binds authored menus.
Evaluate `configured({capacity: 16})` or `configured({owner: "moss", clock: "clock"})`
for typed initial state; configuration never rewrites source. Grant participants
`request`, `cancel`, `page`; grant the named driver `tick`, and a relay task `wake`.

| Command | Input |
|---|---|
| `request` | `id`, `generation`, `due`, `deadline`, `to`, `recipientProgram`, `topic` |
| `quote` | `id`, `due`, `deadline`, `to`, `recipientProgram`, `topic` |
| `cancel` | `id`, `generation` |
| `status` | `id`, `generation` |
| `tick` | `now` |
| `sample` | `unixMillis` |
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

For a physical observation, initialize `Clock.physical` with `capacity`,
`epochMillis` and positive `quantumMillis`, and grant the driver `sample`.
`scripts/clock_physical_driver.py` retains one Unix millisecond observation and
its exact invocation before submission. Bend converts it to logical time and
rejects observations before the epoch or previous observation. A large jump
expires missed deadlines; equal logical time can sweep remaining bounded work.
An uncertain reply retries the retained request without measuring again.

[ScheduledBell](ScheduledBell.obend) joins the clock to the resident Bell, Door
and Lantern. Its schedule invitation captures both its own program and its
listener's program, then atomically arms, quotes, books and retains the actual
booking result. The owner can cancel queued work. Once the clock has sent or
expired that exact generation, the retirement invitation calls `Clock.status`
and retains its immediately preceding `absent` result. Retirement permits a new
booking; a later event for the retired or older generation is consumed with
an explicit `declined` result and no sound. A caller-supplied absence claim
cannot retire the bell. See the [joined relationship tests](../../conformance/test_appointment_relationship.py)
and [physical custody tests](../../conformance/test_appointment_physical.py).

Required schedule fields and message payload fields use checked source lookups.
A missing schedule field asks for that field; a wrong type refuses. Zero due,
deadline or tick values remain valid natural values. Missing captured observations
refuse preparation; malformed appointment messages refuse before changing state.
