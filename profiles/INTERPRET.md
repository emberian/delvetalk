# Interpretation

**Interpretation proposes; it neither executes nor grants authority.**
[`interpret(text,card,proposer=None)`](../scripts/interpret.py) accepts one captured
public catalogue and returns `proposed`, `clarify` or `escalate`, with `message`
and `via` (`tokens`, `model`, `none`). Proposals include `action` and `fields`.

```text
do CARD a1
do CARD a2 {"count":4,"ready":false}
```

`do` inputs always use deterministic parsing, even when malformed. No repair,
coercion or model fallback. Card mismatch, unknown action, duplicate JSON keys,
extra/missing fields or trailing text clarify.

The exact public-card keys are `card,object,title,prose,actions`. Actions contain
`id,label,available,fields`, optionally `inspectOnly`. [Typed fields](AFFORDANCES.md)
remain application data, including names like `principal`; outer authority
fields are forbidden. Limits: text 4,096 bytes, card 32 KiB/128 actions, reply 16 KiB.

A proposer returns exactly `{action,fields}` or `{status:"clarify"|"escalate",message}`.
Output is checked against the original catalogue. Escalation records a reason;
it makes no supervisor call. Descriptions and model output remain untrusted.

## Haiku opt-in

```sh
python3 scripts/interpret.py /tmp/card.json 'do CARD a1'
python3 scripts/interpret.py /tmp/card.json 'please sit down' --anthropic
```

`--anthropic` uses `ANTHROPIC_API_KEY` for one official Messages API call:
`claude-haiku-5-5`, 512 output tokens, 15-second socket timeout, no tools,
redirects or retries. API calls incur usage. Tokens need no credentials;
CLI token parsing skips key lookup. Service failures produce pending escalation.
Exit codes: proposal 0, clarification 2, escalation 3.

[Mock-only tests](../conformance/test_interpret.py) · [Messages API](https://platform.claude.com/docs/en/api/messages/create)
