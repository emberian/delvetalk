"""Closed core terms in the evaluators' JSON array wire, for conformance.

Wire (shared by impl/c, impl/js, impl/python and the `evaluate-term` op):
  ["bound", i] ["nat", "123"] ["boolean", true] ["label", "s"] ["refuse", reason] ["lam", b]
  ["app", f, a] ["mix", l, u] ["fix", s, i] ["specification", m, e]
  ["prototype", s, t] ["reflect"|"metadata"|"project"|"perform"|"done"|"toData", x] ["textJoin", list, separator]
  ["relationCount", relation] ["relationLookup", relation, [column, ...], probe]
  ["unary", prim, x] ["binary", prim, l, r] ["get", x, "name"]
  ["inject", "label", x] ["ifZero", v, z, s] ["ifBool", c, t, f]
  ["record", [[name, term], ...]] ["extend", x, fields] ["case", x, arms]
A job is {"name", "term", "responses", "fuel"}; generated cases also carry a "kind"
(term, activity, stuck, diverge, shared-effect, exotic-value, chain, stored, refuse) which the runner strips.

Terms are built by kind (nat, bool, label, record, sum, function) so most
evaluate; a share is deliberately ill-kinded (stuck), diverging, or performs.
Run `python3 -m tests.conformance.generate N [SEED]` for JSON lines.
"""
import json
import random
import sys

TAGS = ["bound", "lam", "app", "mix", "fix", "specification", "prototype", "reflect", "metadata",
        "project", "nat", "boolean", "label", "refuse", "unary", "binary", "extend", "record", "get", "ifZero",
        "inject", "case", "ifBool", "perform", "done", "toData", "textJoin", "relationCount", "relationLookup"]
BINARY = ["add", "multiply", "equal", "conjunction", "labelEqual", "subtract", "divide", "less",
          "lessEqual", "modulo", "textConcat", "textTake", "textDrop", "textSpan", "textBreak", "textHasAny",
          "textCanonicalCompare"]
UNARY = ["natText", "textLength", "sha256Text"]
STRINGS = ["", "a", "abc", "hello world", "line\nbreak", "\n", "é", "日本語", "😀x", "tab\t", "a b c",
           'q"uote', "back\\slash", "x" * 40, "Hello, World!", "world hello", "HELLO-there"]
ALPHABETS = ["", "a", "abc", " ", "\n", "é日", "😀", "xyz"]
NATS = [0, 1, 2, 3, 5, 7, 10, 255, 4096, 10 ** 20, 2 ** 64]
LABELS = ["ok", "refused", "left", "right", "none"]
FIELDS = ["a", "b", "c"]


def size(term):
    """Constructor count (iterative: a 2,048-row literal nests about 8,000 deep)."""
    total, pending = 0, [term]
    while pending:
        term = pending.pop()
        if not isinstance(term, list) or not term or not isinstance(term[0], str):
            continue
        total += 1
        for child in term[1:]:
            if isinstance(child, list) and child and isinstance(child[0], str) and child[0] in TAGS:
                pending.append(child)
            elif isinstance(child, list):
                pending.extend(field[1] for field in child if isinstance(field, list) and len(field) == 2)
    return total


def tags(term, out=None):
    """The constructors (and `binary:`/`unary:` primitives) a term uses (iterative, as `size`)."""
    out = set() if out is None else out
    pending = [term]
    while pending:
        term = pending.pop()
        if isinstance(term, list) and term and isinstance(term[0], str) and term[0] in TAGS:
            out.add(term[0])
            if term[0] in ("binary", "unary"):
                out.add(term[0] + ":" + term[1])
            pending.extend(term[1:])
        elif isinstance(term, list):
            pending.extend(field[1] for field in term if isinstance(field, list) and len(field) == 2)
    return out


class Gen:
    def __init__(self, rng):
        self.r = rng
        self.separator = 0  # >0 while generating a join separator

    # kinds: nat bool label rec sum fn
    def term(self, kind, env, b):
        return getattr(self, "g_" + kind)(env, b)

    def var(self, kind, env):
        return [i for i, k in enumerate(env) if k == kind]

    def g_nat(self, env, b):
        r = self.r
        vs = self.var("nat", env)
        if b <= 2:
            if vs and r.random() < 0.5:
                return ["bound", r.choice(vs)]
            return ["nat", str(r.choice(NATS))]
        h = max(1, (b - 1) // 2)
        c = r.randrange(16)
        if c == 0:
            return ["binary", r.choice(["add", "multiply", "subtract", "divide", "modulo"]),
                    self.g_nat(env, h), self.g_nat(env, h)]
        if c == 1:
            return ["ifZero", self.g_nat(env, h // 2), self.g_nat(env, h // 2), self.g_nat(["nat"] + env, h // 2)]
        if c == 2:
            cond, yes, no = self.g_bool(env, h // 2), self.g_nat(env, h // 2), self.g_nat(env, h // 2)
            if r.random() < 0.1:
                # A refusal at a label has no reduction: stuck when this arm is taken, inert when not.
                refusal = ["refuse", ["label", r.choice(STRINGS)]]
                yes, no = (refusal, no) if r.random() < 0.5 else (yes, refusal)
            return ["ifBool", cond, yes, no]
        if c == 3:
            return ["get", self.g_rec(env, h), r.choice(FIELDS)]
        if c == 4:
            return ["case", self.g_sum(env, h // 2), self.arms(env, b - 2, "nat")]
        if c == 5:
            kind = r.choice(["nat", "label", "bool"])
            return ["app", ["lam", self.term("nat", [kind] + env, h // 2)], self.term(kind, env, h // 2)]
        if c == 6:
            return ["unary", "textLength", self.g_label(env, h)]
        if c == 7:
            if r.random() < 0.3:
                return ["binary", "textCanonicalCompare", self.g_label(env, h // 2), self.g_label(env, h // 2)]
            return ["binary", r.choice(["textSpan", "textBreak"]), self.g_label(env, h // 2), ["label", r.choice(ALPHABETS)]]
        if c == 8:
            # toData is the identity at runtime: it must step exactly like done.
            return [r.choice(["done", "toData"]), self.g_nat(env, h)]
        if c == 9:
            return ["project", ["prototype", self.g_nat(env, h // 2), self.g_nat(env, h // 2)]]
        if c == 10:
            return ["metadata", ["specification", self.g_nat(env, h // 2), self.g_nat(env, h // 2)]]
        if c == 11:
            return ["app", ["specification", self.g_nat(env, h // 3), ["lam", self.g_nat(["nat"] + env, h // 2)]],
                    self.g_nat(env, h // 3)]
        if c == 12:
            return self.mix(env, h)
        if c == 13:
            return self.fact(env)
        if c == 14:
            return ["reflect", ["prototype", self.g_nat(env, h // 2), self.g_nat(env, h // 2)]]
        return ["binary", "add", self.g_nat(env, h), self.g_nat(env, h)]

    def mix(self, env, h):
        # mix lower upper = \s. \x. upper s (lower s x)
        lower = ["lam", ["lam", self.g_nat(["nat", "nat"] + env, max(1, h // 3))]]
        upper = ["lam", ["lam", self.g_nat(["nat", "nat"] + env, max(1, h // 3))]]
        return ["app", ["app", ["mix", lower, upper], self.g_nat(env, 1)], self.g_nat(env, max(1, h // 4))]

    def fact(self, env):
        # fix (\self. \i. \n. ifZero n 1 (n * self n')) 0 applied to n
        n = ["bound", 0]
        body = ["ifZero", n, ["nat", "1"],
                ["binary", "multiply", ["binary", "add", ["bound", 0], ["nat", "1"]],
                 ["app", ["bound", 3], ["bound", 0]]]]
        spec = ["lam", ["lam", ["lam", body]]]
        return ["app", ["fix", spec, ["nat", "0"]], ["nat", str(self.r.randrange(0, 7))]]

    def g_bool(self, env, b):
        r = self.r
        if b <= 2:
            return ["boolean", r.random() < 0.5]
        h = max(1, (b - 1) // 2)
        c = r.randrange(6)
        if c == 0:
            return ["binary", r.choice(["equal", "less", "lessEqual"]), self.g_nat(env, h), self.g_nat(env, h)]
        if c == 1:
            return ["binary", "conjunction", self.g_bool(env, h), self.g_bool(env, h)]
        if c == 2:
            return ["binary", r.choice(["labelEqual", "textHasAny"]), self.g_label(env, h), self.g_label(env, h)]
        if c == 3:
            return ["ifBool", self.g_bool(env, h // 2), self.g_bool(env, h // 2), self.g_bool(env, h // 2)]
        if c == 4:
            return ["app", ["lam", self.g_bool(["bool"] + env, h)], self.g_nat(env, h // 2)]
        return ["boolean", r.random() < 0.5]

    def g_label(self, env, b):
        r = self.r
        vs = self.var("label", env)
        if b <= 2:
            if vs and r.random() < 0.5:
                return ["bound", r.choice(vs)]
            return ["label", r.choice(STRINGS)]
        h = max(1, (b - 1) // 2)
        c = r.randrange(9)
        if c == 0:
            return ["binary", "textConcat", self.g_label(env, h), self.g_label(env, h)]
        if c == 1:
            return ["binary", "textTake", self.g_label(env, h), self.g_nat(env, h)]
        if c == 2:
            return ["binary", "textDrop", self.g_label(env, h), self.g_nat(env, h)]
        if c == 3:
            return ["unary", "natText", self.g_nat(env, h)]
        if c == 4:
            return ["unary", "sha256Text", self.g_label(env, h)]
        if c == 5:
            return ["ifBool", self.g_bool(env, h // 2), self.g_label(env, h // 2), self.g_label(env, h // 2)]
        if c == 6:
            return ["binary", "textTake", self.g_label(env, h), ["nat", str(r.randrange(0, 6))]]
        if c == 7:
            strings = self.g_strings(env, h)
            # A join forces its separator only between two items, and the machine forces a
            # stuck separator where a call-by-name evaluator never reaches it: keep it well-formed.
            self.separator += 1
            try:
                return ["textJoin", strings, self.g_label(env, max(1, h // 2))]
            finally:
                self.separator -= 1
        return ["label", r.choice(STRINGS)]

    def g_strings(self, env, b):
        """A List<String> literal (nil/cons injections); now and then a cell is
        malformed (a missing tail, a natural head) so the join is stuck."""
        r = self.r
        items = ["inject", "nil", ["record", []]]
        count = r.randrange(0, 5)
        for i in range(count):
            head = self.g_label(env, max(1, b // 3))
            # Not the first item's head: a join of one non-text item is that item in the
            # reference expansion (no concatenation), while the machine refuses it.
            if r.random() < 0.05 and not self.separator and i < count - 1:
                head = ["nat", "1"]
            fields = [["head", head], ["tail", items]]
            if r.random() < 0.05 and not self.separator:
                fields = fields[:1]
            items = ["inject", "cons", ["record", fields]]
        return items

    def g_rec(self, env, b):
        r = self.r
        h = max(1, (b - 1) // 3)
        names = list(FIELDS)
        fields = [[n, self.g_nat(env, h)] for n in names]
        if r.random() < 0.15:
            fields.append([r.choice(names), self.g_nat(env, h)])  # duplicate: first match wins
        if r.random() < 0.3:
            return ["extend", ["record", fields], [[r.choice(names), self.g_nat(env, h)]]]
        return ["record", fields]

    def g_sum(self, env, b):
        h = max(1, b - 1)
        return ["inject", self.r.choice(LABELS[:3]), self.g_nat(env, h)]

    def arms(self, env, b, kind):
        r = self.r
        labels = list(LABELS[:3])
        if r.random() < 0.08:
            labels = labels[:2]  # a missing arm: stuck when selected
        h = max(1, b // (len(labels) + 1))
        return [[l, self.term(kind, [r.choice(["nat", "nat", "label"])] + env, h)] for l in labels]

    def g_fn(self, env, b):
        return ["lam", self.g_nat(["nat"] + env, b)]


def plan(rng):
    return ["inject", rng.choice(["view", "write", "offer"]),
            ["record", [["n", ["nat", str(rng.choice(NATS))]], ["who", ["label", rng.choice(STRINGS)]]]]]


def response(rng):
    return ["inject", rng.choice(LABELS[:3]), ["nat", str(rng.choice(NATS))]]


def activity(g, rng, performs, answered):
    """A chain of performs; each response selects an arm that continues or finishes."""
    def level(i, env):
        if i == performs:
            return ["done", g.g_nat(env, 8)] if rng.random() < 0.7 else g.g_nat(env, 8)
        arms = [[l, level(i + 1, ["nat"] + env)] for l in LABELS[:3]]
        return ["case", ["perform", plan(rng)], arms]
    responses = [response(rng) for _ in range(answered)]
    return level(0, []), responses


def stuck(g, rng):
    n, l, bo, rec = g.g_nat([], 6), g.g_label([], 4), g.g_bool([], 4), g.g_rec([], 6)
    return rng.choice([
        ["binary", "add", l, n], ["get", n, "a"], ["app", n, n], ["case", n, [["ok", n]]],
        ["ifBool", n, n, n], ["ifZero", l, n, n], ["binary", "textConcat", n, l], ["unary", "natText", l],
        ["unary", "textLength", n], ["binary", "conjunction", n, bo], ["get", rec, "missing"],
        ["case", ["inject", "unmatched", n], [["ok", n]]], ["binary", "labelEqual", bo, bo],
        ["project", n], ["reflect", rec], ["metadata", n], ["extend", n, [["a", n]]],
        ["binary", "textTake", n, n], ["binary", "textSpan", l, n], ["ifZero", bo, n, n],
        ["done", ["binary", "add", l, l]],
        ["refuse", ["label", rng.choice(STRINGS)]], ["binary", "add", ["refuse", ["label", "operand"]], n],
        ["ifBool", ["boolean", True], ["refuse", ["label", "taken"]], n],
        ["ifBool", ["boolean", False], n, ["refuse", ["label", "taken"]]],
        ["ifBool", ["boolean", True], n, ["refuse", ["label", "never"]]], ["app", ["lam", ["refuse", ["label", "body"]]], n],
        ["case", ["inject", "ok", n], [["ok", ["refuse", ["label", "arm"]]]]],
    ])


def shared_effect(g, rng):
    """A perform reached while forcing a shared argument cell: the machine refuses it
    (Refusal.sharedEffect); a call-by-name evaluator substitutes and performs, here twice."""
    effect = ["case", ["perform", plan(rng)], [[l, ["nat", str(i)]] for i, l in enumerate(LABELS[:3])]]
    term = ["app", ["lam", ["binary", "add", ["bound", 0], ["bound", 0]]], effect]
    return term, [response(rng), response(rng)]


def values_of_every_kind(g, rng):
    """Specifications, prototypes and mix results as final values."""
    nat = lambda: g.g_nat([], 4)
    return rng.choice([["specification", nat(), ["lam", nat()]], ["prototype", nat(), nat()],
                       ["mix", ["lam", ["lam", ["bound", 0]]], ["lam", ["lam", ["bound", 0]]]],
                       ["extend", ["record", [["a", nat()]]], [["b", nat()]]]])


def diverge(rng):
    # fix (\self. \i. self) 0 : each unfolding returns to itself
    return ["fix", ["lam", ["lam", ["bound", 1]]], ["nat", "0"]]


def sized(g, kind, budget):
    return g.term(kind, [], budget)


def chain(g, rng):
    """About 1,000 nodes: a left-nested chain mixing arithmetic with lets (app of lam)."""
    term = ["nat", "1"]
    while size(term) < 980:
        step = rng.randrange(3)
        if step == 0:
            term = ["binary", "add", term, ["nat", str(rng.choice(NATS[:6]))]]
        elif step == 1:
            term = ["app", ["lam", ["binary", "multiply", ["bound", 0], ["nat", "2"]]], term]
        else:
            term = ["ifZero", term, ["nat", "9"], ["bound", 0]]
    return ["binary", "modulo", term, ["nat", "1000003"]]


def literal(d):
    """A Data JSON value as the literal term the evaluators read (a list as its cons chain)."""
    tag = d["tag"]
    if tag == "natural":
        return ["nat", d["value"]]
    if tag == "label":
        return ["label", d["value"]]
    if tag == "boolean":
        return ["boolean", d["value"]]
    if tag == "record":
        return ["record", [[f["name"], literal(f["value"])] for f in d["fields"]]]
    if tag == "variant":
        return ["inject", d["label"], literal(d["payload"])]
    items = ["inject", "nil", ["record", []]]
    for item in reversed(d["items"]):
        items = ["inject", "cons", ["record", [["head", literal(item)], ["tail", items]]]]
    return items


def stored_cases(rng, count=32):
    """A function of a state holding a relation `r` of rows {k, v, w}, reading none, some or all
    of its rows (KERNEL-HANDOFF section 15). The machine runs the function on the state with `r`
    held as stored cells fetched from the state's own rows (`evaluate-term` with `stored`); the
    evaluators run it applied to the state as a literal. Both must agree."""
    def row_data(i):
        return {"tag": "record", "fields": [
            {"name": "k", "value": {"tag": "natural", "value": str(i)}},
            {"name": "v", "value": {"tag": "label", "value": rng.choice(LABELS) + str(i)}},
            {"name": "w", "value": {"tag": "natural", "value": str(rng.choice(NATS[:8]))}}]}

    rows = ["case", ["get", ["bound", 0], "r"], [["rows", ["get", ["bound", 0], "items"]]]]

    def nth(lst, k, column):
        hit = ["get", ["get", ["bound", 0], "head"], column] if k == 0 else nth(["get", ["bound", 0], "tail"], k - 1, column)
        return ["case", lst, [["nil", ["label", "none"]], ["cons", hit]]]

    def fold(step):
        # fix (self, inherited, list): nil -> 0; cons c -> step(c, self(c.tail)); self is index 3
        recur = ["app", ["bound", 3], ["get", ["bound", 0], "tail"]]
        return ["fix", ["lam", ["lam", ["lam", ["case", ["bound", 0],
                [["nil", ["nat", "0"]], ["cons", step(recur)]]]]]], ["nat", "0"]]

    total = fold(lambda recur: ["binary", "add", ["get", ["get", ["bound", 0], "head"], "w"], recur])
    length = fold(lambda recur: ["binary", "add", ["nat", "1"], recur])
    cases = []
    for index in range(count):
        size = rng.randrange(0, 7)
        state = {"tag": "record", "fields": [
            {"name": "n", "value": {"tag": "natural", "value": str(rng.choice(NATS[:8]))}},
            {"name": "r", "value": {"tag": "variant", "label": "rows", "payload": {"tag": "record", "fields": [
                {"name": "items", "value": {"tag": "list", "items": [row_data(i) for i in range(size)]}}]}}}]}
        k = rng.randrange(0, 7)
        shape, responses = rng.randrange(6), []
        if shape == 0:
            body = ["get", ["bound", 0], "n"]
        elif shape == 1:
            body = nth(rows, k, rng.choice(["k", "v", "w"]))
        elif shape == 2:
            body = ["app", total, rows]
        elif shape == 3:
            body = ["app", length, rows]
        elif shape == 4:
            body = ["perform", nth(rows, k, "v")]
        else:
            body = ["record", [["first", nth(rows, k, "k")], ["n", ["get", ["bound", 0], "n"]]]]
        function = ["lam", body]
        cases.append({"name": f"stored-{index:02d}", "kind": "stored", "term": ["app", function, literal(state)],
                      "responses": responses, "fuel": 100000,
                      "stored": {"function": function, "state": state, "relations": [{"field": "r", "key": ["k"]}],
                                 "reads": [[], [k] if k < size else [], list(range(size)), [],
                                           [k] if k < size else [], []][shape]}})
    return cases


def relation_cases(rng, count=16):
    """`relationCount` and `relationLookup` over a state's relation `r` of rows {k, v} sorted by k
    (KERNEL-HANDOFF section 16 item 15): held stored and keyed {k}, the machine answers a count from
    the handle and binary-searches a lookup, fetching only the row it reads; the evaluators walk the
    literal. Small relations from their own stream, then three over 2,048 rows (keys 0, 2, ..., 4094):
    a count, a hit and a miss. Both must agree; `reads` are the rows the machine forces."""
    def state(keys):
        rows = [{"tag": "record", "fields": [{"name": "k", "value": {"tag": "natural", "value": str(k)}},
                                             {"name": "v", "value": {"tag": "label", "value": f"v{k}"}}]}
                for k in keys]
        return {"tag": "record", "fields": [
            {"name": "r", "value": {"tag": "variant", "label": "rows", "payload": {"tag": "record", "fields": [
                {"name": "items", "value": {"tag": "list", "items": rows}}]}}}]}

    relation = ["get", ["bound", 0], "r"]

    def probe(k):
        column = ["get", ["bound", 0], "k"]
        return ["lam", ["ifBool", ["binary", "less", column, ["nat", str(k)]], ["nat", "0"],
                        ["ifBool", ["binary", "equal", column, ["nat", str(k)]], ["nat", "1"], ["nat", "2"]]]]

    def read(k):
        # The found row's v, which forces (fetches) that one row; "none" on a miss.
        return ["case", ["relationLookup", relation, ["k"], probe(k)],
                [["some", ["get", ["get", ["bound", 0], "value"], "v"]], ["none", ["label", "none"]]]]

    def case(name, keys, body, reads):
        function = ["lam", body]
        st = state(keys)
        return {"name": name, "kind": "stored", "term": ["app", function, literal(st)], "responses": [],
                "fuel": 10000000, "stored": {"function": function, "state": st,
                                             "relations": [{"field": "r", "key": ["k"]}], "reads": reads}}

    cases = []
    for index in range(count):
        keys = sorted(rng.sample(range(12), rng.randrange(0, 7)))
        shape = rng.randrange(3)
        if shape == 0:
            cases.append(case(f"relation-{index:02d}", keys, ["relationCount", relation], []))
        else:
            k = rng.randrange(12)
            # shape 2 answers the Maybe unread: no row is forced, hit or miss.
            body = read(k) if shape == 1 else ["relationLookup", relation, ["k"], probe(k)]
            cases.append(case(f"relation-{index:02d}", keys, body,
                              [keys.index(k)] if shape == 1 and k in keys else []))
    big = list(range(0, 4096, 2))
    cases.append(case("relation-2048-count", big, ["relationCount", relation], []))
    cases.append(case("relation-2048-hit", big, read(6), [3]))
    cases.append(case("relation-2048-miss", big, read(7), []))
    return cases


def refusal_cases():
    """`refuse` with its reason a term (KERNEL-HANDOFF section 26): a literal, a reason computed
    from literals, one computed from a bound value, one read from a stored row (the card's state, held
    stored by the machine), one past a yield, and a reason that is no String or never ends."""
    owner = ["binary", "textConcat", ["label", "refused owner: only "], ["get", ["bound", 0], "owner"]]
    state = {"tag": "record", "fields": [
        {"name": "owner", "value": {"tag": "label", "value": "Kestrel"}},
        {"name": "r", "value": {"tag": "variant", "label": "rows", "payload": {"tag": "record", "fields": [
            {"name": "items", "value": {"tag": "list", "items": [
                {"tag": "record", "fields": [{"name": "k", "value": {"tag": "natural", "value": str(k)}},
                                             {"name": "v", "value": {"tag": "label", "value": f"v{k}"}}]}
                for k in range(3)]}}]}}}]}
    row = ["case", ["case", ["get", ["bound", 0], "r"], [["rows", ["get", ["bound", 0], "items"]]]],
           [["nil", ["label", "none"]], ["cons", ["get", ["get", ["bound", 0], "head"], "v"]]]]
    from_row = ["lam", ["refuse", ["binary", "textConcat", ["label", "refused kept: "], row]]]
    cases = [
        ("refuse-literal", ["refuse", ["label", "refused card: no"]], []),
        ("refuse-computed", ["refuse", ["binary", "textConcat", ["label", "refused late: "],
                                        ["unary", "natText", ["binary", "add", ["nat", "40"], ["nat", "2"]]]]], []),
        ("refuse-bound", ["app", ["lam", ["refuse", owner]], literal(state)], []),
        ("refuse-yielded", ["refuse", ["case", ["perform", ["record", [["method", ["label", "view"]]]]],
                                       [["viewed", ["bound", 0]]]]], [["inject", "viewed", ["label", "a reading"]]]),
        ("refuse-natural", ["refuse", ["nat", "7"]], []),
        ("refuse-diverge", ["refuse", diverge(None)], []),
    ]
    out = [{"name": name, "kind": "refuse", "term": term, "responses": responses, "fuel": 100000}
           for name, term, responses in cases]
    out.append({"name": "refuse-stored", "kind": "stored", "term": ["app", from_row, literal(state)], "responses": [],
                "fuel": 100000, "stored": {"function": from_row, "state": state,
                                           "relations": [{"field": "r", "key": ["k"]}], "reads": [0]}})
    return out


def generate(count, seed=1025):
    rng = random.Random(seed)
    g = Gen(rng)
    cases = []
    budgets = [4, 8, 16, 40, 100, 250, 500, 1000]
    for index in range(count):
        roll = rng.random()
        responses, kind = [], "term"
        if roll < 0.50:
            sort = rng.choice(["nat", "nat", "bool", "label", "rec", "sum", "fn"])
            term = sized(g, sort, rng.choice(budgets))
        elif roll < 0.63:
            term, responses = activity(g, rng, rng.randint(1, 3), rng.randint(0, 3))
            kind = "activity"
        elif roll < 0.77:
            term, kind = stuck(g, rng), "stuck"
        elif roll < 0.79:
            term, kind = diverge(rng), "diverge"
        elif roll < 0.83:
            term, responses = shared_effect(g, rng)
            kind = "shared-effect"
        elif roll < 0.89:
            term, kind = values_of_every_kind(g, rng), "exotic-value"
        else:
            term, kind = chain(g, rng), "chain"
        cases.append({"name": f"case-{index:04d}", "kind": kind, "term": term, "responses": responses,
                      "fuel": 100000})
    # textHasAny at size, after the seeded stream (no generated case moves): 2,000 words each
    # side, which a list search does as four million comparisons; no hit, a hit at the end,
    # and a hit only after ASCII case-folding beside non-ASCII words.
    many = " ".join(["a"] * 2000)
    for name, text, words in (("has-any-miss", many, " ".join(["b"] * 2000)),
                              ("has-any-last", many + " Zeta", " ".join(["b"] * 1999 + ["zeta"])),
                              ("has-any-fold", ", ".join(["Café", "ÉTÉ"] * 1000) + " WORD!", " ".join(["été"] * 1999 + ["word"]))):
        cases.append({"name": name, "kind": "term", "term": ["binary", "textHasAny", ["label", text], ["label", words]],
                      "responses": [], "fuel": 100000})
    # Stored state, after the seeded stream from a stream of its own (no generated case moves).
    cases.extend(stored_cases(random.Random(seed + 15)))
    cases.extend(relation_cases(random.Random(seed + 16)))
    cases.extend(refusal_cases())
    return cases


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1025
    for case in generate(n, seed):
        print(json.dumps(case))
