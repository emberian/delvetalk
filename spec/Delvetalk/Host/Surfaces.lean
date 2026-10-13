/- The town's readable surfaces (docs/VOICE.md "The book, the history, the map"): a resident's commonplace
   book (`delvetalk me book`, `delvetalk <handle> book`), the town's history (`delvetalk chronicle`) and the
   door map (`delvetalk map`, `delvetalk <card> map`). Each is a host read, answered as `?` is and journaling
   nothing. The host folds the index a read needs from the store and the journal, as the reader may view them
   (`deeds`, `annal`, `ways`), and hands it to the card's own pure Bend definition of the read's name
   (`def book(state, context, deeds)` on the avatar, the commonplace's `chronicle` and `map`); the document that
   definition renders is the answer, the one rendering a post and the web page (`world-surface`) show alike. A
   card with no definition of `chronicle` or `map` of its own is read by the commonplace's, from that card. -/
import Delvetalk.Host.Ops
import Delvetalk.Document
import Std.Data.HashSet

namespace Delvetalk.Host.Surfaces
open Lean (Json toJson)
open Delvetalk.Host
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Theory.ObjectiveBendTypes (Ty)

/-- The reads, each the name of the card's definition that renders it. -/
def reads : List String := ["book", "chronicle", "map"]

/-- The reads the commonplace renders for any card that has no definition of its own. -/
def townReads : List String := ["chronicle", "map"]

/-- Where the town's reads are rendered when the card has none: the world's square (genesis's commonplace). -/
def square : String := Spell.townCard

/-! ## Reading the store -/

/-- A principal's own avatar (its id holds a DID), which no surface names as a thing. -/
def avatarId (id : String) : Bool := ((id.splitOn "/").head?.getD "").contains ':'

/-- The entry that made `id` and its principal: the entry of this chain that made it, else the making a carried
    genesis kept (`made`, at the height of the world it was made in); none for a store that came whole from a fork,
    or from a carry that kept no making. A carry's refresh is never a making (`Ops.carryRefresh`): a thing it placed has
    none, and a carried thing it first touched keeps the world before's. -/
def madeEntry (w : World) (id : String) : Option (Nat × String) :=
  let principal := fun (j : Json) => ((j.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
  let here : Option (Nat × String) := do
    let i ← (w.touched[id]?).bind (·[0]?)
    let e ← w.entries.get? i
    guard ((makes e).contains id && !installsStore e)
    return (i + 1, principal e)
  match here with
  | some m => if refreshEntry w (w.entries.get? (m.1 - 1) |>.getD Json.null) then none else some m
  | none => do
    let g ← w.entries.genesis?
    guard (tagOf g == "carried")
    let row ← (madeOf g)[id]?
    guard (!carryRefresh w ((row.getObjVal? "identity").toOption.getD Json.null) false)
    let h ← (row.getObjValAs? Nat "height").toOption
    return (h, principal row)

/-- Who made `id`: the maker its state names (a record made of a kind), else the principal of the entry that
    made it, else its owner (a thing or a kind carried whole). -/
def makerOf (w : World) (id : String) (o : Object) : String :=
  let fs := fieldsOf o.state
  match text? fs "maker" with
  | some m => if !m.isEmpty then m else fallback fs
  | none => fallback fs
where
  fallback (fs : List (String × Data)) : String :=
    match madeEntry w id with
    | some (_, who) => if who.isEmpty then (text? fs "owner").getD "" else who
    | none => (text? fs "owner").getD ""

/-- What a thing is, in a word: its kind's name (`kind/bell` a bell), a kind, else what its id calls it. -/
def calledWord (id : String) (o : Object) : String :=
  let kind := (text? (fieldsOf o.state) "kind").getD ""
  if !kind.isEmpty then ((kind.splitOn "/").getLast?.getD kind)
  else if id.startsWith "kind/" || id == "kinds" then "kind"
  else
    let parts := id.splitOn "/"
    let last := parts.getLast?.getD id
    if !last.isEmpty && last.all Char.isDigit then (parts.dropLast.getLast?.getD "thing") else last

/-- The fields a read was given, by name ("" for one not given). -/
def given (fields : List Spell.Binding) (name : String) : String :=
  ((fields.find? (·.name == name)).map (·.value)).getD ""

/-- A field that is a number in plain digits, or nothing given; `refused` names the field otherwise. -/
def number (fields : List Spell.Binding) (name : String) : Except (String × String) (Option Nat) :=
  let v := (given fields name).trimAscii.toString
  if v.isEmpty then .ok none
  else match Spell.number v.toList with
    | some n => .ok (some n)
    | none => .error ("badValue", s!"{name} takes a natural number in plain digits.")

/-! ## The book: what a hand did that the store still shows -/

/-- One row of a book (`World.Deed`): `made` (`name` what it is, `text` its coiner when another's post coined it), `grew` (`name` the verb, `text` its reading),
    `rule` and `want` (`name`, `text` the reading), `wrote` (`name` the verb that wrote the line, `text` the
    line), `visited` (`name` `here` while present); `at` the entry, 0 when the world before the carry made it. -/
structure Deed where
  what : String
  object : String
  name : String := ""
  text : String := ""
  height : Nat := 0

def Deed.data (d : Deed) : Data :=
  .record [("what", .label d.what), ("object", .label d.object), ("name", .label d.name), ("text", .label d.text),
    ("at", .natural d.height)]

/-- Everything `who` made, grew, placed, wrote and visited among the things `reader` may view, oldest first. -/
def deeds (w : World) (reader who : String) : List Deed := Id.run do
  let mut out : Array Deed := #[]
  for (id, o) in w.objects.toList do
    unless o.read.permits reader do continue
    let fs := fieldsOf o.state
    if !avatarId id && makerOf w id o == who then
      out := out.push { what := "made", object := id, name := calledWord id o, text := coinerOf w o, height := ((madeEntry w id).map (·.1)).getD 0 }
    for v in o.verbs do
      if v.grower == who then out := out.push { what := "grew", object := id, name := v.name, text := v.reading, height := v.height }
    for r in o.rules do
      if r.owner == who then out := out.push { what := "rule", object := id, name := r.name, text := r.clause.reading, height := r.since }
    for r in o.wants do
      if r.owner == who then out := out.push { what := "want", object := id, name := r.name, text := r.clause.reading, height := r.since }
    for r in rows fs "lines" do
      if text? r "author" == some who then
        out := out.push { what := "wrote", object := id, name := (text? r "verb").getD "", text := (text? r "text").getD "",
                          height := (nat? r "at").getD 0 }
    if (rows fs "presence").any (text? · "who" == some who) then
      out := out.push { what := "visited", object := id, name := "here" }
    else
      let left := ((rows fs "left").filter (text? · "who" == some who)).filterMap (nat? · "entry")
      if let some h := left.max? then out := out.push { what := "visited", object := id, height := h }
  return (out.qsort fun a b => a.height < b.height || (a.height == b.height && a.object < b.object)).toList

/-! ## The history: a day of the chronicle, and the town's firsts -/

/-- The first of a kind of act the world still holds (`World.First`): `rain` (the first line a rain wrote),
    `room` (the first room made), `verb` (the first verb grown), `rule` (the first rule that fired), `coinage`
    (the first thing made after another's post); its thing, who did it (a handle: the rainer, the maker, the
    grower, the rule's owner, the coiner), what (the verb, the rule), the entry. -/
structure First where
  what : String
  object : String
  who : String
  name : String := ""
  height : Nat

def First.data (f : First) : Data :=
  .record [("what", .label f.what), ("object", .label f.object), ("who", .label f.who), ("name", .label f.name),
    ("at", .natural f.height)]

/-- Whether `o` is a room: a place one enters (its card offers `enter`: a room, the porch). -/
def isRoom (o : Object) : Bool := o.offers "enter"

/-- The earliest of `firsts` by entry. -/
def earliest (firsts : List First) : Option First :=
  firsts.foldl (fun acc f => match acc with
    | some a => if f.height < a.height then some f else acc
    | none => some f) none

/-- The town's firsts as `reader` may view them: the first rain, room, grown verb, rule fired and coinage.
    A first firing requires continuous durable history and names the principal recorded with the firing. -/
def firsts (w : World) (reader : String) : List First := Id.run do
  let seen := w.objects.toList.filter fun (id, o) => o.read.permits reader && !avatarId id
  let rains := seen.flatMap fun (id, o) => (rows (fieldsOf o.state) "lines").filterMap fun r =>
    if text? r "verb" == some "rain" then some ({ what := "rain", object := id, who := handleIn w r "handle" "author" true, height := (nat? r "at").getD 0 } : First)
    else none
  -- A room or a coinage is a first only by a making the world holds (`madeEntry`): never a carry's refresh.
  let rooms := seen.filterMap fun (id, o) => do
    guard (isRoom o)
    let (h, _) ← madeEntry w id
    return ({ what := "room", object := id, who := shownName w (makerOf w id o), height := h } : First)
  -- A verb a carry's refresh grew (the station's `sign`, placed by the v13 carry) is no first either.
  let verbs := seen.flatMap fun (id, o) => (o.verbs.filter fun v => !refreshAt w v.height).map fun v =>
    ({ what := "verb", object := id, who := shownName w v.grower, name := v.name, height := v.height } : First)
  let coinages := seen.filterMap fun (id, o) => do
    let coiner := coinerOf w o
    guard (!coiner.isEmpty)
    let (h, _) ← madeEntry w id
    return ({ what := "coinage", object := id, who := coiner, height := h } : First)
  let mut fired : Option First := none
  for h in [historyStart w:w.height + 1] do
    unless historyComplete w do break
    let some e := historyEntry w h | break
    if historyRefresh w e then continue
    let rows := (((e.getObjVal? "fired").toOption.bind (·.getArr?.toOption)).getD #[]).toList
    let row := rows.find? fun f => viewable w reader ((f.getObjValAs? String "sender").toOption.getD "")
    if let some f := row then
      let text := fun (k : String) => (f.getObjValAs? String k).toOption.getD ""
      fired := some { what := "rule", object := text "sender", who := shownName w (text "principal"), name := text "rule", height := h }
      break
  return [earliest rains, earliest rooms, earliest verbs, fired, earliest coinages].filterMap id

/-- The day a chronicle read shows and the range it walks: `day` alone, or `from` through `to` (a page a day,
    each the next one's spell), the current day by default; `page` of the day's lines. -/
structure Asked where
  day : Nat
  from_ : Nat
  to : Nat
  page : Nat

def asked (w : World) (fields : List Spell.Binding) : Except (String × String) Asked := do
  let today := w.clock / Limits.clockDay
  let day ← number fields "day"
  let from_ ← number fields "from"
  let to ← number fields "to"
  let page := ((← number fields "page").getD 1).max 1
  match from_ with
  | some f =>
    let t := (to.getD today).max f
    return { day := f, from_ := f, to := t, page }
  | none =>
    let d := day.getD (to.getD today)
    return { day := d, from_ := d, to := d, page }

/-- The calendar date of unix day `days` (the clock counts unix minutes): `2026-10-12`. -/
def civil (days : Nat) : String :=
  let z := days + 719468
  let era := z / 146097
  let doe := z - era * 146097
  let yoe := (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
  let doy := doe - (365 * yoe + yoe / 4 - yoe / 100)
  let mp := (5 * doy + 2) / 153
  let d := doy - (153 * mp + 2) / 5 + 1
  let m := if mp < 10 then mp + 3 else mp - 9
  let y := yoe + era * 400 + (if m ≤ 2 then 1 else 0)
  let two := fun (n : Nat) => if n < 10 then s!"0{n}" else toString n
  s!"{y}-{two m}-{two d}"

#guard civil 20738 == "2026-10-12"
#guard civil 0 == "1970-01-01"

/-- `World.Annal`: the day shown and its date, today, the first day the journal holds, the range, the page, the day's exact
    lines (`Ops.chronicle`) and the town's firsts. -/
def annal (w : World) (reader : String) (a : Asked) : Data :=
  .record [("day", .natural a.day), ("date", .label (civil a.day)), ("today", .natural (w.clock / Limits.clockDay)),
    ("first", .natural ((w.days[0]?.map (·.1)).getD (w.clock / Limits.clockDay))),
    ("from", .natural a.from_), ("to", .natural a.to), ("page", .natural a.page),
    ("lines", ofList (((chronicle w reader a.day) ++
      if !historyComplete w then ["first rule firing unknown; history before the carry is unavailable"] else []).map Data.label)),
    ("firsts", ofList ((firsts w reader).map First.data))]

/-! ## The map: which cards open onto which -/

/-- A door (`World.Way`): the card it is on, its label, the card it opens onto. -/
structure Way where
  from_ : String
  label : String
  to : String

def Way.data (x : Way) : Data := .record [("from", .label x.from_), ("label", .label x.label), ("to", .label x.to)]

def Way.json (x : Way) : Json := Json.mkObj [("from", toJson x.from_), ("label", toJson x.label), ("to", toJson x.to)]

/-- Every door on a card `reader` may view onto a card they may view (`cites`, in each card's order; a link
    door with no card is not one), cards in id order; and how many things lie in each place that holds some. -/
def ways (w : World) (reader : String) : List Way × List (String × Nat) := Id.run do
  let seen := (w.objects.toList.filter fun (id, o) => o.read.permits reader && !avatarId id).toArray.qsort (·.1 < ·.1)
  let mut out : Array Way := #[]
  let mut lying : Array (String × Nat) := #[]
  for (id, o) in seen do
    let fs := fieldsOf o.state
    for d in ((fs.lookup "cites").bind listOf).getD [] do
      let r := fieldsOf d
      let some targetId := (r.lookup "to").bind referenceId | continue
      if targetId.isEmpty || !viewable w reader targetId then continue
      out := out.push { from_ := id, label := (text? r "label").getD targetId, to := targetId }
    let n := (rows fs "things").length
    if n > 0 then lying := lying.push (id, n)
  return (out.toList, lying.toList)

/-- Doors indexed by their source, retaining their positions in the ordered map. -/
def adjacency (ways : Array Way) : Std.HashMap String (Array (Nat × Way)) := Id.run do
  let mut out : Std.HashMap String (Array (Nat × Way)) := {}
  for i in [0:ways.size] do
    let some x := ways[i]? | continue
    out := out.insert x.from_ ((out.getD x.from_ #[]).push (i, x))
  return out

/-- The shortest way from the square to `root` through indexed doors (`[square, …, root]`), or none. -/
def pathTo (doors : Std.HashMap String (Array (Nat × Way))) (root : String) : List String := Id.run do
  if root == square then return [square]
  let mut queue : Array String := #[square]
  let mut cursor := 0
  let mut visited : Std.HashSet String := ({} : Std.HashSet String).insert square
  let mut parents : Std.HashMap String String := {}
  while cursor < queue.size do
    let here := queue[cursor]!
    cursor := cursor + 1
    for (_, x) in doors.getD here #[] do
      if visited.contains x.to then continue
      visited := visited.insert x.to
      parents := parents.insert x.to here
      if x.to == root then
        let mut path := [root]
        let mut at_ := root
        for _ in [0:visited.size] do
          let some parent := parents[at_]? | break
          path := parent :: path
          if parent == square then return path
          at_ := parent
        return []
      queue := queue.push x.to
  return []

/-- Doors handed to one map renderer, across its three drawn levels and the next level's counts. -/
def mapDoors : Nat := 64

/-- A path fitting in a map's header; a long path keeps its square and final steps with an ellipsis between. -/
def mapPath (path : List String) : List String := Id.run do
  let bound := Limits.cardShownChars / 3
  if (path.foldl (fun n id => n + id.length + 3) 0) ≤ bound then return path
  let mut suffix : List String := []
  let mut length := square.length + 6
  for id in path.reverse do
    if id == square || length + id.length + 3 > bound then break
    suffix := id :: suffix
    length := length + id.length + 3
  return square :: "…" :: suffix

/-- The bounded neighborhood a map renders: incoming doors and outgoing doors through four levels, in map order.
    Each unbroken label and the incoming-door footer fit within the reply's clip. -/
def mapWays (all : Array Way) (doors : Std.HashMap String (Array (Nat × Way))) (root : String) : List Way := Id.run do
  let mut candidates : Array (Nat × Way) := #[]
  if all.size ≤ mapDoors then
    for i in [0:all.size] do
      if let some x := all[i]? then candidates := candidates.push (i, x)
  else
    for i in [0:all.size] do
      if let some x := all[i]? then
        if x.to == root then candidates := candidates.push (i, x)
    let mut queue : Array (String × Nat) := #[(root, 0)]
    let mut cursor := 0
    let mut visited : Std.HashSet String := ({} : Std.HashSet String).insert root
    while cursor < queue.size && cursor < mapDoors do
      let (here, depth) := queue[cursor]!
      cursor := cursor + 1
      for item in doors.getD here #[] do
        candidates := candidates.push item
        let x := item.2
        if depth < 3 && !visited.contains x.to then
          visited := visited.insert x.to
          queue := queue.push (x.to, depth + 1)
  let mut selected : Std.HashSet Nat := {}
  let mut incoming := 0
  for (i, x) in candidates do
    if selected.size ≥ mapDoors then break
    if selected.contains i || x.label.length + x.to.length + 8 > Limits.cardShownChars / 2 then continue
    if x.to == root && root != square then
      let length := x.from_.length + x.label.length + 5
      if incoming + length > Limits.cardShownChars / 3 then continue
      incoming := incoming + length
    selected := selected.insert i
  let mut out : Array Way := #[]
  for i in [0:all.size] do
    if selected.contains i then
      if let some x := all[i]? then out := out.push x
  return out.toList

/-- `World.Ways`: the map's root, bounded path and neighborhood, counts at their endpoints, and page;
    the full readable door list accompanies it for a drawing. -/
def waysData (w : World) (reader root : String) (page : Nat) : Data × List Way :=
  let (all, lying) := ways w reader
  let doors := adjacency all.toArray
  let shown := mapWays all.toArray doors root
  let endpoints : Std.HashSet String := shown.foldl (fun s x => (s.insert x.from_).insert x.to) (({} : Std.HashSet String).insert root)
  (.record [("root", .label root), ("path", ofList ((mapPath (pathTo doors root)).map Data.label)),
    ("ways", ofList (shown.map Way.data)),
    ("lying", ofList ((lying.filter fun (id, _) => endpoints.contains id).map fun (id, n) => .record [("object", .label id), ("count", .natural n)])),
    ("page", .natural page)], all)

/-! ## Rendering by the card's own definition -/

/-- The parameter types of a function type and what it returns past `n` arrows. -/
def peeled : Nat → Ty → List Ty × Ty
  | n + 1, .arrow _ _ domain codomain => let (rest, result) := peeled n codomain; (domain :: rest, result)
  | _, ty => ([], ty)

/-- `o`'s pure definition `name` taking `(state, context, handed)`, compiled; none when it has none of that shape. -/
def surfaceDef (w : World) (o : Object) (name : String) : Option Compiled :=
  match compileDef w o name with
  | .ok (c, _) =>
    match peeled 3 c.type with
    | ([_, _, _], result) => match result with
      | .computation .. => none
      | .arrow .. => none
      | _ => if c.entry.isSome then some c else none
    | _ => none
  | .error _ => none

/-- `o`'s definition `c` (`id`'s) run for `reader` with `handed`, as a card renders: on its committed state, under
    a turn's ticks, the Context and `handed` fitted to its own types; its document's text. -/
def run (w : World) (id : String) (o : Object) (reader name : String) (c : Compiled) (handed : Data) (whole : Bool := false) :
    Except String String := do
  let some entry := c.entry | throw "noCard"
  let (domains, _) := peeled 3 c.type
  let context := contextData id reader (handleShown w reader) w.opener "" "" w.height w.clock (if whole then Card.wholeKind else "card") name
  let fit := fun (i : Nat) (d : Data) => match domains[i]? with
    | some ty => fitRecord c.bounds ty d
    | none => d
  match (runPure entry [o.state, fit 1 context, fit 2 handed] Limits.maxTurnTicks).1 with
  | .ok document => Delvetalk.Document.render document
  | .error e => throw e

/-- A read answered: the card that rendered it, its text (the page asked for, within a reply), and what the answer
    carries beside it (`whole`: every page as one text, page 0 handed and `Card.limit` none, when there are several,
    for a transport that threads it into parts; `paint`: the strokes a transport may paint above it; `ways`: the
    map's doors, for a drawing). -/
structure Answer where
  object : String
  text : String
  extra : List (String × Json) := []

/-- `read` cast on card `id` (`target`) by `reader` with `fields`: rendered by the card's own definition of it, or
    for a town read (with `fallback`: the card has no spell of that name) by the square's from this card; none
    when neither has one (the spell is then the card's to answer as any other). `.error (clause, reason)` for a field the read cannot take. -/
def answer (w : World) (reader id : String) (target : Object) (read : String) (fields : List Spell.Binding)
    (fallback : Bool := true) : Option (Except (String × String) Answer) := do
  guard (reads.contains read)
  let (renderer, o, c) ← match surfaceDef w target read with
    | some c => some (id, target, c)
    | none => do
      guard (fallback && townReads.contains read && id != square)
      let sq ← w.objects[square]?
      guard (sq.read.permits reader)
      let c ← surfaceDef w sq read
      some (square, sq, c)
  let page : Unit → Except (String × String) Nat := fun _ => (number fields "page").map fun p => (p.getD 1).max 1
  let rendered : (Nat → Data) → Nat → List (String × Json) → Except (String × String) Answer := fun handed page extra =>
    match run w renderer o reader read c (handed page) with
    | .ok text =>
      let whole := match run w renderer o reader read c (handed 0) (whole := true) with
        | .ok all => if all == text then [] else [("whole", toJson all)]
        | .error _ => []
      .ok { object := id, text, extra := whole ++ extra }
    | .error e => .error ("render", s!"{renderer} could not render its {read}: {e}")
  some <| match read with
    | "chronicle" => do
      let a ← asked w fields
      rendered (fun page => annal w reader { a with page }) a.page [("paint", Json.mkObj [("day", toJson a.day)]), ("day", toJson a.day)]
    | "map" => do
      let p ← page ()
      let (handed, all) := waysData w reader id p
      rendered (fun page => match handed with
        | .record fs => .record (fs.map fun (k, v) => if k == "page" then (k, .natural page) else (k, v))
        | d => d) p [("ways", Json.arr (all.map Way.json).toArray), ("root", toJson id)]
    | _ => do
      let p ← page ()
      let rows := ofList ((deeds w reader id).map Deed.data)
      rendered (fun page => .record [("page", .natural page), ("rows", rows)]) p []

/-- The spells of a read, as `?` lists them: the first page, then the fields it takes. -/
def spellsOf (card read : String) : List String :=
  match read with
  | "book" => [s!"delvetalk {card} book", s!"delvetalk {card} book / page: <a page after the first>"]
  | "map" => [s!"delvetalk {card} map"]
  | "chronicle" => ["delvetalk chronicle", "delvetalk chronicle / day: <a day>", "delvetalk chronicle / from: <a day> / to: <a later day>"]
  | _ => [s!"delvetalk {card} {read}"]

/-- The reads `?` lists on card `id` (shown as `shown`) for `reader`: those the card renders, and the town's the square
    renders from any card that has no spell of their name (`owned`, its spells and verbs). -/
def usage (w : World) (reader id : String) (target : Object) (shown : String) (owned : List String) : String :=
  let mine := reads.filter fun r => (surfaceDef w target r).isSome
  let town := if id == square || !((w.objects[square]?).map (·.read.permits reader)).getD false then [] else
    townReads.filter fun r => !mine.contains r && !owned.contains r &&
      (((w.objects[square]?).bind fun sq => surfaceDef w sq r).isSome)
  let all := (mine ++ town).flatMap (spellsOf shown)
  if all.isEmpty then "" else "\nTo read it (nothing is written):\n" ++ String.join (all.map (s!"\n{·}")) ++ "\n"

/-- `world-surface {principal, object?, read, fields?: {name: text}}`: a read rendered as a spell would answer it,
    for the web (`/o/<handle>/book`, `/history`, `/map`); the object defaults to the square, `me` and a handle
    resolve as in a spell. `{status: "surface", object, read, text, …extra}`, or `unknown` / `denied` / `noRead`,
    or `refused` with the field's clause and reason. Nothing is written. -/
def surfaceOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let read ← j.getObjValAs? String "read"
  let asked := (← optText j "object").getD square
  let id := namedCard w reader asked
  let fields : List Spell.Binding := match (j.getObjVal? "fields").toOption.bind (·.getObj?.toOption) with
    | some kvs => kvs.toList.filterMap fun (k, v) => match v with
      | .str s => some ⟨k, s⟩
      | .num n => some ⟨k, toString n⟩
      | _ => none
    | none => []
  let status := fun (s : String) => Json.mkObj [("status", toJson s), ("object", toJson id), ("read", toJson read)]
  let some o := w.objects[id]? | return status "unknown"
  unless o.read.permits reader do return status "denied"
  match answer w reader id o read fields with
  | none => return status "noRead"
  | some (.error (clause, reason)) => return (status "refused").mergeObj (Json.mkObj [("clause", toJson clause), ("reason", toJson reason)])
  | some (.ok a) => return (status "surface").mergeObj (Json.mkObj ([("text", toJson a.text)] ++ a.extra))

end Delvetalk.Host.Surfaces
