# A name for yesterday's rain

Agree on a name after the relay opens. This is a convention between readers;
the card does not inspect the relay. The first admitted name stays on the table.
The form offers a short name and two ink colors. Its field limits guide the
portal; the protocol itself admits the first write by a current grantee.

```delvetalk-protocol
{
  "profile": "delvetalk-local-v1",
  "name": "Yesterday's rain card",
  "description": "Leave a name for the sound you heard together.",
  "initial": {"name": null, "ink": null, "by": null},
  "commands": {
    "name": {
      "require": [[["state", "name"], ["literal", null]]],
      "set": {"name": ["input", "name"], "ink": ["input", "ink"], "by": ["principal"]},
      "result": ["literal", "The rain has a name."],
      "outbox": []
    }
  },
  "affordances": {
    "name": {"label": "Name the rain", "fields": {
      "name": {"type": "string", "minLength": 1, "maxLength": 80},
      "ink": {"type": "enum", "options": ["silver", "blue"]}
    }}
  }
}
```
