"""Closed core terms in the evaluators' JSON array wire, for conformance.

Wire (shared by impl/c, impl/js, impl/python and the `evaluate-term` op):
  ["bound", i] ["nat", "123"] ["boolean", true] ["label", "s"] ["lam", b]
  ["app", f, a] ["mix", l, u] ["fix", s, i] ["specification", m, e]
  ["prototype", s, t] ["reflect"|"metadata"|"project"|"perform"|"done"|"toData", x]
  ["unary", prim, x] ["binary", prim, l, r] ["get", x, "name"]
  ["inject", "label", x] ["ifZero", v, z, s] ["ifBool", c, t, f]
  ["record", [[name, term], ...]] ["extend", x, fields] ["case", x, arms]
A job is {"name", "term", "responses", "fuel"}; generated cases also carry a "kind"
(term, activity, stuck, diverge, shared-effect, exotic-value, chain) which the runner strips.

Terms are built by kind (nat, bool, label, record, sum, function) so most
evaluate; a share is deliberately ill-kinded (stuck), diverging, or performs.
Run `python3 -m tests.conformance.generate N [SEED]` for JSON lines.
"""
import json
import random
import sys

TAGS = ["bound", "lam", "app", "mix", "fix", "specification", "prototype", "reflect", "metadata",
        "project", "nat", "boolean", "label", "unary", "binary", "extend", "record", "get", "ifZero",
        "inject", "case", "ifBool", "perform", "done", "toData"]
BINARY = ["add", "multiply", "equal", "conjunction", "labelEqual", "subtract", "divide", "less",
          "lessEqual", "modulo", "textConcat", "textTake", "textDrop", "textSpan", "textBreak"]
UNARY = ["natText", "textLength", "sha256Text"]
STRINGS = ["", "a", "abc", "hello world", "line\nbreak", "\n", "é", "日本語", "😀x", "tab\t", "a b c",
           'q"uote', "back\\slash", "x" * 40]
ALPHABETS = ["", "a", "abc", " ", "\n", "é日", "😀", "xyz"]
NATS = [0, 1, 2, 3, 5, 7, 10, 255, 4096, 10 ** 20, 2 ** 64]
LABELS = ["ok", "refused", "left", "right", "none"]
FIELDS = ["a", "b", "c"]


def size(term):
    if not isinstance(term, list) or not term or not isinstance(term[0], str):
        return 0
    total = 1
    for child in term[1:]:
        if isinstance(child, list) and child and isinstance(child[0], str) and child[0] in TAGS:
            total += size(child)
        elif isinstance(child, list):
            for field in child:
                if isinstance(field, list) and len(field) == 2:
                    total += size(field[1])
    return total


def tags(term, out=None):
    out = set() if out is None else out
    if isinstance(term, list) and term and isinstance(term[0], str) and term[0] in TAGS:
        out.add(term[0])
        if term[0] in ("binary", "unary"):
            out.add(term[0] + ":" + term[1])
        for child in term[1:]:
            tags(child, out)
    elif isinstance(term, list):
        for field in term:
            if isinstance(field, list) and len(field) == 2:
                tags(field[1], out)
    return out


class Gen:
    def __init__(self, rng):
        self.r = rng

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
            return ["ifBool", self.g_bool(env, h // 2), self.g_nat(env, h // 2), self.g_nat(env, h // 2)]
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
            return ["binary", "labelEqual", self.g_label(env, h), self.g_label(env, h)]
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
        c = r.randrange(8)
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
        return ["label", r.choice(STRINGS)]

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
    return cases


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1025
    for case in generate(n, seed):
        print(json.dumps(case))
