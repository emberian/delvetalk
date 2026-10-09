# Book, inspect, cancel

**The clock offers its next global generation.** Assemble the explicit modules
listed in [README](README.md), then open the clock's authored card.

1. Choose **Book an appointment**. The card binds `generation: 1`. Supply id
   `night-garden`, due `5`, deadline `8`, recipient `garden-task`, its exact native
   program digest, and activity `water the night garden`.
2. The queue links that recipient and offers cancellation bound to the admitted
   id and generation. **Look inside** exposes owner, due, deadline, generation,
   capacity, current logical time and queue order without changing the object.
   **Next four appointments** pages through a longer queue. Browsing changes only
   the authored page offset and still faces current law and exact-root admission.
3. Cancel before sending. The entry disappears and capacity returns. Another
   participant cannot cancel it. Booking the same id uses generation 2; neither
   an old captured card nor an old cancellation with a fresh root can cancel it.
4. Alternatively, the driver submits a recorded logical tick. Each turn inspects
   up to four entries; future entries rotate behind existing work. A successful
   send removes the active entry and records a native event. There is no recall.
5. The relay delivers the event. The task changes from **Waiting for an
   appointment** to **Appointment received**, displays the activity, and links its
   clock. It offers no ordinary wake action.

If the recipient program changed, the tick returns
`message recipient program changed before emission`. The queue and time remain
unchanged. The driver prints that exact retained receipt; retrying the same attempt
recovers it. Inspect the linked recipient, cancel the blocked generation, and book
with the current program digest. The source view never invents a successful send
or a diagnosis it did not receive.

[Source examples](Clock.examples) run through the proposal runner. [Receiving journeys](../../conformance/test_appointments.py) exercise captured
menus, pagination, cancellation races, collection reclamation, independent tasks,
whole-batch refusal and killed-reply recovery.
