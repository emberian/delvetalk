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
/-- All source text of a package offered to the import scan. -/
def maxPackageSourceBytes : Nat := 1048576
/-- The source of one module offered as a program: what `reprogram`, `extend`, a `create` of
source, a `check` Plan and a form's `source` field take (the host reads it as
`Host.Limits.maxPackageBytes` and `formSourceMax`). Set by two measurements on persvati
(lane/kernel13, 2026-10-10). Compile cost: Garden's entry module grown with copies of Card's
declarations, compiled as the host does (`initial`, then all ten methods, one process): 32 KiB
0.34 s, 64 KiB 0.35 s, 128 KiB 0.42 s, 256 KiB 0.64 s, 106 to 127 MB resident; Card copies alone,
`check-package`: 0.09, 0.11, 0.15, 0.27 s. Every size compiles under a second. The scale rule
(FOUNDATION §9) then decides: a program is also data, held whole in one state cell (a kind's body,
a Workshop draft, a form's reply), and a cell is `maxCellBytes`; 128 KiB is the largest power of
two that leaves its row the other half. -/
def maxPackageBytes : Nat := 131072
/-- One request line of the package driver (`PackageMain`): a compile request carries its
sources, a run its whole artifact (an entry reaching 1,024 generic instances is about 2.6 MB). -/
def maxFrameBytes : Nat := 16777216
/-- A session's cache of prepared closures (parsed, specialized, elaborated, checked
whole), bounded by the source bytes of the closures it holds. -/
def frontCacheSourceBytes : Nat := 8388608
/-- A session's cache of compiled entries held decoded and checked, indexed by
`packetSha256`, bounded by the bytes of their artifacts. -/
def entryCacheBytes : Nat := 67108864
/-- The checkpoint digests a session without a journal remembers having issued, newest kept:
`turn-resume` resumes only those (a digest is 59 bytes, so about 4 MiB). -/
def issuedCheckpoints : Nat := 65536

/-- The canonical bytes of one state cell (KERNEL-HANDOFF §15): a stored relation row the
kernel fetches, and the scalar part of a state (its stored relations emptied), which the host
checks at write. Per cell, where `maxStateBytes` was per object. -/
def maxCellBytes : Nat := 262144

/-! ## Documents rendered by the host -/

/-- Nesting of documents (a sequence's items are one deeper). -/
def documentDepth : Nat := 64
/-- Documents plus list cells visited. -/
def documentNodes : Nat := 65536
/-- Rendered text of one document. -/
def documentOutputBytes : Nat := 1048576
/-- Offers one turn may emit; their text together is bounded by `documentOutputBytes`. -/
def offersPerTurn : Nat := 16

end Delvetalk.Bounds
