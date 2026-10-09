/- Default ordered-transaction entry point. -/
import TransactionsCore
import FileCustody

def main (args : List String) : IO Unit :=
  FileCustody.mainWith Transactions.handle Transactions.job args
