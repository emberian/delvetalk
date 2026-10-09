/-
# Theory.Sp800185Cshake256Core -- cSHAKE256: the specification and its compiled path

Import this module.  It is `Sp800185Cshake256Spec`, the list/`BitVec`
definitions that every theorem in the repository is about, together with
`Sp800185Cshake256Fast`, the word and byte-array implementation proved equal
to them for every input (`cshake256Fast_eq`, `absorbPadded_fast_eq`) and
attached with `@[csimp]`.  Every module compiled with this import in scope
calls the fast code where the source says `cshake256Bytes` or `absorbPadded`.
A module importing only the spec would compile against the list definitions:
correct, and about three orders of magnitude slower.
-/

import Theory.Sp800185Cshake256Spec
import Theory.Sp800185Cshake256Fast
