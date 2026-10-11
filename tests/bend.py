"""The world's Bend sources as the packages the host takes: a module and its imports, a package's
declared methods. Every module under world/lib, world/objects, tests/fixtures/objects and
examples/automatafl, by name (module names are flat)."""
import os
import re

from tests.host import ROOT

WORLD = os.path.join(ROOT, "world")
IMPORT = re.compile(r"^import \./(\w+)\.obend", re.M)
METHOD = re.compile(r"^def (\w+)\(state: ", re.M)


def modules_on_disk():
    found = {}
    for root in (os.path.join(WORLD, "lib"), os.path.join(WORLD, "objects"), os.path.join(ROOT, "tests", "fixtures", "objects"),
                 os.path.join(ROOT, "examples", "automatafl")):
        for directory, _, files in os.walk(root):
            for name in files:
                if name.endswith(".obend"):
                    assert name not in found, "module names are flat: " + name
                    found[name[:-6]] = os.path.join(directory, name)
    return found


MODULES = modules_on_disk()


def closure(*names, override=None):
    """The named modules and their imports in dependency order (imports first), each once;
    `override` maps a module name to the source that replaces its file."""
    seen, out = set(), []

    def visit(name):
        if name in seen:
            return
        seen.add(name)
        if override and name in override:
            source = override[name]
        else:
            with open(MODULES[name]) as handle:
                source = handle.read()
        for dep in IMPORT.findall(source):
            visit(dep)
        out.append({"name": name, "source": source})
    for name in names:
        visit(name)
    return out


def counter_modules():
    return closure("Counter")


def pure(modules):
    """The modules without their law lines: the stateless compile is the pure profile, which
    refuses package laws ("package laws require a host law adapter"); the host keeps them."""
    return [dict(m, source="".join(l for l in m["source"].splitlines(True) if not l.startswith("law ")))
            for m in modules]


def declared(source, *names):
    """`source` with a `def methods()` naming `names`, or every definition whose first parameter is
    the State: the host runs only the methods a package declares."""
    names = names or tuple(n for n in METHOD.findall(source) if n not in ("receive", "render", "set", "law"))
    if not names or "\ndef methods(" in source:
        return source
    if "List.obend as Lists" not in source:
        first, rest = source.split("\n", 1)
        source = first + "\nimport ./List.obend as Lists\n" + rest
    body = "Lists.List::<String>.nil({})"
    for n in reversed(names):
        body = 'Lists.List::<String>.cons({head: "%s", tail: %s})' % (n, body)
    return source.rstrip("\n") + "\ndef methods() -> Lists.List<String>:\n  " + body + "\n"
