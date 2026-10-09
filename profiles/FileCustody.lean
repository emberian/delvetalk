/- Local file custody transport. Admission stays in the selected receiver;
   its caller locks custody and makes the candidate durable before replying. -/
import WorldCore
open Lean

namespace FileCustody

-- JsonNumber equality includes decimal scale. Json.compress erases trailing
-- zeros, so using it for custody can make an exact retry collide after restart.
-- Scientific notation preserves the stored mantissa and exponent without a
-- decimal expansion proportional to the exponent. The framed legacy CLI keeps
-- its existing serializer; this transport changes no receiving equality rule.
partial def encode : Json → String
  | .num number => toString number.mantissa ++
      (if number.exponent == 0 then "" else "e-" ++ toString number.exponent)
  | .arr values => "[" ++ String.intercalate "," (values.toList.map encode) ++ "]"
  | .obj values => "{" ++ String.intercalate "," (values.toList.map fun (key, value) =>
      (Json.str key).compress ++ ":" ++ encode value) ++ "}"
  | value => value.compress

def readRequest : IO Json := do
  let stdin ← IO.getStdin
  let mut bytes := ByteArray.empty
  repeat
    let chunk ← stdin.read 4096
    if chunk.isEmpty then break
    if bytes.size + chunk.size > 65537 then throw (IO.userError "request exceeds 64 KiB")
    bytes := bytes ++ chunk
  let some line := String.fromUTF8? bytes | throw (IO.userError "request is not UTF-8")
  IO.ofExcept (Json.parse line)

def lookup (snapshot : System.FilePath) : IO Unit := do
  let result ← try
    let request ← readRequest
    let world ← if ← snapshot.pathExists then
        IO.ofExcept (Json.parse (← IO.FS.readFile snapshot))
      else pure World.empty
    IO.ofExcept (World.retainedReply (← IO.ofExcept ((← IO.ofExcept (World.field world "receipts")).getArr?)) request)
  catch error => pure (World.obj [("error", .str error.toString)])
  (← IO.getStdout).putStrLn (encode result)

def run (receive : Json → Json → Except String (Json × Json))
    (snapshot candidate : System.FilePath) : IO Unit := do
  let stdout ← IO.getStdout
  let result ← try
    if snapshot == candidate then throw (IO.userError "candidate must differ from snapshot")
    let request ← readRequest
    let world ← if ← snapshot.pathExists then
        IO.ofExcept (Json.parse (← IO.FS.readFile snapshot))
      else pure World.empty
    let (next, reply) ← IO.ofExcept (receive world request)
    let changed := next != world
    if changed then IO.FS.writeFile candidate (encode next ++ "\n")
    pure (World.obj [("changed", .bool changed), ("reply", reply)])
  catch error => pure (World.obj [("error", .str error.toString)])
  stdout.putStrLn (encode result)

def mainWith (receive : Json → Json → Except String (Json × Json))
    (framed : Json → Json) (args : List String) : IO Unit :=
  match args with
  | [] => World.serve framed
  | ["--files", snapshot, candidate] => run receive snapshot candidate
  | ["--lookup-files", snapshot] => lookup snapshot
  | _ => throw (IO.userError "expected no arguments, --files SNAPSHOT CANDIDATE, or --lookup-files SNAPSHOT")

end FileCustody
