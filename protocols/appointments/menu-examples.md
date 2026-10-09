# Booking through an authored clock

**A slot panel offers its next generation or its current cancellation.** Translate
[Clock.obend](Clock.obend) and [Task.obend](Task.obend) with
`objective-bend-spell@3`. Each source supplies its own description and view.

1. Open **Slot 7** on the clock. Its empty panel offers **Schedule this slot**,
   capturing `slot: 7` and `generation: 1`. Supply due time `5`, deadline `8`,
   recipient `garden-task`, that recipient's exact native program digest, and
   activity `water the night garden`.
2. After admission, the panel says **queued** and links the recipient. **Look
   inside** exposes exact generation, due time, deadline, owner and clock time
   without changing the object. The cancellation action captures generation 1;
   another participant still lacks the owner's cancellation authority.
3. Cancel before sending. The panel becomes **cancelled** and offers generation 2.
   An old cancellation cannot affect a later booking. A captured card with a stale
   root refuses and must be reread.
4. Alternatively, the driver submits explicit logical time. Each tick inspects
   four slots; two admitted ticks cover all eight. A successful send changes its
   panel to **sent**. There is no recall action.
5. Deliver the retained native message. The independent task's card changes from
   **Waiting for an appointment** to **Appointment received** and displays the
   activity. It links its clock and exposes no ordinary wake action.

If a recipient program changed, the tick returns the retained refusal
`message recipient program changed before emission`. The clock remains queued,
with the same root and cursor. The driver prints that exact receipt; retrying the
same attempt recovers it. Inspect the linked recipient, cancel the old booking,
and book a new generation with its current program digest. The menu does not
invent a blocker or infer a successful send.

[Executable menu journeys](../../conformance/test_appointments.py) exercise these
captured actions against native admission, including owner refusal and pure
inspection.
