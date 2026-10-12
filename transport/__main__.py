"""`python3 -m transport <command> --state DIR [--world W] ...`: the transport's one entry point (docs/OPERATIONS.md
section b). Every command works on one world of one state directory, `State(--state, --world)`, configured by
`<state>/delvetalk.toml` and `DELVETALK_*`; its own arguments are only what the configuration does not hold.
"""
import argparse
import importlib
import json
import os
import sys

from transport.state import State


def serve(st, a, out):
    """`serve`: become `delvetalk-obend serve`, configured as the config says."""
    argv = st.serve_argv()
    os.execvp(argv[0], argv)


def open_world(st, a, out):
    """`open`: write the world's bridge row (docs/FEDERATION.md section 4); start nothing. Its bridge and interpreter are
    `bridge` and `interpret` with `--world`; genesis and the welcome are the operator's next step (docs/GENESIS.md)."""
    if a.transport == 'zulip' and not (a.realm and a.channel and a.zuliprc):
        raise SystemExit('open: a zulip world needs --realm, --channel and --zuliprc')
    if a.transport == 'delve' and not a.realm:
        raise SystemExit('open: a delve world needs --realm, its PDS host')
    row = {'world': st.world, 'transport': a.transport, 'realm': a.realm, 'channel': a.channel,
           'zuliprc': os.path.expanduser(a.zuliprc) if a.zuliprc else None, **({'topic': a.topic} if a.topic else {})}
    if st.row.exists():
        raise SystemExit(f'open: {st.world} already has a bridge row at {st.row}')
    st.write(st.row, row)
    out.write(f'open: wrote {st.row}\n' + json.dumps(row, indent=1, sort_keys=True) + '\n')
    return 0


def repokey(st, a, out):
    """`repokey`: make the world's repository signing key once; prints the did:key it names and nothing secret."""
    from transport.repo import make_key
    try:
        out.write(f'{st.repo_key}: {make_key(st, a.curve)}\n')
    except FileExistsError:
        print(f'{st.repo_key} exists; not replaced', file=sys.stderr)
        return 1
    return 0


COMMANDS = {'serve': (__name__, 'serve'), 'bridge': ('transport.bridge', 'command'), 'interpret': ('transport.interpret', 'command'),
            'post': ('transport.post', 'command'), 'hand': ('transport.hand', 'command'), 'http': ('transport.http', 'command'),
            'open': (__name__, 'open_world'), 'watch': ('transport.watch', 'watch'), 'repokey': (__name__, 'repokey'),
            'status': ('transport.watch', 'status'), 'tables': ('transport.tables', 'command')}
# Commands over two state directories, not one world of one: they take their own arguments.
WHOLE = {'carry': ('transport.carry', 'command')}


def parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--state', default=os.environ.get('DELVETALK_STATE'), help='the state directory (default DELVETALK_STATE)')
    common.add_argument('--world', default='town', help='the world (default town)')
    ap = argparse.ArgumentParser(prog='python3 -m transport', description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='command', required=True)
    add = lambda name, what, parents=(common,): sub.add_parser(name, parents=list(parents), help=what, description=what)
    add('serve', 'run delvetalk-obend serve over the state, as the config says')
    p = add('bridge', "observe the world's source, turn what is addressed, draft the replies")
    p.add_argument('--once', action='store_true', help='one step, not a step every `poll` seconds')
    p.add_argument('--since', metavar='ISO', help='observe posts created at or after this time (a deliberate replay)')
    p.add_argument('--now', type=float, metavar='UNIX_SECONDS', help='the clock for an offline replay (default the wall clock)')
    add('interpret', 'ask the model for each pending interpretation and submit its answer').add_argument('--once', action='store_true')
    p = add('post', "post once per intent: to delve.town (a dry run without the flag), or to the world's Zulip channel")
    p.add_argument('--draft', metavar='FILE', help='an outbox draft: its text, reply-to, object and slot')
    p.add_argument('--text-file', help='the text; an agentwiki post is one whose first line is `wiki: <page>` or `edit: <page> › <section>`')
    p.add_argument('--reply-to', metavar='AT_URI', help='thread under this post (its cid is read with getRecord)')
    p.add_argument('--intent', required=True, help='posted at most once: a retry of the intent is the same post')
    p.add_argument('--object', help='the object the post addresses: world-posted records it and settles its reservation')
    p.add_argument('--slot', metavar='JSON', help='the slot the post settles, as the host names it: {"principal": ..., "intent": ...}')
    p.add_argument('--mention', action='append', default=[], metavar='HANDLE', help='deliberately ping this handle (appended to the text)')
    p.add_argument('--topic', help="a Zulip world: the topic of its channel to post in")
    p.add_argument('--i-am-ember-and-authorize-posting', dest='authorized', action='store_true', default=False)
    from transport import hand
    hand.parser(sub.add_parser('hand', help="the owner's console: drafts, moderation and root, as the opener"), common)
    add('http', 'the public front: /AGENTS.md for agents, pages for people')
    p = add('open', "write a world's bridge row")
    p.add_argument('--transport', required=True, choices=('zulip', 'delve'))
    p.add_argument('--realm', help='zulip: the realm host; delve: the PDS host')
    p.add_argument('--channel', help='zulip: the stream the world lives in')
    p.add_argument('--topic', help='zulip: one topic of the stream only')
    p.add_argument('--zuliprc', metavar='PATH', help="zulip: the bot's .zuliprc")
    p = add('watch', 'probe, and post each crossed threshold to the ops stream')
    p.add_argument('--unhealthy', nargs='*', default=[], metavar='SERVICE', help='compose services not running or unhealthy')
    p.add_argument('--dry-run', action='store_true', help='print the lines; post nothing, remember nothing')
    add('repokey', "make the world's repository signing key").add_argument('--curve', default='secp256k1', choices=('secp256k1', 'secp256r1'))
    p = sub.add_parser('carry', help='carry a state directory to the configured host binary: every world, no wipe',
                       description='carry a state directory to the configured host binary: every world, no wipe')
    p.add_argument('--from', dest='source', required=True, metavar='OLD', help="the old state directory (serve stopped); only read")
    p.add_argument('--to', required=True, metavar='NEW', help='the new state directory; holds no journal')
    p.add_argument('--reason', required=True, help='one line, journaled in each carried genesis')
    p.add_argument('--leave', action='append', default=[], metavar='[WORLD=]OBJ', help='carry this object retired (the town when no WORLD)')
    p.add_argument('--obend', help="the host binary (default the new state's config, DELVETALK_OBEND)")
    p = add('tables', "the dealer's local Automatafl tables: serve over the state and a page on 127.0.0.1 (examples/automatafl/README.md)")
    p.add_argument('--port', type=int, default=8790, help='the page on 127.0.0.1 (default 8790)')
    p.add_argument('--obend', help='the host binary (default DELVETALK_OBEND, then .lake/build/bin/delvetalk-obend)')
    p.add_argument('--dealer', default='ember.delve.town', help="the dealer's principal: owns the tables, resolves the rounds")
    p = add('status', 'one probe of the world, as JSON')
    p.add_argument('--health', choices=('host', 'http', 'hand', 'bridge', 'interpret'), help='exit 0 if the service is healthy (a compose healthcheck)')
    p.add_argument('--playtest', action='store_true', help="the playtest's measures from the journal (docs/PLAYTEST-2.md section 4)")
    return ap


def main(argv=None, out=None, **seams):
    """`seams` replace a command's network or host (a test's stubs)."""
    ap = parser()
    a = ap.parse_args(argv)
    if a.command in WHOLE:
        module, name = WHOLE[a.command]
        return getattr(importlib.import_module(module), name)(a, out or sys.stdout) or 0
    if not a.state:
        ap.error('--state (or DELVETALK_STATE) is required')
    module, name = COMMANDS[a.command]
    return getattr(importlib.import_module(module), name)(State(a.state, a.world), a, out or sys.stdout, **seams) or 0


if __name__ == '__main__':
    sys.exit(main())
