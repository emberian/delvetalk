"""A derived `forms()` is a pure lowering: every entry of the objects whose `forms()` is derived
compiles to the packet (without `sourceModules`) of the same object with `forms()` written, as the
kernel derives it, at the end of its module (KERNEL-HANDOFF §23: derived declarations end the
module as `forms()`, then `Edits` and `keep()`, then the form inputs).

Evidence for KERNEL-HANDOFF §16 item 8c (layer: kernel).

    DELVETALK_OBEND=... python3 -m unittest tests.test_derived_forms -v
"""
import re
import unittest

from tests import host
from tests.test_artifact_pins import entries
from tests.test_objects import closure, pure
from tests.test_sugar import core

# The objects whose packets differed when the derived declarations ended the module in another order.
OBJECTS = ("Deal", "Env", "Garden", "Policy", "Scene", "Workshop")


def written(source):
    """The module with `forms()` spelled at its end as the kernel derives it."""
    alias = lambda f: re.search(r"^import \./%s\.obend as (\w+)$" % f, source, re.M).group(1)
    lists, form = alias("List"), alias("Form")
    body = lists + ".List.nil({})"
    for m in reversed(list(re.finditer(r"^form (\w+)(?: as (\w+))?:$", source, re.M))):
        body = "%s.List.cons({head: %s(), tail: %s})" % (lists, m.group(2) or m.group(1) + "Form", body)
    return source.rstrip("\n") + "\ndef forms() -> %s.List<%s.Form>:\n  %s\n" % (lists, form, body)


class DerivedForms(unittest.TestCase):
    def test_every_entry_is_the_packet_of_forms_written_at_the_end(self):
        process = host.Host()
        self.addCleanup(process.close)
        for name in OBJECTS:
            modules = pure(closure(name))
            self.assertIsNone(re.search(r"^def forms\(", modules[-1]["source"], re.M), name)
            hand = [dict(m) for m in modules]
            hand[-1]["source"] = written(hand[-1]["source"])
            for entry in entries(name):
                with self.subTest(module=name, entry=entry):
                    a = process.send(op="compile", modules=modules, entry=entry)
                    b = process.send(op="compile", modules=hand, entry=entry)
                    self.assertEqual(a["status"], b["status"], (a, b))
                    if a["status"] == "compiled":
                        self.assertEqual(core(a["artifact"]), core(b["artifact"]), f"{name}.{entry}")


if __name__ == "__main__":
    unittest.main()
