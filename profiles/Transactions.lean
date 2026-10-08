/- Default ordered-transaction entry point. -/
import TransactionsCore

def main : IO Unit := World.serve Transactions.job
