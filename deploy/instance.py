#!/usr/bin/env python3
"""The deploy as a template (docs/DEPLOY.md "A second instance"): every value that makes one DelveTalk instance on the
workhorse its own, from its name and its table in deploy/instances.toml.

  python3 -m deploy.instance check                         # every instance apart: no shared port, path or origin
  python3 -m deploy.instance render NAME --out DIR [--image delvetalk:<sha12> --host-image delvetalk-host:<sha12>]

`render` writes the instance's kit into DIR: `env` (its /opt/<project>/.env: the compose project, origin, opener, data
directory, root socket, keys, ports, backups; image tags as given, else `<sha12>` to fill), its systemd units (the
watch and the backup timer on the workhorse, the backup pull as hbox's user units), `Caddyfile.site` (its block for the
anchor's Caddy) and, when its table has one, `delvetalk.toml` (its state's config). deploy/compose.yml and
compose.hand.yml are the same files for every instance: what differs enters through `.env` alone, so the instance
`delvetalk` renders exactly what the live town runs today (tests/test_instances.py compares each file).
"""
import argparse
import dataclasses
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTANCES = Path(__file__).resolve().parent / 'instances.toml'
LIVE = 'delvetalk'  # the live town's name: its paths are the ones it has always had
PRIVATE_IP = '10.10.1.10'  # the workhorse on the private net, which the anchor's Caddy reaches
BACKUP_PULL = 'root@2.28.141.27'  # the workhorse as hbox's pull names it (DEPLOY "Durability and backups")


@dataclasses.dataclass(frozen=True)
class Instance:
    """One instance: `name` and its table. Every path is its project's: `/opt/<project>`, `/var/lib/<project>`,
    `/etc/<project>`, `/var/backups/<project>`, where the project is `delvetalk` for the live town and
    `delvetalk-<name>` for any other."""
    name: str
    origin: str
    data: str
    http_port: int
    hand_port: int
    firehose_port: int
    backup_minute: int
    opener: str = ''  # empty: the origin's did:web, the config's default for a new world
    station: bool = False
    hosted_accounts: bool = False  # DELVETALK_HOSTED_ACCOUNTS: hosted guest DIDs, off for want of wildcard DNS (cx-tidy)
    firehose: bool = False  # publish the firehose's port (deploy/compose.firehose.yml) and route it at the edge
    anthropic_key: str = ''
    watch_zuliprc: str = ''
    config: dict = dataclasses.field(default_factory=dict)

    @property
    def project(self):
        return LIVE if self.name == LIVE else f'{LIVE}-{self.name}'

    @property
    def title(self):
        return 'DelveTalk' if self.name == LIVE else f'DelveTalk {self.name}'

    @property
    def host(self):
        return self.origin.split('://', 1)[1].rstrip('/')

    @property
    def paths(self):
        """Every host path the instance owns, by what it is."""
        p = self.project
        return {'home': f'/opt/{p}', 'towns': f'/var/lib/{p}', 'data': f'/var/lib/{p}/{self.data}', 'root': f'/var/lib/{p}/root',
                'repo_keys': f'/etc/{p}/repo', 'hand_token': f'/etc/{p}/hand.token', 'delve_dir': f'/etc/{p}/delve',
                'anthropic_key': self.anthropic_key or f'/etc/{p}/anthropic.key',
                'watch_zuliprc': self.watch_zuliprc or f'/etc/{p}/watch.zuliprc', 'backups': f'/var/backups/{p}',
                'pull_dir': f'%h/{p}-backups', 'pull_key': f'%h/.ssh/{p}-backups', 'pulled': f'/tank/{p}-backups'}

    def opener_did(self):
        from transport.config import town_did
        return self.opener or town_did(self.origin)

    def env(self, image='delvetalk:<sha12>', host_image='delvetalk-host:<sha12>'):
        """The instance's `.env`: every variable compose.yml, compose.hand.yml and the units read, so none falls to a
        compose default (which are the live town's). No comment after a value (systemd's EnvironmentFile keeps it)."""
        p = self.paths
        files = 'compose.yml:compose.hand.yml' + (':compose.firehose.yml' if self.firehose else '')
        rows = [('COMPOSE_PROJECT_NAME', self.project), ('COMPOSE_FILE', files), ('DELVETALK_IMAGE', image),
                ('DELVETALK_HOST_IMAGE', host_image), ('DELVETALK_ORIGIN', self.origin), ('DELVETALK_OPENER', self.opener_did()),
                ('DELVETALK_DATA', p['data']), ('DELVETALK_ROOT', p['root']), ('DELVETALK_TOWNS', p['towns']),
                ('DELVETALK_REPO_KEYS', p['repo_keys']), ('DELVETALK_HAND_TOKEN_PATH', p['hand_token']),
                ('DELVETALK_DELVE_DIR', p['delve_dir']), ('DELVETALK_ANTHROPIC_KEY_PATH', p['anthropic_key']),
                ('DELVETALK_PRIVATE_IP', PRIVATE_IP), ('DELVETALK_HTTP_PORT', self.http_port), ('DELVETALK_HAND_PORT', self.hand_port),
                ('DELVETALK_FIREHOSE_PORT', self.firehose_port), ('DELVETALK_BACKUPS', p['backups']),
                ('DELVETALK_WATCH_ZULIPRC', p['watch_zuliprc']), ('DELVETALK_REQUESTS', 'off'),
                ('DELVETALK_HOSTED_ACCOUNTS', 'on' if self.hosted_accounts else 'off'),
                ('DELVETALK_STATION', 'on' if self.station else 'off')]
        return f'# {self.title}: /opt/{self.project}/.env (mode 0600), rendered by `python3 -m deploy.instance render {self.name}`\n' + \
            ''.join(f'{k}={v}\n' for k, v in rows)

    def units(self):
        """{file name: text}: the watch and the backup timer (the workhorse's system units) and the pull (hbox's user
        units), named after the project: the live town's are the names and bytes it runs."""
        p, s, t = self.paths, self.project, self.title
        pull = (self.backup_minute + 30) % 60
        return {
            f'{s}-watch.service': f'''# The {t} watch, one run (docs/DEPLOY.md "Watching"). Installed with deploy/{s}-watch.timer:
#   cp deploy/{s}-watch.{{service,timer}} /etc/systemd/system/ && systemctl enable --now {s}-watch.timer
[Unit]
Description={t} watch: one probe against the thresholds, one Zulip line per crossed threshold
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
Environment=DELVETALK_HOME={p["home"]}
ExecStart={p["home"]}/watch.sh
TimeoutStartSec=120
''',
            f'{s}-watch.timer': f'''# Every five minutes (docs/OPERATIONS.md section b).
[Unit]
Description={t} watch every five minutes

[Timer]
OnCalendar=*:0/5
Persistent=true
AccuracySec=30s

[Install]
WantedBy=timers.target
''',
            f'{s}-backup.service': f'''# /etc/systemd/system/{s}-backup.service
[Unit]
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
EnvironmentFile={p["home"]}/.env
WorkingDirectory={p["home"]}
ExecStart={p["home"]}/deploy/backup.sh --image ${{DELVETALK_HOST_IMAGE}} ${{DELVETALK_DATA}} {p["backups"]}
Nice=10
IOSchedulingClass=idle
''',
            f'{s}-backup.timer': f'''# /etc/systemd/system/{s}-backup.timer
[Timer]
OnCalendar=*-*-* 00/6:{self.backup_minute:02d}:00
RandomizedDelaySec=5m
Persistent=true
[Install]
WantedBy=timers.target
''',
            f'{s}-pull-backups.service': f'''# ~/.config/systemd/user/{s}-pull-backups.service — ON HBOX, user hbox (linger on).
# Pulls the workhorse's verified {t} tarballs into {p["pulled"]}, applies 7/56/forever,
# and replays the newest (delvetalk repo deploy/pull-backups.sh + deploy/verify.sh, copied beside pull.env).
# The key (~/.ssh/{s}-backups) is pinned on the workhorse to `rrsync -ro {p["backups"]}`;
# the workhorse holds no credential to hbox.
# pull.env names the host image of the deployed commit: DELVETALK_HOST_IMAGE=delvetalk-host:<sha12>.
# On a new binary, build it here (it then exists in hbox's docker) and change pull.env.
[Unit]
Description=Pull and replay-verify {t} backups from the workhorse

[Service]
Type=oneshot
EnvironmentFile={p["pull_dir"]}/pull.env
ExecStart={p["pull_dir"]}/pull-backups.sh --from {BACKUP_PULL} --key {p["pull_key"]} --image ${{DELVETALK_HOST_IMAGE}} {p["pulled"]}
Nice=10
IOSchedulingClass=idle
TimeoutStartSec=30min
''',
            f'{s}-pull-backups.timer': f'''# ~/.config/systemd/user/{s}-pull-backups.timer — ON HBOX. Every six hours at :{pull:02d} UTC,
# thirty minutes after the workhorse's {"delvetalk-v2-backup.timer" if self.name == LIVE else s + "-backup.timer"} (00/6:{self.backup_minute:02d} UTC, up to 5 min late).
[Unit]
Description=Pull {t} backups every six hours

[Timer]
OnCalendar=*-*-* 00/6:{pull:02d}:00 UTC
Persistent=true
RandomizedDelaySec=2m

[Install]
WantedBy=timers.target
'''}

    def caddy(self):
        """The instance's site block for the anchor's Caddy (dregg-infra edge/anchor/Caddyfile; the installed one is
        /etc/caddy/Caddyfile there): TLS for its host, the hand's paths answered 404 (the hand has its own listener on
        the workhorse's loopback), bodies capped at the front's MAX_BODY, everything else to its front's port."""
        firehose = f'\treverse_proxy /xrpc/com.atproto.sync.subscribeRepos {PRIVATE_IP}:{self.firehose_port}\n' if self.firehose else ''
        return f'''{self.host} {{
\timport baseline_headers
\tencode zstd gzip
\t@hand path /hand /hand/*
\trespond @hand 404
\trequest_body {{
\t\tmax_size 262144
\t}}
{firehose}\treverse_proxy {PRIVATE_IP}:{self.http_port} {{
\t\ttransport http {{
\t\t\tdial_timeout 3s
\t\t\tresponse_header_timeout 60s
\t\t}}
\t}}
}}
'''

    def toml(self):
        """The state's delvetalk.toml from the table's `config` (each key a transport/config.py field), or None."""
        if not self.config:
            return None
        from transport.config import TYPES
        unknown = sorted(set(self.config) - set(TYPES))
        if unknown:
            raise SystemExit(f'instance {self.name}: config names no setting {", ".join(unknown)}')

        def value(v):
            return ('true' if v else 'false') if isinstance(v, bool) else repr(v) if isinstance(v, (int, float)) else \
                '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'
        return f'# {self.paths["data"]}/state/delvetalk.toml: {self.title}\'s choices (transport/config.py)\n' + \
            ''.join(f'{k} = {value(v)}\n' for k, v in self.config.items())


def load(path=INSTANCES):
    """{name: Instance} from instances.toml, in its order."""
    table = tomllib.loads(Path(path).read_text())
    return {name: Instance(name=name, **fields) for name, fields in table.items()}


def check(instances):
    """Why two instances would collide on the one box (a port, a path, an origin, a backup minute), or []. Paths an
    instance names as another's on purpose (the shared Anthropic key, the watch bot's rc) are not collisions."""
    problems, seen = [], {}
    shared = {'anthropic_key', 'watch_zuliprc'}
    for i in instances.values():
        claims = [('port', i.http_port), ('port', i.hand_port), ('port', i.firehose_port), ('origin', i.origin),
                  ('project', i.project), ('backup minute', i.backup_minute % 30)]
        claims += [('path', v) for k, v in i.paths.items() if k not in shared]
        for what, v in claims:
            if (what, v) in seen and seen[what, v] != i.name:
                problems.append(f'{i.name} and {seen[what, v]} share the {what} {v}')
            seen.setdefault((what, v), i.name)
        if len({i.http_port, i.hand_port, i.firehose_port}) != 3:
            problems.append(f'{i.name} names one port twice')
    return problems


def render(i, out, image=None, host_image=None):
    """Write `i`'s kit into `out`; -> the paths written."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = {'env': i.env(*(x for x in (image, host_image) if x)), **i.units(), 'Caddyfile.site': i.caddy()}
    if i.toml() is not None:
        files['delvetalk.toml'] = i.toml()
    for name, text in files.items():
        (out / name).write_text(text)
    return [out / name for name in files]


def main(argv=None):
    ap = argparse.ArgumentParser(prog='deploy.instance', description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='verb', required=True)
    sub.add_parser('check')
    r = sub.add_parser('render')
    r.add_argument('name')
    r.add_argument('--out', required=True)
    r.add_argument('--image')
    r.add_argument('--host-image')
    a = ap.parse_args(argv)
    instances = load()
    problems = check(instances)
    if a.verb == 'check' or problems:
        print('\n'.join(problems) or f'{len(instances)} instances, apart: ' + ', '.join(i.project for i in instances.values()),
              file=sys.stderr if problems else sys.stdout)
        return 1 if problems else 0
    if a.name not in instances:
        print(f'no instance {a.name}; deploy/instances.toml names {", ".join(instances)}', file=sys.stderr)
        return 64
    for path in render(instances[a.name], a.out, a.image, a.host_image):
        print(path)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
