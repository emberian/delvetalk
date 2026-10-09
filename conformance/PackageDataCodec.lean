/- Executable regression probe: strict package framing, duplicate refusal,
record order, exact naturals, and generic response duplicate preservation. -/
import Delvetalk.Package
open Lean
open Delvetalk.PackageData
open Minidregg.Compiler.ObjectiveBendDataWire
open Minidregg.Theory.ObjectiveBendDemandData
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendTypes

def identityPacket (domain : Ty) (quantity : Quantity)
    (bounds : List (Nat × Ty) := []) (shareable : List Nat := []) (context : Json := .arr #[]) : Json :=
  Json.mkObj [
    ("schema", toJson "dregg.objective-bend.typed-core.v3"), ("types", .arr #[]),
    ("term", Json.mkObj [("tag", toJson "lam"), ("body", Json.mkObj
      [("tag", toJson "bound"), ("index", toJson 0)])]),
    ("annotations", .arr #[Json.mkObj [("path", .arr #[]), ("domain", typeJson domain),
      ("codomain", typeJson domain), ("parameter", quantityJson quantity), ("reuse", reuseJson .once)]]),
    ("bounds", .arr (bounds.map (fun (index, type) => Json.mkObj
      [("index", toJson index), ("type", typeJson type)])).toArray),
    ("shareableVariables", toJson shareable), ("context", context), ("fuel", toJson 256)]

def main : IO Unit := do
  let fields := (List.range 200).map fun n => (s!"field{n}", Data.natural n)
  let datum := Data.record fields
  let wire := dataJson datum
  let .ok (decoded, remaining) := (decode 256 wire).run 10000
    | throw (IO.userError "strict record decode failed")
  unless dataJsonBytes datum == wire.compress.utf8ByteSize do throw (IO.userError "wire byte count differs")
  unless dataJson decoded == wire do throw (IO.userError "record order changed")
  for leaf in [Data.boolean true, .boolean false, .label "a\n\"\\λ", .record [], .variant "a\nλ" (.label "payload")] do
    unless dataJsonBytes leaf == (dataJson leaf).compress.utf8ByteSize do
      throw (IO.userError "leaf wire bytes differ")
  unless remaining == 8997 do throw (IO.userError s!"work changed: {remaining}")
  let duplicated := dataJson (Data.record [("x", .natural 1), ("x", .natural 2)])
  match (decode 256 duplicated).run 10000 with
  | .error "duplicate typed data field" => pure ()
  | _ => throw (IO.userError "strict duplicate was accepted")
  let .ok permissive := decodeData 256 duplicated
    | throw (IO.userError "generic duplicate decode failed")
  unless dataJson permissive == duplicated do throw (IO.userError "generic duplicate order changed")
  let large := Data.natural (2^256 + 12345)
  let .ok (decodedLarge, _) := (decode 256 (dataJson large)).run 100
    | throw (IO.userError "large natural decode failed")
  unless dataJson decodedLarge == dataJson large do throw (IO.userError "natural lost precision")
  let aliases : Assumptions := { bounds := [(0, .variant (.field "nil" .emptyRow
    (.field "cons" (.field "head" .natural (.field "tail" (.variable 0) .emptyRow)) .emptyRow)))] }
  let list (size : Nat) : Data := (List.range size).reverse.foldl
    (fun tail n => .variant "cons" (.record [("head", .natural n), ("tail", tail)]))
    (.variant "nil" (.record []))
  -- Dynamic depth counts the same variant and record visits as the old codec;
  -- finite alias/schema preprocessing has its own charged 256-deep bound.
  let boundary := list 127
  let .ok (encoded, _) := (encodeCompact aliases 256 (.variable 0) boundary).run 100000
    | throw (IO.userError "valid recursive depth boundary refused")
  let .ok (back, _) := (decodeCompact aliases 256 (.variable 0) encoded).run 100000
    | throw (IO.userError "recursive codec boundary decode refused")
  unless dataJson back == dataJson boundary do throw (IO.userError "recursive codec changed data")
  let .ok (_, validationLeft) := (validate aliases 256 boundary (.variable 0)).run 100000
    | throw (IO.userError "recursive validation boundary refused")
  match (validate aliases 256 boundary (.variable 0)).run (100000 - validationLeft - 1) with
  | .error "typed data work capacity" => pure ()
  | _ => throw (IO.userError "static preprocessing/value visits escaped shared fuel")
  for action in [validate aliases 256 (list 128) (.variable 0),
      (encodeCompact aliases 256 (.variable 0) (list 128)).map (fun _ => ())] do
    match action.run 100000 with
    | .error "typed data nesting capacity" => pure ()
    | _ => throw (IO.userError "recursive data depth cap weakened")
  let wide := (List.range 257).foldr (fun n tail => Ty.field s!"field{n}" .natural tail) .emptyRow
  match (schemaGraph {} false 256 wide).run 100000 with
  | .error "typed data nesting capacity" => pure ()
  | _ => throw (IO.userError "static schema depth cap weakened")
  match (encodeCompact {} 256 (.field "x" .natural .emptyRow)
      (.record [("x", .natural 1), ("x", .natural 2)])).run 100000 with
  | .error _ => pure ()
  | _ => throw (IO.userError "compact duplicate data field accepted")
  let rigid := { aliases with rigid := [0] }
  match (validate rigid 256 boundary (.variable 0)).run 100000 with
  | .error "typed data requires a transparent sum alias" => pure ()
  | _ => throw (IO.userError "rigid bound treated as recursive alias")
  let source := "edition ObjectiveBend 1\nrecord Box:\n  x: Nat\n  y: Nat\ndef identity(value: Box) -> Box:\n  value\n"
  let .ok artifact := Delvetalk.Package.compile (Json.mkObj [("source", toJson source), ("entry", toJson "identity")])
    | throw (IO.userError "native admission fixture compilation failed")
  let .ok packet := artifact.getObjVal? "packet" | throw (IO.userError "native fixture packet missing")
  let reordered := Data.record [("y", .natural 2), ("x", .natural 1)]
  let .ok (native, _) := (prepareNative packet #[reordered]).run 100000
    | throw (IO.userError "native typed preparation refused valid reordered record")
  unless native.arguments.toList.map dataJson ==
      [dataJson (.record [("x", .natural 1), ("y", .natural 2)])] do
    throw (IO.userError "native preparation changed declared field order")
  let .ok ((_, quotedType, _), _) := (prepareValues packet #[reordered]).run 100000
    | throw (IO.userError "quoted differential preparation refused")
  unless native.resultType == quotedType do
    throw (IO.userError "native and quoted preparation selected different result types")
  let .ok (.finished nativeValue nativeType _ nativeUsage) :=
      Delvetalk.Package.executeDataValues packet #[reordered] (.mkObj [])
    | throw (IO.userError "native record execution refused")
  let .ok (.finished quotedValue quotedType _ quotedUsage) :=
      Delvetalk.Package.executeQuotedDataValue packet (.arr #[dataJson reordered]) (.mkObj [])
    | throw (IO.userError "quoted record execution refused")
  unless dataJson nativeValue == dataJson quotedValue && nativeType == quotedType do
    throw (IO.userError "native/quoted execution changed value or selected type")
  unless nativeUsage.ticksUsed < quotedUsage.ticksUsed do
    throw (IO.userError "native first force still performs source literal transitions")
  match Delvetalk.Package.executeDataValuesSized packet #[reordered] 1048577 (.mkObj []) with
  | .error "typed data input byte capacity" => pure ()
  | _ => throw (IO.userError "native execution bypassed actual physical input bound")
  let .ok decodedPacket := decodePacket packet
    | throw (IO.userError "checker cutoff fixture decode failed")
  let mut low := 1
  let mut high := decodedPacket.fuel
  while low < high do
    let middle := (low + high) / 2
    if (check decodedPacket.source [] middle).isSome then high := middle
    else low := middle + 1
  let .ok packetFields := packet.getObj?
    | throw (IO.userError "checker cutoff packet fields missing")
  let cutoffPacket := Json.mkObj (packetFields.toList.map fun (name, value) =>
    (name, if name == "fuel" then toJson low else value))
  match (prepareNative cutoffPacket #[reordered]).run 100000 with
  | .ok _ => pure ()
  | .error _ => throw (IO.userError "native domain admission reused whole-application checker cutoff")
  match (prepareValues cutoffPacket #[reordered]).run 100000 with
  | .error "applied typed package refused by Mini type checker" => pure ()
  | _ => throw (IO.userError "quoted checker cutoff reference changed")
  let sumType := Ty.variant (.field "some" .natural .emptyRow)
  let sumData := Data.variant "some" (.natural 9)
  for (quantity, shareable) in [(Quantity.linear, []), (.unrestricted, [0])] do
    let p := identityPacket (.variable 0) quantity [(0, sumType)] shareable
    match (prepareNative p #[sumData]).run 100000, (prepareValues p #[sumData]).run 100000 with
    | .ok (native, _), .ok ((_, oldType, _), _) =>
      unless native.resultType == oldType do throw (IO.userError "alias/quantity result type changed")
    | _, _ => throw (IO.userError "valid transparent alias/quantity refused")
  let captures := Json.arr #[Json.mkObj [("type", typeJson .natural), ("quantity", quantityJson .linear)]]
  for (p, value) in [
      (identityPacket (.variable 0) .unrestricted [(0, sumType)], sumData),
      (identityPacket .natural .erased, Data.natural 1),
      (identityPacket .natural .linear [] [] captures, Data.natural 1),
      (identityPacket (.specification .natural .natural) .linear, Data.natural 1),
      (identityPacket (.computation .natural .natural .natural) .linear, Data.natural 1),
      (identityPacket (.variable 0) .linear [(0, sumType)], Data.variant "unknown" (.natural 1))] do
    match (prepareNative p #[value]).run 100000, (prepareValues p #[value]).run 100000 with
    | .error _, .error _ => pure ()
    | _, _ => throw (IO.userError "native/quoted admission refusal differs")
  let duplicate := Data.record [("x", .natural 1), ("x", .natural 2)]
  match Delvetalk.Package.executeDataValues packet #[duplicate] (.mkObj []) with
  | .error _ => pure ()
  | _ => throw (IO.userError "fused native quotation accepted duplicate fields")
  let listSource := "edition ObjectiveBend 1\nsum List:\n  nil: {}\n  cons: {head: Nat, tail: List}\ndef identity(value: List) -> List:\n  value\n"
  let .ok listArtifact := Delvetalk.Package.compile (Json.mkObj [("source", toJson listSource), ("entry", toJson "identity")])
    | throw (IO.userError "native depth fixture compilation failed")
  let .ok listPacket := listArtifact.getObjVal? "packet" | throw (IO.userError "native depth packet missing")
  match Delvetalk.Package.executeDataValues listPacket #[list 128] (.mkObj []) with
  | .error "typed data nesting capacity" => pure ()
  | _ => throw (IO.userError "fused native quotation weakened depth cap")
  IO.println "typed data codec/order/exact natural/duplicate/depth/shared-work regression passed"
