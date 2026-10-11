/- Root (docs/ROOT.md §1): the opener's unrestricted acts, each a journaled entry marked `root`
   inside its hash, carrying the value it replaced. `rootBefore`, `applyRoot` and `recordActs`
   (Ops.lean) are what live and replay share; this file reads the request and runs `as`. -/
import Delvetalk.Host.TurnLoop

namespace Delvetalk.Host
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Compiler.ObjectiveBendDataWire (dataJson decodeData)

/-- The acts of `world-root`. -/
def rootKinds : List String :=
  ["set", "delete", "as", "settings", "library", "ignore", "unignore", "card", "quiet", "hide", "show",
   "retire", "unretire", "revoke", "expire", "unquiet"]

/-- What a backward or forward clock touches: the suspensions whose deadline and the grants whose
    end lie between the two clocks (docs/ROOT.md §1.1). -/
def clockAffected (w : World) (to : Nat) : List (String × Json) :=
  let lo := min w.clock to
  let hi := max w.clock to
  let between := fun (n : Nat) => lo ≤ n && n ≤ hi
  [("suspensions", toJson (w.suspended.toList.filterMap fun s =>
      match (s.getObjVal? "outcome").toOption.bind (·.getObjValAs? Nat "deadline" |>.toOption) with
      | some d => if between d then (s.getObjValAs? String "hash").toOption else none
      | none => none)),
   ("grants", toJson (w.grants.toList.filterMap fun (id, g) => if between g.expires && !g.revoked then some id else none))]

/-- The outcome fields of an act other than `as`, `after` included; `before` is read after. -/
def rootFieldsOf (w : World) (kind : String) (act : Json) (reason : String) : Except String (List (String × Json)) := do
  let text := fun (k : String) => act.getObjValAs? String k
  let object := fun (_ : Unit) => do
    let id ← text "object"
    match w.objects[id]? with
    | some o => pure (id, o)
    | none => throw s!"no object {id}"
  match kind with
  | "set" =>
    let (id, o) ← object ()
    let field ← text "field"
    unless rootFields.contains field do throw s!"set names no field {field}; one of {", ".intercalate rootFields}"
    let value ← act.getObjVal? "value"
    let base := [("object", toJson id), ("field", toJson field)]
    match field with
    | "state" =>
      let state ← decodeData Limits.dataDepth value
      return base ++ [("after", value), ("version", toJson (o.version + 1)), ("cid", toJson (stateCid state))]
    | "owner" =>
      let owner ← value.getStr?
      let state := match o.state with
        | .record fs => Data.record (if fs.any (·.1 == "owner") then replaceField fs "owner" (.label owner) else fs ++ [("owner", .label owner)])
        | d => d
      return base ++ [("after", value), ("version", toJson (o.version + 1)), ("cid", toJson (stateCid state))]
    | "program" =>
      -- `{modules: [{name, source}]}` over the object's entry and limits; the host recompiles.
      let inputs := o.inputs.setObjVal! "modules" (← value.getObjVal? "modules")
      let built ← compileObject w inputs
      return base ++ [("after", inputs), ("pin", toJson (← built.artifact.getObjValAs? String "sourcesSha256"))]
    | _ => return base ++ [("after", value)]
  | "delete" =>
    let (id, _) ← object ()
    return [("object", toJson id), ("after", Json.null)]
  | "settings" =>
    let some given := act.getObj?.toOption | throw "settings names its values"
    let values := given.toList.filter (·.1 != "kind")
    if values.isEmpty then throw "settings names none of clock, clockPrincipal, postQuota, interpretQuota, modelQuota, opener, libraryLaw"
    for (k, v) in values do
      match k with
      | "clock" | "postQuota" | "interpretQuota" | "modelQuota" => discard <| natOf v
      | "clockPrincipal" | "opener" | "libraryLaw" => discard <| v.getStr?
      | _ => throw s!"no setting {k}"
    return [("after", Json.mkObj values)]
  | "library" =>
    let lib ← sealLibrary (← parseModules (← act.getObjVal? "modules"))
    return [("after", Json.mkObj [("pin", toJson lib.pin), ("modules", modulesJson lib.modules)])]
  | "ignore" | "unignore" =>
    let h ← natField act "height"
    if h == 0 || h > w.height then throw s!"height must be 1..{w.height}"
    if kind == "ignore" && w.ignored.contains h then throw s!"entry {h} is ignored already"
    if kind == "unignore" && !w.ignored.contains h then throw s!"entry {h} is not ignored"
    return [("height", toJson h), ("after", Json.mkObj [("ignored", toJson (kind == "ignore"))])]
  | "card" =>
    let (id, _) ← object ()
    let after ← match act.getObjVal? "text" with
      | .ok (.str t) => pure (toJson t)
      | .ok .null | .error _ => pure Json.null
      | .ok _ => throw "card text is text, or null to clear"
    return [("object", toJson id), ("after", after)]
  | "quiet" =>
    let who ← text "principal"
    let hours ← natField act "hours"
    return [("principal", toJson who), ("after", if hours == 0 then Json.null else
      Json.mkObj [("until", toJson (w.clock + hours * 60)), ("reading", toJson reason)])]
  | "hide" =>
    let (id, o) ← object ()
    if w.hidden.contains id then throw s!"{id} is hidden already"
    let owner := ownerOf o.state
    let readers := (if owner.isEmpty || owner == w.opener then [] else [owner]) ++ [w.opener]
    return [("object", toJson id), ("after", ReadPolicy.json (.principals readers))]
  | "show" =>
    let (id, _) ← object ()
    let some prior := w.hidden[id]? | throw s!"{id} is not hidden"
    return [("object", toJson id), ("after", prior)]
  | "retire" =>
    let (id, o) ← object ()
    if (lawClauses o.lawText).any (·.1 == "retired") then throw s!"{id} is retired already"
    if reason.any (fun c => c == '"' || c == '\\' || c == '\n') then throw "a retiring reason is one line without quotes"
    let clause := s!"law retired \"{reason}\": request.kind == 2 and request.subject == \"{w.opener}\""
    return [("object", toJson id), ("after", toJson (if o.lawText.isEmpty then clause else s!"{o.lawText}\n{clause}"))]
  | "unretire" =>
    let (id, o) ← object ()
    let kept := (o.lawText.splitOn "\n").filter fun l => !(l.trimAscii.toString.startsWith "law retired ")
    return [("object", toJson id), ("after", toJson ("\n".intercalate kept))]
  | "revoke" =>
    let g ← text "grant"
    unless w.grants.contains g do throw s!"no grant {g}"
    return [("grant", toJson g), ("after", Json.mkObj [("revoked", toJson true)])]
  | "expire" => throw "expire waits on scratch worlds (docs/FEDERATION.md §3), which this host does not hold yet"
  | k => throw s!"no root act {k}; one of {", ".intercalate rootKinds}"

/-- `world-root {principal, reason, act}` (docs/ROOT.md §1.1): the opener's act, unjudged except
    `as`, which runs an ordinary turn under `act.principal` with `root {by, reason}` beside it. Every
    other act journals `{identity {opener, root:<n>}, root: true, reason, outcome {tag: root, kind,
    object?, field?, before, after}}`; after an `ignore`/`unignore` the session re-derives the store
    under the new ignore set (`Session`, `Snapshot.reopen`). -/
def rootOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  if w.opener.isEmpty || principal != w.opener then throw "world-root is the opener's"
  let reason ← match j.getObjValAs? String "reason" with
    | .ok r => pure r
    | .error _ => throw "a root act needs a reason"
  if reason.isEmpty || reason.utf8ByteSize > Limits.maxReasonBytes || reason.any (· == '\n') then
    throw s!"a root act's reason is one line of 1..{Limits.maxReasonBytes} bytes"
  let act ← j.getObjVal? "act"
  let kind ← act.getObjValAs? String "kind"
  -- `unquiet {principal}` is journaled as the `quiet` of zero hours it is, so replay reads no new kind.
  let (kind, act) := if kind == "unquiet" then ("quiet", (act.setObjVal! "kind" (toJson "quiet")).setObjVal! "hours" (toJson (0 : Nat)))
    else (kind, act)
  if kind == "as" then
    let who ← boundedText "principal" Limits.maxPrincipalBytes (← act.getObjValAs? String "principal")
    let turn ← act.getObjVal? "turn"
    let req ← parseTurn (turn.setObjVal! "principal" (toJson who))
    let req := { req with object := resolveCard who req.object }
    return ← runTurnWith w req { root := some (Json.mkObj [("by", toJson principal), ("reason", toJson reason)]),
                                 via := lentVia w who req.object req.method }
  let fields ← rootFieldsOf w kind act reason
  let outcome := Json.mkObj ([("tag", toJson "root"), ("kind", toJson kind)] ++ fields)
  let outcome := outcome.setObjVal! "before" (← rootBefore w outcome)
  let w1 ← applyRoot w outcome
  let intent := s!"root:{w.rootActs + 1}"
  let id := (outcome.getObjValAs? String "object").toOption.getD ""
  let (w2, entry) := push w1 (identityKey principal intent)
    [("identity", identityJson principal intent), ("root", toJson true), ("reason", toJson reason),
     ("turn", toJson 0), ("roots", rootsJson []),
     ("request", toJson (Journal.bodyHash (Json.mkObj [("act", act), ("reason", toJson reason)]))),
     ("outcome", outcome)] (if id.isEmpty then [] else [id])
  let extra := (match (outcome.getObjVal? "after").toOption.bind (·.getObjValAs? Nat "clock" |>.toOption) with
      | some c => if kind == "settings" then clockAffected w c else []
      | none => []) ++
    (if kind == "set" && (outcome.getObjValAs? String "field").toOption == some "pin" then
      [("note", toJson "the pin is stored alone: the object's turns still run the closure its sources compile to, and world-inspect shows the stored pin, until program is set")]
     else [])
  return (w2, Json.mkObj ([("status", toJson "root"), ("kind", toJson kind), ("receipt", slugged entry)] ++ extra))

/-- `world-settings {principal, reading, identity?, postQuota?, interpretQuota?, modelQuota?}`: the
    opener replaces quotas without a genesis (docs/ROOT.md §2.2). -/
def worldSettingsOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let reading ← boundedText "reading" Limits.maxReasonBytes (← j.getObjValAs? String "reading")
  let values ← ["postQuota", "interpretQuota", "modelQuota"].filterMapM fun k => do
    return (← optNat j k).map (k, ·)
  let intent := (← optText j "identity").getD s!"settings:{w.height + 1}"
  let digest := Journal.bodyHash (Json.mkObj (values.map (fun (k, n) => (k, toJson n)) ++ [("reading", toJson reading)]))
  settingsChange w principal intent digest values reading

end Delvetalk.Host
