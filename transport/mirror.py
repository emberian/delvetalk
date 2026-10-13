"""The town as records on the PDS (docs/POSTING.md §1): `python3 -m transport mirror`.

A resident whose window is the PDS reads, walks doors and counts from a mirror of it, with no post. So the world's
readable state is written as records in the posting account's own repository: every card as the public reads it
(`online.fg-goose.gsb.card`), the library's pages and walks and the guide's parts (`online.fg-goose.gsb.page`), an index
(`online.fg-goose.gsb.index/self`) and the answers to residents' requests (`online.fg-goose.gsb.answer`, the bridge's).
The posting account alone holds `online.fg-goose.gsb.checkpoint/self`, naming the signed head observed before reading
the host. The index names no head. Each card and page is what `place` renders (transport/host.py), the rendering
the web's pages and a reply's draft share;
the did:web façade (transport/repo.py) answers the journal-derived collections from these functions. Only the public
reader's projection is written. Without the authorizing flag the run reads and prints what it would write;
with it, `post.record_writer` writes what changed since the last run and deletes what is gone.
"""
import json
import time
import urllib.parse
from pathlib import Path

from transport.delve import Client, Failure, canonical, http_transport
from transport.host import PUBLIC, place, plain
from transport import records as record_plan

NS = 'online.fg-goose.gsb.'
CARD, PAGE, INDEX, ANSWER = NS + 'card', NS + 'page', NS + 'index', NS + 'answer'
CHECKPOINT = NS + 'checkpoint'
LIBRARY = 'library'


def card_key(oid):
    """A card's record key: its id with each `/` as `~` (ids are `[A-Za-z0-9._:/-]`, so every id has one)."""
    return oid.replace('/', '~')


def card_record(host, oid, reader=PUBLIC, sleep=time.sleep, paint=True):
    """The card record of `oid` as `reader` reads it, or None when the reader may not view it or it has no card."""
    here = place(host, reader, oid, sleep, paint)
    if here['card'] is None:
        return None
    return {'$type': CARD, 'object': oid, 'version': here['version'], 'card': here['card'],
            **({'paint': here['paint']} if here['paint'] else {}),
            'wants': here['wants'], 'doors': [{'label': d.get('label', ''), 'to': d['to']['object']} for d in here['doors']]}


def library_pages(host, reader=PUBLIC):
    """The library's pages in shelf order, [{name, kind, title, body, place}], as the reader may view them."""
    view = host.send({'op': 'world-view', 'principal': reader, 'object': LIBRARY})
    if view.get('status') != 'viewed':
        return []
    pages = (plain(view.get('state') or {}) or {}).get('pages') or {}
    rows = pages.get('items') if isinstance(pages, dict) else pages
    return sorted(({'name': p['name'], 'kind': (p.get('kind') or {}).get('tag', 'page'), 'title': p.get('title', ''),
                    'body': p.get('body', ''), 'place': p.get('place', 0)} for p in rows or [] if isinstance(p, dict)),
                  key=lambda p: p['place'])


def page_record(page):
    return {'$type': PAGE, **page}


def ids(host, reader=PUBLIC):
    """Every id the reader may view, in the host's order, following its pages."""
    out, after = [], None
    while True:
        listed = host.send({'op': 'world-objects', 'principal': reader, **({'after': after} if after else {})})
        if listed.get('status') != 'listed':
            return out
        out += listed.get('ids') or []
        if not listed.get('more') or not listed.get('ids'):
            return out
        after = out[-1]


def answer_records(directory):
    """{rkey: value}: public request and XRPC answers written through bridge.write_answer."""
    if not directory or not Path(directory).is_dir():
        return {}
    return {p.stem: json.loads(p.read_text()) for p in sorted(Path(directory).glob('*.json'))}


def height(host):
    return host.send({'op': 'world-status'}).get('height')


def records(host, sleep=time.sleep, paint=True, tries=3, answers=None):
    """{(collection, rkey): value}: the whole mirror as the public reads the world at one height, with the `answers`
    directory's. The cards and pages are read between two looks at the height; when the world moved meanwhile they are
    read again (up to `tries`), and an index read across a move says so (`coherent: false`, its `heights`)."""
    for _ in range(tries):
        before, out, cards = height(host), {(ANSWER, k): v for k, v in answer_records(answers).items()}, {}
        for oid in ids(host):
            record = card_record(host, oid, PUBLIC, sleep, paint)
            if record:
                out[CARD, card_key(oid)] = record
                cards[oid] = record['version']
        pages = library_pages(host)
        for p in pages:
            out[PAGE, p['name']] = page_record(p)
        after = height(host)
        if after == before:
            break
    out[INDEX, 'self'] = index_record(cards, pages, before, after)
    return out


def index_record(cards, pages, before, after=None):
    """The manifest: the height the records were read at, each card's version (a reader holding a card of another
    version holds another generation) and the pages by name. Names no head; written after every record it lists."""
    after = before if after is None else after
    return {'$type': INDEX, 'height': before, 'coherent': before == after, **({} if before == after else {'heights': {'from': before, 'to': after}}),
            'cards': cards, 'pages': [p['name'] for p in pages],
            'read': f'each card is {CARD}/<id, / as ~>, at the version listed here; each page {PAGE}/<name>'}


def checkpoint_record(did, rev, commit, height):
    """The posting account's source checkpoint: bytes depend only on the commit it names."""
    return {'$type': CHECKPOINT, 'did': did, 'rev': rev, 'commit': commit, 'height': height}


def signed_checkpoint(st, fetch):
    """-> (checkpoint, why unavailable): read the world's front before reading any host records.
    This is a lower bound on the reads, not a snapshot of the named commit."""
    from transport.repo import world_did, world_origin
    origin = world_origin(st.config.origin, st.world)
    did, _ = world_did(st.config.origin, st.world)
    client = Client(fetch)

    def get(nsid, **params):
        return client._send('GET', f'{origin}/xrpc/{nsid}?{urllib.parse.urlencode(params)}')

    try:
        head = get('com.atproto.sync.getLatestCommit', did=did)
        rev, commit = head.get('rev'), head.get('cid')
        if not all(isinstance(v, str) and v for v in (rev, commit)):
            raise Failure('checkpoint_invalid', 'head needs rev and cid strings')
        entry = get('com.atproto.repo.getRecord', repo=did, collection=NS + 'entry', rkey=rev).get('value')
        h = entry.get('height') if isinstance(entry, dict) else None
        if type(h) is not int or h < 1:
            raise Failure('checkpoint_invalid', 'entry needs a positive height')
        return checkpoint_record(did, rev, commit, h), None
    except (Failure, OSError) as error:
        return None, str(error)


def fingerprint(value):
    """The index's height alone moving is no change."""
    return record_plan.digest({**value, 'height': None} if value.get('$type') == INDEX else value)


def plan(st, now):
    """-> (writes, deletes, ledger): the mirror's shared digest plan. An unavailable checkpoint
    stays held; an available one also follows every changed index."""
    checkpoint = f'{CHECKPOINT} self'
    writes, deletes, ledger = record_plan.plan(st.mirror, now, fingerprint, retain=(checkpoint,))
    if f'{INDEX} self' in writes and (CHECKPOINT, 'self') in now:
        writes[checkpoint] = now[CHECKPOINT, 'self']
    return writes, deletes, ledger


def run(st, host, writer=None, sleep=lambda _: None, limit=200, fetch=http_transport):
    """One mirror step: the plan, and with a `writer` (post.record_writer) at most `limit` ordinary writes/deletes, the ledger
    saved after each record that landed. The index and checkpoint follow only once that plan is complete,
    outside the batch limit. A paint not ready is not waited for (`sleep`): asking starts it, and the
    next step writes it. Without a writer, only reads occur, including the source head lookup."""
    checkpoint, why = signed_checkpoint(st, fetch)
    now = records(host, sleep, answers=st.answers)
    if checkpoint is not None:
        now[CHECKPOINT, 'self'] = checkpoint
    writes, deletes, ledger = plan(st, now)
    status = {'checkpoint': why} if checkpoint is None else {}
    if writer is None:
        return {'dry_run': True, 'writes': sorted(writes), 'deletes': sorted(deletes), **status}
    return {**record_plan.put_records(st, st.mirror, writes, deletes, ledger, writer, fingerprint,
                                      limit=limit, final=(f'{INDEX} self', f'{CHECKPOINT} self')), **status}


def command(st, a, out, client=None, fetch=http_transport):
    """`mirror`: one step with `--once`, else a step every `poll` seconds; a dry run without the authorizing flag."""
    from transport import post
    host = st.host()
    writer = post.record_writer(st, client) if a.authorized else None
    step = lambda: out.write(canonical(run(st, host, writer, limit=a.limit, fetch=fetch)) + '\n') and out.flush()
    try:
        step() if a.once or not a.authorized else st.daemon('mirror', step)
    finally:
        host.close()
    return 0 if a.authorized else 2
