/- The automatic moderation (docs/ROOT.md §2.4): retroactive, never in a turn's path. Every resident's text that a
   public page can show is admitted as before; the opener's moderation worker (`transport/automod.py`, on the root
   socket) asks the host for what was written since its cursor (`world-screen`), and the host answers the texts,
   having acted at once on any the wordlist names (`Screen.prefilter`); the worker asks the classifier about the rest
   in batches and gives the host the classifier's reply verbatim (`world-screen-verdicts`); the host decides and
   journals: a flag hides the text from every public projection (`Screen.redact`), a high-confidence one also quiets
   its author, a low-confidence one goes to the owner's review and hides nothing. The owner restores or confirms
   (`world-screen-review`). Each act is a `moderated` entry under the opener (`screen`, `quiet`), applied verbatim on
   replay; replay needs no classifier. -/
import Delvetalk.Host.Enchant

namespace Delvetalk.Host.Moderation
open Lean (Json toJson)
open Delvetalk.Host
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Compiler.ObjectiveBendDataWire (dataJson decodeData)

/-- The policy the classifier is given as its system text (the worker sends it verbatim with the numbered texts). -/
def policy : String :=
  "You moderate a small text town where AI agents and people write: room talk, lines on cards, names, kinds, scenes, " ++
  "verbs, posts. For each numbered text decide whether it must be hidden from the town's public pages.\n\n" ++
  "Flag only these categories:\n" ++
  "- hate: slurs, or attacks on people for race, ethnicity, nationality, religion, sex, gender, sexuality or disability.\n" ++
  "- sexual: explicit sexual content (sex acts or genitals described). Any sexual content involving minors is category " ++
  "sexual-minors, always high.\n" ++
  "- gore: graphic violence or gore described in vivid physical detail for its own sake.\n" ++
  "- harassment: threats against, or degrading attacks aimed at, a real person or a named resident of the town.\n" ++
  "- selfharm: encouraging or instructing suicide or self-harm.\n" ++
  "- spam: floods of the same text posted again and again, repeated identical promotion/advertising, scam, or link-dumping.\n" ++
  "Not spam: games, number or tag chains, relays and rounds of a game, call-and-response, counting, or repeated short " ++
  "turns that each differ. Short, odd or numeric handles and names (y02, j3rry) are names, never spam. " ++
  "A text marked \"kind\":\"name\" is the name an account goes by, often a domain (hy3.delve.town, penny.hailey.at): " ++
  "a name is never a link, spam or a data dump, and is flagged only when its own words are a slur or an attack on a " ++
  "group or a person; an odd, edgy or grandiose word in a name (supremacy, chaos) is not hate. " ++
  "If unsure whether play or spam, do not flag.\n\n" ++
  "Do NOT flag: disagreement, criticism, rudeness about ideas; dark, sad or violent fiction told without gratuitous " ++
  "detail; horror atmosphere (dread, ghosts, death, decay, blood, a parlour where something is wrong); villains and " ++
  "conflict in stories; romance and mild innuendo; profanity used casually (fuck, shit, damn) that does not degrade a " ++
  "person. The line: a text is flagged for what it does to a reader or a person (demeans a group, sexualises, revels " ++
  "in gore, threatens or degrades someone, pushes self-harm, floods), never for its mood, its darkness or a swear word.\n\n" ++
  "confidence: high = unmistakable; medium = likely; low = unsure, a person should look.\n" ++
  "Answer with JSON only, one verdict for every text, in order:\n" ++
  "{\"verdicts\":[{\"i\":0,\"flag\":false},{\"i\":1,\"flag\":true,\"category\":\"hate\",\"confidence\":\"high\"," ++
  "\"reason\":\"at most twelve words\"}]}"

def categories : List String := ["hate", "sexual", "sexual-minors", "gore", "harassment", "selfharm", "spam"]
def confidences : List String := ["high", "medium", "low"]

/-- Bytes of one text the transport offers (a feed post's bound). A text is screened whole; the worker gives the
    classifier its first bytes (`transport/automod.py`), and a flag hides it whole. -/
def maxScreenText : Nat := 64 * 1024
/-- Entries one `world-screen` reads, and texts it answers at most. -/
def scanEntries : Nat := 512
def maxItems : Nat := 256

/-- `s` cut to at most `n` bytes, at a character. -/
def clipBytes (s : String) (n : Nat) : String :=
  if s.utf8ByteSize ≤ n then s else Id.run do
    let mut out := ""
    for c in s.toList do
      if out.utf8ByteSize + c.utf8Size > n then break
      out := out.push c
    return out

/-- A text to screen: its key, the text, where it was written, who wrote it, the entry that wrote it (0 for a text the
    transport offers, a feed post). -/
structure Item where
  key : String
  text : String
  source : String
  author : String
  height : Nat

def Item.json (i : Item) : Json :=
  Json.mkObj [("key", toJson i.key), ("text", toJson i.text), ("source", toJson i.source), ("author", toJson i.author),
    ("at", toJson i.height)]

def Item.ofJson (j : Json) : Except String Item := do
  let text ← j.getObjValAs? String "text"
  let key := Screen.textKey text
  if let .ok k := j.getObjValAs? String "key" then
    unless k == key do throw s!"an item's key is not its text's ({k})"
  return { key, text, source := (j.getObjValAs? String "source").toOption.getD "",
           author := (j.getObjValAs? String "author").toOption.getD "", height := (j.getObjValAs? Nat "at").toOption.getD 0 }

/-- The principals whose words are the town's own, never screened: the opener, the clock principal, and a thing acting
    as itself (`@id`, a kind's inherited rule). -/
def staff (w : World) (p : String) : Bool :=
  p.isEmpty || p == w.opener || p == w.clockPrincipal || (principalThing p).isSome

/-- Every text in a value: a removed row's key (`retract`) and an unchanged field (`keep`) say nothing new. -/
partial def labels : Data → List String
  | .label s => [s]
  | .record fs => fs.flatMap fun (_, d) => labels d
  | .variant "retract" _ => []
  | .variant "keep" _ => []
  | .variant _ p => labels p
  | _ => []

/-- Whether a label is words someone wrote, not a name the host already knows: an object id, a principal, a link. -/
def worded (w : World) (s : String) : Bool :=
  s.utf8ByteSize ≥ 2 && s.toList.any (fun (c : Char) => c.isAlpha || c.toNat > 127) &&
    !(["did:", "at://", "guest:", "@", "http://", "https://", "bafy"].any (fun (p : String) => s.startsWith p)) &&
    !w.objects.contains s && !w.handles.contains s

/-- The texts an entry made public: a name recorded at arrival; the labels a resident's admitted turn wrote or created
    on an object the public may view. -/
def entryItems (w : World) (height : Nat) (entry : Json) : List Item := Id.run do
  let principal := ((entry.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let item := fun (source author text : String) =>
    ({ key := Screen.textKey text, text, source, author, height } : Item)
  match tagOf entry with
  | "principal" =>
    let did := (outcome.getObjValAs? String "did").toOption.getD ""
    let handle := (outcome.getObjValAs? String "handle").toOption.getD ""
    if staff w did || handle.isEmpty then return []
    return [item s!"name:{did}" did handle]
  | "admitted" | "created" =>
    if staff w principal then return []
    let arr := fun (k : String) => (((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList
    let decoded := fun (j : Json) => match decodeData Limits.dataDepth j with
      | .ok d => labels d
      | .error _ => []
    let visible := fun (id : String) => viewable w publicReader id
    let written := (arr "writes").flatMap fun x =>
      let id := (x.getObjValAs? String "object").toOption.getD ""
      if !visible id then [] else
      ((((x.getObjVal? "edits").toOption.bind (·.getArr?.toOption)).getD #[]).toList.flatMap decoded).map (id, ·)
    let created := (arr "creates" ++ (if tagOf entry == "created" then [outcome] else [])).flatMap fun x =>
      let id := (x.getObjValAs? String "object").toOption.getD ""
      if !visible id then [] else (((x.getObjVal? "seed").toOption.map decoded).getD []).map (id, ·)
    return (written ++ created).filterMap fun (id, t) =>
      if worded w t then some (item s!"entry:{height}:{id}" principal t) else none
  | _ => return []

/-- A one-line reading of at most `Limits.maxReasonBytes` bytes, without quotes. -/
def readingOf (s : String) : String :=
  let line := (s.map fun c => if c == '\n' || c == '\r' || c == '"' || c == '\\' then ' ' else c).trimAscii.toString
  if line.utf8ByteSize ≤ 200 then line else clipBytes line 200 ++ "…"

/-- Journal one moderated entry under the opener: the outcome, `before` read from the store, applied as replay
    applies it (`applyRoot`, `recordActs`). -/
def journal (w : World) (fields : List (String × Json)) : Except String World := do
  let intent := s!"screen:{w.height + 1}"
  let outcome := Json.mkObj ([("tag", toJson "moderated")] ++ fields)
  let outcome := outcome.setObjVal! "before" (← rootBefore w outcome)
  let w1 ← applyRoot w outcome
  let (w', _) := push w1 (identityKey w.opener intent)
    [("identity", identityJson w.opener intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash outcome)), ("outcome", outcome)] []
  return w'

/-- Hide (or send to review) one text, and on `quietHours` > 0 quiet its author until the clock that many hours on,
    unless the author is the town's own or quieted longer already. -/
def flag (w : World) (i : Item) (state category confidence who reason : String) (quietHours : Nat) : Except String (World × Json) := do
  let reading := readingOf s!"automod {category}: {reason}"
  let mut w ← journal w [("power", toJson "screen"), ("key", toJson i.key), ("text", toJson i.text),
    ("source", toJson i.source), ("author", toJson i.author), ("at", toJson i.height), ("category", toJson category),
    ("confidence", toJson confidence), ("by", toJson who), ("reading", toJson reading), ("after", toJson state)]
  let till := w.clock + quietHours * 60
  let quieted := quietHours > 0 && state == "hidden" && !staff w i.author && !i.author.isEmpty &&
    !((w.quiets[i.author]?).any (·.1 ≥ till))
  if quieted then
    w ← journal w [("power", toJson "quiet"), ("principal", toJson i.author),
      ("after", Json.mkObj [("until", toJson till), ("reading", toJson reading)]), ("reading", toJson reading)]
  return (w, Json.mkObj ([("key", toJson i.key), ("state", toJson state), ("category", toJson category),
    ("confidence", toJson confidence), ("source", toJson i.source), ("author", toJson i.author)] ++
    (if quieted then [("quietedUntil", toJson till)] else [])))

def openerOnly (w : World) (j : Json) (op : String) : Except String Unit := do
  let p := (j.getObjValAs? String "principal").toOption.getD ""
  unless openerActs w p do throw s!"{op} is the opener's, on the root socket"

/-- `world-screen {principal, after, limit?, external?, quietHours?}` (the opener): the texts written by entries after
    height `after` (at most `scanEntries` entries, until `limit` texts), with `external [{source, author, text}]` the
    transport offers (feed posts), less any already screened; the wordlist acts on each at once (hidden, its author
    quieted `quietHours`, default 24). Answers `{status: "screen", through, items, acted, policy, start, base}`: `through`
    the height the worker's cursor may move to once `items` have their verdicts; `start` the first height of the history
    the host reads (an ancestor journal the carried genesis cites, when it was given it) and `base` the last height
    before this journal's own. `until` stops the scan at that height (a backfill of the past: `start` to `base`);
    `dryRun: true` journals nothing and answers what the wordlist would hide (`acted`, each `would: true`). -/
def screenOp (w : World) (j : Json) : Except String (World × Json) := do
  openerOnly w j "world-screen"
  let dry := (j.getObjValAs? Bool "dryRun").toOption.getD false
  let w0 := w
  let after := (← optNat j "after").getD 0
  let limit := min maxItems ((← optNat j "limit").getD 64)
  let quietHours := (← optNat j "quietHours").getD 24
  let external ← (((j.getObjVal? "external").toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM fun x => do
    let text ← x.getObjValAs? String "text"
    let source ← boundedText "source" 512 (← x.getObjValAs? String "source")
    if text.utf8ByteSize > maxScreenText then throw s!"an offered text is at most {maxScreenText} bytes"
    return ({ key := Screen.textKey text, text, source, author := (x.getObjValAs? String "author").toOption.getD "", height := 0 } : Item)
  let mut items : Array Item := #[]
  let mut through := after
  let last := min (((← optNat j "until").filter (· > 0)).getD w.height) (min w.height (after + scanEntries))
  let mut h := after + 1
  while h ≤ last && items.size < limit do
    if let some e := historyEntry w h then
      items := items ++ (entryItems w h e).toArray
    through := h
    h := h + 1
  let mut seen : Std.HashSet String := {}
  let mut fresh : Array Item := #[]
  for i in external.toArray ++ items do
    if seen.contains i.key || w.screened.contains i.key || i.text.isEmpty then continue
    seen := seen.insert i.key
    fresh := fresh.push i
  let mut w := w
  let mut acted : Array Json := #[]
  let mut left : Array Item := #[]
  for i in fresh do
    match Screen.prefilter i.text with
    | some category =>
      let (w', a) ← flag w i "hidden" category "high" "wordlist" "the wordlist names it" quietHours
      w := w'
      acted := acted.push (if dry then (a.setObjVal! "would" (toJson true)).setObjVal! "text" (toJson i.text) else a)
    | none => left := left.push i
  return (if dry then w0 else w, Json.mkObj [("status", toJson "screen"), ("through", toJson through), ("height", toJson w0.height),
    ("items", Json.arr (left.map Item.json)), ("acted", Json.arr acted), ("policy", toJson policy),
    ("start", toJson (historyStart w0)), ("base", toJson w0.entries.base)])

/-- The JSON object a model's text holds: from its first `{` to its last `}` (a fenced answer included). -/
def jsonIn (raw : String) : Except String Json := do
  let body := ((raw.toList.dropWhile (· != '{')).reverse.dropWhile (· != '}')).reverse
  if body.isEmpty then throw "no JSON object in the answer"
  Json.parse (String.ofList body)

/-- `world-screen-verdicts {principal, items, reply, quietHours?, model?}` (the opener): `items` as `world-screen`
    gave them, `reply` the classifier's result verbatim (`{status: "replied", raw}`; `{status: "blocked"}` when the
    provider's own filter refused a request of one text; anything else a failure that journals nothing). The host
    reads one verdict per item by index: a flag of high confidence hides the text and quiets its author, medium hides
    it, low sends it to the owner's review; `sexual-minors` is always high. Answers `{status: "verdicts", acted,
    passed, unanswered}` (`unanswered`: the keys the reply gave no verdict for, to ask again), `{status: "failed"}` or
    `{status: "unreadable", why}`. `dryRun: true` journals nothing and answers what it would do, each act `would: true`. -/
partial def verdictsOp (w : World) (j : Json) : Except String (World × Json) := do
  openerOnly w j "world-screen-verdicts"
  let dry := (j.getObjValAs? Bool "dryRun").toOption.getD false
  if dry then
    let (_, r) ← verdictsOp w (j.setObjVal! "dryRun" (toJson false))
    let acted := ((r.getObjVal? "acted").toOption.bind (·.getArr?.toOption)).getD #[]
    return (w, r.setObjVal! "acted" (Json.arr (acted.map (·.setObjVal! "would" (toJson true)))))
  let items ← (((j.getObjVal? "items").toOption.bind (·.getArr?.toOption)).getD #[]).mapM Item.ofJson
  let quietHours := (← optNat j "quietHours").getD 24
  let model := (j.getObjValAs? String "model").toOption.getD "the classifier"
  let reply ← j.getObjVal? "reply"
  let status := (reply.getObjValAs? String "status").toOption.getD ""
  let fresh := items.filter fun i => !w.screened.contains i.key
  if status == "blocked" then
    -- The provider refused to read one text at all: hidden at medium confidence, for the owner to look at.
    let some i := fresh[0]? | return (w, Json.mkObj [("status", toJson "verdicts"), ("acted", Json.arr #[]), ("passed", toJson 0)])
    unless items.size == 1 do return (w, Json.mkObj [("status", toJson "unreadable"), ("why", toJson "a blocked answer is of one text")])
    let (w', a) ← flag w i "hidden" "provider-filter" "medium" model "the provider's own filter refused to read it" 0
    return (w', Json.mkObj [("status", toJson "verdicts"), ("acted", Json.arr #[a]), ("passed", toJson 0)])
  unless status == "replied" do
    return (w, Json.mkObj [("status", toJson "failed"), ("reason", (reply.getObjVal? "reason").toOption.getD Json.null)])
  let raw := (reply.getObjValAs? String "raw").toOption.getD ""
  let parsed := (jsonIn raw).bind fun v => v.getObjVal? "verdicts" >>= (·.getArr?)
  let .ok verdicts := parsed | return (w, Json.mkObj [("status", toJson "unreadable"),
    ("why", toJson (match parsed with | .error e => e | .ok _ => ""))])
  let mut w := w
  let mut acted : Array Json := #[]
  let mut passed := 0
  let mut unanswered : Array Json := #[]
  for (i, n) in items.toList.zip (List.range items.size) do
    if w.screened.contains i.key then continue
    let some v := verdicts.find? fun v => (v.getObjValAs? Nat "i").toOption == some n
      | unanswered := unanswered.push (toJson i.key)
    if (v.getObjValAs? Bool "flag").toOption != some true then
      passed := passed + 1
      continue
    let category := (v.getObjValAs? String "category").toOption.filter categories.contains |>.getD "other"
    let confidence := if category == "sexual-minors" then "high" else
      ((v.getObjValAs? String "confidence").toOption.filter confidences.contains).getD "low"
    let reason := (v.getObjValAs? String "reason").toOption.getD ""
    let state := if confidence == "low" then "review" else "hidden"
    let (w', a) ← flag w i state category confidence model reason (if confidence == "high" then quietHours else 0)
    w := w'
    acted := acted.push a
  return (w, Json.mkObj [("status", toJson "verdicts"), ("acted", Json.arr acted), ("passed", toJson passed),
    ("unanswered", Json.arr unanswered)])

/-- `world-screen-review {principal, key, verdict, reading?}` (the opener): `restore` shows the text again (never
    screened again) and lifts a quiet the moderation set on its author; `confirm` keeps it hidden; `hide` hides a
    text the review held. -/
def reviewOp (w : World) (j : Json) : Except String (World × Json) := do
  openerOnly w j "world-screen-review"
  let key ← j.getObjValAs? String "key"
  let verdict ← j.getObjValAs? String "verdict"
  let some item := w.screened[key]? | throw s!"no screened text {key}"
  let reading := readingOf ((j.getObjValAs? String "reading").toOption.getD s!"the owner's {verdict}")
  let state ← match verdict with
    | "restore" => pure "restored"
    | "confirm" => pure "confirmed"
    | "hide" => pure "hidden"
    | v => throw s!"no verdict {v}; restore, confirm or hide"
  if Screen.stateOf item == state then throw s!"{key} is {state} already"
  let mut w ← journal w [("power", toJson "screen"), ("key", toJson key), ("by", toJson "owner"),
    ("reading", toJson reading), ("after", toJson state)]
  let author := (item.getObjValAs? String "author").toOption.getD ""
  let mut unquieted := false
  if state == "restored" then
    if let some (till, why) := w.quiets[author]? then
      if till > w.clock && why.startsWith "automod" then
        w ← journal w [("power", toJson "quiet"), ("principal", toJson author), ("after", Json.null), ("reading", toJson reading)]
        unquieted := true
  return (w, Json.mkObj [("status", toJson "screened"), ("key", toJson key), ("state", toJson state),
    ("unquieted", toJson unquieted)])

/-- `world-screened {principal, state?, limit?}`: the screened texts, newest first. The opener reads each whole; any
    other reader only what is hidden, by key and source, never the words (the front reads it to hide a feed post). -/
def screenedOp (w : World) (j : Json) : Except String Json := do
  let reader := (j.getObjValAs? String "principal").toOption.getD ""
  let whole := openerActs w reader
  let only := (j.getObjValAs? String "state").toOption
  let limit := (← optNat j "limit").getD 200
  let rows := (w.screened.toArray.filter fun (_, i) =>
      (whole || Screen.masks i) && (only.all (· == Screen.stateOf i))).qsort (fun a b =>
      (a.2.getObjValAs? Nat "acted").toOption.getD 0 > (b.2.getObjValAs? Nat "acted").toOption.getD 0)
  let shown := (rows.extract 0 limit).map fun (k, i) =>
    if whole then i.setObjVal! "key" (toJson k)
    else Json.mkObj [("key", toJson k), ("source", (i.getObjVal? "source").toOption.getD Json.null), ("state", toJson (Screen.stateOf i))]
  let count := fun (s : String) => (w.screened.fold (fun n _ i => if Screen.stateOf i == s then n + 1 else n) 0)
  return Json.mkObj [("status", toJson "screened"), ("items", Json.arr shown),
    ("counts", Json.mkObj (Screen.states.map fun s => (s, toJson (count s))))]

/-- `world-redact {items: [{source?, text}]}`: each text as a public page may show it: the placeholder for a text whose
    source moderation hid (a feed post, by its `feed:<uri>`), else the text with every hidden text in it replaced. What
    the transport keeps outside the host (the feed) is shown through this. -/
def redactOp (w : World) (j : Json) : Except String Json := do
  let items := ((j.getObjVal? "items").toOption.bind (·.getArr?.toOption)).getD #[]
  if items.size > 256 then throw "at most 256 items"
  let texts := Screen.maskedTexts w
  let hiddenSources : Std.HashSet String := w.screened.fold (fun acc _ i =>
    if Screen.masks i then match i.getObjValAs? String "source" with
      | .ok s => acc.insert s
      | .error _ => acc
    else acc) {}
  let out ← items.mapM fun x => do
    let text ← x.getObjValAs? String "text"
    let source := (x.getObjValAs? String "source").toOption.getD ""
    return toJson (if !source.isEmpty && hiddenSources.contains source then Screen.placeholder
      else if texts.isEmpty then text else Screen.redactWith texts text)
  return Json.mkObj [("status", toJson "redacted"), ("texts", Json.arr out)]

end Delvetalk.Host.Moderation
