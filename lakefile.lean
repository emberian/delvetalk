import Lake
open Lake DSL System

package delvetalk where
  version := v!"0.2.0"

lean_lib Theory where
  srcDir := "spec/bend"

lean_lib Compiler where
  srcDir := "spec/bend"

lean_lib Pred where
  srcDir := "spec/bend"

lean_lib Delvetalk where
  srcDir := "spec"

/-- The one piece of C: fsync for the journal (`spec/native/sync.c`). -/
target syncObject pkg : FilePath := do
  let source ← inputTextFile (pkg.dir / "spec" / "native" / "sync.c")
  let weak := #["-I", (← getLeanIncludeDir).toString]
  buildO (pkg.buildDir / "native" / "sync.o") source weak #["-fPIC"] "cc" getLeanTrace

extern_lib delvetalk_sync pkg := do
  let object ← syncObject.fetch
  buildStaticLib (pkg.staticLibDir / nameToStaticLib "delvetalk_sync") #[object]

@[default_target]
lean_exe «delvetalk-obend» where
  root := `PackageMain
  srcDir := "spec"

/-- Stage timings of a compile and the front end's differential self-checks
(`spec/CompileProfile.lean`); not a default target. -/
lean_exe «compile-profile» where
  root := `CompileProfile
  srcDir := "spec"
