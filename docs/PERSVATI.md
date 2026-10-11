# persvati: second build and test box

`persvati` (ssh alias, user `ember`) is the overflow box for lanes when hbox is loaded.
It has other tenants (a logflare beam, a python tools job): never `pkill`, `killall` or
`kill -u` there; stop only a process you started, by its PID file.

## Facts (measured 2026-10-10)

| | persvati | hbox |
|---|---|---|
| cores / RAM | 24 / 83 GB | 24 / 123 GB |
| disk | ~303 GB free | ext4 root, ~76 GB free |
| Lean toolchain | v4.34.1 via elan (also 4.16, 4.30, 4.32, 4.33) | v4.34.1 via elan (default `lean` there is 4.17.0) |
| python3 | 3.14.4 | 3.12.7 |
| cryptography | 46.0.5 (already installed) | n/a |
| swarm-build | MemoryMax 64G, `taskset -c 0-19` | MemoryMax 96G, `taskset -c 0-15` |
| systemd user scopes | work (linger already enabled for ember) | work |

Non-interactive ssh does not put elan or `swarm-build` on PATH. Prefix every remote command:

    export PATH=$HOME/.elan/bin:$HOME/.local/bin:$PATH

`~/.local/bin/swarm-build` is hbox's wrapper with the two numbers changed. Override per build
with `SWARM_MEM_MAX=<n>G`. It nests under `swarm.slice`; no slice-wide drop-in was installed
on persvati, so concurrent builds are each capped at 64G but not summed. Keep concurrent
builds to a few.

## Lane recipe

    ssh persvati
    export PATH=$HOME/.elan/bin:$HOME/.local/bin:$PATH
    mkdir -p ~/scratch/dt-<lane> && cd ~/scratch
    # source tree: from the Mac,
    #   git -C /Users/ember/dev/delvetalk2-lanes/<lane> archive HEAD | ssh persvati 'mkdir -p ~/scratch/dt-<lane> && tar -x -C ~/scratch/dt-<lane>'
    rsync -a ~/scratch/dt-foundation/.lake/ ~/scratch/dt-<lane>/.lake/     # seed the build cache
    cd ~/scratch/dt-<lane>
    LEAN_NUM_THREADS=2 swarm-build lake build
    LEAN_NUM_THREADS=2 swarm-build lake build Delvetalk.PackageDataAdmission Delvetalk.PackageDataNormalization \
        Delvetalk.PackageDataSchemaProofs Theory.ObjectiveBendNativeDataSimulation
    DELVETALK_OBEND=$PWD/.lake/build/bin/delvetalk-obend python3 -W ignore -m tests.run

Binary: `.lake/build/bin/delvetalk-obend`. The four proof-only modules are `PROOF_ONLY` in the Makefile.
Local Lean compilation stays at two processes (`LEAN_NUM_THREADS=2`). Seeding hbox-to-persvati
works directly: `ssh hbox 'rsync -a ~/scratch/dt-foundation/.lake/ persvati:scratch/dt-foundation/.lake/'`.

## Timings

| step | persvati | hbox reference |
|---|---|---|
| `lake build` on a `.lake` seeded from hbox (134 jobs, all replayed) | ~0.5 s | (not measured) |
| the proof-only modules, seeded (19 jobs then) | ~0.5 s | (not measured) |
| `tests.run` | 35.5 s wall, 1347 tests, 323 classes, 0 failed | ~1,347 tests, 0 failed, 30-70 s (hbox was loaded) |

The build times above are cache replays, not cold builds: a cold build on persvati was not
measured. A lane whose sources change pays for the changed modules and their dependents.
Slowest classes on persvati: test_hypermedia.Controls 34.2 s, test_kinds.Kinds 21.5 s,
test_policy.PolicyObject 19.5 s, test_zulip.Bridging 17.3 s, test_receive.Cards 17.0 s.

## What differs from hbox

- **persvati is the box for the transport suites.** hbox's python has cryptography 42.0.5, which
  lacks deterministic ECDSA (`deterministic_signing`, from 43.0); test_repo's signing tests
  (`Repository`'s signed journal, `Vectors`' signatures, `SignedRepository`) skip there by name and
  run only on persvati (46.0.5).

- python 3.14 versus 3.12; the suite is standard library plus `cryptography` (`tests/test_oauth.py`), and it passes on 3.14 with no red class.
- Cgroup cap 64G and 20 pinned cores rather than 96G and 16, because the box is smaller and shared.
- No dedicated-tenant assumption: check `ps -eo rss,etime,cmd --sort=-rss | head` before calling it busy, and never touch other tenants' processes.
- Seeded `.lake` from hbox was accepted as-is (trace hashes are path-independent), so no rebuild of 134 jobs was needed.
