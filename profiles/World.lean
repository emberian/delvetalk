/- Default local host entry point; shared semantics live in WorldCore. -/
import WorldCore
import FileCustody
import ResidentStore

def main (args : List String) : IO Unit :=
  if args == ["--resident"] then ResidentStore.serve World.transition
  else FileCustody.mainWith World.handle World.job args
