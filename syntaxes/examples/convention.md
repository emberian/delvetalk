# A greeting convention

This text is a convention card. Participants may change its prose and notation.
Only the explicit payload below is lowered; prose is retained, never executed.

```delvetalk-protocol
{
  "profile": "delvetalk-local-v1",
  "name": "greeting-card",
  "initial": {"greeting": null},
  "commands": {
    "greet": {
      "require": [[["state", "greeting"], ["literal", null]]],
      "set": {"greeting": ["input", "message"]},
      "result": ["literal", "greeted"],
      "outbox": []
    }
  }
}
```

The host's current law decides who may call `greet`; this card grants no rights.
