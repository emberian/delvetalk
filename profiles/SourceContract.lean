/- Law-owned source interface bounds. This compares checker-verified method
   schemas; metadata claims are retained description, never behavioral proofs. -/
import SourceState
import WorldCore
import SourcePackages
import Delvetalk.Package
import Delvetalk.Reflection

namespace SourceContract
open Lean World
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendTyping

/-- Ground leaves use the existing recursive-data equivalence, including each
    packet's own alias table. We compare only the finite outer method arrows. -/
def sameSignature (left right : Assumptions) : Nat → Ty → Ty → Evaluation Bool
  | 0, _, _ => throw "source contract method arity exceeds eight"
  | fuel + 1, a, b => do
    tick
    match a, b with
    | .arrow ar aq ad ac, .arrow br bq bd bc =>
        if ar != br || aq != bq then return false
        Delvetalk.PackageData.shape left 256 [] ad
        Delvetalk.PackageData.shape right 256 [] bd
        if !(← Delvetalk.PackageData.equivalent left right 256 [] ad bd) then return false
        sameSignature left right fuel ac bc
    | .arrow .., _ | _, .arrow .. => return false
    | _, _ =>
        Delvetalk.PackageData.shape left 256 [] a
        Delvetalk.PackageData.shape right 256 [] b
        Delvetalk.PackageData.equivalent left right 256 [] a b

def charge (amount : Nat) : Evaluation Unit := Delvetalk.PackageData.spend amount

def exact (j : Json) (keys : List String) : Except String Unit := do
  let names := (← pairs j).map Prod.fst
  unless names.length == keys.length && names.all keys.contains do
    throw "source contract has missing or unknown fields"

def signature (artifact : Json) : Except String (Assumptions × Ty) := do
  let packet ← decodePacket (← field artifact "packet")
  unless packet.context.isEmpty do throw "source contract requires a closed package"
  let some checked := check packet.source [] packet.fuel | throw "source contract checker refusal"
  return (packet.source.assumptions, checked.type)

/-- Every candidate state is checked against the law-owned source schema. Method
    packages and metadata are additionally checked at creation/program/law changes.
    Compile is the receiving executable's source-only compiler, never a supplied
    packet. At most one specification and sixteen required methods are compiled. -/
def check (compile : Json → Evaluation Json) (contract candidate : Json)
    (checkMethods : Bool) : Evaluation Unit := do
  exact contract ["profile", "package", "stateProfile", "metadata"]
  if (← str contract "profile") != "delvetalk-source-contract-v1" then
    throw "unknown source contract profile"
  let mode ← str contract "stateProfile"
  if mode != "model" then throw "source contracts require the current model state profile"
  -- A law package is self-contained. It never resolves names in the candidate.
  let package ← field contract "package"
  exact package ["modules", "entry"]
  let artifact ← compile package
  let (assumptions, type) ← signature artifact
  let .specification _ (.arrow _ _ _ (.arrow _ _ _ target)) := type
    | throw "source contract entry must be a Specification of a method record"
  let methods ← Delvetalk.PackageData.members 64 target
  if methods.isEmpty || methods.length > 16 then
    throw "source contract requires one to sixteen method bounds"
  if (methods.map Prod.fst).eraseDups.length != methods.length then
    throw "source contract has duplicate method bounds"
  let protocol ← field candidate "protocol"
  let state ← field candidate "state"
  exact state ["model"]
  let datum ← SourceState.readWith compile protocol (← field state "model")
  let .record _ := datum | throw "source contract state requires a record root"
  if checkMethods then
    -- Metadata comes from observing the exact checked specification. Application
    -- may discard its wrapper; this retained law snapshot cannot silently drift.
    let observed ← Delvetalk.Reflection.metadataPacket (← field artifact "packet")
    let remaining ← get
    let response ← Delvetalk.Package.executeDataPacket observed (.arr #[])
      (obj [("ticks", toJson remaining), ("heap", toJson (100000 : Nat)),
        ("stack", toJson (10000 : Nat)), ("nodes", toJson (100000 : Nat)),
        ("bytes", toJson (1048576 : Nat))])
    charge ((← (← field response "ticksUsed").getNat?) +
      (← (← field response "conversionNodes").getNat?))
    if (← str response "status") != "finished" then throw "source contract metadata evaluation refused"
    if (← field response "value") != (← field contract "metadata") then
      throw "source contract metadata differs from its specification"
  let commands ← field protocol "commands"
  for (name, required) in methods do
    tick
    let .arrow _ _ stateSchema _ := required | throw "source contract method bound must be callable"
    match stateSchema with
    | .emptyRow | .field .. => pure ()
    | _ => throw "source contract method state must be a closed record"
    Delvetalk.PackageData.shape assumptions 256 [] stateSchema
    -- Admission needs a schema verdict, not a discarded term/annotation tree.
    -- Both sinks use the same bounded traversal and charge the same work.
    Delvetalk.PackageData.validate assumptions 256 datum stateSchema
    if !checkMethods then continue
    let command ← (field commands name).mapError (fun _ => "source contract missing method: " ++ name)
    let some transition := World.sourceTransition? command
      | throw ("source contract requires source method: " ++ name)
    World.validateTransitionCommand command
    -- sourceTransition? and command validation select the one current typed ABI.
    -- State schema quotation above checks the same retained model the body receives.
    let candidatePackage ← SourcePackages.resolve protocol (← field transition "package")
    let candidate ← compile candidatePackage
    let (candidateAssumptions, actual) ← signature candidate
    unless (← sameSignature assumptions candidateAssumptions 9 required actual) do
      throw ("source contract method signature mismatch: " ++ name)

end SourceContract
