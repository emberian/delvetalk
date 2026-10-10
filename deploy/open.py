#!/usr/bin/env python3
"""Open a community: write its bridge row and print how to start it (docs/FEDERATION.md section 4).

    python3 -m deploy.open --state /data/state --world ring --transport zulip --realm tulip.arke.me \
        --channel ring --zuliprc ~/.zuliprc-ring

Writes `<state>/bridges/<world>.json`, one file per world: {world, transport, realm, channel, zuliprc, topicMode}.
Starts nothing. One `serve` holds every world's journal (`<state>/<world>.journal`, opened at the world's first op);
the printed commands start the world's bridge and interpreter, each over serve's socket with `--world <world>` and its
own transport state under `<state>/worlds/<world>/`. Genesis and the welcome are the operator's next step (docs/GENESIS.md).
"""
import argparse
import json
import re
import shlex
import sys
from pathlib import Path

NAME = re.compile(r'[a-z][a-z0-9-]{0,31}\Z')
RESERVED = ('did', 'zulip', 'at', 'world', 'me', 'scratch')  # prefixes a local id can start with


def row(a):
    """The bridge row, or a SystemExit naming what is wrong."""
    if not NAME.match(a.world) or a.world in RESERVED:
        raise SystemExit(f'open: {a.world!r} is not a world name: [a-z][a-z0-9-]{{0,31}}, never {", ".join(RESERVED)}')
    if a.transport == 'zulip' and not (a.realm and a.channel and a.zuliprc):
        raise SystemExit('open: a zulip world needs --realm, --channel and --zuliprc')
    if a.transport == 'delve' and not a.realm:
        raise SystemExit('open: a delve world needs --realm, its PDS host')
    return {'world': a.world, 'transport': a.transport, 'realm': a.realm, 'channel': a.channel,
            'zuliprc': str(Path(a.zuliprc).expanduser()) if a.zuliprc else None, 'topicMode': 'topic' if a.topic else 'channel',
            **({'topic': a.topic} if a.topic else {})}


def commands(state, r):
    """The world's bridge and interpreter on serve's socket, each with the world's own transport state."""
    home, sock = Path(state) / 'worlds' / r['world'], Path(state) / 'host.sock'
    q = lambda p: shlex.quote(str(p))
    source = (f" --source zulip --zuliprc {q(r['zuliprc'])} --stream {q(r['channel'])}" + (f" --topic {q(r['topic'])}" if r.get('topic') else '')
              if r['transport'] == 'zulip' else ' --observe')
    on = f'--host-socket {q(sock)} --world {q(r["world"])}'
    return [f'python3 -m transport.bridge run --state {q(home)} {on}{source} --poll 60 &',
            f'python3 -m transport.interpret run --state {q(home)} {on} --poll 60 &']


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='open.py', description='write a world\'s bridge row and print how to start it')
    ap.add_argument('--state', required=True, help='the state directory that holds bridges/ and worlds/')
    ap.add_argument('--world', required=True)
    ap.add_argument('--transport', required=True, choices=('zulip', 'delve'))
    ap.add_argument('--realm', help='zulip: the realm host; delve: the PDS host')
    ap.add_argument('--channel', help='zulip: the stream the world lives in')
    ap.add_argument('--topic', help='zulip: one topic of the stream only')
    ap.add_argument('--zuliprc', metavar='PATH', help="zulip: the bot's .zuliprc")
    a = ap.parse_args(argv)
    r = row(a)
    path = Path(a.state) / 'bridges' / f'{a.world}.json'
    if path.exists():
        raise SystemExit(f'open: {a.world} already has a bridge row at {path}')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(r, indent=1, sort_keys=True) + '\n')
    out.write(f'open: wrote {path}\n' + ''.join(c + '\n' for c in commands(a.state, r)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
