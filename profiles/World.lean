/- Default local host entry point; shared semantics live in WorldCore. -/
import WorldCore

def main : IO Unit := World.serve World.job
