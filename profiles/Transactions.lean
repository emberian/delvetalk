/- Default ordered-transaction entry point. -/
import TransactionsCore
import FileCustody
import ResidentStore

def retainedHandle := RetainedRoots.handleWith Transactions.transition

def main (args : List String) : IO Unit :=
  if args == ["--resident"] then ResidentStore.serve Transactions.transition
  else FileCustody.mainWith retainedHandle (World.jobWith retainedHandle) args
