"""`python3 -m transport carry --from OLD --to NEW --reason R [--leave [WORLD=]OBJ]...`: a state directory carried to
the host binary the configuration names (docs/FOUNDATION.md §2; docs/DEPLOY.md "A new binary").

Every world journal of OLD (`<world>.journal`; `scratch/` is not custody) is carried by `delvetalk-obend carry`, which
reads the world from the snapshot at its head (written by the binary of its edition: `deploy/verify.sh --snapshot`)
and writes NEW's journal, whose genesis cites the old head. Then the transport's own files move with it, the height
cursors that named the old chain's entries set to the new genesis (`publications.after`, each `awaiting` turn), and
the carried worlds are checked in a throwaway copy, independently of the binary's own check: every object at the state
CID the snapshot held and rendering for its owner, every old receipt resolving by its slug, and a new turn admitted.
OLD is only read; its journal lock must be free (serve stopped). NEW must hold no journal. The channel line the hand
posts once is printed last (FOUNDATION §2).
"""
import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from transport import journal
from transport.config import Config
from transport.host import HostProcess
from transport.identity import slug

# What is serve's and is made again, never copied: journals (carried instead), snapshots, the lock, the sealed library
# (the carry seals the configured one; serve rebuilds it at start), the root socket's directory, scratch worlds (not
# custody), sockets and pid files.
SKIP_DIRS = {'library', 'root', 'scratch'}


def skipped(name):
    return (name.endswith(('.journal', '.journal.blocks', '.cbor', '.sock', '.pid', '.tmp')) or '.journal.snapshot.' in name
            or name == 'journal.lock')


def worlds(old):
    """The worlds of a state directory: each `<world>.journal` beside the lock."""
    return sorted(p.name[:-len('.journal')] for p in Path(old).glob('*.journal'))


def leaves(given, world):
    """The objects of `world` to carry retired: `WORLD=OBJ`, or a bare `OBJ` for the town."""
    out = []
    for g in given:
        w, _, obj = g.partition('=') if '=' in g else ('town', '', g)
        if w == world:
            out.append(obj)
    return out


def copy_transport(old, new):
    """Every transport file of OLD into NEW, SQLite through its own backup; what `skipped` names is serve's."""
    for src in sorted(Path(old).rglob('*')):
        rel = src.relative_to(old)
        if rel.parts[0] in SKIP_DIRS or skipped(src.name) or not src.is_file():
            continue
        dst = Path(new) / rel
        dst.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if src.suffix == '.sqlite':
            a, b = sqlite3.connect(f'file:{src}?mode=ro', uri=True), sqlite3.connect(dst)
            a.backup(b)
            b.close()
            a.close()
        else:
            shutil.copy2(src, dst)


def reset_cursors(new, world):
    """The transport's cursors that named heights of the old chain, set to the carried genesis (height 1)."""
    home = Path(new) / 'worlds' / world
    if (home / 'publications.after').exists():
        (home / 'publications.after').write_text('1\n')
    for p in sorted((home / 'awaiting').glob('*.json')):
        record = json.loads(p.read_text())
        p.write_text(json.dumps(dict(record, height=1), sort_keys=True) + '\n')


def reader(row, opener):
    """Who may read a snapshot's object row, to read it as: its owner, else a named reader, else the opener."""
    fields = {f['name']: f['value'] for f in (row['state'].get('fields') or [])} if isinstance(row['state'], dict) else {}
    owner = (fields.get('owner') or {}).get('value') or opener
    read = row.get('read')
    if isinstance(read, dict) and owner not in read.get('principals', [owner]):
        return read['principals'][0]
    return owner


def check(obend, old_journal, new_journal, moved=()):
    """The carried world against the snapshot it was carried from, in a throwaway copy: {objects, rendered, receipts,
    turn, problems}. An object the carry moved to the image's packages (`moved`) is at its migrated state."""
    after = {m['object']: m['after'] for m in moved}
    links = journal.links(old_journal)
    body = journal.snapshot(dict(journal.snapshots(old_journal))[len(links)])
    opener = (body.get('settings') or {}).get('opener') or ''
    clock = (body.get('settings') or {}).get('clock') or opener
    problems, rendered, resolved, turn = [], 0, 0, {}
    # Beside the new journal, not in /tmp: the ops container's /tmp is a small tmpfs.
    with tempfile.TemporaryDirectory(prefix='.carry-check-', dir=os.path.dirname(os.path.abspath(new_journal))) as tmp:
        copy = os.path.join(tmp, 'w.journal')
        journal.copy(new_journal, copy)
        host = HostProcess(obend)
        try:
            opened = host.send(op='world-open', path=copy, sync='none', verify=True)
            if opened.get('status') != 'opened':
                return {'problems': [f'the carried journal does not open: {opened}']}
            for row in body['objects']:
                who = reader(row, opener)
                got = host.send(op='world-object', principal=who, object=row['id'])
                now, expected = (got.get('record') or {}).get('stateCid'), after.get(row['id'], row['stateCid'])
                if now != expected:
                    problems.append(f"{row['id']}: state {now or got.get('status')} after, {expected} expected")
                card = host.send(op='world-card', principal=who, object=row['id'])
                if card.get('status') == 'card':
                    rendered += 1
                else:
                    problems.append(f"{row['id']} does not render for {who}: {card.get('message') or card.get('status')}")
            for link in links:
                got = host.send(op='world-resolve', principal=opener or 'transport', slug=slug(link['hash']))
                if got.get('status') == 'resolved' and got.get('cid') == link['hash'] and (got.get('carried') or {}).get('height') == link['height']:
                    resolved += 1
                elif got.get('status') == 'ambiguous':
                    resolved += 1  # two CIDs share 32 bits of digest: the slug names both, as it would have before
                else:
                    problems.append(f"entry {link['height']} ({slug(link['hash'])}) does not resolve: {got.get('message') or got}")
            status = host.send(op='world-status')
            turn = host.send(op='world-advance', principal=clock, height=status['clock'] + 1)
            if turn.get('status') != 'advanced' or 'receipt' not in turn:
                problems.append(f'the carried world does not take a turn: {turn}')
        finally:
            host.close()
    return {'objects': len(body['objects']), 'rendered': rendered, 'receipts': resolved, 'turn': turn.get('status'), 'problems': problems}


def lock_free(old):
    lock = Path(old) / 'journal.lock'
    if not lock.exists():
        return True
    with open(lock) as f:  # read only: OLD may be mounted read-only (the ops container's /towns)
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(f, fcntl.LOCK_UN)
    return True


def body_args(library):
    """`--body OBJ=FILE` for each body genesis lays (deploy/genesis.py KINDS, and the commonplace's), from the
    image's `bodies/` beside its library: the carry sets each kind's `body` to it and lays it over that kind's
    things, and lays the commonplace's over the commonplace."""
    from deploy import genesis
    bodies = Path(library).parent / 'bodies'
    pairs = [('kind/' + name, body) for name, _, _, _, _, body in genesis.KINDS if body] + [('commonplace', 'commonplace')]
    return [a for obj, body in pairs for a in ('--body', f'{obj}={bodies / (body + ".obend")}')]


def command(a, out):
    old, new = Path(a.source), Path(a.to)
    names = worlds(old)
    if 'town' not in names:
        raise SystemExit(f'carry: {old} holds no town.journal')
    if new.exists() and any(new.glob('*.journal')):
        raise SystemExit(f'carry: {new} holds a journal already; a carry writes a new state')
    if not lock_free(old):
        print(f'carry: {old}/journal.lock is held: stop serve first', file=sys.stderr)
        return 75
    new.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (old / 'delvetalk.toml').exists() and not (new / 'delvetalk.toml').exists():
        shutil.copy2(old / 'delvetalk.toml', new / 'delvetalk.toml')
    config = Config.load(new)
    obend = a.obend or config.obend
    library = ['--library', str(config.library), *body_args(config.library)] if config.library else []  # serve's: the library ships with the host
    written, carried = [], {}
    for w in names:
        target = new / f'{w}.journal'
        argv = [obend, 'carry', '--from', str(old / f'{w}.journal'), '--out', str(target), '--reason', a.reason, *library]
        for obj in leaves(a.leave, w):
            argv += ['--leave', obj]
        p = subprocess.run(argv, capture_output=True, text=True)
        if p.returncode != 0:
            for path in written:  # this run's own files only
                Path(path).unlink(missing_ok=True)
            print(f'carry: {w}: ' + (p.stderr.strip() or f'exit {p.returncode}'), file=sys.stderr)
            return p.returncode
        written += [str(target), str(target) + '.blocks']
        carried[w] = json.loads(p.stdout)
    copy_transport(old, new)
    for w in names:
        reset_cursors(new, w)
    failed = False
    for w in names:
        r = carried[w]
        checked = check(obend, str(old / f'{w}.journal'), str(new / f'{w}.journal'), r['moved'])
        failed = failed or bool(checked['problems'])
        out.write(json.dumps({'world': w, 'slug': r['slug'], 'hash': r['hash'], 'height': r['carriedFrom']['height'],
                              'replay': [r['carriedFrom']['replay'], r['replay']], 'library': r['library'], 'objects': r['objects'], 'left': r['left'],
                              'moved': r['moved'],
                              'dropped': r['dropped'], 'kept': r['kept'], 'rearmed': r['rearmed'], 'check': checked}, sort_keys=True) + '\n')
        if checked['problems']:
            continue
        # Then genesis's own laws and kinds as the image stands (`deploy.genesis refresh`, as the opener): after the
        # check, which compares the carried states with the carry's own `moved`.
        from deploy import genesis
        for row in genesis.carried(obend, str(new / f'{w}.journal')):
            out.write(json.dumps({'world': w, 'refresh': row}, sort_keys=True) + '\n')
            failed = failed or row.get('status') not in ('refreshed', 'current', 'left')
    town = carried['town']
    out.write(f"hob: the world was carried to a newer host at entry {town['carriedFrom']['height']}; everything is where it was, "
              f"and the carry is receipt {town['slug']}.\n")
    return 1 if failed else 0
