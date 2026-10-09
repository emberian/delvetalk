/- Default local host entry point; shared semantics live in WorldCore. -/
import WorldCore
import FileCustody

def main (args : List String) : IO Unit := FileCustody.mainWith World.handle World.job args
