# Appointments

**Leave work for an explicit logical time.** [Clock.obend](Clock.obend) admits
requests and cancellations; bounded ticks send native messages to independent
[task objects](Task.obend). Lean decides deadlines, ownership and delivery.

Translate with `objective-bend-spell@3` for authored menus and compact source.
Raw bindings remain available. Use the `compiled` host;
initialize its message registry first. Grant `request`/`cancel` to participants, `tick` to the named
driver, and task `wake` to a relay. Set each task's owner and clock identity.

| Command | Explicit input |
|---|---|
| `request` | `slot`, `generation`, `due`, `deadline`, `to`, `recipientProgram`, `topic` |
| `cancel` | `slot`, `generation` |
| `tick` | `now` |

Slots are 0–7. Booking requires a free or terminal slot, its next generation,
`due >= now`, and `deadline >= due`. Only its owner can cancel its queued
generation. Slot panels bind the exact generation; booking forms collect due time,
deadline, recipient, program digest and activity. Read-only inspection exposes
exact state independently. Recipient digests come from `program-digest`.

Each tick checks **four slots**, alternates halves, and emits at most four events.
Two admitted ticks inspect every slot; rebooking an early slot cannot jump the
queue. Explicit migration from the older two-slot clock must set cursor 0 or 4.
Equal-time ticks drain work. Time cannot decrease. Work sends when
`due <= now <= deadline`; otherwise overdue work expires. Deadlines bound sends,
not later relay delivery. No wall clock is read.

A sent appointment cannot be recalled, even before delivery. Relay admission
still checks the recipient's current authority and captured program. Invalid
recipients, changed programs or full mailboxes refuse the whole tick without
advancing time or cursor. Owners can cancel blocked queued work. Fairness depends
on admitted ticks; it is not a wall-time guarantee.

Persist a tick before submitting it:

```sh
python3 protocols/appointments/clock_driver.py WORLD PRIVATE_ATTEMPT \
  --principal driver --intent tick-5 --now 5
```

Retry the same attempt after an uncertain reply. After confirmed refusal, use a fresh
intent and attempt. The driver never chooses time or due work.

[Receiving and menu tests](../../conformance/test_appointments.py) cover both raw
bindings and authored objects, including killed-reply recovery.
[Menu examples](menu-examples.md) show booking, cancellation and refusal. Run
`python3 conformance/test_appointments.py`.
