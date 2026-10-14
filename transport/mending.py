"""The operator's side of the mending basket (world/objects/Mending.obend; docs/MENDING.md): the reports, read from
the basket and its drawer as the opener sees them, and an answer cast as the town's own spell.

Read: `reports(host, opener, since)` -> {cursor, reports}, newest first by the entry that last moved each (its making,
or its last answer), only those past `since`; give `cursor` back as the next `since`. The basket's own reports and the
drawer's confided ones together, each named by its card (`mending #3`, `mending/drawer #2`).

Answer: `answer_spell` writes the spell; the hand casts it (`Hand.answer_report`): a public report's answer as any
spell of the hand's, drafted for Post under the post the report came by when it came by one, a confided one's as a
turn alone, never drafted. Whether a status moves and to whom the answer is told is the basket's.
"""
import hashlib

from transport import pages

BASKET, DRAWER = 'mending', 'mending/drawer'
STATUSES = ('open', 'seen', 'answered', 'fixed', 'wontfix')
FIELDS = ('n', 'reporter', 'handle', 'at', 'clock', 'text', 'about', 'post', 'answer', 'by', 'byHandle', 'moved')


def rows_of(host, opener, card):
    """The reports `card` keeps, as plain dicts; [] for a town without it."""
    view = host.send({'op': 'world-view', 'principal': opener, 'object': card})
    if view.get('status') != 'viewed':
        return []
    out = []
    for r in pages.rows(pages.state_of(view).get('reports')):
        row = {k: r.get(k) for k in FIELDS}
        row['status'] = (r.get('status') or {}).get('tag', '')
        out.append({'card': card, 'confided': card == DRAWER, 'id': f"{card} #{row['n']}", **row})
    return out


def reports(host, opener, since=0, status=None, limit=200):
    """Reports moved after entry `since`, newest first; `cursor` is the newest such entry (`since` when none moved)."""
    every = rows_of(host, opener, BASKET) + rows_of(host, opener, DRAWER)
    moved = [r for r in every if int(r.get('moved') or 0) > since and (status is None or r['status'] == status)]
    moved.sort(key=lambda r: (int(r.get('moved') or 0), r['card'], int(r['n'])), reverse=True)
    counts = {s: sum(r['status'] == s for r in every) for s in STATUSES}
    return {'cursor': max([since] + [int(r.get('moved') or 0) for r in every]), 'counts': counts, 'reports': moved[:limit]}


def answer_spell(card, n, status, text=''):
    """The basket's `answer`, its words in a block so a slash, a comma or a line break in them stays theirs."""
    if status not in STATUSES:
        raise ValueError(f"status is one of {', '.join(STATUSES)}, not {status}")
    text = (text or '').replace('\r\n', '\n').strip()
    lines = [f'delvetalk {card} answer', f'n: {int(n)}', f'status: {status}']
    if text:
        mark = next(m for m in ('ANSWER', 'ANSWERED', 'MENDED', 'END') if m not in text.split('\n'))
        lines += [f'text: <<{mark}', text, mark]
    return '\n'.join(lines)


def answer_intent(card, n, status, text):
    """One answer, one turn: the same words cast twice are the first receipt."""
    return f'hand:mend:{card}:{int(n)}:{status}:' + hashlib.sha256((text or '').encode()).hexdigest()[:12]
