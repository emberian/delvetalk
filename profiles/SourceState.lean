/- Compact typed custody resolves its schema only in the caller-held protocol.
The exact selected packet hash is checked before interpreting positional bytes.
No state schema is guessed from a newer/different program. -/
import SourcePackages
import Delvetalk.Package

namespace SourceState
open Lean
open Minidregg.Theory.ObjectiveBendDemandData (Data)
abbrev Work := Delvetalk.PackageData.Work

def format : String := "delvetalk-compact-state"

private def exact (j : Json) (keys : List String) : Except String Unit := do
  let actual := (← j.getObj?).toArray.map Prod.fst
  unless actual.size == keys.length && keys.all actual.contains do
    throw "compact state has missing or unknown fields"

/-- Inline schemas must be an actual retained executable descriptor. Explicit
selectors resolve only in the protocol's retained source table. A state envelope
cannot smuggle unrelated source and claim it is the object's schema. -/
def retainedSpec (protocol descriptor : Json) : Except String Json := do
  if (descriptor.getObjValAs? String "format").toOption == some SourcePackages.referenceFormat then
    return ← SourcePackages.resolve protocol descriptor
  let viewMatch := match (protocol.getObjVal? "viewProgram").toOption with
    | some view => (view.getObjVal? "package").toOption == some descriptor
    | none => false
  let commands ← (← protocol.getObjVal? "commands").getObj?
  let commandMatch := commands.toList.any fun (_, command) =>
    ((command.getObjVal? "transition").bind fun transition => transition.getObjVal? "package").toOption == some descriptor
  unless viewMatch || commandMatch do throw "compact schema is not retained by this protocol"
  return descriptor

structure Resolved where
  artifact : Json
  assumptions : Minidregg.Theory.ObjectiveBendTyping.Assumptions
  type : Minidregg.Theory.ObjectiveBendTypes.Ty

section
variable {m : Type → Type} [Monad m] [MonadExceptOf String m]
  [MonadLiftT Work m] [MonadLiftT (Except String) m]

/-- All callers select schemas through the same checked retained source route. -/
def resolveWith (compile : Json → m Json) (protocol descriptor path : Json) : m Resolved := do
  let spec ← retainedSpec protocol descriptor
  let artifact ← compile spec
  let packet ← Minidregg.Theory.ObjectiveBendTyping.decodePacket (← artifact.getObjVal? "packet")
  let some checked := Minidregg.Theory.ObjectiveBendTyping.check packet.source [] packet.fuel
    | throw "compact schema checker refusal"
  let ty ← Delvetalk.PackageData.select packet.source.assumptions checked.type path
  Delvetalk.PackageData.shape packet.source.assumptions 256 [] ty
  return ⟨artifact, packet.source.assumptions, ty⟩

def readWith (compile : Json → m Json) (protocol model : Json) : m Data := do
  if (model.getObjValAs? String "tag").toOption == some "record" then
    return ← Delvetalk.PackageData.decode 256 model
  unless (model.getObjValAs? String "format").toOption == some format do
    throw "unknown source state codec"
  exact model ["format", "schema", "value"]
  let schema ← model.getObjVal? "schema"
  exact schema ["package", "path", "packetSha256", "sourcesSha256"]
  let selected ← resolveWith compile protocol (← schema.getObjVal? "package") (← schema.getObjVal? "path")
  unless (← schema.getObjValAs? String "packetSha256") == (← selected.artifact.getObjValAs? String "packetSha256") do
    throw "compact state schema differs from retained program"
  unless (← schema.getObjValAs? String "sourcesSha256") == (← selected.artifact.getObjValAs? String "sourcesSha256") do
    throw "compact state source differs from retained program"
  -- The selected codec checks every node against this exact schema itself.
  Delvetalk.PackageData.decodeCompact selected.assumptions 256 selected.type (← model.getObjVal? "value")

def writeWith (compile : Json → m Json) (protocol descriptor path : Json) (data : Data) : m Json := do
  let selected ← resolveWith compile protocol descriptor path
  let value ← Delvetalk.PackageData.encodeCompact selected.assumptions 256 selected.type data
  return Json.mkObj [("format", toJson format), ("value", value), ("schema", Json.mkObj [
    ("package", descriptor), ("path", path), ("packetSha256", ← selected.artifact.getObjVal? "packetSha256"),
    ("sourcesSha256", ← selected.artifact.getObjVal? "sourcesSha256")])]

/-- Select the child's retained initial-state schema, never producer-authored framing. -/
def initialSchema (protocol : Json) : Except String (Json × Json) := do
  let initial ← (← protocol.getObjVal? "initial").getObjVal? "model"
  if (initial.getObjValAs? String "format").toOption == some format then
    let schema ← initial.getObjVal? "schema"
    return (← schema.getObjVal? "package", ← schema.getObjVal? "path")
  match (protocol.getObjVal? "viewProgram").toOption with
  | some view => return (← view.getObjVal? "package", Json.arr #[.str "domain"])
  | none =>
    let commands ← (← protocol.getObjVal? "commands").getObj?
    let some (_, command) := commands.toList.head? | throw "child has no selected state schema"
    return (← (← command.getObjVal? "transition").getObjVal? "package", Json.arr #[.str "domain"])

/-- Bind an initial envelope's claimed schema to the exact retained artifact.
This checks the claim without decoding a default model that configuration replaces. -/
def checkedInitialSchemaWith (compile : Json → m Json) (protocol : Json) : m (Json × Json) := do
  let selection ← initialSchema protocol
  let initial ← (← protocol.getObjVal? "initial").getObjVal? "model"
  if (initial.getObjValAs? String "format").toOption == some format then
    exact initial ["format", "schema", "value"]
    let schema ← initial.getObjVal? "schema"
    exact schema ["package", "path", "packetSha256", "sourcesSha256"]
    let selected ← resolveWith compile protocol selection.1 selection.2
    unless (← schema.getObjValAs? String "packetSha256") == (← selected.artifact.getObjValAs? String "packetSha256") do
      throw "compact state schema differs from retained program"
    unless (← schema.getObjValAs? String "sourcesSha256") == (← selected.artifact.getObjValAs? String "sourcesSha256") do
      throw "compact state source differs from retained program"
  return selection

/-- A retained initial schema must describe the state actually consumed by
all current views and commands, not merely another valid export in the table. -/
def coherentInitialWith (compile : Json → m Json) (protocol : Json) : m Resolved := do
  let (descriptor, path) ← checkedInitialSchemaWith compile protocol
  let initial ← resolveWith compile protocol descriptor path
  let check (descriptor : Json) (kind : String) : m Unit := do
    let consumed ← resolveWith compile protocol descriptor (Json.arr #[.str "domain"])
    unless (← Delvetalk.PackageData.equivalent initial.assumptions consumed.assumptions 256 [] initial.type consumed.type) do
      throw ("initial state schema differs from " ++ kind ++ " state domain")
  if let some view := (protocol.getObjVal? "viewProgram").toOption then
    check (← view.getObjVal? "package") "view"
  let commands ← (← protocol.getObjVal? "commands").getObj?
  for (_, command) in commands.toList do
    check (← (← command.getObjVal? "transition").getObjVal? "package") "command"
  return initial

/-- A typed source effect never authors envelope encoding. Frame its already
checked Data against the observed recipient's actual exported input schema. -/
def inputWireWith (compile : Json → m Json) (protocol : Json) (command : String) (data : Data) : m Json := do
  let descriptor ← (← (← protocol.getObjVal? "commands").getObjVal? command).getObjVal? "transition"
  if (descriptor.getObjValAs? String "inputCodec").toOption != some "compact" then
    return Minidregg.Compiler.ObjectiveBendDataWire.dataJson data
  unless (descriptor.getObjValAs? String "profile").toOption == some "delvetalk-source-transition" do
    throw "unknown source transition profile"
  let selected ← resolveWith compile protocol (← descriptor.getObjVal? "package") (.arr #[.str "codomain", .str "domain"])
  let value ← Delvetalk.PackageData.encodeCompact selected.assumptions 256 selected.type data
  return Json.mkObj [("schemaPacketSha256", ← selected.artifact.getObjVal? "packetSha256"), ("value", value)]

/-- Recode an explicitly supplied compact migration against its actual old
source, then the replacement's declared schema. Never reinterpret old bytes. -/
def recodeWith (compile : Json → m Json) (oldProtocol newProtocol state : Json) : m Json := do
  exact state ["model"]
  let model ← state.getObjVal? "model"
  if (model.getObjValAs? String "format").toOption != some format then return state
  let schema ← model.getObjVal? "schema"
  let newArtifact ← (try
    let spec ← retainedSpec newProtocol (← schema.getObjVal? "package")
    pure (.ok (← compile spec))
    catch error => pure (.error error) : m (Except String Json))
  let alreadyNew := match newArtifact with
    | .ok artifact => (schema.getObjVal? "sourcesSha256").toOption == (artifact.getObjVal? "sourcesSha256").toOption &&
        (schema.getObjVal? "packetSha256").toOption == (artifact.getObjVal? "packetSha256").toOption
    | .error _ => false
  if alreadyNew then
    let _ ← readWith compile newProtocol model
    return state
  let data ← readWith compile oldProtocol model
  let initial ← (← newProtocol.getObjVal? "initial").getObjVal? "model"
  let (descriptor, path) ← if (initial.getObjValAs? String "format").toOption == some format then do
    let schema ← initial.getObjVal? "schema"
    pure (← schema.getObjVal? "package", ← schema.getObjVal? "path")
    else match (newProtocol.getObjVal? "viewProgram").toOption with
    | some view => pure (← view.getObjVal? "package", Json.arr #[.str "domain"])
    | none =>
      let commands ← (← newProtocol.getObjVal? "commands").getObj?
      let some (_, command) := commands.toList.head? | throw "replacement has no selected state schema"
      pure (← (← command.getObjVal? "transition").getObjVal? "package", Json.arr #[.str "domain"])
  return Json.mkObj [("model", ← writeWith compile newProtocol descriptor path data)]

end

-- Pure custody/inspection consumers keep the original interfaces. Receiving
-- consumers inject the same compiler through per-turn checked-artifact custody.
def resolve (protocol descriptor path : Json) : Work Resolved :=
  resolveWith (fun spec => Delvetalk.Package.compile spec) protocol descriptor path

def read (protocol model : Json) : Work Data :=
  readWith (fun spec => Delvetalk.Package.compile spec) protocol model

def write (protocol descriptor path : Json) (data : Data) : Work Json :=
  writeWith (fun spec => Delvetalk.Package.compile spec) protocol descriptor path data

def inputWire (protocol : Json) (command : String) (data : Data) : Work Json :=
  inputWireWith (fun spec => Delvetalk.Package.compile spec) protocol command data

def recode (oldProtocol newProtocol state : Json) : Work Json :=
  recodeWith (fun spec => Delvetalk.Package.compile spec) oldProtocol newProtocol state

/-- Pure inspection of a caller-held root; no acquisition, current-read grant,
mutation or source behavior is performed by this physical decoding query. -/
def inspect (request : Json) : Except String Json := do
  exact request ["op", "root"]
  let root ← request.getObjVal? "root"
  let (data, remaining) ← (read (← root.getObjVal? "protocol")
    (← (← root.getObjVal? "state").getObjVal? "model")).run 100000
  return Json.mkObj [("status", toJson "decoded"),
    ("value", Minidregg.Compiler.ObjectiveBendDataWire.dataJson data),
    ("conversionNodes", toJson (100000 - remaining))]

end SourceState
