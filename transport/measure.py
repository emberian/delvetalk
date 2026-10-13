"""docs/PLAYTEST-2.md §4's measures, counted live from a world's journal and the transport's files beside it.

The hand's Measure page, `python3 -m transport status --playtest` and the ring's harvest read these same numbers, so the
operator and the lessons file never count twice. Every row is a count with the ids behind it. A resident is any
principal but the opener, the owner's other principals (config `owner_principals`) and the world's clock. A turn is a
direct one (not a delivery, whose principal is its sender's); what it made is its `creates`, what it used its writes and
subscriptions. What needs a person's judgement (a misread, whether a refusal was right) is listed for it, not decided.
"""
import json
import re
import time

from transport import journal
from transport.host import plain
from transport.observe import instant

SPELL = re.compile(r'^\s*delvetalk\s+\S', re.M)  # a spell at a line's start, as the host casts one
GENESIS = re.compile(r'^(?:did:|zulip:)')  # a principal's own object, its avatar, made at its arrival


def counted(n, word, plural=None):
    """The count before the thing (docs/VOICE.md): `1 door`, `3 doors`."""
    return f"{n} {word if n == 1 else plural or word + 's'}"


def labels(value):
    """Every text a typed value carries, its edits' included."""
    if isinstance(value, dict):
        return ([value['value']] if value.get('tag') == 'label' and isinstance(value.get('value'), str) else []) + [t for v in value.values() for t in labels(v)]
    return [t for v in value for t in labels(v)] if isinstance(value, list) else []


def doors(write):
    """The objects a write's `cites` appends name: the doors a `door` spell hangs."""
    out = []
    for edit in write.get('edits') or []:
        for f in (edit or {}).get('fields') or []:
            if f.get('name') == 'cites' and (f.get('value') or {}).get('label') == 'append':
                to = (plain((f['value'].get('payload') or {})) or {}).get('item', {}).get('to') or {}
                if to.get('object'):
                    out.append(to['object'])
    return out


def kind_of(obj, seed):
    """`kind` for a kind made, else the kind its seed names (`kind/room` -> room), else the id's family."""
    if obj.startswith('kind/'):
        return 'kind'
    named = (seed or {}).get('kind') if isinstance(seed, dict) else None
    return named.split('/', 1)[1] if isinstance(named, str) and named.startswith('kind/') else re.sub(r'/\d+$', '', obj).rsplit('/', 1)[-1]


def confirmed_post(line, world):
    return line.get('what') in ('post', 'posted') and line.get('world') == world and bool(line.get('uri'))


def post_time(line):
    return instant(line['createdAt']) if line.get('createdAt') else line['at']


def t0(st):
    """The playtest's T0: the Post of the T+0 invitation the hand drafted (docs/PLAYTEST-2.md §6 step 4); None before."""
    zero = {p.stem for p, d in st.drafts() if (d.get('speak') or {}).get('invitation') == 0}
    return min((post_time(l) for l in st.lines(st.hand_log) if confirmed_post(l, st.world) and l.get('draft') in zero), default=None)


def no_reply(st, observed, entries):
    """Posts addressed to the world (a summons, or a spell at a line's start, as the host casts one) that it heard (a turn
    under the post's own uri) and answered with nothing: no draft with text replies, and the turn is not still waiting on
    hob. Prose in a thread that hob reads as `none` is quiet by design, and residents talking to each other reach only
    each other's avatars (`<uri>#mention:`)."""
    last = {(x.get('identity') or {}).get('intent'): (x.get('outcome') or {}).get('tag') for x in entries}
    said = {d.get('replyTo') for _, d in st.drafts() if d.get('text')}
    asked = [o for o in observed if o['kind'] == 'summon' or SPELL.search(o.get('text') or '')]
    return [o['uri'] for o in asked if o['uri'] in last and o['uri'] not in said and last[o['uri']] != 'suspended']


def hand_posts(st):
    """[(wall seconds, text)] of every draft the hand confirmed posting, oldest first."""
    drafts = {p.stem: d for p, d in st.drafts()}
    return sorted((post_time(l), (drafts.get(l.get('draft')) or {}).get('text') or '') for l in st.lines(st.hand_log)
                  if confirmed_post(l, st.world))


PROMPTED = 600  # seconds after a hand post naming a thing within which an act on it counts as prompted (docs/GENESIS.md)


def clock_after(out, clock):
    if out.get('tag') in ('carried', 'forked'):
        return (out.get('state') or {}).get('clock', 0)
    return out.get('to') or clock if out.get('tag') == 'advanced' else clock


def wants(entries, posted_at, hand, resident=lambda p: True):
    """docs/GENESIS.md "The measure": each want that held (an entry's `wanted`) and a resident's write stopped holding
    (`unwanted`; one the opener or the hand closed is no answer), with that hand, `prompted` when that write came within PROMPTED seconds after a hand post naming the
    thing, else unprompted; and each want still holding at the end, ignored. A want true or false by the clock alone is
    journaled only when its thing is next written."""
    holding, answered, clock = {}, [], 0
    for x in entries:
        out, ident = x.get('outcome') or {}, x.get('identity') or {}
        if out.get('tag') in ('carried', 'forked'):
            holding = {(obj, name): height for obj, wants in ((out.get('index') or {}).get('wanting') or {}).items()
                       for name, height in wants.items()}
        clock = clock_after(out, clock)
        for w in x.get('wanted') or []:
            holding.setdefault((w.get('object'), w.get('want')), x.get('height'))
        for w in x.get('unwanted') or []:
            since = holding.pop((w.get('object'), w.get('want')), None)
            by = ((x.get('delivery') or {}).get('from') or {}).get('principal') or ident.get('principal')
            if since is None or not resident(by):
                continue
            at = posted_at.get(ident.get('intent'), clock * 60)
            near = any(t <= at <= t + PROMPTED and re.search(rf'(?<![\w/]){re.escape(w.get("object") or "")}(?![\w/])', text) for t, text in hand)
            answered.append({'object': w.get('object'), 'want': w.get('want'), 'since': since, 'height': x.get('height'), 'by': by, 'prompted': near})
    return {'prompted': [a for a in answered if a['prompted']], 'unprompted': [a for a in answered if not a['prompted']],
            'ignored': [{'object': o, 'want': n, 'since': h} for (o, n), h in holding.items()]}


def measures(st, entries=None):
    """§4's table for `st`'s world. `entries` (default the journal, read whole) for a caller that holds them."""
    entries = journal.entries(st.journal) if entries is None else entries
    c = st.config
    names, settings = {}, {}
    for x in entries:
        out = x.get('outcome') or {}
        if out.get('tag') == 'principal':
            names[out.get('did')] = out.get('handle')
        if out.get('tag') == 'settings':
            settings.update(out)
        if out.get('tag') in ('carried', 'forked'):  # a store-installing genesis holds the settings of the world before
            settings.update((out.get('state') or {}).get('settings') or {})
    obs, posted_at, invalid_observations = [], {}, 0
    for o in st.observations():
        try:
            at = instant(o.get('createdAt'))
        except ValueError:
            invalid_observations += 1
            continue
        obs.append(o)
        posted_at[o['uri']] = at
    for o in obs:
        names.setdefault(o['author']['did'], o['author']['handle'])
    staff = {settings.get('opener') or c.opener, settings.get('clock') or 'transport', 'world', *c.owner_principals.split()}
    resident = lambda p: bool(p) and p not in staff
    who = lambda p: names.get(p) or p
    # Wall time: a turn's is the post it answers (the transport's timestamp); the clock's minutes only stand in for a turn
    # no post made. T0 and every first are wall time, so a make 21 s after T0 is 21 s, never a minute's rounding.
    first = {}
    for o in sorted(obs, key=lambda o: posted_at[o['uri']]):
        if resident(o['author']['did']):
            first.setdefault(o['author']['did'], posted_at[o['uri']])
    start = t0(st)
    start = start if start is not None else min(first.values(), default=None)

    # A kind with no law clause holds its package's law (rules and wants after it), so a kind's seed law is the resident's
    # own only when it is not that package law; the staff's kinds, made by the opener, show the package's text.
    seeds = [plain(cr['seed']) for x in entries for cr in ([x['outcome']] if (x.get('outcome') or {}).get('tag') == 'created' else (x.get('outcome') or {}).get('creates') or [])
             if str(cr.get('object') or '').startswith('kind/') and cr.get('seed') and not resident((x.get('identity') or {}).get('principal'))]
    package_law = min((str(sd['law']).strip() for sd in seeds if isinstance(sd, dict) and str(sd.get('law') or '').strip()), key=len, default=None)
    own_law = lambda law: bool(law) and not (package_law and (law == package_law or law.startswith(package_law + '\n')))

    makers, made, used, written, adopted, cites, named, refusals, unposted = {}, [], {}, [], [], [], [], [], []
    by_identity, moved, now_clock = {}, set(), 0
    for x in entries:
        out, ident, height = x.get('outcome') or {}, x.get('identity') or {}, x.get('height')
        p, tag = ident.get('principal'), out.get('tag')
        by_identity[(p, ident.get('intent'))] = height
        now_clock = clock_after(out, now_clock)
        direct = 'delivery' not in x
        creates = [out] if tag == 'created' else out.get('creates') or []
        for cr in creates:
            obj, seed = cr.get('object'), plain(cr.get('seed') or {}) if cr.get('seed') else {}
            if not obj:
                continue
            maker = p if direct else ((x.get('delivery') or {}).get('from') or {}).get('principal', p)
            makers[obj] = maker
            if resident(maker) and not GENESIS.match(obj):
                made.append({'object': obj, 'kind': kind_of(obj, seed), 'maker': who(maker), 'height': height, 'principal': maker,
                             'at': posted_at.get(ident.get('intent'), now_clock * 60)})
                if obj.startswith('kind/') and isinstance(seed, dict) and own_law(str(seed.get('law') or '').strip()):
                    written.append({'object': obj, 'maker': who(maker), 'height': height, 'law': str(seed['law']).split('\n')[0][:200]})
        # The clock moves the world with nobody posting: a delivered turn the clock resumed (a wake's due tick; a turn
        # resumed by hob's reading answers a post, and has no delivery), and every turn delivered from one; from T0 on.
        sender = by_identity.get((((x.get('delivery') or {}).get('from') or {}).get('principal'), ((x.get('delivery') or {}).get('from') or {}).get('intent')))
        if (x.get('resumes') and 'delivery' in x) or (sender is not None and sender in moved):
            moved.add(height)
            wrote = [w.get('object') for w in out.get('writes') or [] if w.get('object')]
            if wrote and (start is None or now_clock >= start // 60):
                unposted.append({'height': height, 'objects': wrote, 'notes': sum(1 for o in wrote if str(o).startswith(('did:', 'zulip:')))})
        if not direct or not resident(p):
            continue
        if tag == 'refused':
            refusals.append({'height': height, 'by': who(p), 'class': out.get('class'), 'reason': (out.get('reason') or '')[:200], 'object': out.get('object')})
            continue
        if tag != 'admitted':
            continue
        for w in out.get('writes') or []:
            obj = w.get('object')
            if obj and makers.get(obj) not in (None, p) and obj != p:
                used.setdefault((obj, p), {'object': obj, 'by': who(p), 'maker': who(makers[obj]), 'height': height, 'residentMade': resident(makers[obj])})
            hung = doors(w)
            for to in hung:
                if makers.get(to) != makers.get(obj) and resident(makers.get(obj)):
                    cites.append({'from': obj, 'to': to, 'by': who(p), 'height': height, 'toResident': resident(makers.get(to))})
            texts = ' '.join(labels(w.get('edits') or []))
            for other in {m['object'] for m in made if m['principal'] != p} - set(hung):  # a door is a citation already
                if re.search(rf'(?<![\w/]){re.escape(other)}(?![\w/])', texts):
                    named.append({'in': obj, 'names': other, 'by': who(p), 'height': height})
        for s in out.get('subscribes') or []:
            obj = s.get('object')
            if obj and makers.get(obj) not in (None, p):
                used.setdefault((obj, p), {'object': obj, 'by': who(p), 'maker': who(makers[obj]), 'height': height, 'residentMade': resident(makers[obj])})
        for r in out.get('reprograms') or out.get('amendments') or []:
            adopted.append({'object': r.get('object'), 'by': who(p), 'height': height})

    count = lambda rows, key: dict(sorted(((k, sum(1 for r in rows if r[key] == k)) for k in {r[key] for r in rows}), key=lambda kv: (-kv[1], kv[0])))
    theirs = [u for u in used.values() if u['residentMade']]
    makes = {}
    for m in made:
        makes.setdefault(m['principal'], m)
    interps = [json.loads(p.read_text()) for p in sorted(st.interpretations.glob('*.json'))] if st.interpretations.exists() else []
    verdict = lambda i: 'failed' if (i.get('reply') or {}).get('status') == 'failed' else \
        next((w for w in ('delvetalk', 'none', 'unclear') if (i.get('reply') or {}).get('raw', '').strip().lower().startswith(w)), 'other').replace('delvetalk', 'spell')
    return {
        'world': st.world, 'names': names, 'height': entries[-1].get('height') if entries else 0, 'clock': now_clock,
        'invalidObservations': invalid_observations,
        'T0': None if start is None else time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start)),
        'made': {'count': len(made), 'byKind': count(made, 'kind'), 'byMaker': count(made, 'maker'), 'rows': made},
        'used': {'count': len(used), 'residentMade': len(theirs), 'makers': len({u['maker'] for u in theirs}), 'rows': list(used.values())},
        'laws': {'written': written, 'adopted': adopted},
        'citations': {'doors': cites, 'named': named},
        'unposted': {'count': len(unposted), 'notes': sum(u['notes'] for u in unposted), 'rows': unposted},
        'interpretations': {'count': len(interps), 'byVerdict': count([{'v': verdict(i)} for i in interps], 'v'),
                            'toJudge': [{'object': i.get('object'), 'said': (i.get('reply') or {}).get('raw', '').strip().split('\n')[0][:200]}
                                        for i in interps if verdict(i) in ('spell', 'none')]},
        'refusals': {'count': len(refusals), 'byClass': count(refusals, 'class'), 'rows': refusals},
        'firstMade': {'secondsFromT0': round(made[0]['at'] - start) if made and start is not None else None,
                      'byResident': {who(p): round(m['at'] - first[p]) if p in first else None for p, m in makes.items()}},
        'noReply': no_reply(st, obs, entries),
        'wants': wants(entries, posted_at, hand_posts(st), resident),
        'goNoGo': {'used by another, at least 3 by at least 2 makers': len(theirs) >= 3 and len({u['maker'] for u in theirs}) >= 2}}


def table(m):
    """§4's rows as the lessons file prints them and the hand shows them: (measure, the number, what it breaks into,
    the ids behind it)."""
    split = lambda d: ', '.join(f'{k} {v}' for k, v in d.items())
    made, used, laws, cit, rain, i, ref, first, w = (m[k] for k in ('made', 'used', 'laws', 'citations', 'unposted', 'interpretations', 'refusals', 'firstMade', 'wants'))
    who = lambda p: m['names'].get(p, p)
    return [
        ('things made by residents', made['count'], f"by kind: {split(made['byKind']) or 'none'}; by maker: {split(made['byMaker']) or 'none'}",
         [f"{r['object']} by {r['maker']}, entry {r['height']}" for r in made['rows']]),
        ('things used by someone other than their maker', used['count'], f"{used['residentMade']} of them residents' things, by {counted(used['makers'], 'maker')}",
         [f"{r['object']} ({r['maker']}'s) by {r['by']}, entry {r['height']}" for r in used['rows']]),
        ('laws written or adopted by residents', len(laws['written']) + len(laws['adopted']), f"{len(laws['written'])} written, {len(laws['adopted'])} adopted",
         [f"{r['object']} by {r['maker']}: {r['law']}" for r in laws['written']] + [f"{r['object']} adopted by {r['by']}, entry {r['height']}" for r in laws['adopted']]),
        ("citations between residents' things", len(cit['doors']) + len(cit['named']), f"{counted(len(cit['doors']), 'door')}, {counted(len(cit['named']), 'line')} naming another's thing",
         [f"{r['from']} -> {r['to']} by {r['by']}, entry {r['height']}" for r in cit['doors']] + [f"{r['in']} names {r['names']}, by {r['by']}" for r in cit['named']]),
        ('rain that fell with nobody posting', rain['count'], f"{counted(rain['notes'], 'note')} on avatars", [f"entry {r['height']}: {', '.join(r['objects'])}" for r in rain['rows']]),
        ('interpretations', i['count'], split(i['byVerdict']) or 'none', [f"{r['object']}: {r['said']}" for r in i['toJudge']]),
        ('refusals by class', ref['count'], split(ref['byClass']) or 'none', [f"{r['class']} by {r['by']}, entry {r['height']}: {r['reason']}" for r in ref['rows']]),
        ('seconds to the first resident-made thing', first['secondsFromT0'], f"T0 {m['T0'] or 'not yet'}",
         [f"{h}: {v} s from their first post" for h, v in first['byResident'].items()]),
        ('addressed posts with no reply', len(m['noReply']), 'heard by the world, answered with nothing', m['noReply']),
        ('invalid observation timestamps', m['invalidObservations'], 'skipped', []),
        ('wants answered unprompted', len(w['unprompted']), f"{len(w['prompted'])} prompted (within ten minutes of a hand post naming the thing); {len(w['ignored'])} still wanted",
         [f"{r['object']} {r['want']} by {who(r['by'])}, entry {r['height']} (wanted since {r['since']})" for r in w['unprompted']]
         + [f"still wanted: {r['object']} {r['want']}, since entry {r['since']}" for r in w['ignored']]),
    ]
