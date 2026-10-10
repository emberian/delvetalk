/- `compile-profile`: where a package's compile time goes, stage by stage, and the
differential self-checks of the front end's direct scanners. Not part of the host; build it
with `lake build compile-profile`.

    compile-profile REQUEST.json [entry ...]     stage timings, three rounds (REQUEST is a
                                                 compile request: {modules, entry, limits?})
    compile-profile REQUEST.json loop STAGE N    one stage N times (parse, generics,
                                                 elaborate, lower, check), for perf
    compile-profile self-check                   tokenLength vs tokenRe and splitTop vs its
                                                 List definition on 300,000 random strings each;
                                                 SHA-256 on the FIPS 180-4 vectors and against
                                                 the stored-schedule reference
    compile-profile sha                          SHA-256 throughput on 1 MB
    compile-profile replay LINES DIR FILTER R    host requests (one JSON per line, as the
                                                 binary reads them) through
                                                 `PackageSession.stepIO`, with `world-open`
                                                 moved to DIR/world.journal (emptied first,
                                                 `sync: none`); each request whose class
                                                 (`op object method` or `op entry`) starts
                                                 with FILTER runs R times from the same
                                                 session. Prints per class: requests, the
                                                 fastest run's wall summed, `ticksUsed`
                                                 summed, ticks per second (docs/PERF.md) -/
import Delvetalk.PackageSession
import Std.Data.HashMap
open Lean (Json toJson)
open Minidregg.Compiler
open Minidregg.Compiler.ObjectiveBendFrontEnd
open Minidregg.Theory.ObjectiveBendTyping

def ms (a b : Nat) : String := toString (((b - a) / 10000).toFloat / 100.0) ++ " ms"

def timed {α : Type} (label : String) (f : Unit → Except String α) : IO α := do
  let t0 ← IO.monoNanosNow
  let r ← IO.ofExcept (f ())
  let t1 ← IO.monoNanosNow
  IO.println s!"{label}: {ms t0 t1}"
  return r

/-- `splitTop` as it was written over `List Char` (the reference for the byte scanner). -/
def splitTopRef (text : String) (sep : String) : List String :=
  let chars := text.toList
  let sepChars := sep.toList
  let rec go : Nat → List Char → Option Char → Int → List Char → List String → List String
    | 0, _, _, _, current, parts => String.ofList current.reverse :: parts
    | _ + 1, [], _, _, current, parts => String.ofList current.reverse :: parts
    | fuel + 1, c :: rest, prev, depth, current, parts =>
      if "<({".toList.contains c then go fuel rest (some c) (depth + 1) (c :: current) parts
      else if ">)}".toList.contains c && !(c == '>' && prev == some '-') then go fuel rest (some c) (depth - 1) (c :: current) parts
      else if depth == 0 && sepChars.isPrefixOf (c :: rest) then
        go fuel ((c :: rest).drop sepChars.length) (sepChars.getLast?) depth [] (String.ofList current.reverse :: parts)
      else go fuel rest (some c) depth (c :: current) parts
  (go (chars.length + 1) chars none 0 [] []).reverse.map Minidregg.Compiler.ObjectiveBendElaborate.trimStr

/-- `ticksUsed` of a reply, a number or a decimal string. -/
def ticksOf (reply : Json) : Nat :=
  match reply.getObjVal? "ticksUsed" with
  | .ok (.num n) => n.mantissa.toNat
  | .ok (.str s) => s.toNat?.getD 0
  | _ => 0

def requestClass (request : Json) : String :=
  let text := fun (k : String) => (request.getObjValAs? String k).toOption.getD ""
  let entry := ((request.getObjVal? "artifact").toOption.bind fun a => (a.getObjValAs? String "entry").toOption).getD ""
  let object := text "object"
  -- one class per kind of object, not per instance (`garden/bell/2`, `env/did:…`)
  let kind := match object.splitOn "/" with | first :: _ :: _ => first ++ "/*" | _ => object
  " ".intercalate ([text "op", kind, text "method", entry].filter (· != ""))

def replay (lines : Array String) (dir : String) (filter : String) (repeats : Nat) : IO Unit := do
  if ← System.FilePath.pathExists dir then IO.FS.removeDirAll dir
  IO.FS.createDirAll dir
  let mut session : Delvetalk.PackageSession.Session := {}
  -- class -> (requests, fastest wall summed in ns, ticks summed)
  let mut tally : Std.HashMap String (Nat × Nat × Nat) := {}
  let mut order : Array String := #[]
  for line in lines do
    if line.isEmpty then continue
    let request ← IO.ofExcept (Json.parse line)
    let request := if (request.getObjValAs? String "op").toOption == some "world-open" then
      (request.setObjVal! "path" (toJson s!"{dir}/world.journal")).setObjVal! "sync" (toJson "none")
      else request
    let cls := requestClass request
    let runs := if cls.startsWith filter then repeats else 1
    let mut best := 0
    let mut next := session
    let mut ticks := 0
    for i in [0:runs] do
      let t0 ← IO.monoNanosNow
      let (after, result) ← Delvetalk.PackageSession.stepIO session request
      let t1 ← IO.monoNanosNow
      if i == 0 || t1 - t0 < best then best := t1 - t0
      next := after
      ticks := match result with | .ok reply => ticksOf reply | .error _ => 0
    session := next
    if runs > 1 then IO.println s!"  {cls}: {best / 1000} us, {ticks} ticks"
    if !tally.contains cls then order := order.push cls
    tally := tally.alter cls fun
      | some (n, ns, t) => some (n + 1, ns + best, t + ticks)
      | none => some (1, best, ticks)
  IO.println "class\trequests\tms\tticks\tticks/s"
  for cls in order do
    let (n, ns, t) := tally.getD cls (0, 0, 0)
    let rate := if ns == 0 then 0 else t * 1000000000 / ns
    if cls.startsWith filter || ns > 100000000 then
      IO.println s!"{cls}\t{n}\t{ns / 1000000}\t{t}\t{rate}"

/-! SHA-256 as it was written before the unboxed-window rounds (the reference for
`Sha256.digest` in `self-check`): the schedule stored in an `Array`. -/
namespace ShaRef
open Minidregg.Compiler.Sha256
def schedule (bytes : ByteArray) (offset : Nat) : Array UInt32 := Id.run do
  let mut w : Array UInt32 := Array.mkEmpty 64
  for t in [0:16] do w := w.push (word bytes (offset + 4 * t))
  for t in [16:64] do
    let x := w[t - 15]!
    let y := w[t - 2]!
    let s0 := rotr x 7 ^^^ rotr x 18 ^^^ (x >>> 3)
    let s1 := rotr y 17 ^^^ rotr y 19 ^^^ (y >>> 10)
    w := w.push (w[t - 16]! + s0 + w[t - 7]! + s1)
  return w
def rounds (w : Array UInt32) (t : Nat) (a b c d e f g h : UInt32) : UInt32 × UInt32 × UInt32 × UInt32 × UInt32 × UInt32 × UInt32 × UInt32 :=
  if t < 64 then
    let t1 := h + (rotr e 6 ^^^ rotr e 11 ^^^ rotr e 25) + ((e &&& f) ^^^ (~~~e &&& g)) + k[t]! + w[t]!
    let t2 := (rotr a 2 ^^^ rotr a 13 ^^^ rotr a 22) + ((a &&& b) ^^^ (a &&& c) ^^^ (b &&& c))
    rounds w (t + 1) (t1 + t2) a b c (d + t1) e f g
  else (a, b, c, d, e, f, g, h)
termination_by 64 - t
def compress (state : Array UInt32) (bytes : ByteArray) (offset : Nat) : Array UInt32 :=
  let (a, b, c, d, e, f, g, h) := rounds (schedule bytes offset) 0
    state[0]! state[1]! state[2]! state[3]! state[4]! state[5]! state[6]! state[7]!
  #[state[0]! + a, state[1]! + b, state[2]! + c, state[3]! + d,
    state[4]! + e, state[5]! + f, state[6]! + g, state[7]! + h]
def digest (message : ByteArray) : Array UInt32 := Id.run do
  let full := message.size / 64
  let mut state := initial
  for block in [0:full] do state := compress state message (64 * block)
  let tail := padTail (message.extract (64 * full) message.size) message.size
  for block in [0:tail.size / 64] do state := compress state tail (64 * block)
  return state
end ShaRef

def main (args : List String) : IO Unit := do
  if args[0]! == "replay" then
    let lines := (← IO.FS.lines args[1]!)
    replay lines args[2]! args[3]! args[4]!.toNat!
    return
  if args[0]! == "self-check" then
    let alphabet := "ab ,:-><(){}w ith\té\n".toList.toArray
    let seps := #["->", ",", " with ", ":"]
    let mut seed := 777
    let mut bad := 0
    for _ in [0:300000] do
      let mut str : List Char := []
      seed := (seed * 1103515245 + 12345) % 2147483648
      let len := seed % 14
      for _ in [0:len] do
        seed := (seed * 1103515245 + 12345) % 2147483648
        str := str ++ [alphabet[seed % alphabet.size]!]
      let sep := seps[seed % 4]!
      let t := String.ofList str
      if splitTopRef t sep != Minidregg.Compiler.ObjectiveBendElaborate.splitTop t sep then
        bad := bad + 1
        if bad < 10 then IO.println s!"differ {repr t} {repr sep}: {splitTopRef t sep} vs {Minidregg.Compiler.ObjectiveBendElaborate.splitTop t sep}"
    IO.println s!"splitTop mismatches {bad}"
    let splitBad := bad
    let alphabet := "ab_1n\"\\\n:-><=!&|{}().,+*/%x é".toList.toArray
    seed := 12345
    bad := 0
    for _ in [0:300000] do
      let mut str : List Char := []
      seed := (seed * 1103515245 + 12345) % 2147483648
      let len := seed % 9
      for _ in [0:len] do
        seed := (seed * 1103515245 + 12345) % 2147483648
        str := str ++ [alphabet[seed % alphabet.size]!]
      let viaRe := match Minidregg.Compiler.ObjectiveBendParse.anchored Minidregg.Compiler.ObjectiveBendParse.tokenRe str with
        | .ok (some (stop, _)) => some stop
        | _ => none
      if viaRe != Minidregg.Compiler.ObjectiveBendParse.tokenLength str then
        bad := bad + 1
        if bad < 10 then IO.println s!"differ on {repr (String.ofList str)}: {viaRe} vs {Minidregg.Compiler.ObjectiveBendParse.tokenLength str}"
    IO.println s!"tokenLength mismatches {bad}"
    let tokenBad := bad
    -- SHA-256: FIPS 180-4 vectors, then the reference on every length 0..400 and 1 MB
    bad := 0
    for (text, expected) in [("", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        ("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
          "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1")] do
      if Minidregg.Compiler.Sha256.hexString text != expected then
        bad := bad + 1
        IO.println s!"sha256 {repr text} is {Minidregg.Compiler.Sha256.hexString text}"
    seed := 4242
    for len in [0:401] do
      let mut bytes := ByteArray.empty
      for _ in [0:len] do
        seed := (seed * 1103515245 + 12345) % 2147483648
        bytes := bytes.push (UInt8.ofNat (seed % 256))
      if Minidregg.Compiler.Sha256.digest bytes != ShaRef.digest bytes then
        bad := bad + 1
        if bad < 10 then IO.println s!"sha256 differs at length {len}"
    let big := (String.ofList (List.replicate 1000000 'a')).toUTF8
    if Minidregg.Compiler.Sha256.digest big != ShaRef.digest big then bad := bad + 1
    IO.println s!"sha256 mismatches {bad}"
    if splitBad + tokenBad + bad > 0 then IO.Process.exit 1
    return
  if args[0]! == "wire" then
    let line := (← IO.FS.readFile args[1]!).trimRight
    for _ in [0:3] do
      discard <| timed "scalarEscapes" fun _ => pure (Delvetalk.scalarEscapesText line)
      let j ← timed "Json.parse request" fun _ => Json.parse line
      let req := j.setObjVal! "entry" (toJson "initial")
      let request ← IO.ofExcept ((Delvetalk.Package.prepareRequest req).mapError (·.message))
      let c ← timed "compileEntryFrom initial" fun _ => (Delvetalk.Package.compileEntryFrom request "initial").mapError (·.message)
      discard <| timed "artifact compress" fun _ => pure c.artifact.compress.length
      discard <| timed "artifact size" fun _ => pure (Delvetalk.PackageSession.compressedSize c.artifact)
      IO.println s!"sizes {c.artifact.compress.utf8ByteSize} {Delvetalk.PackageSession.compressedSize c.artifact}"
      discard <| timed "sourcesSha256" fun _ => pure (Delvetalk.Canonical.cidJson request.sources)
    return
  if args[0]! == "sha" then
    let big := String.ofList (List.replicate 1000000 'a')
    for _ in [0:3] do
      discard <| timed "sha256 1MB" fun _ => pure (Minidregg.Compiler.Sha256.hexString big)
    return
  let req ← IO.ofExcept (Json.parse (← IO.FS.readFile args[0]!))
  let entries := args.drop 1
  if entries.head? == some "loop" then
    let stage := entries[1]!
    let n := entries[2]!.toNat!
    let (modules, _, asts) ← IO.ofExcept ((Delvetalk.Package.modulesAndAsts req).mapError (·.message))
    let srcs := (modules.zip asts).map fun (module, ast) => Delvetalk.Generics.Source.mk module ast
    let specialized ← IO.ofExcept (Delvetalk.Generics.run srcs.toArray)
    let elaborated ← IO.ofExcept (ObjectiveBendElaborate.elaboratePackage specialized.modules)
    let limits := Delvetalk.Package.getLimits req
    let whole := elaborated.whole
    let lw := Lowering.make whole whole.term "" "unapplied-definition" "definition" modules limits 4096 []
    let pk ← IO.ofExcept (decodePacket lw.packet)
    for i in [0:n] do
      let r : Nat ← match stage with
        | "parse" => IO.ofExcept ((Delvetalk.Package.modulesAndAsts (req.setObjVal! "x" (toJson i))).map (·.1.length) |>.mapError (·.message))
        | "generics" => IO.ofExcept ((Delvetalk.Generics.run (srcs.toArray.push default |>.pop)).map (·.modules.length))
        | "elaborate" => IO.ofExcept ((ObjectiveBendElaborate.elaboratePackage (specialized.modules ++ [])).map (·.fields.length))
        | "lower" => pure (Lowering.make whole whole.term (toString i) "unapplied-definition" "definition" modules limits 4096 []).packet.compress.length
        | "check" => pure (match check { pk.source with assumptions := { pk.source.assumptions with rigid := [i + 100000] } } [] pk.fuel with | some _ => 1 | none => 0)
        | _ => pure 0
      if r == 12345678 then IO.println "x"
    return
  for round in [0:3] do
    IO.println s!"--- round {round}"
    let (modules, sources, asts) ← timed "parse (modulesAndAsts)" fun _ => (Delvetalk.Package.modulesAndAsts req).mapError (·.message)
    let srcs := (modules.zip asts).map fun (module, ast) => Delvetalk.Generics.Source.mk module ast
    let specialized ← timed "generics" fun _ => Delvetalk.Generics.run srcs.toArray
    let elaborated ← timed "elaboratePackage" fun _ => ObjectiveBendElaborate.elaboratePackage specialized.modules
    let limits := Delvetalk.Package.getLimits req
    let (_, typeFuel) ← IO.ofExcept ((options (.arr #[]) limits "definition").mapError (·.message))
    let whole := elaborated.whole
    timed "checkTemplates" fun _ => (checkTemplates whole typeFuel).mapError (·.message)
    let pr ← timed "  propose" fun _ => ObjectiveBendElaborate.propose whole
    let er ← timed "  erase" fun _ => whole.term.erase
    let ds ← timed "  directSource" fun _ => pure (directSource pr er)
    discard <| timed "  check direct" fun _ => match check ds [] 4096 with | some c => pure c.type | none => throw "refused"
    IO.println s!"  annotations {pr.annotations.length}"
    discard <| timed "whole checkDirect" fun _ => (checkDirect whole typeFuel []).mapError (·.message)
    let lw ← timed "whole lowering (proposal+packet)" fun _ => do
      let l := Lowering.make whole whole.term "" "unapplied-definition" "definition" modules limits typeFuel []
      match l.proposal with | .ok _ => pure () | .error e => throw e
      pure l
    let pk ← timed "whole decodePacket" fun _ => decodePacket lw.packet
    discard <| timed "whole check" fun _ => match check pk.source [] pk.fuel with | some c => pure c.type | none => throw "refused"
    let prepared : Delvetalk.FrontEnd.Prepared := ⟨modules, asts, specialized.modules, elaborated, specialized.instances⟩
    let request : Delvetalk.Package.PreparedRequest := ⟨prepared, sources, limits, Delvetalk.Canonical.cidJson sources⟩
    for e in entries do
      IO.println s!"  entry {e}"
      let lowered ← timed "    select" fun _ => (prepared.lower (modules.length - 1) e (.arr #[]) (.arr #[]) limits "definition").mapError (·.message)
      discard <| timed "    proposal" fun _ => lowered.proposal
      discard <| timed "    packet json" fun _ => pure lowered.packet.compress.length
      let pk ← timed "    decodePacket" fun _ => decodePacket lowered.packet
      discard <| timed "    check" fun _ => match check pk.source [] pk.fuel with | some c => pure c.type | none => throw "refused"
      discard <| timed "    cid" fun _ => pure (Delvetalk.Canonical.cidJson lowered.packet)
      let bytes ← timed "    cbor" fun _ => Delvetalk.Canonical.encodeJson lowered.packet
      IO.println s!"    cbor bytes {bytes.size}"
      discard <| timed "    sha of cbor" fun _ => pure (Minidregg.Compiler.Sha256.digest bytes)
      discard <| timed "    compileEntryFrom total" fun _ => (Delvetalk.Package.compileEntryFrom request e).mapError (·.message)
