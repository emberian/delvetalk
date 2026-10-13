"""What a spell cites, read before the spell is carried: each at:// URI in its text, read once, read-only, and written on
the desk of the register the spell is cast on, as what was read: `<uri> <cid>`, or `<uri> absent` when the repository
answers RecordNotFound. A URI in a delve.town repository is read from pds.delve.town (`com.atproto.repo.getRecord`,
transport/delve.Client.record); one in the town's own repository (its did:web) is never sent there: a post of the town's
own feed is read from the feed's store, `<uri> <cid> <author>` (the repository is the town's, the words the author's),
and any other record of it is left unread. Carries bytes; decides nothing: a register (world/bodies/register.obend) holds
each anchor to these lines at its admission, and the desk's law takes lines from the transport alone (deploy/genesis.py
`DESK_LAW`). A repository that cannot be reached writes nothing, and a register then holds that anchor unresolved.

`before` is the bridge's and the front's call (transport/bridge.run for posts, the feed and request records;
transport/http.Server.turn for the web and the API): only a turn on a card whose state names a `desk` reads, nothing in
the host reaches the network, and reads are bounded: `MOST` URIs a turn, `TIMEOUT` seconds a read and `TURN` a turn,
`HOURLY` reads an hour in this process and `HAND` an hour for one principal; a URI read in the last `FRESH` seconds is
not read again. What a bound leaves unread stands unresolved, and the turn is carried as it would be.

The identity of a desk line is `read:<uri>:<cid>` (or `:absent`), so a reading is journaled once, and a post rewritten
under its URI is read again at its new CID beside the old one.
"""
import collections
import re
import threading
import time

from transport.delve import POST, Client, Failure, http_transport, parse_at_uri

AT = re.compile(r'at://[A-Za-z0-9:._%-]+/[A-Za-z0-9.-]+/[A-Za-z0-9._~:-]+')
SPELL = re.compile(r'^\s*delvetalk\s+(\S+)', re.M)
MOST = 8  # at:// URIs read for one turn; a turn citing more has the rest held unresolved
TIMEOUT = 5  # seconds for one read from pds.delve.town
TURN = 12  # seconds of reading for one turn, after which the rest stand unresolved
HOURLY = 240  # reads from pds.delve.town an hour, in one process (the bridge's, the front's)
HAND = 40  # of which, for one principal
FRESH = 600  # seconds a reading stands before the same URI is read again
CARDS = 3  # cards a turn's text names whose desks are looked for


def uris(text):
    """The at:// record URIs a text cites, in order, each once, at most MOST."""
    out = []
    for uri in AT.findall(text or ''):
        try:
            parse_at_uri(uri)
        except Failure:
            continue
        if uri not in out:
            out.append(uri)
    return out[:MOST]


def cited(argument):
    """The text of a turn's typed argument, every label but the `post` it answers (the post a spell came in is not
    one it cites)."""
    out = []

    def walk(v, name=None):
        if isinstance(v, dict):
            if v.get('tag') == 'label' and name != 'post':
                out.append(str(v.get('value', '')))
            for f in v.get('fields') or []:
                walk(f.get('value'), f.get('name'))
            for item in v.get('items') or []:
                walk(item)
            if isinstance(v.get('payload'), dict):
                walk(v['payload'])
    walk(argument)
    return '\n'.join(out)


def reading(client, uri):
    """`<cid>` as the repository serves the record, `absent` for RecordNotFound, None when it could not be read."""
    try:
        got = client.record(uri)
    except Failure as e:
        return 'absent' if 'RecordNotFound' in str(e) else None
    cid = got.get('cid') if isinstance(got, dict) else None
    if got.get('uri') not in (uri, None) or not isinstance(cid, str) or not re.fullmatch(r'b[a-z2-7]{20,200}', cid):
        return None
    return cid


def written(host, desk, principal, uri, cid, author=''):
    """The reading on the desk, as `principal`: the host's status."""
    line = f'{uri} {cid}' + (f' {author}' if author else '')
    return host.send({'op': 'world-turn', 'principal': principal, 'object': desk, 'method': 'write', 'identity': f'read:{uri}:{cid}',
                      'argument': {'tag': 'record', 'fields': [{'name': 'text', 'value': {'tag': 'label', 'value': line}}]}}).get('status')


def desk_of(host, obj):
    """The desk a card's state names (a register's `desk` field), '' for none."""
    view = host.send({'op': 'world-view', 'principal': 'transport', 'object': obj})
    state = view.get('state') if view.get('status') == 'viewed' else None
    for f in (state or {}).get('fields') or []:
        if f['name'] == 'fields':
            for row in f['value'].get('items') or []:
                kv = {x['name']: x['value'].get('value') for x in row.get('fields') or []}
                if kv.get('name') == 'desk':
                    return kv.get('value') or ''
    return ''


class Reader:
    """The bounded reader one process keeps (`before`): its hour's reads, each principal's, and what it read lately."""

    def __init__(self, client=None, own=(), feed=None, clock=time.monotonic, hourly=HOURLY, hand=HAND):
        self.client = client or Client(transport=lambda method, url, headers, body: http_transport(method, url, headers, body, timeout=TIMEOUT))
        self.own, self.feed, self.clock, self.hourly, self.hand = set(own), feed, clock, hourly, hand
        self.reads = collections.deque()  # (when, principal) of each read from pds.delve.town this hour
        self.fresh = {}  # (desk, uri) -> when it was written
        self.lock = threading.Lock()

    def spent(self, who):
        """Whether the hour's reads, or `who`'s, are spent (and one more counted when not)."""
        with self.lock:
            now = self.clock()
            while self.reads and self.reads[0][0] <= now - 3600:
                self.reads.popleft()
            if len(self.reads) >= self.hourly or sum(1 for _, w in self.reads if w == who) >= self.hand:
                return True
            self.reads.append((now, who))
            return False

    def ours(self, uri):
        """(cid, author) of a post of the town's own feed, 'absent' when the feed holds none at that URI, None for a record
        of the town's repository that is not a feed post (or with no feed to read)."""
        parsed = parse_at_uri(uri)
        if parsed.collection != POST or self.feed is None:
            return None
        row = self.feed.get(uri)
        return (row['cid'], row['did']) if row else 'absent'

    def before(self, host, objects, text, who):
        """Read what `text` cites onto the desk of each card in `objects` (those whose state names one) before `who`'s
        turn on them; -> [(uri, cid or 'absent' or None, status)]."""
        found = uris(text)
        if not found:
            return []
        desks = list(dict.fromkeys(d for d in (desk_of(host, o) for o in list(dict.fromkeys(objects))[:CARDS]) if d))
        if not desks:
            return []
        out, deadline = [], self.clock() + TURN
        if len(self.fresh) > 4096:  # what is no longer fresh is forgotten, so the process holds at most what an hour read
            self.fresh = {k: t for k, t in self.fresh.items() if self.clock() - t <= FRESH}
        for uri in found:
            pending = [d for d in desks if self.clock() - self.fresh.get((d, uri), -FRESH - 1) > FRESH]
            if not pending:
                out.append((uri, None, 'fresh'))
                continue
            author = ''
            if parse_at_uri(uri).repo in self.own:
                got = self.ours(uri)
                cid, author = (got if isinstance(got, tuple) else (got, ''))
                status = 'unread' if got is None else None
            elif self.clock() > deadline:
                cid, status = None, 'late'
            elif self.spent(who):
                cid, status = None, 'spent'
            else:
                cid = reading(self.client, uri)
                status = None if cid else 'unread'
            if status:
                out.append((uri, None, status))
                continue
            for d in pending:
                got = written(host, d, 'transport', uri, cid, author)
                if got == 'admitted':
                    self.fresh[(d, uri)] = self.clock()
                out.append((uri, cid, got))
        return out


def cards(obj, text):
    """The cards a turn is on: the one it reached, then each a spell line in its text names."""
    return [o for o in [obj, *SPELL.findall(text or '')] if o]


def before(reader, host, obj, argument, who):
    """The bridge's and the front's hook: what a turn's argument cites, read onto its card's desk before it is sent.
    Never fails the turn: a failure to read is an anchor left unresolved. -> before's rows, or [] on any error."""
    try:
        text = cited(argument)
        return reader.before(host, cards(obj, text), text, who) if AT.search(text) else []
    except Exception:  # noqa: BLE001 (a reading never stops a turn: the anchor stands unresolved)
        return []


class Feed:
    """The town's own feed, opened at its first post (transport/feed.py), read for a feed post's CID and author."""

    def __init__(self, st):
        self.st, self.store = st, None

    def get(self, uri):
        from transport import feed
        if self.store is None and feed.exists(self.st):
            self.store = feed.Feed(self.st)
        return self.store.get(uri) if self.store else None


READERS = {}


def reader_for(st):
    """This process's Reader for a world's state (`State`): its repositories (the feed's did:web, the world's)."""
    key = str(st.home)
    if key not in READERS:
        from transport import feed
        from transport.repo import world_did
        READERS[key] = Reader(own={feed.authority(st.config.origin, st.world), world_did(st.config.origin, st.world)[0]}, feed=Feed(st))
    return READERS[key]
