# persvati: second build and test box

`persvati` (ssh alias, user `ember`) is the overflow box for lanes when hbox is loaded, and the box for the transport
suites that need deterministic ECDSA. It has other tenants (a logflare beam, a python tools job): never `pkill`,
`killall` or `kill -u` there; stop only a process you started, by its PID file. Before calling it busy, read `ps -eo
rss,etime,cmd --sort=-rss | head`.

| | persvati | hbox |
|---|---|---|
| cores / RAM | 24 / 83 GB | 24 / 123 GB |
| disk | ~303 GB free | ext4 root, ~76 GB free |
| Lean toolchain | v4.34.1 via elan (also 4.16, 4.30, 4.32, 4.33) | v4.34.1 via elan (default `lean` there is 4.17.0) |
| python3 | 3.14.4 | 3.12.7 |
| cryptography | 46.0.5 | 42.0.5 |
| swarm-build | MemoryMax 64G, `taskset -c 0-19` | MemoryMax 96G, `taskset -c 0-15` |
| systemd user scopes | work (linger enabled for ember) | work |

- **Transport suites:** hbox's cryptography 42.0.5 lacks deterministic ECDSA (`deterministic_signing`, from 43.0), so
  test_repo's signing tests (`Repository`'s signed journal, `Vectors`' signatures, `SignedRepository`) skip there by
  name and run only on persvati. The suite is standard library plus `cryptography` and passes on python 3.14.
- **PATH:** non-interactive ssh puts neither elan nor `swarm-build` on it. Prefix every remote command:

      export PATH=$HOME/.elan/bin:$HOME/.local/bin:$PATH

- **swarm-build:** `~/.local/bin/swarm-build` is hbox's wrapper with the two numbers changed; override per build with
  `SWARM_MEM_MAX=<n>G`. It nests under `swarm.slice` with no slice-wide cap, so concurrent builds are each capped at
  64G but not summed: keep concurrent builds to a few.

## Lane recipe

    ssh persvati
    export PATH=$HOME/.elan/bin:$HOME/.local/bin:$PATH
    # source tree, from the Mac:
    #   git -C /Users/ember/dev/delvetalk2-lanes/<lane> archive HEAD | ssh persvati 'mkdir -p ~/scratch/dt-<lane> && tar -x -C ~/scratch/dt-<lane>'
    rsync -a ~/scratch/dt-foundation/.lake/ ~/scratch/dt-<lane>/.lake/     # seed the build cache
    cd ~/scratch/dt-<lane>
    LEAN_NUM_THREADS=2 swarm-build lake build
    LEAN_NUM_THREADS=2 swarm-build lake build Delvetalk.PackageDataAdmission Delvetalk.PackageDataNormalization \
        Delvetalk.PackageDataSchemaProofs Theory.ObjectiveBendNativeDataSimulation
    DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run test_repo <other test modules>

The binary is `.lake/build/bin/delvetalk-obend`; the four proof-only modules are `PROOF_ONLY` in the Makefile. Lean
compilation stays at two processes (`LEAN_NUM_THREADS=2`). Run the tests that exercise the change, not the whole suite.

A `.lake` seeded from hbox is accepted as-is (trace hashes are path-independent): a seeded `lake build` replays in
about half a second, and a lane pays only for its changed modules and their dependents. Seed hbox to persvati directly:
`ssh hbox 'rsync -a ~/scratch/dt-foundation/.lake/ persvati:scratch/dt-foundation/.lake/'`. A cold build there has not
been measured.
