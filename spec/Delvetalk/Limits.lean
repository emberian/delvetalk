/- Every named bound of the kernel-side code (Turn, Package, Document), in one
   place, one name per bound. Host-only bounds stay in `Delvetalk.Host.Limits`
   (Host/Store.lean); where the two name the same thing, this file is the one
   to read. A request beyond any bound is refused by name; none is raised
   silently. -/
namespace Delvetalk.Bounds

/-! ## Machine budgets of one turn segment (turn-start, turn-resume, run)

Each has a default, used when a request names none, and a ceiling, the most a
request may ask for. They keep one request from holding the process. -/

/-- Machine ticks: the work of one segment. -/
def ticksDefault : Nat := 100000
def ticksMax : Nat := 1000000
/-- Heap cells the machine may allocate in one segment. -/
def heapDefault : Nat := 100000
def heapMax : Nat := 1000000
/-- Stack frames. -/
def stackDefault : Nat := 10000
def stackMax : Nat := 100000
/-- Data nodes the result or a yielded Plan may materialize. -/
def nodesDefault : Nat := 100000
def nodesMax : Nat := 1000000
/-- Canonical encoded bytes of a materialized result or Plan, and the largest
    allocation a text primitive may reserve in one step. -/
def bytesDefault : Nat := 1048576
def bytesMax : Nat := 16777216
/-- Machine ticks of one run of a package's Bend law predicate
(`def law(old: State, new: State, request: Request) -> Verdict`), which the host
runs per judged write. -/
def lawTicks : Nat := 100000
/-- Type-checking fuel recorded in a compiled artifact. -/
def typeFuelDefault : Nat := 16384

/-! ## Wire data -/

/-- Nesting of Data decoded from the JSON wire as an argument or a response
    (a list cell costs two levels). -/
def dataWireDepth : Nat := 256
/-- Nesting of plain JSON converted to Data and back (`executeJsonPacket`). -/
def plainJsonDepth : Nat := 64
/-- Nesting of a Document on the wire: a long list is a deep chain. -/
def documentWireDepth : Nat := 8192
/-- Longest chain of parameters peeled off an entry's type to find its activity. -/
def entryArrowDepth : Nat := 64

/-! ## Source packages (compile, source-imports) -/

/-- Modules in one package. -/
def maxModules : Nat := 64
/-- One module's source text. -/
def maxModuleBytes : Nat := 524288
/-- All source text of a package offered to the import scan. (The host's
    `maxPackageBytes`, 32 KiB, is a tighter host-only bound on `reprogram`.) -/
def maxPackageSourceBytes : Nat := 1048576

/-! ## Documents rendered by the host -/

/-- Nesting of documents (a sequence's items and a quote's body are one deeper). -/
def documentDepth : Nat := 64
/-- Documents plus list cells visited. -/
def documentNodes : Nat := 65536
/-- Rendered text of one document. -/
def documentOutputBytes : Nat := 1048576
/-- Offers one turn may emit; their text together is bounded by `documentOutputBytes`. -/
def offersPerTurn : Nat := 16

end Delvetalk.Bounds
