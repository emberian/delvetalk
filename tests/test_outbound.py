"""The host-owned outbound channel: what the world says to whom, retained and readable under
the reader's authority, and the posts transport made for objects, so replies find their way back.

Each case is named by the defect that would make it fail.
"""
import json
import unittest

from tests.test_chain import field
from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.test_turn_world import label, nat, record

URI = "at://did:plc:world/town.delve.feed.post/3abc"
SLOT = {"principal": "did:plc:kim", "intent": "strike-1"}


class Posts(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("bell", PACKAGE, source_seed())

    def posted(self, uri=URI, principal="transport", **extra):
        return self.host.send(op="world-posted", principal=principal, uri=uri, cid="bafyreiabc", object="bell", **extra)

    def test_a_reply_to_a_recorded_post_finds_its_object_and_slot_and_a_stranger_post_is_unknown(self):
        r = self.posted(slot=SLOT)
        self.assertEqual(r["status"], "posted", r)
        self.assertEqual(r["height"], self.host.send(op="world-status")["height"])
        found = self.host.send(op="world-addressee", parent=URI)
        self.assertEqual(found, {"status": "addressee", "object": "bell", "slot": SLOT})
        plain = self.posted(uri=URI + "x")
        self.assertEqual(self.host.send(op="world-addressee", parent=URI + "x"), {"status": "addressee", "object": "bell"})
        self.assertEqual(plain["status"], "posted")
        self.assertEqual(self.host.send(op="world-addressee", parent="at://nobody/p/1"), {"status": "unknown"})

    def test_the_index_is_rebuilt_by_replay(self):
        self.posted(slot=SLOT)
        self.reopen()
        self.assertEqual(self.host.send(op="world-addressee", parent=URI)["slot"], SLOT)

    def test_a_retried_confirmation_is_the_same_entry_and_another_cid_is_refused(self):
        first = self.posted()
        again = self.posted()
        self.assertEqual(again["height"], first["height"])
        other = self.host.send(op="world-posted", principal="transport", uri=URI, cid="bafyreiother", object="bell")
        self.assertEqual(other.get("class"), "duplicateIdentity", other)

    def test_a_post_for_an_unknown_object_or_a_non_at_uri_is_a_request_error(self):
        self.assertEqual(self.host.send(op="world-posted", principal="transport", uri=URI, cid="c", object="ghost")["status"], "error")
        self.assertEqual(self.posted(uri="https://example.com")["status"], "error")


CARDED = PACKAGE.replace("import ./Plan.obend as Plans", "import ./Plan.obend as Plans\nimport ./Document.obend as Document") + """def render(state: State) -> Document.Document:
  Document.text(textConcat("Count: ", natText(state.count)))
"""

DIRECTORY = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Document.obend as Document
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def joined(ids: Lists.List<String>, tail: String) -> String:
  match ids:
    case nil(_): tail
    case cons(c): textConcat(textConcat(c.head, ","), joined(c.tail, tail))
def listing(state: State, input: {prefix: String, after: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.objects({prefix: input.prefix, after: input.after})):
    case listed(l): said(context, joined(l.ids, if l.more then "+" else "."))
    case _: said(context, "other")
def show(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.card({object: {world: "", object: input.target}})):
    case carded(c): said(context, Document.plain(c.document))
    case denied(_): said(context, "denied")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
"""


class Catalogue(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("directory", DIRECTORY, record(note=label("")))
        for name in ("bell-b", "bell-a", "lamp"):
            self.make(name, CARDED, source_seed())
        self.make("bell-secret", CARDED, source_seed(), read={"principals": ["ember"]})


class Listing(Catalogue):
    def listing(self, prefix="", after="", principal="kim"):
        r = self.turn("directory", "listing", record(prefix=label(prefix), after=label(after)), principal=principal)
        self.assertEqual(r["status"], "admitted", r)
        return r["result"]["value"]

    def test_a_listing_names_only_what_the_reader_may_view_in_byte_order(self):
        self.assertEqual(self.listing("bell"), "bell-a,bell-b,.")
        self.assertEqual(self.listing("bell", principal="ember"), "bell-a,bell-b,bell-secret,.")
        self.assertEqual(self.listing("bell", after="bell-a"), "bell-b,.")
        self.assertEqual(self.listing(), "bell-a,bell-b,directory,lamp,.")

    def test_the_op_pages_by_64_and_says_more(self):
        for i in range(66):
            self.host.send(op="world-create", principal="ember", identity=f"mk-n{i}", object=f"n{i:03}",
                           source=CARDED, entry="initial", seed=source_seed())
        page = self.host.send(op="world-objects", principal="kim", prefix="n")
        self.assertEqual((len(page["ids"]), page["more"], page["ids"][0]), (64, True, "n000"))
        rest = self.host.send(op="world-objects", principal="kim", prefix="n", after=page["ids"][-1])
        self.assertEqual((rest["ids"], rest["more"]), (["n064", "n065"], False))
        self.assertEqual(self.host.send(op="world-objects", principal="kim", prefix=7)["status"], "error")


class Cards(Catalogue):
    def show(self, target, principal="kim"):
        r = self.turn("directory", "show", record(target=label(target)), principal=principal)
        self.assertEqual(r["status"], "admitted", r)
        return r["result"]["value"]

    def test_an_object_shows_another_of_a_different_state_type_by_its_card(self):
        self.assertEqual(self.show("bell-a"), "Count: 0")

    def test_a_card_is_denied_where_the_state_would_be_and_absent_render_is_noCard(self):
        self.assertEqual(self.show("bell-secret"), "denied")
        self.assertEqual(self.show("bell-secret", principal="ember"), "Count: 0")
        self.assertEqual(self.show("ghost"), "denied")
        self.make("bare", PACKAGE, source_seed())
        self.assertEqual(self.show("bare"), "noCard")

    def test_the_card_op_returns_text_and_document_under_the_readers_authority(self):
        height = self.host.send(op="world-status")["height"]
        r = self.host.send(op="world-card", principal="kim", object="bell-a")
        self.assertEqual((r["status"], r["text"]), ("card", "Count: 0"), r)
        self.assertEqual(r["document"]["tag"], "variant")
        self.assertEqual(self.host.send(op="world-card", principal="kim", object="bell-secret")["status"], "denied")
        self.assertEqual(self.host.send(op="world-card", principal="kim", object="ghost")["status"], "unknown")
        self.assertEqual(self.host.send(op="world-status")["height"], height)


WAITER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def wait(state: State, input: {until: Nat}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.awaitUntil({slot: {principal: "nobody", intent: "never"}, until: input.until})):
    case timedOut(_): said(context, "timedOut")
    case _: said(context, "other")
"""


class Time(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("waiter", WAITER, record(note=label("")))

    def test_await_until_is_an_absolute_clock_height_not_a_patience(self):
        self.host.send(op="world-advance", height=5)
        r = self.turn("waiter", "wait", record(until=nat(7)))
        self.assertEqual(r["status"], "suspended", r)
        self.assertEqual(r["deadline"], 7)
        self.assertNotIn("resumed", self.host.send(op="world-advance", height=7))
        [resumed] = self.host.send(op="world-advance", height=8)["resumed"]
        self.assertEqual(resumed["result"], label("timedOut"))

    def test_an_until_already_past_answers_timedOut_without_suspending(self):
        self.host.send(op="world-advance", height=5)
        r = self.turn("waiter", "wait", record(until=nat(3)))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("timedOut")), r)


TELLER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Document.obend as Document
record Said:
  text: String
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits, Said>
type Response = Plans.Response<State, String>
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def offered(to: String, text: String, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.offer({to: to, document: Document.text(text)})):
    case _: said(context, "told")
def tell(state: State, input: {to: String, text: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  offered(input.to, input.text, context)
def echo(state: State, input: Said, context: Abi.Context) -> Activity<Plan, Response, String>:
  offered("", input.text, context)
def relay(state: State, input: {target: String, text: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.send({object: {world: "", object: input.target}, method: "echo", argument: {text: input.text}})):
    case _: said(context, "sent")
def waitAndTell(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.await({slot: {principal: "glm", intent: "x"}, patience: 10n})):
    case _: offered("", "woken", context)
def stamp(state: State, input: Said, context: Abi.Context) -> Activity<Plan, Response, String>:
  said(context, input.text)
def pokeOther(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: "secret-xyz"})}})):
    case _: poked(input.target)
def poked(target: String) -> Activity<Plan, Response, String>:
  match perform(Plan.call({object: {world: "", object: target}, method: "stamp", argument: {text: "stamped"}})):
    case returned(r): r.result
    case _: "other"
"""


class Offers(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("teller", TELLER, record(note=label("")))

    def offers(self, principal, after=None):
        request = dict(op="world-offers", principal=principal)
        if after is not None:
            request["after"] = after
        r = self.host.send(**request)
        self.assertEqual(r["status"], "offers", r)
        return [o["text"] for o in r["offers"]]

    def test_an_offer_to_b_in_a_turn_run_by_a_is_readable_by_b_and_not_by_c(self):
        r = self.turn("teller", "tell", record(to=label("bea"), text=label("for bea")), principal="ann", identity="t-1")
        self.assertEqual(r["status"], "admitted", r)
        self.assertNotIn("offers", r)                    # not addressed to ann
        self.assertEqual(r["receipt"]["offers"], [{"to": "bea", "text": "for bea"}])
        self.assertEqual(self.offers("bea"), ["for bea"])
        self.assertEqual(self.offers("cid"), [])
        self.assertEqual(self.offers("ann"), [])

    def test_a_retry_returns_the_same_offer_and_retains_it_once(self):
        first = self.turn("teller", "tell", record(to=label(""), text=label("hello")), principal="ann", identity="t-1")
        again = self.turn("teller", "tell", record(to=label(""), text=label("hello")), principal="ann", identity="t-1")
        self.assertEqual(first["offers"], [{"principal": "ann", "text": "hello"}])
        self.assertEqual((again["offers"], again["receipt"]), (first["offers"], first["receipt"]))
        self.assertEqual(self.offers("ann"), ["hello"])
        self.reopen()
        self.assertEqual(self.offers("ann"), ["hello"])
        height = first["receipt"]["height"]
        self.assertEqual(self.offers("ann", after=height), [])
        self.assertEqual(self.host.send(op="world-offers", principal="ann", after="soon")["status"], "error")

    def test_a_delivered_offer_goes_to_its_addressee_not_into_the_reply_that_ran_it(self):
        self.make("echo", TELLER, record(note=label("")))
        r = self.turn("teller", "relay", record(target=label("echo"), text=label("echoed")), principal="ann")
        [delivered] = r["delivered"]
        self.assertEqual(delivered["status"], "admitted", delivered)
        self.assertNotIn("offers", delivered)
        self.assertEqual(self.offers("ann"), ["echoed"])

    def test_a_resumed_turns_offer_goes_to_its_principal_not_to_whoever_settled_the_slot(self):
        waiting = self.turn("teller", "waitAndTell", principal="kim")
        self.assertEqual(waiting["status"], "suspended", waiting)
        self.make("other", TELLER, record(note=label("")))
        settler = self.turn("other", "tell", record(to=label("nobody"), text=label("x")), principal="glm", identity="x")
        [resumed] = settler["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertNotIn("offers", settler)
        self.assertNotIn("offers", resumed)
        self.assertEqual(self.offers("kim"), ["woken"])
        self.assertEqual(self.offers("glm"), [])


class Projection(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("vault", TELLER, record(note=label("")), read={"principals": ["ann"]})
        self.make("lamp", TELLER, record(note=label("")))

    def test_a_stranger_reading_a_receipt_sees_the_projection_and_nothing_of_the_state(self):
        r = self.turn("vault", "pokeOther", record(target=label("lamp")), principal="ann", identity="poke")
        self.assertEqual(r["status"], "admitted", r)
        mine = self.host.send(op="world-receipt", principal="ann", identity="poke")
        self.assertEqual(mine["receipt"], r["receipt"])
        theirs = self.host.send(op="world-receipt", principal="cid", identity="poke", of="ann")
        self.assertEqual(theirs["status"], "receipt", theirs)
        shown = theirs["receipt"]
        self.assertEqual([w["object"] for w in shown["outcome"]["writes"]], ["lamp"])
        self.assertEqual(shown["elided"], 2)            # the vault's root and its write
        self.assertNotIn("result", shown)
        self.assertNotIn("secret-xyz", json.dumps(theirs))
        self.assertEqual(shown["hash"], r["receipt"]["hash"])

    def test_a_refusal_shows_a_stranger_its_class_and_root_and_nothing_else(self):
        stale = self.host.send(op="world-propose", principal="ann", identity="stale",
                               roots=[{"object": "vault", "version": 7}], writes=[])
        self.assertEqual(stale["status"], "refused", stale)
        theirs = self.host.send(op="world-receipt", principal="cid", identity="stale", of="ann")
        self.assertEqual(theirs, {"status": "refused", "class": "staleRoot", "root": "vault"})

    def test_history_is_denied_for_an_object_the_reader_cannot_view_and_elides_the_rest(self):
        self.turn("vault", "pokeOther", record(target=label("lamp")), principal="ann", identity="poke")
        self.assertEqual(self.host.send(op="world-history", principal="cid", object="vault")["status"], "denied")
        history = self.host.send(op="world-history", principal="cid", object="lamp")
        last = history["entries"][-1]
        self.assertEqual((last["identity"]["principal"], last["elided"]), ("ann", 2))
        self.assertNotIn("secret-xyz", json.dumps(history))
        full = self.host.send(op="world-history", principal="ann", object="vault")
        self.assertIn("secret-xyz", json.dumps(full))
        self.assertEqual(self.host.send(op="world-history", object="lamp")["status"], "error")


class Settings(Reflection):
    def test_a_named_clock_alone_moves_the_clock_and_confirms_posts(self):
        r = self.host.send(op="world-open", path=self.path, library=self.library(), principal="ember", clock="transport")
        self.assertEqual(r["status"], "opened", r)
        self.make("bell", PACKAGE, source_seed())
        self.assertEqual(self.host.send(op="world-advance", height=3)["status"], "error")
        self.assertEqual(self.host.send(op="world-advance", height=3, principal="mallory")["status"], "error")
        self.assertEqual(self.host.send(op="world-advance", height=3, principal="transport")["status"], "advanced")
        mallory = self.host.send(op="world-posted", principal="mallory", uri=URI, cid="c", object="bell")
        self.assertEqual(mallory["status"], "error")
        self.reopen()
        self.assertEqual(self.host.send(op="world-advance", height=4)["status"], "error")
        self.assertEqual(self.host.send(op="world-status")["clock"], 3)

    def test_post_quota_defaults_to_16_is_set_at_open_and_fixed_after(self):
        self.assertEqual(self.host.send(op="world-status")["postQuota"], 16)
        self.host.send(op="world-open", path=self.path, postQuota=4)
        self.assertEqual(self.host.send(op="world-status")["postQuota"], 4)
        self.reopen()
        self.assertEqual(self.host.send(op="world-status")["postQuota"], 4)
        differ = self.host.send(op="world-open", path=self.path, postQuota=5)
        self.assertEqual(differ["status"], "error")
        self.assertIn("settings differ", differ["message"])

    def library(self):
        from tests.test_reflection import LIBRARY
        return LIBRARY


if __name__ == "__main__":
    unittest.main()
