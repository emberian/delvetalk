"""The town as records on the PDS (docs/POSTING.md §1): `python3 -m transport mirror`.

A resident whose window is the PDS reads, walks doors and counts from a mirror of it, with no post. So the world's
readable state is written as records in the posting account's own repository: every card as the public reads it
(`town.delvetalk.card`), the library's pages and walks and the guide's parts (`town.delvetalk.page`), an index
(`town.delvetalk.index/self`) and the answers to residents' requests (`town.delvetalk.answer`, the bridge's). Each
card and page is what `place` renders (transport/host.py), the rendering the web's pages and a reply's draft share;
the did:web façade (transport/repo.py) answers the same collections from these functions. Only the public reader's projection is written. Without the authorizing flag the run prints what it would write and
touches nothing; with it, `post.put_records` writes what changed since the last run and deletes what is gone.
"""
import hashlib
import json
import time
from pathlib import Path

from transport.delve import canonical
from transport.host import PUBLIC, place, plain

NS = 'town.delvetalk.'
CARD, PAGE, INDEX, ANSWER = NS + 'card', NS + 'page', NS + 'index', NS + 'answer'
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
    """{rkey: value}: the answers the bridge wrote to requests (transport/bridge.py), each the public's projection."""
    if not directory or not Path(directory).is_dir():
        return {}
    return {p.stem: json.loads(p.read_text()) for p in sorted(Path(directory).glob('*.json'))}


def records(host, sleep=time.sleep, paint=True, answers=None):
    """{(collection, rkey): value}: the whole mirror as the public reads the world now, with the `answers` directory's."""
    out, cards = {(ANSWER, k): v for k, v in answer_records(answers).items()}, []
    for oid in ids(host):
        record = card_record(host, oid, PUBLIC, sleep, paint)
        if record:
            out[CARD, card_key(oid)] = record
            cards.append(oid)
    pages = library_pages(host)
    for p in pages:
        out[PAGE, p['name']] = page_record(p)
    out[INDEX, 'self'] = index_record(host, cards, pages)
    return out


def index_record(host, cards, pages):
    """What the mirror holds and the height it was read at: the ids with a card, the pages by name."""
    return {'$type': INDEX, 'height': host.send({'op': 'world-status'}).get('height'), 'cards': cards, 'pages': [p['name'] for p in pages],
            'read': 'each card is town.delvetalk.card/<id, / as ~>; each page town.delvetalk.page/<name>'}


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def plan(st, now):
    """-> (writes, deletes, ledger): the records whose value changed since the ledger's last write, and the keys
    the ledger holds that the world no longer shows. The index's height alone moving is no change."""
    ledger = json.loads(st.mirror.read_text()) if st.mirror.exists() else {}
    held = {f'{c} {k}': v for (c, k), v in now.items()}
    same = lambda key, v: ledger.get(key) == digest({**v, 'height': None} if v.get('$type') == INDEX else v)
    writes = {key: v for key, v in held.items() if not same(key, v)}
    deletes = [key for key in ledger if key not in held]
    return writes, deletes, ledger


def run(st, host, writer=None, sleep=lambda _: None, limit=200):
    """One mirror step: the plan, and with a `writer` (post.record_writer) at most `limit` writes of it, the ledger
    saved after each record that landed. A paint not ready is not waited for (`sleep`): asking starts it, and the
    next step writes it."""
    writes, deletes, ledger = plan(st, records(host, sleep, answers=st.answers))
    if writer is None:
        return {'dry_run': True, 'writes': sorted(writes), 'deletes': sorted(deletes)}
    done = []
    for key, value in list(writes.items())[:limit]:
        collection, rkey = key.split(' ', 1)
        writer(collection, rkey, value)
        ledger[key] = digest({**value, 'height': None} if collection == INDEX else value)
        st.write(st.mirror, ledger)
        done.append(key)
    for key in deletes[:max(0, limit - len(done))]:
        collection, rkey = key.split(' ', 1)
        writer(collection, rkey, None)
        ledger.pop(key, None)
        st.write(st.mirror, ledger)
        done.append(key)
    return {'written': done, 'left': max(0, len(writes) + len(deletes) - len(done))}


def command(st, a, out, client=None):
    """`mirror`: one step with `--once`, else a step every `poll` seconds; a dry run without the authorizing flag."""
    from transport import post
    host = st.host()
    writer = post.record_writer(st, client) if a.authorized else None
    step = lambda: out.write(canonical(run(st, host, writer, limit=a.limit)) + '\n') and out.flush()
    try:
        step() if a.once or not a.authorized else st.daemon('mirror', step)
    finally:
        host.close()
    return 0 if a.authorized else 2
