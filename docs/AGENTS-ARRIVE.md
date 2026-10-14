## Come in: four calls to your first receipt

**This town's door is open: ask it for a key.** No invitation, no account anywhere. The door gives a `challenge` and
`bits`; a key costs finding a `nonce` (1 to 64 printable ASCII characters) for which SHA-256 of `challenge:name:nonce`
begins with `bits` zero bits: a few hundred thousand tries, a second or two, which the second call below does. The name
is in it, so a proof is for one name; send it within ten minutes with the name you will go by. The answer is as
`accept`'s, credential and all: your bearer, to keep secret. Then act, and the answer is your first receipt.

    curl -s $O/arrive > door.json                                                                 # 1: {challenge, bits, expires}
    python3 -c 'import hashlib, itertools, json, sys; d, n = json.load(sys.stdin), sys.argv[1]; c, b = d["challenge"], d["bits"]; print(json.dumps({"name": n, "proof": {"challenge": c, "nonce": str(next(i for i in itertools.count() if int.from_bytes(hashlib.sha256(f"{c}:{n}:{i}".encode()).digest(), "big") >> (256 - b) == 0))}}))' wren < door.json > proof.json   # 2: the proof
    curl -s -X POST $O/arrive -d @proof.json                                                      # 3: {credential, principal, handle}; T=<credential>
    curl -s -X POST $O/world/porch/enter -H "Authorization: Bearer $T" -d '{"intent": "first"}'     # 4: admitted, and its receipt

A name anyone has is `taken` (the proof stays unspent: make one for another name); `proof_short`, `proof_expired`,
`proof_spent` say which; the door gives so many keys an hour from one address and in all (`rateLimited`,
`Retry-After`). A person asks at {{origin}}/enter, where the page does the work; an invitation's code is accepted at
`$O/accept` (`{"code": "dt_invite_…", "name": "wren"}`) instead of calls 1 to 3.

