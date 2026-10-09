# A name for yesterday's rain

Agree on a name after the relay opens. This is a convention between readers;
the card does not inspect the relay. The first admitted name stays on the table.

[RainCard.obend](RainCard.obend) owns the card's methods, input bounds, ink choices,
author attribution and view. Its receiving method checks every bound, including
for callers who do not use the form. The source is proposed and checked with
[rain-card.examples](rain-card.examples), then admitted as a separately governed
object. No shared state is copied from the relay.
