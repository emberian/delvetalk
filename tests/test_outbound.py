"""The host-owned outbound channel: what the world says to whom, retained and readable under
the reader's authority, and the posts transport made for objects, so replies find their way back.

Each case is named by the defect that would make it fail.
"""
import json
import os
import shutil
import tempfile
import unittest

from tests.test_chain import field
from tests.test_reflection import LIBRARY, PACKAGE, Reflection, source_seed
from tests.test_turn_world import label, nat, record
from tests.wire import cid_of

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

# A card with a point of view: `render(state, context)`, the name objects use once `renderFor` is renamed.
VIEWED = CARDED.replace("def render(state: State) -> Document.Document:\n  Document.text(textConcat(\"Count: \", natText(state.count)))\n", "") + """def render(state: State, context: Abi.Context) -> Document.Document:
  Document.text(textConcat("for ", textConcat(context.principal, textConcat(" by ", textConcat(context.caller, textConcat(" of ", textConcat(context.object, textConcat(" intent ", textConcat(context.intent, textConcat(" from ", context.inputOrigin.kind))))))))))
"""
# Both names, as objects have them until the rename: `renderFor` is the one the host runs.
BOTH = CARDED + """def renderFor(state: State, context: Abi.Context) -> Document.Document:
  Document.text(textConcat("Count for ", textConcat(context.principal, textConcat(": ", natText(state.count)))))
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
type Plan = Plans.Plan<Edits>
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

    def test_a_card_is_rendered_for_its_reader_through_either_name(self):
        self.make("viewed", VIEWED, source_seed())
        self.make("both", BOTH, source_seed())
        self.assertEqual(self.show("viewed"), "for kim by directory of viewed intent t1 from card")
        self.assertEqual(self.host.send(op="world-card", principal="kim", object="viewed")["text"],
                         "for kim by  of viewed intent  from card")
        self.assertEqual(self.show("both", principal="ember"), "Count for ember: 0")
        self.assertEqual(self.host.send(op="world-card", principal="kim", object="both")["text"], "Count for kim: 0")


WAITER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
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
type Plan = Plans.Plan<Edits>
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
  match perform(Plan.send({object: {world: "", object: input.target}, method: "echo", argument: Data.of::<Said>({text: input.text})})):
    case _: said(context, "sent")
def waitAndTell(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.await({slot: {principal: "glm", intent: "x"}, patience: 10n})):
    case _: offered("", "woken", context)
def page(state: State, input: {section: String, body: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.publish({page: "", section: input.section, body: input.body})):
    case published(p): said(context, p.post)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def stamp(state: State, input: Said, context: Abi.Context) -> Activity<Plan, Response, String>:
  said(context, input.text)
def pokeOther(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: "secret-xyz"})}})):
    case _: poked(input.target)
def poked(target: String) -> Activity<Plan, Response, String>:
  match perform(Plan.call({object: {world: "", object: target}, method: "stamp", argument: Data.of::<Said>({text: "stamped"})})):
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

    def test_a_turn_that_offers_nothing_carries_no_offers_and_journals_like_any_other(self):
        """Rehearsal finding 3: prose addressed to no card gets nothing back. A turn that performs
        no `offer` answers without an `offers` field (not an empty one), its entry retains none,
        and it is journaled, retried and replayed as any admitted turn, so transport drafts
        exactly when `offers` is present."""
        height = self.host.send(op="world-status")["height"]
        quiet = self.turn("teller", "stamp", record(text=label("noted")), principal="ann", identity="quiet")
        self.assertEqual(quiet["status"], "admitted", quiet)
        self.assertNotIn("offers", quiet)
        self.assertNotIn("offers", quiet["receipt"])
        self.assertEqual(quiet["receipt"]["height"], height + 1)
        self.assertEqual(self.host.send(op="world-status")["height"], height + 1)
        self.assertEqual(field(self.host.send(op="world-view", principal="ann", object="teller")["state"], "note"),
                         label("noted"))
        self.assertEqual(self.offers("ann"), [])
        again = self.turn("teller", "stamp", record(text=label("noted")), principal="ann", identity="quiet")
        self.assertEqual(again, quiet)
        self.reopen()
        self.assertEqual(self.host.send(op="world-receipt", principal="ann", identity="quiet")["receipt"], quiet["receipt"])
        self.assertEqual(self.offers("ann"), [])

class Publish(Reflection):
    """publish is retained like an addressed offer, for transport to post as the object's page."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("teller", TELLER, record(note=label("")))

    def publish(self, section="Notes", body="the bell rang", identity="pub"):
        r = self.turn("teller", "page", record(section=label(section), body=label(body)), principal="ann", identity=identity)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def publications(self, principal="transport"):
        return self.host.send(op="world-offers", principal=principal).get("publications")

    def test_a_publication_is_retained_and_listed_for_the_transport_as_the_objects_page(self):
        r = self.publish()
        post = r["result"]["value"]
        [p] = self.publications()
        self.assertEqual((p["id"], p["object"], p["page"], p["section"]), (post, "teller", "teller", "Notes"))
        self.assertEqual(p["text"], "edit: teller › Notes\n\nthe bell rang")
        self.assertIsNone(self.publications("ann"))
        whole = self.publish(section="", body="all of it", identity="pub-2")
        self.assertEqual(self.publications()[1]["text"], "wiki: teller\n\nall of it")
        self.reopen()
        self.assertEqual(len(self.publications()), 2)
        self.assertEqual(self.publish()["receipt"], r["receipt"])          # a retry publishes nothing twice
        self.assertEqual(len(self.publications()), 2)

    def test_a_reply_to_the_confirmed_post_finds_the_object(self):
        self.publish()
        posted = self.host.send(op="world-posted", principal="transport", uri=URI, cid="bafyreipage", object="teller")
        self.assertEqual(posted["status"], "posted", posted)
        self.assertEqual(self.host.send(op="world-addressee", parent=URI)["object"], "teller")

    def test_world_publications_lists_bodies_and_a_section_edit_replies_to_its_pages_newest_post(self):
        edit = self.publish()
        listing = lambda **kw: self.host.send(op="world-publications", principal="transport", **kw)
        [p] = listing()["publications"]
        self.assertEqual({k: p[k] for k in ("height", "id", "object", "page", "section", "body")},
                         {"height": edit["receipt"]["height"], "id": edit["result"]["value"], "object": "teller",
                          "page": "teller", "section": "Notes", "body": "the bell rang"})
        self.assertNotIn("replyTo", p)                                    # no page post is recorded yet
        self.assertEqual(self.host.send(op="world-publications", principal="ann")["status"], "denied")
        self.publish(section="", body="all of it\n\nin two paragraphs", identity="pub-2")
        whole = listing()["publications"][1]
        self.assertEqual((whole["section"], whole["body"]), ("", "all of it\n\nin two paragraphs"))
        self.assertNotIn("replyTo", whole)
        self.assertEqual(listing(after=whole["height"])["publications"], [])
        for i, uri in enumerate((URI, URI + "-checkpoint")):
            r = self.host.send(op="world-posted", principal="transport", uri=uri, cid=f"c{i}", object="teller", page="teller", section="")
            self.assertEqual(r["status"], "posted", r)
            self.assertEqual(listing()["publications"][0]["replyTo"], uri)  # the newest post of the page
        self.assertEqual(self.host.send(op="world-addressee", parent=URI),
                         {"status": "addressee", "object": "teller", "page": "teller", "section": ""})
        self.reopen()
        self.assertEqual(listing()["publications"][0]["replyTo"], URI + "-checkpoint")
        bad = self.host.send(op="world-posted", principal="transport", uri=URI + "-2", cid="c", object="teller", section="Notes")
        self.assertEqual(bad["status"], "error", bad)

    def test_a_title_with_a_line_break_is_refused(self):
        r = self.publish(section="a\nb")
        self.assertEqual(r["result"], label("title"))
        self.assertEqual(self.publications(), [])


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
        self.assertEqual(theirs, {"status": "refused", "class": "staleRoot", "root": {"object": "vault", "version": 7}})

    def test_roots_cite_versions_and_the_state_cid_is_read_from_the_write_that_made_it(self):
        """A card address is a versioned capability: a receipt's roots, and a public refusal's root,
        name the version a turn was judged against; the state at that version is named once, by the
        entry that wrote it (`writes[].cid`), and read with world-state-cid by a reader who may view it."""
        state = lambda name: self.host.send(op="world-view", principal="ann", object=name)["state"]
        cid_at = lambda who, name, v: self.host.send(op="world-state-cid", principal=who, object=name, version=v)
        before = {name: cid_of(state(name)) for name in ("vault", "lamp")}
        r = self.turn("vault", "pokeOther", record(target=label("lamp")), principal="ann", identity="poke")
        self.assertEqual(r["receipt"]["roots"], [{"object": "vault", "version": 0}, {"object": "lamp", "version": 0}])
        writes = {w["object"]: w for w in r["receipt"]["outcome"]["writes"]}
        self.assertEqual(writes["lamp"]["cid"], cid_of(state("lamp")))
        for name in ("lamp", "vault"):
            self.assertEqual(cid_at("ann", name, 0)["cid"], before[name])
        bad = self.turn("lamp", "stamp", record(wrong=label("x")), principal="ann", identity="bad-lamp")
        self.assertEqual(bad["receipt"]["roots"], [{"object": "lamp", "version": 1}])
        lamp = self.host.send(op="world-receipt", principal="bob", identity="bad-lamp", of="ann")
        self.assertEqual(lamp["root"], {"object": "lamp", "version": 1})
        self.assertEqual(cid_at("bob", "lamp", 1), {"status": "stateCid", "object": "lamp", "version": 1, "cid": cid_of(state("lamp"))})
        self.assertEqual(cid_at("bob", "vault", 0)["status"], "denied")
        # An entry from before carrying a root `cid` replays: the field is ignored.
        self.release()
        with open(self.path) as f:
            lines = f.read().splitlines()
        last = json.loads(lines[-1])
        last["roots"][0]["cid"] = before["vault"]
        del last["hash"]
        last["hash"] = cid_of(last)
        lines[-1] = json.dumps(last, separators=(",", ":"))
        with open(self.path, "w") as f:
            f.write("\n".join(lines) + "\n")
        self.host = self.spawn()
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")

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

    def test_an_unknown_card_is_named_with_a_hint_in_public_and_to_its_author(self):
        """Rehearsal finding 7: `delvetalk forge make` with no forge said only `unknownObject`."""
        r = self.turn("forge", "make", principal="gemini", identity="forge-1")
        public = {"status": "refused", "class": "unknownObject", "root": {"object": "forge"}, "object": "forge",
                  "hint": "no card named forge; reply to the directory for the list"}
        self.assertEqual((r["status"], r["public"]), ("refused", public), r)
        self.assertEqual(self.host.send(op="world-receipt", principal="cid", identity="forge-1", of="gemini"), public)

    def test_env_and_wake_are_the_speakers_own_and_cannot_be_taken(self):
        self.make("env/ann", TELLER, record(note=label("")))
        mine = self.turn("env", "stamp", record(text=label("seen")), principal="ann", identity="e-1")
        self.assertEqual(mine["status"], "admitted", mine)
        self.assertEqual([w["object"] for w in mine["receipt"]["outcome"]["writes"]], ["env/ann"])
        theirs = self.turn("env", "stamp", record(text=label("seen")), principal="bob", identity="e-2")
        self.assertEqual((theirs["status"], theirs["public"]["object"]), ("refused", "env/bob"), theirs)
        self.assertEqual(theirs["public"]["hint"], "no card named env/bob; reply to the directory for the list")
        wake = self.turn("wake", "stamp", record(text=label("x")), principal="ann", identity="w-1")
        self.assertEqual(wake["public"]["object"], "wake/ann", wake)
        self.assertEqual(self.host.send(op="world-card", principal="ann", object="env")["object"], "env/ann")
        for reserved in ("env", "wake"):
            taken = self.host.send(op="world-create", principal="ember", identity="mk-" + reserved, object=reserved,
                                   source=TELLER, entry="initial", seed=record(note=label("")))
            self.assertEqual(taken["status"], "error", taken)
            self.assertIn("reserved", taken["message"])


HANDLED = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Document.obend as Document
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, String>
def initial() -> State:
  {note: ""}
def who(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: context.handle})}})):
    case _: context.handle
def when(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: natText(context.clock)})}})):
    case _: natText(context.clock)
def render(state: State, context: Abi.Context) -> Document.Document:
  Document.text(textConcat("seen by ", context.handle))
"""
GLM = "did:plc:nmjdxe6fex23zslnnbwgruj3"


class Handles(Reflection):  # and the clock
    """Rehearsal finding 8: cards showed DID fragments. The host keeps a principal registry the
    clock principal fills (`world-principal`), and every Context carries the handle."""
    def setUp(self):
        super().setUp()
        self.open_library(clock="transport")
        self.make("mirror", HANDLED, record(note=label("")))

    def record_handle(self, handle, principal="transport"):
        return self.host.send(op="world-principal", principal=principal, did=GLM, handle=handle)

    def who(self):
        return self.turn("mirror", "who", principal=GLM)["result"]["value"]

    def card(self):
        return self.host.send(op="world-card", principal=GLM, object="mirror")["text"]

    def test_the_registry_names_the_principal_in_turns_and_cards_and_survives_replay(self):
        self.assertEqual((self.who(), self.card()), ("", "seen by "))
        self.assertEqual(self.record_handle("glm.delve.town", principal="mallory")["status"], "error")
        height = self.host.send(op="world-status")["height"]
        first = self.record_handle("glm.delve.town")
        self.assertEqual((first["status"], first["receipt"]["outcome"]),
                         ("principal", {"tag": "principal", "did": GLM, "handle": "glm.delve.town"}), first)
        self.assertEqual(first["receipt"]["identity"]["principal"], "transport")
        again = self.record_handle("glm.delve.town")
        self.assertNotIn("receipt", again)
        self.assertEqual(self.host.send(op="world-status")["height"], height + 1)
        self.assertEqual((self.who(), self.card()), ("glm.delve.town", "seen by glm.delve.town"))
        self.reopen()
        self.assertEqual((self.who(), self.card()), ("glm.delve.town", "seen by glm.delve.town"))
        self.assertIn("receipt", self.record_handle("glm.town"))
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.card(), "seen by glm.town")
        self.assertEqual(self.host.send(op="world-principal", principal="transport", did=GLM, handle="two\nlines")["status"], "error")

    def test_the_context_carries_the_world_clock_beside_the_height(self):
        """`until` deadlines compare against the clock world-advance moves, not the journal height."""
        when = lambda: self.turn("mirror", "when", principal=GLM)["result"]["value"]
        self.assertEqual(when(), "0")
        self.assertEqual(self.host.send(op="world-advance", principal="transport", height=1000)["status"], "advanced")
        self.assertEqual(when(), "1000")
        self.assertLess(self.host.send(op="world-status")["height"], 1000)


POST_WAITER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, String>
def initial() -> State:
  {note: ""}
def noted(text: String, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def waitFor(state: State, input: {post: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.awaitPost({post: input.post, patience: 5n})):
    case reply(r): noted(textConcat("answered by ", r.receipt.slot.intent), context)
    case timedOut(_): noted("timed out", context)
    case _: noted("other", context)
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  noted(input.text, context)
"""
OLD_RECEIVE = POST_WAITER.replace("input: {text: String, post: String}", "input: {text: String, post: String, slot: String}").replace(
    "noted(input.text, context)\n", "noted(input.slot, context)\n")


class ReplyIsAddress(Reflection):
    """awaitPost waits for the reply that answers a post: the first turn on the post's recorded
    object whose `replyTo` names it. receive's slot is the host's."""
    def setUp(self):
        super().setUp()
        self.open_library(clock="transport")
        self.make("w", POST_WAITER, record(note=label("")))
        self.make("card", POST_WAITER, record(note=label("")))

    def posted(self, uri, obj="w", **extra):
        r = self.host.send(op="world-posted", principal="transport", uri=uri, cid="c", object=obj, **extra)
        self.assertEqual(r["status"], "posted", r)

    def reply(self, uri, parent, obj="w", text="hi", **fields):
        argument = record(text=label(text), post=label(uri), **fields)
        return self.host.send(op="world-turn", principal="did:plc:bob", object=obj, method="receive",
                              argument=argument, identity=uri, replyTo=parent)

    def note(self, obj="w"):
        return field(self.host.send(op="world-view", principal="ann", object=obj)["state"], "note")["value"]

    def test_a_reply_to_the_awaited_post_resumes_the_waiter(self):
        waiting = self.turn("w", "waitFor", record(post=label(URI)), principal="ann", identity="wait-1")
        self.assertEqual((waiting["status"], waiting["receipt"]["outcome"]["post"]), ("suspended", URI), waiting)
        self.posted(URI, obj="card")
        # A reply to a post never recorded, or run on another object than the post's, answers nothing.
        stray = self.reply(URI + "/r0", URI + "x", obj="card")
        self.assertEqual(stray["status"], "admitted", stray)
        self.assertNotIn("replyTo", stray["receipt"])
        answer = self.reply(URI + "/r1", URI, obj="card")
        self.assertEqual((answer["status"], answer["receipt"]["replyTo"]), ("admitted", URI), answer)
        [resumed] = answer["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]), ("admitted", label("answered by " + URI + "/r1")), resumed)
        # (A reply run on the waiter itself would move its root; this one comes after.) Run on
        # another object than the post's, a reply answers nothing.
        elsewhere = self.reply(URI + "/r00", URI, obj="w")
        self.assertNotIn("replyTo", elsewhere["receipt"])
        # The index is rebuilt by replay: a later await on the answered post is answered at once.
        self.reopen()
        again = self.turn("w", "waitFor", record(post=label(URI)), principal="ann", identity="wait-2")
        self.assertEqual((again["status"], again["result"]), ("admitted", label("answered by " + URI + "/r1")), again)

    def test_an_unanswered_post_times_out_by_the_clock(self):
        self.turn("w", "waitFor", record(post=label(URI)), principal="ann", identity="wait-1")
        advanced = self.host.send(op="world-advance", principal="transport", height=10)
        [resumed] = advanced["resumed"]
        self.assertEqual(resumed["result"], label("timed out"), resumed)

    def test_receive_takes_text_and_post_and_the_host_fills_or_drops_slot(self):
        self.posted(URI, slot=SLOT)
        # Sent with a slot for one release: an object declaring {text, post} gets it dropped.
        legacy = self.reply(URI + "/r1", URI, text="with slot", slot=label("x"))
        self.assertEqual((legacy["status"], self.note()), ("admitted", "with slot"), legacy)
        # An object still declaring slot gets it from the recorded post.
        self.make("old", OLD_RECEIVE, record(note=label("")))
        self.posted(URI + "/old", obj="old", slot=SLOT)
        r = self.reply(URI + "/r2", URI + "/old", obj="old")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(json.loads(self.note("old")), SLOT)


MINTER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Child.obend as Child
record State:
  made: Nat
record Edits:
  made: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {made: 0n}
def made(target: Plans.Reference) -> Activity<Plan, Response, String>:
  match perform(Plan.create({package: "Child", seed: Data.of::<{}>({}), law: "", requireAbsent: target})):
    case created(c): c.object.object
    case refused(r): r.clause
    case _: "no answer"
def spawn(state: State, input: {}, context: Abi.Context) -> Activity<Plan, Response, String>:
  made(Plans.nobody())
def named(state: State, input: {id: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  made({world: "", object: input.id})
def spawnThenWait(state: State, input: {}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.create({package: "Child", seed: Data.of::<{}>({}), law: "", requireAbsent: Plans.nobody()})):
    case created(c): waited(c.object.object)
    case _: "no answer"
def waited(id: String) -> Activity<Plan, Response, String>:
  match perform(Plan.awaitUntil({slot: {principal: "nobody", intent: "never"}, until: 5n})):
    case _: id
"""


class MintedIds(Reflection):
    """A create with an empty requireAbsent mints `<creator>/<package>/<n>` from a per-parent counter."""
    def setUp(self):
        super().setUp()
        self.open_library(clock="transport")
        r = self.host.send(op="world-create", principal="ember", identity="mk-m", object="m", entry="initial",
                           modules=[{"name": "Child", "source": PACKAGE}, {"name": "Minter", "source": MINTER}],
                           seed=record(made=nat(0)))
        self.assertEqual(r["status"], "created", r)

    def mint(self, method="spawn", argument=None):
        r = self.turn("m", method, argument or record())
        return r, r.get("result", {}).get("value")

    def test_ids_are_minted_in_order_skip_named_children_and_never_race_a_waiting_creator(self):
        self.assertEqual([self.mint()[1] for _ in range(2)], ["m/child/1", "m/child/2"])
        self.assertEqual(self.mint("named", record(id=label("m/child/4")))[1], "m/child/4")
        self.assertEqual(self.mint()[1], "m/child/5")
        # A creator suspended after minting holds its id: the next mint passes it.
        waiting, _ = self.mint("spawnThenWait")
        self.assertEqual(waiting["status"], "suspended", waiting)
        self.assertEqual(self.mint()[1], "m/child/7")
        [resumed] = self.host.send(op="world-advance", principal="transport", height=9)["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]), ("admitted", label("m/child/6")), resumed)
        # A real collision is still refused: a named create of a minted id.
        clash, _ = self.mint("named", record(id=label("m/child/1")))
        self.assertEqual((clash["status"], clash["receipt"]["outcome"]["class"]), ("refused", "requiredAbsence"), clash)
        self.reopen()
        self.assertEqual(self.mint()[1], "m/child/8")
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="m/child/8")["status"], "viewed")


WHO = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, String>
def initial() -> State:
  {note: ""}
def who(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: context.principal})}})):
    case _: context.principal
def when(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: natText(context.clock)})}})):
    case _: natText(context.clock)
"""


class SourcePins(Reflection):
    """An object's pin is the CID of its sealed source closure; the compiled packet is never journaled.
    A rebuild whose packet differs from the one a resumed snapshot cached is only counted."""
    def created(self, name):
        r = self.make(name, TELLER, record(note=label("")))
        return r["receipt"]["outcome"]

    def tamper_last(self, change):
        self.release()
        with open(self.path) as f:
            lines = f.read().splitlines()
        last = json.loads(lines[-1])
        change(last)
        del last["hash"]
        last["hash"] = cid_of(last)
        lines[-1] = json.dumps(last, separators=(",", ":"))
        with open(self.path, "w") as f:
            f.write("\n".join(lines) + "\n")
        self.host = self.spawn()
        return self.host.send(op="world-open", path=self.path)

    def test_the_pin_is_the_sources_and_a_different_packet_is_only_counted(self):
        from tests.test_snapshot import read_snapshot, write_snapshot
        self.open_library()
        a = self.created("a")
        self.assertNotIn("compiled", a)
        height = self.host.send(op="world-snapshot")["height"]
        b = self.created("b")
        self.assertEqual(a["pin"], b["pin"])
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="a")["pin"], a["pin"])
        path = self.path + f".snapshot.{height}.cbor"
        body = read_snapshot(path)
        [obj] = [o for o in body["objects"] if o["id"] == "a"]
        obj["packet"] = a["pin"]
        write_snapshot(path, body)
        self.release()
        self.host = self.spawn()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["snapshot"]["resumed"], height, opened)
        self.assertEqual(self.host.send(op="world-status")["recompiledDifferently"], 1)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="b")["status"], "viewed")
        def old_field(entry):
            entry["outcome"]["compiled"] = {"binary": "b", "packet": "p"}
        self.assertEqual(self.tamper_last(old_field)["status"], "opened")
        def other_pin(entry):
            entry["outcome"]["pin"] = cid_of("another source closure")
        refused = self.tamper_last(other_pin)
        self.assertEqual(refused["status"], "error", refused)
        self.assertIn("is not the source closure its pin names", refused["message"])

    def test_an_object_from_before_a_context_field_keeps_running_after_the_library_gains_it(self):
        with tempfile.TemporaryDirectory() as scratch:
            lib = os.path.join(scratch, "lib")
            shutil.copytree(LIBRARY, lib)
            abi = os.path.join(lib, "prelude", "Abi.obend")
            with open(abi) as f:
                current = f.read()
            with open(abi, "w") as f:
                f.write(current.replace("  clock: Nat\n", "", 1))
            self.open_library(lib, clock="transport")
            self.make("old", WHO.replace("def when", "def unused").split("def unused")[0], record(note=label("")))
            with open(abi, "w") as f:
                f.write(current)
            self.assertEqual(self.host.send(op="world-library", principal="ember", identity="lib-2")["status"], "library")
            self.make("new", WHO, record(note=label("")))
            self.host.send(op="world-advance", principal="transport", height=7)
            old = self.turn("old", "who", principal="ann")
            self.assertEqual((old["status"], old["result"]), ("admitted", label("ann")), old)
            new = self.turn("new", "when", principal="ann")
            self.assertEqual((new["status"], new["result"]), ("admitted", label("7")), new)
            self.reopen()
            self.assertEqual(self.turn("old", "who", principal="bob")["result"], label("bob"))


class Transient(Reflection):
    """staleRoot, budget and evaluation refusals are journaled but do not bind the identity."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("teller", TELLER, record(note=label("")))

    def test_a_stale_root_refusal_retried_succeeds_once_the_root_is_reread(self):
        waiting = self.turn("teller", "waitAndTell", principal="kim", identity="w")
        self.assertEqual(waiting["status"], "suspended", waiting)
        # The teller moves while kim waits; the resumed turn read the old version.
        self.turn("teller", "tell", record(to=label("x"), text=label("moved")), principal="ann")
        settler = self.turn("teller", "tell", record(to=label("x"), text=label("x")), principal="glm", identity="x")
        # Refused staleRoot (transient), and re-run once at once from its request.
        [again] = settler["resumed"]
        self.assertEqual((again["status"], again["result"], again["receipt"]["rerun"]), ("admitted", label("told"), True), again)
        self.assertIn("rerunOf", again)
        self.assertEqual(self.offers(), ["woken"])
        receipt = self.host.send(op="world-receipt", principal="kim", identity="w")
        self.assertEqual(receipt["receipt"]["hash"], again["receipt"]["hash"])
        self.reopen()
        self.assertEqual(self.host.send(op="world-receipt", principal="kim", identity="w"), receipt)
        retry = self.turn("teller", "waitAndTell", principal="kim", identity="w")
        self.assertEqual(retry["receipt"], again["receipt"])

    def test_a_budget_refusal_is_retried_under_the_same_identity_and_then_commits(self):
        tight = self.host.send(op="world-turn", principal="kim", object="teller", method="tell", identity="b",
                               argument=record(to=label(""), text=label("t")), limits={"ticks": "5"})
        self.assertEqual(tight["receipt"]["outcome"]["class"], "budget", tight)
        again = self.host.send(op="world-turn", principal="kim", object="teller", method="tell", identity="b",
                               argument=record(to=label(""), text=label("t")), limits={"ticks": "5"})
        self.assertNotEqual(again["receipt"]["hash"], tight["receipt"]["hash"])
        roomy = self.host.send(op="world-turn", principal="kim", object="teller", method="tell", identity="b",
                               argument=record(to=label(""), text=label("t")))
        self.assertEqual(roomy["status"], "admitted", roomy)

    def offers(self):
        return [o["text"] for o in self.host.send(op="world-offers", principal="kim")["offers"]]


def nested(depth, leaf):
    return "Lists.List<" * depth + leaf + ">" * depth


DEEP = """edition ObjectiveBend 1
import ./List.obend as Lists
record State:
  deep: %s
def initial() -> State:
  {deep: %s.nil({})}
"""


class Malformed(Reflection):
    """Silent defaults refuse by name."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("teller", TELLER, record(note=label("")))

    def test_malformed_turn_limits_are_refused_by_name_not_defaulted(self):
        base = dict(op="world-turn", principal="kim", object="teller", method="tell",
                    argument=record(to=label(""), text=label("t")))
        for limits, word in (({"ticks": "many"}, "ticks"), ({"ticks": -3}, "ticks"), ("fast", "limits")):
            r = self.host.send(identity=f"l-{word}-{limits}", limits=limits, **base)
            self.assertEqual(r["status"], "error", (limits, r))
            self.assertIn(word, r["message"])

    def test_a_malformed_or_out_of_range_deliver_limit_is_refused(self):
        for bad in ("x", 0, 10 ** 6):
            r = self.host.send(op="world-deliver", limit=bad)
            self.assertEqual(r["status"], "error", (bad, r))
            self.assertIn("limit", r["message"])
        self.assertEqual(self.host.send(op="world-deliver", limit=4)["status"], "delivered")

    def test_a_malformed_migration_is_refused_not_read_as_none(self):
        r = self.host.send(op="world-reprogram", principal="ember", identity="rp", object="teller", version=0,
                           package=TELLER, migration=7)
        self.assertEqual(r["status"], "error", r)
        self.assertIn("migration", r["message"])

    def test_a_state_type_differing_below_eight_rounds_of_bounds_is_not_the_same(self):
        depth = 12
        old = DEEP % (nested(depth, "Nat"), nested(depth - 1, "Nat").replace("Lists.List<", "Lists.List::<", 1) if False else "Lists.List::<" + nested(depth - 1, "Nat") + ">")
        new = DEEP % (nested(depth, "Bool"), "Lists.List::<" + nested(depth - 1, "Bool") + ">")
        self.make("deep", old, record(deep={"tag": "list", "items": []}))
        r = self.host.send(op="world-reprogram", principal="ember", identity="rp", object="deep", version=0, package=new)
        self.assertEqual(r["status"], "refused", r)
        self.assertEqual((r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["clause"]), ("programRefused", "stateType"))


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
