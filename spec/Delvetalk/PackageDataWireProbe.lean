/- Executable regression probe: strict package framing, duplicate refusal,
record order, exact naturals, and generic response duplicate preservation. -/
import Delvetalk.PackageData
open Lean
open Delvetalk.PackageData
open Minidregg.Compiler.ObjectiveBendDataWire
open Minidregg.Theory.ObjectiveBendDemandData

def main : IO Unit := do
  let fields := (List.range 200).map fun n => (s!"field{n}", Data.natural n)
  let datum := Data.record fields
  let wire := dataJson datum
  let .ok (decoded, remaining) := (decode 256 wire).run 10000
    | throw (IO.userError "strict record decode failed")
  unless dataJsonBytes datum == wire.compress.utf8ByteSize do throw (IO.userError "wire byte count differs")
  unless dataJson decoded == wire do throw (IO.userError "record order changed")
  let .ok (_, nativeRemaining) := (admitValue 256 datum).run 10000
    | throw (IO.userError "native admission failed")
  unless nativeRemaining == remaining do throw (IO.userError "native work differs")
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
  IO.println "package-data-wire probe passed"
