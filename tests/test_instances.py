"""The deploy as a template (docs/DEPLOY.md "A second instance", deploy/instance.py): the live town's name renders the
files it runs today byte for byte, every value compose reads comes from an instance's `.env`, and two instances on the
one box share no port, path, origin or backup minute.

Evidence for docs/DEPLOY.md "A second instance" (layer: transport).
"""
import re
import tempfile
import unittest
from pathlib import Path

from deploy import instance
from transport.config import Config

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = (ROOT / 'docs' / 'DEPLOY.md').read_text()


def block(first, last, indent):
    """The lines of DEPLOY.md indented `indent`, from the one that is `first` to the next that is `last`, dedented."""
    lines = DEPLOY.split('\n')
    start = next(n for n, line in enumerate(lines) if line == ' ' * indent + first)
    end = next(n for n in range(start, len(lines)) if lines[n] == ' ' * indent + last)
    return ''.join(line[indent:] + '\n' for line in lines[start:end + 1])


class Live(unittest.TestCase):
    """The instance `delvetalk` is the live town as it runs: its units, its backup timer and its Caddy block are the bytes
    the workhorse and the anchor hold, so rendering it changes nothing."""

    def setUp(self):
        self.live = instance.load()[instance.LIVE]

    def test_its_watch_units_are_the_checked_in_files(self):
        units = self.live.units()
        for name in ('delvetalk-watch.service', 'delvetalk-watch.timer'):
            self.assertEqual(units[name], (ROOT / 'deploy' / name).read_text(), name)

    def test_its_backup_timer_is_the_one_installed(self):
        units = self.live.units()
        self.assertEqual(units['delvetalk-backup.service'] + units['delvetalk-backup.timer'],
                         block('# /etc/systemd/system/delvetalk-backup.service', 'WantedBy=timers.target', 4))

    def test_its_caddy_block_is_the_installed_gsb_route(self):
        self.assertEqual(self.live.caddy(), block('gsb.fg-goose.online {', '}', 6))

    def test_its_paths_are_the_ones_it_has_always_had(self):
        env = dict(line.split('=', 1) for line in self.live.env().splitlines() if not line.startswith('#'))
        self.assertEqual((env['COMPOSE_PROJECT_NAME'], env['DELVETALK_DATA'], env['DELVETALK_ROOT'], env['DELVETALK_REPO_KEYS'],
                          env['DELVETALK_HTTP_PORT'], env['DELVETALK_HAND_PORT'], env['DELVETALK_OPENER']),
                         ('delvetalk', '/var/lib/delvetalk/v16', '/var/lib/delvetalk/root', '/etc/delvetalk/repo', '8765', '8766',
                          'did:plc:6amo7col5h4ciq2gpm5eur7b'))

    def test_against_compose_defaults_only_the_data_directory_and_the_station_differ(self):
        """compose.yml's own defaults are the live town's; its `.env` moved two of them since (v11 to v16 by the
        carries, the station by the owner's word), and names the rest as compose would take them."""
        defaults = {}
        for name in ('compose.yml', 'compose.hand.yml'):
            for var, default in re.findall(r'\$\{(\w+):-([^}]*)\}', (ROOT / 'deploy' / name).read_text()):
                defaults.setdefault(var, default)
        env = dict(line.split('=', 1) for line in self.live.env(image=defaults['DELVETALK_IMAGE']).splitlines() if not line.startswith('#'))
        differ = {k for k, v in defaults.items() if env.get(k) != v}
        self.assertEqual(differ, {'DELVETALK_DATA', 'DELVETALK_STATION'}, {k: (defaults[k], env.get(k)) for k in differ})


class Instances(unittest.TestCase):

    def setUp(self):
        self.all = instance.load()
        self.open = self.all['open']

    def test_every_variable_compose_reads_is_in_each_env(self):
        """A variable an instance's `.env` did not name would fall to compose's default, the live town's: none does."""
        used = set()
        for name in ('compose.yml', 'compose.hand.yml', 'compose.firehose.yml'):
            used |= set(re.findall(r'\$\{(\w+)', (ROOT / 'deploy' / name).read_text()))
        for i in self.all.values():
            named = {line.split('=', 1)[0] for line in i.env().splitlines() if not line.startswith('#')}
            self.assertEqual(used - named, set(), i.name)

    def test_the_open_instance_owns_nothing_of_the_live_town(self):
        live = self.all[instance.LIVE].paths
        for what, path in self.open.paths.items():
            if what in ('anthropic_key', 'watch_zuliprc'):  # shared on purpose: the one key and the one watch bot
                self.assertEqual(path, live[what])
                continue
            self.assertFalse(path == live[what] or path.startswith(live[what].rstrip('/') + '/'), (what, path))
        env = self.open.env()
        self.assertIn('COMPOSE_PROJECT_NAME=delvetalk-open\n', env)
        self.assertIn('DELVETALK_OPENER=did:web:obend.fg-goose.online\n', env)  # the origin's did:web, never the live opener
        self.assertIn('DELVETALK_TOWNS=/var/lib/delvetalk-open\n', env)  # genesis's guard looks at this instance's towns
        self.assertIn('reverse_proxy 10.10.1.10:8775 {', self.open.caddy())

    def test_each_hand_is_behind_the_anchors_password_with_its_token_from_the_anchors_file(self):
        """No `respond @hand 404` left on an instance's name: `/hand` asks the password, the client's own token header is
        stripped on every path, and the hand on the private address gets the token Caddy reads from its own file, never
        the Authorization; no secret is in the block."""
        files = set()
        for i in self.all.values():
            site = i.caddy()
            self.assertNotIn('respond @hand 404', site)
            for line in ('request_header -X-Delvetalk-Hand-Token', f'import {instance.HAND_USERS}', 'header Cache-Control "no-store"',
                         f'reverse_proxy {instance.PRIVATE_IP}:{i.hand_port} {{', 'header_up -Authorization',
                         f'header_up X-Delvetalk-Hand-Token {{file.{i.hand_token_at_edge}}}'):
                self.assertIn(line, site, (i.name, line))
            self.assertLess(site.index('handle @hand {'), site.index(f'reverse_proxy {instance.PRIVATE_IP}:{i.http_port} {{'))
            files.add(i.hand_token_at_edge)
        self.assertEqual(len(files), len(self.all))  # each hand its own token
        hand = (ROOT / 'deploy' / 'compose.hand.yml').read_text()
        self.assertIn('- "${DELVETALK_PRIVATE_IP:-10.10.1.10}:${DELVETALK_HAND_PORT:-8766}:${DELVETALK_HAND_PORT:-8766}/tcp"', hand)
        self.assertIn('- "127.0.0.1:${DELVETALK_HAND_PORT:-8766}:${DELVETALK_HAND_PORT:-8766}/tcp"', hand)  # root's ssh forward

    def test_check_refuses_two_instances_on_one_port_or_path(self):
        self.assertEqual(instance.check(self.all), [])
        twin = instance.Instance(name='twin', origin='https://twin.example', data='v1', http_port=8775, hand_port=8796,
                                 firehose_port=8797, backup_minute=47)
        self.assertIn('twin and open share the port 8775', instance.check({**self.all, 'twin': twin}))
        twin = instance.Instance(name='twin', origin=self.open.origin, data='v1', http_port=8785, hand_port=8786,
                                 firehose_port=8787, backup_minute=17)
        problems = instance.check({**self.all, 'twin': twin})
        self.assertIn(f'twin and open share the origin {self.open.origin}', problems)
        self.assertIn('twin and delvetalk share the backup minute 17', problems)

    def test_the_rendered_config_is_one_the_transport_reads(self):
        with tempfile.TemporaryDirectory() as d:
            written = {p.name for p in instance.render(self.open, d)}
            self.assertIn('delvetalk.toml', written)
            self.assertEqual({'delvetalk-open-watch.service', 'delvetalk-open-backup.timer', 'delvetalk-open-pull-backups.service', 'env',
                              'Caddyfile.site'} - written, set())
            config = Config.load(d, environ={})
            self.assertEqual((config.hand_find, config.watch_topic), (False, 'watch-open'))

    def test_a_config_key_the_transport_lacks_is_refused(self):
        bad = instance.Instance(name='bad', origin='https://bad.example', data='v1', http_port=1, hand_port=2, firehose_port=3,
                                backup_minute=5, config={'no_such_setting': 1})
        with self.assertRaises(SystemExit):
            bad.toml()



class Image(unittest.TestCase):
    """The transport image carries every document the transport and genesis read at run time: an open town's genesis
    read docs/AGENTS-ARRIVE.md, which the image lacked, and refused at the deploy of obend (2026-10-14); the
    rehearsal ran from a checkout, which has every file. A file must be both in the build context (the dockerignore's
    re-included paths) and copied."""

    def test_every_document_read_at_run_time_is_copied_into_the_image(self):
        from deploy import genesis
        from transport import http, pages
        copied = set()
        for line in (ROOT / 'deploy' / 'Dockerfile.transport').read_text().splitlines():
            if line.startswith('COPY ') and '--from' not in line:
                copied.update(line.split()[1:-1])
        context = [line[1:] for line in (ROOT / 'deploy' / 'Dockerfile.transport.dockerignore').read_text().splitlines()
                   if line.startswith('!')]  # the build context is `*` and these, re-included
        read = {pages.GUIDE, pages.ARRIVE, http.EXAMPLES, genesis.GUIDE, Path(Config().plan)}
        for path in sorted(read):
            rel = path.resolve().relative_to(ROOT).as_posix()
            self.assertTrue(any(rel == c or rel.startswith(c.rstrip('/') + '/') for c in copied),
                            f'{rel} is read at run time but deploy/Dockerfile.transport does not copy it')
            self.assertTrue(any(rel == c or rel.startswith(c.rstrip('/') + '/') for c in context),
                            f'{rel} is read at run time but deploy/Dockerfile.transport.dockerignore leaves it out of the build')


if __name__ == '__main__':
    unittest.main()
