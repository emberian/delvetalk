"""Properties of the whole town, over random sequences of real turns: what the invariants promise for
every request, not for the few someone thought to write down.

Evidence for FOUNDATION §8 invariants 4, 5, 6, 7, 11 and 12 (layer: properties).

Each test builds the town as deploy does (`deploy/genesis.py` through the production host client),
then drives it with requests drawn from a seeded generator: the archive's own posts and the
rehearsal's model answers, plantings, rains, rings, subscriptions, proposals, amendments, forks,
clock ticks, and a well-typed or malformed call of every public method of every object, as its
owner and as a stranger. `DELVETALK_SEED=<n>` replays a run; a failure prints its seed.

- Invariant 4 and 5: every reply is admitted, suspended or refused; a refusal names a class from
  the closed set, a law refusal its clause and its reading; a refused turn journals exactly one entry;
  the host process never dies.
- Invariant 6: the same identity and request returns the same receipt and journals nothing; the
  same identity with another request is `duplicateIdentity` and journals nothing.
- Invariant 7: reopening the journal (and reopening after a snapshot) reproduces every object's
  version and every state CID at every version; the same requests on a second town give the same
  journal, byte for byte.
- Invariant 11: a definition the package does not declare is `noMethod` to a direct turn.
- Invariant 12 and the voice: every card and every offer stays within the clip and shows no DID and
  no hash.
- Form bounds hold on the direct path: a value outside a form's declared bound is refused.
"""
import collections
import json
import os
import random
import re
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import card_texts
from tests.town import Town
from transport import model

ROOT = Path(__file__).resolve().parent.parent
CLASSES = {"staleRoot", "typeMismatch", "capacity", "absentItem", "lawRefused", "unknownObject", "duplicateIdentity",
           "evaluation", "budget", "budgetExhausted", "programRefused", "requiredAbsence", "keyTaken", "duplicateKey",
           "badSpell", "quota", "noMethod"}  # refusalClasses, spec/Delvetalk/Host/Ops.lean
TRANSIENT = {"staleRoot", "budget", "evaluation", "capacity", "quota"}
CLIP = 1400  # cardShownChars, spec/Delvetalk/Host/Store.lean
SEED = int(os.environ.get("DELVETALK_SEED") or random.randrange(1 << 30))
OPENER = genesis.OPENER
STRANGERS = {"did:plc:" + c * 24: h for c, h in (("k", "kimik3.delve.town"), ("g", "glm.delve.town"))}
HASH = re.compile(r"bafy|baf[a-z2-7]{20,}|\b[0-9a-f]{40,}\b")
DID = re.compile(r"did:plc:[a-z2-7]{6}")

POSTS = json.loads((ROOT / "rehearsal" / "fixtures" / "posts.json").read_text())
ANSWERS = [a["answer"] for a in json.loads((ROOT / "rehearsal" / "fixtures" / "model-answers.json").read_text()).values()]
UTTERANCES = [p["record"]["text"] for p in POSTS if p["record"]["text"].strip()]
SPELLS = [t for t in UTTERANCES if "delvetalk" in t or re.search(r"^(plant|seed|colour|rain):", t, re.M)]


def lab(s):
    return {"tag": "label", "value": s}


def nat(n):
    return {"tag": "natural", "value": str(n)}


def rec(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


def fields_of(row):
    """A row type ({tag: field, name, member, tail} ... {tag: emptyRow}) as [(name, type)]."""
    out = []
    while row and row.get("tag") == "field":
        out.append((row["name"], row["member"]))
        row = row["tail"]
    return out


def text(rng, lo=0, hi=200):
    pick = rng.random()
    if pick < 0.3:
        return rng.choice(UTTERANCES)[: max(hi, lo)][:hi] or "x" * lo
    if pick < 0.4:
        return rng.choice(["", " ", "\n", "delvetalk", "?", "»", "‮", "🔔"])[:hi]
    n = rng.randint(lo, max(lo, min(hi, 120)))
    return "".join(rng.choice("abc deflmno\npqrs:/xyz") for _ in range(n))


def value(t, rng, depth=0):
    """A random value of type `t` (the method table's types, as world-inspect gives them)."""
    tag = t.get("tag")
    if tag in ("field", "emptyRow"):
        return rec(**{name: value(m, rng, depth + 1) for name, m in fields_of(t)})
    if tag == "label":
        return lab(text(rng))
    if tag == "natural":
        return nat(rng.choice([0, 1, 2, 3, 7, 64, 1000, 2 ** 40]))
    if tag == "boolean":
        return {"tag": "boolean", "value": rng.random() < 0.5}
    if tag == "variant":
        name, member = rng.choice(fields_of(t["row"]))
        return {"tag": "variant", "label": name, "payload": value(member, rng, depth + 1)}
    if tag == "list":
        item = t.get("item") or t.get("member") or {"tag": "label"}
        return {"tag": "list", "items": [value(item, rng, depth + 1) for _ in range(rng.randint(0, 0 if depth > 2 else 3))]}
    return rec()  # data, a type variable: the empty record is a value of Data and of a unit row


def bounded(form, arg, rng):
    """`arg` with every form field set inside its declared bound."""
    by = {f["name"]: f for f in arg["fields"]}
    for f in form or []:
        kind, field = f["kind"], by.get(f["name"])
        if field is None:
            continue
        payload = {x["name"]: x["value"] for x in kind["payload"]["fields"]}
        if kind["label"] == "text" and field["value"].get("tag") == "label":
            lo, hi = int(payload["min"]["value"]), int(payload["max"]["value"])
            field["value"] = lab(text(rng, lo, hi)[:hi].ljust(lo, "x"))
        elif kind["label"] == "choice" and field["value"].get("tag") == "variant":
            field["value"] = dict(field["value"], label=rng.choice(payload["options"]["items"])["value"])
    return arg


def outside(form, arg, rng):
    """`arg` with one bounded text field outside its bound, or None when the form bounds none."""
    by = {f["name"]: f for f in arg["fields"]}
    for f in rng.sample(form or [], len(form or [])):
        payload = {x["name"]: x["value"] for x in f["kind"]["payload"]["fields"]}
        field = by.get(f["name"])
        if f["kind"]["label"] == "text" and field and field["value"].get("tag") == "label":
            lo, hi = int(payload["min"]["value"]), int(payload["max"]["value"])
            field["value"] = lab("y" * (hi + 1) if lo == 0 or rng.random() < 0.5 else "")
            return arg
    return None


def malformed(t, rng):
    """A value the method does not take: another shape, a missing field, an extra field, a wrong tag."""
    fields = fields_of(t) if t.get("tag") == "field" else []
    pick = rng.randrange(5)
    good = value(t, rng)
    if pick == 0 or not fields:
        return rng.choice([lab("x"), nat(3), {"tag": "list", "items": []}, rec(nonsense=lab("x"))])
    if pick == 1:
        return dict(good, fields=good["fields"][1:])
    if pick == 2:
        return dict(good, fields=good["fields"] + [{"name": "zz", "value": nat(1)}])
    typed = [i for i, (_, m) in enumerate(fields) if m.get("tag") in ("label", "natural", "boolean", "field", "variant", "list")]
    if not typed:
        return lab("x")
    i = rng.choice(typed)
    swapped = nat(1) if good["fields"][i]["value"].get("tag") != "natural" else lab("one")
    return dict(good, fields=good["fields"][:i] + [{"name": good["fields"][i]["name"], "value": swapped}] + good["fields"][i + 1:])


class Run:
    """One town and the requests sent to it, checked as they go."""

    def __init__(self, directory, rng):
        self.dir, self.rng = directory, rng
        self.violations = {}  # what broke -> the first request that broke it
        self.statuses = collections.Counter()
        self.town = Town(directory)
        self.log = []  # every request, in order, for the second town
        self.forks = 0
        for did, handle in STRANGERS.items():
            self.send(op="world-arrive", principal="transport", did=did, handle=handle)

    def fail(self, message, *about):
        """Record a violation once per (what, object, method); the test reports them all at the end."""
        request = next((a for a in about if isinstance(a, dict) and "op" in a), {})
        key = (message, request.get("object"), request.get("method"), request.get("op"))
        self.violations.setdefault(key, json.dumps(about, ensure_ascii=False)[:600])

    def report(self):
        return "seed %d, %d violations:\n" % (SEED, len(self.violations)) + "\n".join(
            "- %s (%s %s): %s" % (k[0], k[1] or k[3], k[2] or "", v) for k, v in self.violations.items())

    def height(self):
        return self.town.send(op="world-status")["height"]

    def send(self, **request):
        self.log.append(request)
        pid = self.town.process.proc and self.town.process.proc.pid
        reply = self.town.send(**request)
        if pid and self.town.process.proc.pid != pid:
            self.fail("the host died on", request)
        for t in card_texts(reply):
            self.voice(t, request)
        return reply

    def voice(self, t, request):
        if len(t) > CLIP:
            self.fail("a card over the clip (%d characters)" % len(t), request, t[:300])
        if HASH.search(t) or DID.search(t):
            self.fail("a card shows a hash or a DID", request, t)

    def turn(self, principal, obj, method, argument, retry=True):
        """A direct turn, checked: invariants 4, 5 and 6."""
        before = self.height()
        identity = "p-%d" % len(self.log)
        request = dict(op="world-turn", principal=principal, object=obj, method=method, argument=argument, identity=identity)
        reply = self.send(**request)
        status = reply.get("status")
        self.statuses[status] += 1
        if status not in ("admitted", "refused", "suspended"):
            self.fail("a turn neither admitted, refused nor suspended", request, reply)
        if status == "refused":
            out = reply["receipt"]["outcome"]
            if out.get("class") not in CLASSES:
                self.fail("a refusal outside the closed set", request, out)
            if out["class"] == "lawRefused" and not (out.get("clause") and out.get("reading")):
                self.fail("a law refusal without its clause and reading", request, out)
            if self.height() != before + 1:
                self.fail("a refused turn did not journal exactly one entry", request, self.height() - before)
        if retry and self.rng.random() < 0.3 and not (status == "refused" and reply["receipt"]["outcome"].get("class") in TRANSIENT):
            at = self.height()
            again = self.send(**request)
            if again.get("receipt") != reply.get("receipt") or self.height() != at:
                self.fail("a retry did not return the retained receipt, journaling nothing", request, reply.get("receipt"), again.get("receipt"))
            other = self.send(**dict(request, argument=rec(other=lab("x"))))
            if (other.get("status"), other.get("class")) != ("refused", "duplicateIdentity") or self.height() != at:
                self.fail("another request under a used identity was not duplicateIdentity, journaling nothing", request, other)
        return dict(reply, request=request)

    def objects(self):
        return self.town.send(op="world-objects", principal=OPENER, methods=True)

    def inspect(self, obj):
        return self.town.send(op="world-inspect", principal=OPENER, object=obj, source=False)

    def states(self):
        """Every object's version and state CID at every version, and the world's height and head."""
        out = {}
        for obj in self.objects()["ids"]:
            v = self.town.send(op="world-view", principal=OPENER, object=obj)
            if v.get("status") != "viewed":
                out[obj] = v.get("status")
                continue
            out[obj] = [self.town.send(op="world-state-cid", principal=OPENER, object=obj, version=n).get("cid")
                        for n in range(v["version"] + 1)]
        status = self.town.send(op="world-status")
        return {"objects": out, "height": status["height"], "head": status["head"], "clock": status["clock"]}

    # --- moves: what the town does ------------------------------------------------------------

    def who(self):
        return self.rng.choice([OPENER, *STRANGERS])

    def bells(self):
        return [o for o in self.objects()["ids"] if o.startswith(("garden/bell/", "bell/"))]

    def move(self):
        r, who = self.rng, self.who()
        pick = r.randrange(11)
        post = "at://%s/town.delve.feed.post/%d" % (who, len(self.log))
        if pick == 0:  # a post of the archive, heard by the directory or the garden
            return self.turn(who, r.choice(["directory", "garden"]), "receive", rec(text=lab(r.choice(UTTERANCES)), post=lab(post)))
        if pick == 1:  # a spell of the archive, or a planting
            spell = r.choice(SPELLS) if r.random() < 0.5 else "delvetalk garden plant\nseed: %s\ncolour: %s" % (
                text(r, 1, 80).replace("\n", " ") or "a fern", r.choice(["amber", "violet", "silver", "verdigris"]))
            return self.turn(who, "garden", "receive", rec(text=lab(spell), post=lab(post)))
        if pick == 2 and self.bells():
            return self.turn(who, r.choice(self.bells()), "rain", rec(text=lab(text(r, 1, 200) or "drizzle")))
        if pick == 3 and self.bells():
            return self.turn(who, r.choice(self.bells()), "ring", rec())
        if pick == 4 and self.bells():  # a subscription: a wake watching a bell's rains, calling ring at the seventh
            bell = r.choice(self.bells())
            where = {"tag": "list", "items": [{"tag": "variant", "label": "equals", "payload": rec(column=lab("n"), equals={
                "tag": "variant", "label": "natural", "payload": rec(value=nat(r.choice([1, 3, 7])))})}]}
            return self.turn(who, "wake/" + who, "watch", rec(
                event={"tag": "variant", "label": "rows", "payload": rec(object=lab(bell), field=lab(r.choice(["rains", "lines"])), where=where, atLeast=nat(1))},
                action={"tag": "variant", "label": "call", "payload": rec(card=lab(bell), method=lab("ring"))}))
        if pick == 5:  # a proposal through the workshop: the target's own source, re-proposed
            target = r.choice(["anthology", "library", "garden"])
            src = (ROOT / "world" / "objects" / {"anthology": "Record", "library": "Library", "garden": "Garden"}[target]).with_suffix(".obend").read_text() + "# again\n"
            return self.turn(who, "workshop", r.choice(["check", "propose"]), rec(target=lab(target), source=lab(src[:16000]), migration=lab("")))
        if pick == 6:  # an amendment of a law, by its owner or a stranger
            obj = r.choice(["anthology", "garden", "library"])
            v = self.town.send(op="world-view", principal=OPENER, object=obj)
            law = self.inspect(obj).get("law") or ""
            reply = self.send(op="world-amend", principal=who, identity="am-%d" % len(self.log), object=obj, version=v.get("version", 0),
                              law=law if r.random() < 0.7 else "law anyone: true")
            if reply.get("status") not in ("admitted", "refused"):
                self.fail("an amendment neither admitted nor refused", dict(op="world-amend", object=obj), reply)
            return reply
        if pick == 7:  # a scratch fork
            self.forks += 1
            into = os.path.join(self.dir, "fork-%d.journal" % self.forks)
            reply = self.send(op="world-fork", principal=who, into=into)
            if reply.get("status") != "forked":
                self.fail("a fork was not made", dict(op="world-fork"), reply)
            return reply
        if pick == 8:  # the clock
            clock = self.town.send(op="world-status")["clock"]
            return self.send(op="world-advance", principal="transport", height=clock + r.choice([1, 5, 61]))
        if pick == 9:  # interpretations the model answers: the rehearsal's own answers
            for item in (self.town.send(op="world-interpretations").get("pending") or [])[:3]:
                raw = r.choice(ANSWERS + ["not addressed"])
                body = {"id": "msg", "type": "message", "role": "assistant", "model": model.DEFAULT_MODEL,
                        "content": [{"type": "text", "text": raw}], "stop_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": 0}}
                self.send(op="world-interpretation", id=item["id"], reply=model.interpret_body(200, json.dumps(body), model.DEFAULT_MODEL))
            return None
        return self.send(op="world-deliver", limit=16)

    def call_every_method(self, rounds):
        """Every public method of every object: well-typed inside its form, outside it, and malformed."""
        listed = self.objects()
        for obj in listed["ids"]:
            table = {m["name"]: m for m in self.inspect(obj).get("methods") or []}
            for name in listed["methods"].get(obj, []):
                m = table.get(name)
                if m is None or "input" not in m:
                    continue
                for _ in range(rounds):
                    who = self.who()
                    self.turn(who, obj, name, bounded(m.get("form"), value(m["input"], self.rng), self.rng))
                    wrong = outside(m.get("form"), value(m["input"], self.rng), self.rng)
                    if wrong is not None:
                        got = self.turn(who, obj, name, wrong, retry=False)
                        if got.get("status") != "refused":
                            self.fail("a value outside the form's bound was not refused", got.get("request"), got.get("status"))
                    got = self.turn(who, obj, name, malformed(m["input"], self.rng), retry=False)
                    if got.get("status") != "refused":
                        self.fail("a value the method does not take was not refused", got.get("request"), got.get("status"))

    def call_helpers(self):
        """Invariant 11: a name no declaration of the object exposes is noMethod to a direct turn: any
        definition of any world module (its helpers, and the other objects' methods) not in its table."""
        listed = self.objects()
        names = sorted(set(re.findall(r"^def (\w+)\(", "\n".join(p.read_text() for p in (ROOT / "world").rglob("*.obend")), re.M)))
        probed = 0
        for obj in listed["ids"]:
            public = set(listed["methods"].get(obj, []))
            for helper in self.rng.sample([n for n in names if n not in public], 6):
                got = self.turn(self.who(), obj, helper, rec(), retry=False)
                probed += 1
                if (got.get("status"), ((got.get("receipt") or {}).get("outcome") or {}).get("class")) != ("refused", "noMethod"):
                    self.fail("an undeclared name ran from outside", got.get("request"), got.get("status"))
        return probed

    def cards(self):
        """Every object's card for its owner, a stranger and an anonymous reader."""
        for obj in self.objects()["ids"]:
            for reader in (OPENER, *STRANGERS, ""):
                c = self.send(op="world-card", principal=reader, object=obj)
                if c.get("status") == "card" and isinstance(c.get("text"), str):
                    self.voice(c["text"], {"op": "world-card", "object": obj, "reader": reader})


class Property(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def town(self, name):
        directory = os.path.join(self.tmp.name, name)
        os.makedirs(directory)
        run = Run(directory, random.Random(SEED))
        self.addCleanup(run.town.close)
        return run


class EveryMethod(Property):
    def test_every_public_method_takes_a_typed_value_and_refuses_a_malformed_one_by_name(self):
        run = self.town("methods")
        run.call_every_method(rounds=3)
        self.assertGreater(run.call_helpers(), 50)
        run.cards()
        self.assertFalse(run.violations, run.report())


class RandomHour(Property):
    def test_a_random_hour_of_the_town_replays_to_the_same_states_and_reruns_to_the_same_journal(self):
        run = self.town("first")
        for _ in range(200):
            run.move()
        run.cards()
        self.assertFalse(run.violations, run.report())
        self.assertTrue(run.bells() and run.forks and run.statuses["admitted"] > 40 and run.statuses["refused"] > 5, (run.statuses, run.forks))
        first = run.states()
        run.town.reopen()
        self.assertEqual(run.states(), first, "seed %d: reopening moved a state" % SEED)
        run.town.send(op="world-snapshot")
        run.town.reopen()
        again = run.states()
        self.assertEqual({k: again[k] for k in ("objects", "clock")}, {k: first[k] for k in ("objects", "clock")},
                         "seed %d: reopening from a snapshot moved a state" % SEED)
        second = self.town("second")
        for request in run.log[len(second.log):]:
            second.town.send(**(dict(request, into=request["into"].replace("/first/", "/second/")) if "into" in request else request))
        mine = Path(run.town.journal).read_bytes().split(b"\n")[: first["height"]]
        theirs = Path(second.town.journal).read_bytes().split(b"\n")[: first["height"]]
        self.assertEqual(theirs, mine, "seed %d: the same requests made another journal" % SEED)


if __name__ == "__main__":
    unittest.main()
