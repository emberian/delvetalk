/- Default ordered-transaction entry point. -/
import TransactionsCore
import FileCustody
import ResidentStore

def main (args : List String) : IO Unit :=
  if args == ["--resident"] then ResidentStore.serve Transactions.transition
  else FileCustody.mainWith Transactions.handle Transactions.job args
