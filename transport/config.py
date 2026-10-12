"""The transport's one configuration (docs/OPERATIONS.md section b): every setting the programs share is a field below,
with its default and what it means, and nothing else holds a default. `Config.load(state)` reads `<state>/delvetalk.toml`
(optional; an unknown key or a value of the wrong type is refused by name), then the environment: `DELVETALK_<FIELD>`
overrides `<field>`. A world's bridge is not configuration here but its row (`State.bridge`), which `open` writes."""
import dataclasses
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / 'world' / 'lib'  # what serve seals at its start
ORIGIN = 'https://gsb.fg-goose.online'
PREFIX = 'DELVETALK_'


def field(default, what):
    return dataclasses.field(default=default, metadata={'what': what})


@dataclasses.dataclass(frozen=True)
class Config:
    origin: str = field(ORIGIN, "the front's public origin: links in posts, the repository's did:web, the login's client id")
    opener: str = field('did:plc:6amo7col5h4ciq2gpm5eur7b', "the world's opener (ember.delve.town): serve's --opener, the hand's principal")
    host_socket: str = field('', "serve's public socket (default <state>/host.sock)")
    root_socket: str = field('', "serve's root socket, the opener's (default <state>/root/root.sock)")
    root_group: str = field('', "the root socket's group, so the hand may run under a uid of its own (default serve's)")
    library: str = field(str(LIBRARY), 'the library serve seals at its start')
    sync: str = field('fsync', "how serve makes an append durable: none, fsync or full")
    obend: str = field('delvetalk-obend', 'the host binary `serve` runs')
    poll: int = field(60, 'seconds between two steps of the bridge')
    model_poll: float = field(1.0, "seconds between two rounds of the model worker (interpretations and paints): a paint must come inside the host's patience")
    http_bind: str = field('127.0.0.1', "the front's listening address")
    http_port: int = field(8765, "the front's port (the one the edge's Caddy route names)")
    firehose_bind: str = field('127.0.0.1', "subscribeRepos listener's address, independent of HTTP workers")
    firehose_port: int = field(0, "subscribeRepos listener's TCP port; 0 disables it; the edge routes its WebSocket path here")
    trust_proxy: bool = field(False, "key the front's unauthenticated limits on the last X-Forwarded-For entry")
    hand_bind: str = field('127.0.0.1', "the hand's listening address: loopback, reached by an ssh forward")
    hand_port: int = field(8766, "the hand's port")
    hand_token_file: str = field('', "the file holding the hand's secret, read once at its start")
    summon_handle: str = field('livedelvetalk.delve.town', "the town's address on delve.town, whose mention summons it: fictional, matched as the post's text, never resolved; its replies go out through `credentials`, the owner's account")
    requests: bool = field(False, "poll residents' `online.fg-goose.gsb.request` records from the PDS (transport/requests.py): "
                           "reads every repository pds.delve.town lists; off until the owner turns it on")
    credentials: str = field('~/.config/delvetown/credentials.json', "the Delve posting account's credentials, read only to post")
    repo_keys: str = field('/etc/delvetalk/repo', "the directory of the repositories' signing keys, <world>.key; unsigned without one")
    backups: str = field('/var/backups/delvetalk', "backup.sh's destination, whose newest tarball and last verify the probe reads")
    anthropic_key_file: str = field('', 'the file holding the Anthropic API key (model_auth key)')
    model_auth: str = field('key', 'key: the API key; oauth: the subscription accounts in tokens_toml')
    model_thinking: bool = field(False, "let the model think before it answers (off: it spent 0 to 337 tokens on `unclear:` lines)")
    model_account: str = field('', 'model_auth oauth: the account to try first (default the one with the most headroom)')
    key_name: str = field('key', 'the name model-spend.jsonl gives the API key')
    tokens_toml: str = field('~/.config/tokeman/tokens.toml', "model_auth oauth: tokeman's accounts")
    delve_mock: str = field('', "the bridge observes these fixture pages instead of delve.town (tests, the rehearsal)")
    model_mock: str = field('', 'the interpreter answers from these model fixtures instead of the network')
    watch_zuliprc: str = field('', "the watch bot's .zuliprc")
    watch_stream: str = field('delvetalk-ops', 'the stream the watch posts to')
    watch_topic: str = field('watch', 'the topic the watch posts to')
    welcome: str = field(str(ROOT / 'docs' / 'previews' / 'zulip-welcome.txt'), 'the welcome deploy/playtest.sh posts')
    grant: float = field(200.0, 'the monthly API credit in dollars, against which the hand reports spend')
    plan: str = field(str(ROOT / 'docs' / 'PLAYTEST-2.md'), "the playtest's plan, whose seeds (§2) and invitations (§3) the hand's Speak offers")
    owner_principals: str = field('', "the owner's principals besides the opener (his Zulip user), space-separated: no measure counts them as residents")

    @classmethod
    def load(cls, state=None, environ=os.environ, **given):
        """The file under `state`, then the environment, then `given` (a test's or a script's own)."""
        values, path = {}, Path(state) / 'delvetalk.toml' if state else None
        if path and path.exists():
            values = {k: check(k, v, path.name) for k, v in tomllib.loads(path.read_text()).items()}
        for f in dataclasses.fields(cls):
            if PREFIX + f.name.upper() in environ:
                values[f.name] = parse(f.name, environ[PREFIX + f.name.upper()])
        return cls(**{**values, **given})


TYPES = {f.name: type(f.default) for f in dataclasses.fields(Config)}


def check(name, value, where):
    kind = TYPES.get(name)
    if kind is None:
        raise SystemExit(f'{where}: no setting {name!r}; the settings are {", ".join(TYPES)}')
    if kind is float and type(value) is int:
        value = float(value)
    if type(value) is not kind:
        raise SystemExit(f'{where}: {name} is a {kind.__name__}, not {value!r}')
    return value


def parse(name, text):
    """An environment value as its field's type."""
    kind = TYPES[name]
    if kind is bool:
        if text.lower() not in ('1', '0', 'true', 'false', 'on', 'off', 'yes', 'no'):
            raise SystemExit(f'{PREFIX}{name.upper()}: on or off, not {text!r}')
        return text.lower() in ('1', 'true', 'on', 'yes')
    try:
        return kind(text)
    except ValueError:
        raise SystemExit(f'{PREFIX}{name.upper()}: a {kind.__name__}, not {text!r}') from None
