"""The town unfolded and every thing inspected, for people (docs/WEB.md "The town unfolded"): the walking graph of every
room and door the reader may see, each room unfolding in place; an inspector for any object or kind (its Bend, its
fields, its kind chain, its law, rules, wants and verbs, who may do what, its receipts, and the workshop to amend it);
the library's pages and modules; the kinds. The markup is static/atlas.html; Python fills it with escaped host facts.

What a room shows and how a view lays out are the host's and Bend's (`world-view`, `world-card`, `world-derived`,
`world-inspect`); this module draws the door graph (a layout of the host's `ways`, as pages.door_map draws its tree),
sets Bend source in type, and decides nothing about the world."""
import re
import urllib.parse
from html import escape as e
from urllib.parse import quote

from transport import pages
from transport.pages import T as PAGES, by, page, rows, sections, slip, state_of

A = pages.Shaped(sections('atlas.html'))


def href(kind, obj):
    """A thing's page of a kind: `o` read it, `play` go there, `inspect` inspect it."""
    return f'/{kind}/' + quote(obj, safe='/:')


def anchor(obj):
    """A room's panel id on /town."""
    return 'p-' + re.sub(r'[^A-Za-z0-9_-]', '-', obj)


# ---- Bend, set in type: keywords, strings, comments, numbers; every declaration and line an anchor

KEYWORDS = frozenset('edition import as layer over record sum type protocol def form law rule want verb match case let if then else fn '
                     'and or not implies true false Super world write keep add append retract insert upsert extend'.split())
TOKEN = re.compile(r'(?P<comment>#.*)|(?P<string>"(?:\\.|[^"\\])*"?)|(?P<word>[A-Za-z_][A-Za-z0-9_]*)|(?P<num>\d+n?\b)')
DECL = re.compile(r'(def|form|law|rule|want|record|sum|type|protocol)\s+([A-Za-z_][A-Za-z0-9_]*)')
MODULE = re.compile(r'(import|layer over)(\s+)\./([A-Za-z0-9_]+)\.obend')
DECLARES = ('def', 'form', 'law', 'rule', 'want', 'record', 'sum', 'type', 'protocol')


def tokens(line):
    """A line of Bend as markup: each keyword, string, comment and number in its class, the rest escaped."""
    out, at = [], 0
    for m in TOKEN.finditer(line):
        out.append(e(line[at:m.start()]))
        kind, text = m.lastgroup, m.group()
        if kind == 'word':
            out.append(f'<span class="k">{e(text)}</span>' if text in KEYWORDS else e(text))
        else:
            out.append(f'<span class="{kind[0]}">{e(text)}</span>')
        at = m.end()
    return ''.join(out) + e(line[at:])


def bend(text, prefix='s', module=None):
    """Bend source set in type, each line numbered and anchored (`{prefix}-L{n}`), each top-level declaration anchored
    (`{prefix}-def-{name}`, `-form-`, `-law-`, …) and its name marked, each module a line imports or lays a layer over a
    link (`module(name)` its href, or none). -> (markup, outline [(keyword, name, line)])."""
    lines, outline, seen = [], [], set()
    for n, line in enumerate(text.rstrip('\n').split('\n'), 1):
        ids, body = [f'{prefix}-L{n}'], tokens(line)
        d = DECL.match(line)
        if d and d[1] in DECLARES:
            key = f'{prefix}-{d[1]}-{d[2]}'
            if key not in seen:
                seen.add(key)
                ids.append(key)
                outline.append((d[1], d[2], n))
            body = body.replace(e(d[2]), f'<b class="n">{e(d[2])}</b>', 1)
        m = MODULE.match(line)
        if m and module:
            target = module(m[3])
            if target:
                body = f'<span class="k">{e(m[1])}</span>{m[2]}<a class="mod" href="{e(target)}">./{e(m[3])}.obend</a>' + tokens(line[m.end():])
        lines.append(f'<span class="ln" id="{ids[0]}"><a class="no" href="#{ids[0]}" aria-hidden="true" tabindex="-1">{n}</a>'
                     + ''.join(f'<i id="{x}"></i>' for x in ids[1:]) + f'{body}\n</span>')
    return ''.join(lines), outline


def outline_of(text, prefix, at=''):
    """A module's declarations as links to their lines (`at` the page they are drawn on, '' this one)."""
    outline = [(m[1], m[2], n) for n, line in enumerate(text.rstrip('\n').split('\n'), 1) if (m := DECL.match(line)) and m[1] in DECLARES]
    item = lambda k, name, n: A['outline_item'].format(href=e(f'{at}#{prefix}-L{n}'), kind=e(k), name=e(name))
    defs = [x for x in outline if x[0] == 'def']
    toc = ''.join(item(*x) for x in outline if x[0] in ('form', 'law', 'rule', 'want')) + \
        (A['outline_defs'].format(n=len(defs), items=''.join(item(*x) for x in defs)) if defs else '')
    return A['outline'].format(items=toc) if toc else ''


def source_block(title, text, prefix, module, open_=True, note=''):
    """One module's source: its outline (declarations, each a link to its line) above it, folded or open."""
    if not text:
        return ''
    markup, _ = bend(text, prefix, module)
    return A['source_block'].format(open=' open' if open_ else '', title=e(title), lines=len(text.rstrip('\n').split('\n')), note=note,
                                    outline=outline_of(text, prefix), prefix=e(prefix), code=markup)


NEAR = 20  # a layer differing from the entry module in at most this many lines is shown as those lines


def near_diff(entry, text):
    """The lines by which `text` differs from `entry`, as a diff, when they are few (`NEAR`); else None."""
    import difflib
    if not entry:
        return None
    lines = [l for l in difflib.unified_diff(entry.rstrip('\n').split('\n'), text.rstrip('\n').split('\n'), 'the entry module', 'this layer', lineterm='', n=0)]
    changed = sum(1 for l in lines if l[:1] in '+-' and not l.startswith(('+++', '---')))
    return ('\n'.join(lines), changed) if changed <= NEAR else None


# ---- the door graph: the host's ways laid out in columns, a column a step from the commonplace

COLUMN, ROW, LEFT, TOP, LABEL = 172, 58, 86, 30, 22  # the drawing's units: a column's width, a row's height, margins (half a column, so a label fits), characters of a label


def layout(nodes, ways, root='commonplace'):
    """Positions for the door graph: every node in a column by its steps from `root` through doors either way, the nodes no
    door joins to it after it in columns of their own groups; within a column ordered by the mean place of their
    neighbours in the column before (three passes down and back), so doors cross as little as a simple pass makes them.
    -> ({node: (x, y)}, width, height)."""
    near = {n: set() for n in nodes}
    for w in ways:
        if w['from'] in near and w['to'] in near and w['from'] != w['to']:
            near[w['from']].add(w['to'])
            near[w['to']].add(w['from'])
    depth, columns, base = {}, [], 0
    for start in [root] + sorted(nodes):
        if start not in near or start in depth:
            continue
        depth[start], order = base, [start]
        for n in order:
            for m in sorted(near[n]):
                if m not in depth:
                    depth[m] = depth[n] + 1
                    order.append(m)
        top = max(depth[n] for n in order)
        while len(columns) <= top:
            columns.append([])
        for n in order:
            columns[depth[n]].append(n)
        base = top + 1
    for _ in range(3):
        for k in list(range(1, len(columns))) + list(range(len(columns) - 2, -1, -1)):
            ref = {n: i for i, n in enumerate(columns[k - 1 if k else 1] if len(columns) > 1 else [])}
            def mean(n, ref=ref):
                places = [ref[m] for m in near[n] if m in ref]
                return sum(places) / len(places) if places else len(ref)
            columns[k].sort(key=lambda n: (mean(n), n))
    tall = max((len(c) for c in columns), default=1)
    place = {}
    for k, column in enumerate(columns):
        offset = (tall - len(column)) * ROW / 2
        for i, n in enumerate(column):
            place[n] = (LEFT + k * COLUMN, TOP + offset + i * ROW)
    return place, LEFT * 2 + max(len(columns) - 1, 0) * COLUMN, TOP + tall * ROW


def label(text):
    return text if len(text) <= LABEL else text[:LABEL - 1] + '…'


def graph(nodes, ways, info, root='commonplace', target=None):
    """The door graph as SVG: a door a curve from the card it hangs on to the card it opens onto (a pair of doors one
    curve, arrowed both ways); a room a circle, lit when someone is in it, the count of who is here beside it; each a
    link (`target(node)`: its panel, or its page). `info` {node: {name, present, things}}."""
    target = target or (lambda n: '#' + anchor(n))
    place, width, height = layout(nodes, ways)
    pairs, drawn = {(w['from'], w['to']) for w in ways}, set()
    curves = []
    for w in ways:
        a, b = w['from'], w['to']
        if a not in place or b not in place or a == b or (a, b) in drawn:
            continue
        both = (b, a) in pairs
        drawn |= {(a, b), (b, a)} if both else {(a, b)}
        (x1, y1), (x2, y2) = place[a], place[b]
        if x1 == x2:  # the same column: an arc out to the right
            bend_ = 34 + abs(y2 - y1) / 4
            d = f'M{x1 + 6:.0f} {y1:.0f} C{x1 + bend_:.0f} {y1:.0f} {x2 + bend_:.0f} {y2:.0f} {x2 + 6:.0f} {y2:.0f}'
        else:
            s = 1 if x2 > x1 else -1
            mid = (x1 + x2) / 2
            d = f'M{x1 + 7 * s:.0f} {y1:.0f} C{mid:.0f} {y1:.0f} {mid:.0f} {y2:.0f} {x2 - 7 * s:.0f} {y2:.0f}'
        curves.append(A['graph_door'].format(d=d, both=' both' if both else ''))
    marks = []
    for n, (x, y) in place.items():
        i = info.get(n) or {}
        present = i.get('present') or []
        badge = A['graph_count'].format(x=f'{x + 9:.0f}', y=f'{y - 9:.0f}', cls='who', n=len(present)) if present else ''
        title = (i.get('name') or n) + (f": {', '.join(present[:6])}{'…' if len(present) > 6 else ''} here" if present else '')
        marks.append(A['graph_node'].format(href=e(target(n)), x=f'{x:.0f}', y=f'{y:.0f}', cls=' lit' if present else '', id=e(n),
                                            label=e(label(i.get('name') or n)), ty=f'{y + 20:.0f}', title=e(title), badge=badge))
    return A['graph'].format(width=f'{width:.0f}', height=f'{height + 8:.0f}', doors=''.join(curves), nodes=''.join(marks))


def resident_of(principal, town='', probes=()):
    """Whether a line's author is a resident speaking: an avatar's principal (a DID or an invited guest), not the town's
    own, not a deploy's check (a guest named with one of `probes`, config `probe_names`). The weather, a place's
    inhabitants (`@…`) and the town keep the town's books; their lines are counted, not shown."""
    p = str(principal or '')
    if not pages.resident(p) or (town and p == town):
        return False
    return not any(pages.guest_name(p).startswith(x) for x in probes if x)


def info_of(view, town='', probes=()):
    """What the door graph and a room's panel read of its state: its name (`head`), the residents here (a place's
    inhabitants apart), what lies here, and its residents' newest lines, each said once (`said`), and how many lines of
    the town's own it holds besides (`books`)."""
    s = state_of(view)
    head = s.get('head') if isinstance(s.get('head'), str) and s.get('head').strip() else None
    here = rows(s.get('presence'))
    said, seen, books = [], set(), 0
    for r in sorted(rows(s.get('lines')), key=lambda r: r.get('at') or 0, reverse=True):
        if not resident_of(r.get('author'), town, probes):
            books += 1
        elif (r.get('verb'), r.get('text')) not in seen:
            seen.add((r.get('verb'), r.get('text')))
            said.append(r)
    return {'name': head, 'present': [by(r.get('who'), r.get('handle'), town) for r in here if resident_of(r.get('who'), town, probes)],
            'others': [by(r.get('who'), r.get('handle'), town) for r in here if not pages.resident(str(r.get('who') or ''))],  # its inhabitants; never a deploy's check
            'things': [r['object'] for r in rows(s.get('things')) if isinstance(r.get('object'), str) and r.get('object')],
            'said': said, 'books': books, 'state': s}


LINES = 3  # a room's residents' newest lines in its panel


def lively(i):
    """A room worth a panel: someone is in it, something lies in it, or a resident has said something there."""
    return bool(i['present'] or i['others'] or i['things'] or i['said'])


def panel(obj, view, i, ways, names, signed_in, town='', unfold=False, target=None):
    """A room on /town: its name, who is here and what lies here, its residents' newest lines, its doors (each to that
    room's panel), and one row of ways: go there, inspect it. Unfolded, its scene, view and spells come from its own
    pages (say.js); without a script the links are the way."""
    lines = ''.join(PAGES['line'].format(who=e(by(r.get('author'), r.get('handle'), town)), verb=e(str(r.get('verb') or 'wrote')),
                                         text=PAGES['line_text'].format(text=e(r['text'])) if r.get('text') else '', at=e(str(r.get('at', ''))))
                    for r in i['said'][1:LINES + 1])  # the newest is in its summary
    out = [w for w in ways if w['from'] == obj and w['to'] != obj]
    target = target or (lambda n: '#' + anchor(n))
    door = lambda w: A['panel_door'].format(href=e(target(w['to'])), label=e(w.get('label') or names.get(w['to']) or w['to']))
    who = i['present'] + [names.get(x[1:]) or x[1:] if x.startswith('@') else x for x in i['others']]  # an inhabitant by its own name
    summary = ' · '.join(x for x in (f"{len(who)} here" if who else '', f"{len(out)} door{'s' * (len(out) != 1)}" if out else '') if x)
    return A['panel'].format(
        id=e(anchor(obj)), obj=e(obj), open=' open' if unfold else '', name=e(i['name'] or obj), summary=e(summary),
        last=A['panel_last'].format(who=e(by(i['said'][0].get('author'), i['said'][0].get('handle'), town)), text=e(i['said'][0].get('text') or i['said'][0].get('verb') or ''))
        if i['said'] else '',
        lit=' lit' if i['present'] else '', version=e(str(view.get('version', ''))),
        here=PAGES['present'].format(names=e(', '.join(who)), verb='is' if len(who) == 1 else 'are') if who else '',
        things=A['panel_things'].format(items=', '.join(PAGES['link'].format(href=e(href('o', t)), rel=e(names.get(t) or t.rpartition('/')[2])) for t in i['things'])) if i['things'] else '',
        lines=A['panel_lines'].format(items=lines) if lines else '',
        books=A['panel_books'].format(n=i['books'], s='s' * (i['books'] != 1), read=e(href('o', obj))) if i['books'] else '',
        doors=A['panel_doors'].format(items=' · '.join(door(w) for w in out)) if out else '',
        go=e(href('play' if signed_in else 'o', obj)), read=e(href('o', obj)), inspect=e(href('inspect', obj)))


def town(who, nodes, ways, views, *, alone=(), height=None, town_principal='', unfold=None, probes=(), wanting=(), signed_in=False):
    """/town: what a visitor can do and who is around first; the door graph; a panel for each room where someone is,
    something lies or a resident spoke (the commonplace first, then the lit rooms); every quieter place a name in one
    line. `views` {node: world-view reply}; `wanting` world-wanting's rows."""
    every = [*nodes, *alone]
    info = {n: info_of(views.get(n) or {}, town_principal, probes) for n in every}
    names = {n: i['name'] for n, i in info.items() if i['name']}
    live = [n for n in every if n == 'commonplace' or lively(info[n]) or n == unfold]
    order = sorted(live, key=lambda n: (n != 'commonplace', not info[n]['present'], not info[n]['said'], (info[n]['name'] or n).lower()))
    quiet = sorted((n for n in every if n not in live), key=lambda n: (info[n]['name'] or n).lower())
    target = lambda n: '#' + anchor(n) if n in live else href('o', n)
    about = [(p, n) for n in order for p in info[n]['present']]
    groups = [n for n in order if info[n]['present']]
    around = A['around_item'].format(items=''.join(A['around_one'].format(who=e(', '.join(info[n]['present'])), href=e('#' + anchor(n)), place=e(info[n]['name'] or n))
                                                   for n in groups)) if groups else A['around_none']
    go = lambda w: href('play' if signed_in else 'o', w['object']) + ('?say=' + urllib.parse.quote(w['asks'], safe='') if signed_in and w.get('asks') else '')
    asked, distinct = set(), []
    for w in wanting:  # what wants a hand, each want once however many places pose it
        if isinstance(w, dict) and w.get('object') and (w.get('reading') or w.get('name')) not in asked and len(distinct) < 3:
            asked.add(w.get('reading') or w.get('name'))
            distinct.append(w)
    wants = ''.join(A['can_want'].format(href=e(go(w)), reading=e(w.get('reading') or w.get('name', '')), place=e(names.get(w['object']) or w['object']))
                    for w in distinct)
    body = A['town'].format(
        places=len(every), residents=len(about), can=A['can_in' if signed_in else 'can_out'].format(wants=A['can_wants'].format(items=wants) if wants else ''),
        around=around, height=e(str(height or '')), graph=graph(nodes, ways, info, target=target) if nodes else '',
        panels=''.join(panel(n, views.get(n) or {}, info[n], ways, names, signed_in, town_principal, unfold == n, target) for n in order),
        quiet=A['town_quiet'].format(items=' '.join(PAGES['link'].format(href=e(href('o', n)), rel=e(info[n]['name'] or n)) for n in quiet)) if quiet else '')
    return page('the town', who, body, layout='atlas')


# ---- the inspector

def chain(kinds):
    """A kind chain as links: the thing, its kind, what that kind is of, … (`kinds` [(id, of-text)])."""
    return ' → '.join(PAGES['link'].format(href=e(href('inspect', k)), rel=e(k)) if k not in ('record', 'kind', 'thing') else e(k) for k in kinds)


def field_value(v, depth=0):
    """A state's field as a reader takes it in: short text inline, long text folded, a relation or list as its rows
    (the first twelve, the rest counted), a record as a small definition list."""
    if isinstance(v, dict) and v.get('tag') == 'rows':
        v = v.get('items') or []
    if isinstance(v, str) and v.startswith('guest:') and v.count(':') == 2:  # an invited guest's principal, as a person reads it
        return f'<span class="ftext" title="{e(v)}">{e(pages.guest_name(v))}</span>'
    if isinstance(v, str):
        if len(v) > 160 or '\n' in v:
            return A['field_long'].format(head=e(v.split('\n', 1)[0][:100]), n=len(v), text=e(v))
        return A['field_text'].format(text=e(v)) if v else A['field_empty']
    if isinstance(v, bool):
        return e('yes' if v else 'no')
    if isinstance(v, int):
        return A['field_num'].format(n=v)
    if isinstance(v, list):
        if not v:
            return A['field_empty']
        shown = ''.join(f'<li>{field_value(x, depth + 1)}</li>' for x in v[:12])
        return A['field_list'].format(n=len(v), items=shown, more=A['field_more'].format(n=len(v) - 12) if len(v) > 12 else '')
    if isinstance(v, dict):
        if depth > 3:
            return e('…')
        if set(v) == {'world', 'object'}:
            return PAGES['link'].format(href=e(href('inspect', v['object'])), rel=e(v['object'])) if v['object'] else A['field_empty']
        tag = f'<span class="tag">{e(str(v["tag"]))}</span> ' if 'tag' in v else ''
        return tag + '<dl class="rec">' + ''.join(f'<dt>{e(str(k))}</dt><dd>{field_value(x, depth + 1)}</dd>' for k, x in v.items() if k != 'tag') + '</dl>'
    return e(str(v))


def verbs(obj, inspected, methods, signed_in):
    """The spells this reader is offered, each a small form that casts it (`do` on /play/<id>, the view's own act path:
    the host judges it as any spell), with its fields as inputs within their bounds, its exact spell as its title, a
    link to the line that defines it, and Try it first. A stranger sees the spells and the way in."""
    forms = pages.plain(inspected.get('forms') or {'tag': 'list', 'items': []})
    templates = inspected.get('templates') or {}
    out = []
    for f in forms if isinstance(forms, list) else []:
        action = f.get('action')
        if not isinstance(action, str) or action not in (inspected.get('offered') or []):
            continue
        inputs = []
        for x in f.get('fields') or []:
            k, name = x.get('kind') or {}, x.get('name', '')
            tag = k.get('tag')
            if tag == 'natural':
                inputs.append(A['verb_number'].format(name=e(name), min=e(str(k.get('min', 0))), max=e(str(k.get('max', 10 ** 9))),
                                                      required=' required'))
            elif tag == 'choice':
                inputs.append(A['verb_choice'].format(name=e(name), options=''.join(f'<option>{e(str(o))}</option>' for o in k.get('options') or [])))
            else:
                inputs.append(A['verb_text'].format(name=e(name), max=e(str(k.get('max', 1400))), required=' required' if k.get('min', 0) > 0 else ''))
        where = ('def', action) if action in methods else None
        out.append(A['verb'].format(
            action=e(action), path=e(quote(obj, safe='/:')), spell=e(templates.get(action, f'delvetalk {obj} {action}')),
            inputs=''.join(inputs) if signed_in else A['verb_spell'].format(spell=e(templates.get(action, '').strip().replace(chr(10), ' / '))), grown='' if action in methods else A['verb_grown'],
            line=A['verb_line'].format(href=e(href('inspect', obj) + f'#src-def-{action}')) if where else '',
            act=A['verb_act'] if signed_in else ''))
    if not out:
        return A['verbs_none']
    return A['verbs'].format(items=''.join(out), comein='' if signed_in else A['verbs_comein'])


def admits_cell(a):
    if a is True:
        return A['admit_yes']
    if isinstance(a, dict):
        return A['admit_no'].format(clause=e(str(a.get('clause', ''))), reading=e(str(a.get('reading', ''))))
    return A['admit_unknown']


def who_can(mine, anyone, signed_in):
    """Who may do what: each method a turn may run, judged by the law for the reader and for a newcomer as it stands
    now (`world-inspect` `methods.admits`): yes, or the clause that refuses and its reading. The spell's own Bend may
    still refuse; the law is what the host can say beforehand."""
    names = [m['name'] for m in anyone if isinstance(m, dict) and m.get('context') and m.get('name') not in ('render', 'receive')]
    mine_by = {m.get('name'): m.get('admits') for m in mine if isinstance(m, dict)}
    any_by = {m.get('name'): m.get('admits') for m in anyone if isinstance(m, dict)}
    rows_ = ''.join(A['who_row'].format(name=e(n), href=e(f'#src-def-{n}'), mine=admits_cell(mine_by.get(n)) if signed_in else '',
                                        anyone=admits_cell(any_by.get(n))) for n in names)
    return A['who'].format(you=A['who_you'] if signed_in else '', rows=rows_) if names else ''


def laws(rows_, source_has):
    out = []
    for r in rows_:
        name, kw = str(r.get('name', '')), r.get('keyword') or ('host' if r.get('host') else 'law')
        link = A['law_line'].format(href=e(f'#src-law-{name}')) if f'law-{name}' in source_has else ''
        out.append(A['law'].format(kw=e(kw), name=e(name), reading=e(str(r.get('reading') or '')), clause=e(str(r.get('clause') or '')), line=link))
    return A['laws'].format(items=''.join(out)) if out else ''


def rules(rule_rows, want_rows, town=''):
    items = []
    for r in rule_rows:
        fired = r.get('fired') or {}
        last = (A['rule_fired'].format(height=e(str(fired.get('height', ''))), receipt=e(str(fired.get('receipt', ''))))
                if fired.get('receipt') else A['rule_unfired'].format(why=e(str((r.get('unfired') or {}).get('why', '')))) if r.get('unfired') else '')
        items.append(A['rule'].format(kw='rule', name=e(str(r.get('name', ''))), reading=e(str(r.get('reading') or '')), when=e(str(r.get('when', ''))),
                                      then=e(str(r.get('then', ''))), who=e(by(r.get('owner'), r.get('handle'), town)),
                                      placed=A['rule_placed'].format(h=e(str(r['placed']))) if r.get('placed') else '', last=last))
    for r in want_rows:
        items.append(A['rule'].format(kw='want', name=e(str(r.get('name', ''))), reading=e(str(r.get('reading') or '')), when=e(str(r.get('when', ''))),
                                      then=e(str(r.get('asks', ''))), who=e(by(r.get('owner'), '', town) if not str(r.get('owner', '')).startswith('@') else r.get('from', '')),
                                      placed=A['rule_since'].format(h=e(str(r.get('since', '')))) if r.get('since') else '',
                                      last=A['want_open'] if r.get('answerable') else A['want_waiting']))
    return A['rules'].format(items=''.join(items)) if items else ''


def workshop(obj, edit, signed_in):
    """The workshop, here: the spell that checks this thing's Bend over what it lays on, its source in the block, to edit
    and send; with a script, the same block as a fork of its kind or a layer over this thing. It goes to the workshop's
    own card (`/play/workshop`), the one write path the town has for code; the reply, with each problem's line, comes
    back beside it (say.js), or on the workshop's page without one. `edit` {text, over, kind}: the Bend a reader would
    amend (a kind's body, else what the thing runs), what it is checked over, and the kind a fork is after."""
    if not edit or not edit.get('text'):
        return ''
    head = 'delvetalk workshop check' + (f"\nover: {edit['over']}" if edit.get('over') else '')
    spell = f"{head}\nsource: <<BEND\n{edit['text'].rstrip()}\nBEND"
    return A['workshop'].format(obj=e(obj), spell=e(spell), rows=min(30, max(8, spell.count('\n') + 1)), over=e(edit.get('over') or ''),
                                kind=e(edit.get('kind') or ''), act=A['workshop_act'] if signed_in else A['workshop_comein'])


def inspector(obj, who, view, inspected, *, stranger=None, rules_=(), wants_=(), entries=(), kinds=(), did=None, town='',
              components=(), body=None, module_names=(), edit=None, shown=None):
    """/inspect/<id>: everything the host can say of a thing, beside its Bend. `inspected` world-inspect for the reader
    (with source), `stranger` for a newcomer; `kinds` its kind chain; `components` its layers as madeFrom lists them
    [(at, body)], `body` a kind's body as text; `module_names` the modules the town holds (for links). The entry module is
    set in type, and a layer or body beside it when `shown` names it (`?bend=layer0`, `body`); else its outline, or, when it is the
    entry module's but for a few lines, those lines (obend 10-14: /inspect/room/14 was 429 KB, its 659 lines set in type
    twice and once more in the workshop's box). `shown` 'none' sets nothing in type (a panel's fetch of its spells)."""
    s = state_of(view)
    names = set(module_names)
    drawn = lambda key: key == shown or (key == 'entry' and shown != 'none')  # the entry always, so its anchors hold
    page_of = lambda key: '' if drawn(key) else f'?bend={key}'
    layers = {f'Layer{c[0]}': f'{page_of(f"layer{c[0]}")}#src{c[0]}-L1' for c in components}
    module = lambda name: layers.get(name) or (f'/lib/{quote(name)}' if name in names else None)
    source = inspected.get('source') or ''
    methods = {m.get('name') for m in inspected.get('methods') or [] if isinstance(m, dict)}
    blocks, has = [], set()

    def part(key, title, text, prefix, note=''):
        if drawn(key):
            return source_block(title, text, prefix, module, open_=key == 'entry' or key == shown, note=note)
        lines = len(text.rstrip('\n').split('\n'))
        near = near_diff(source, text) if key != 'entry' and shown != 'none' else None
        if near:
            return A['source_diff'].format(title=e(title), lines=lines, n=near[1], diff=e(near[0]), href=e(f'?bend={key}#{prefix}'))
        return A['source_folded'].format(title=e(title), lines=lines, note=note, outline=outline_of(text, prefix, page_of(key)),
                                         href=e(f'?bend={key}#{prefix}'))
    # The entry module first (what runs on top), then each layer below it, then a kind's body.
    if source:
        blocks.append(part('entry', 'what it runs: its entry module', source, 'src'))
        _, outline = bend(source, 'src')
        has |= {f'{k}-{n}' for k, n, _ in outline}
    for at, text in sorted(components, reverse=True):
        if text.strip() == source.strip():
            continue
        blocks.append(part(f'layer{at}', f'layer {at} (Layer{at}), laid by its kind', text, f'src{at}'))
    if body:
        blocks.append(part('body', 'the body this kind lays on what it makes', body, 'body', note=A['body_note']))
    maker = by(inspected.get('maker'), s.get('makerHandle'), town) if inspected.get('maker') else None
    owner = by(s.get('owner'), s.get('ownerHandle') or s.get('makerHandle') if s.get('owner') == inspected.get('maker') else s.get('ownerHandle'), town) \
        if isinstance(s.get('owner'), str) and s.get('owner') else None
    facts = [('id', e(obj)), ('called', e(s['head'])) if isinstance(s.get('head'), str) and s.get('head') else None,
             ('kind chain', chain(kinds)) if kinds else None, ('owner', e(owner)) if owner else None,
             ('made by', e(maker)) if maker else None, ('after', e(inspected['lineage'].strip())) if inspected.get('lineage') else None,
             ('version', e(str(view.get('version', '')))), ('pin', f'<span class="code">{e(str(inspected.get("pinSlug") or ""))}</span>'),
             ('state', e(f"{inspected.get('stateBytes', '?')} bytes")), ('views', e(', '.join(inspected['views']))) if inspected.get('views') else None,
             ('retired', 'yes') if inspected.get('retired') else None]
    fields = ''.join(A['field'].format(name=e(k), value=field_value(v)) for k, v in s.items())
    receipts = PAGES['receipts'].format(n=len(entries), slips=''.join(slip(x, did) for x in entries)) if entries else ''  # folded, as fields are
    return page(f'inspect {obj}', who, A['inspector'].format(
        name=e(s.get('head') if isinstance(s.get('head'), str) and s.get('head') else obj), obj=e(obj),
        read=e(href('o', obj)), go=e(href('play' if who else 'o', obj)),
        facts=''.join(A['fact'].format(k=e(k), v=v) for k, v in (f for f in facts if f)),
        verbs=verbs(obj, inspected, methods, bool(who)),
        who=who_can(inspected.get('methods') or [], (stranger or {}).get('methods') or inspected.get('methods') or [], bool(who)),
        laws=laws(inspected.get('laws') or [], has), rules=rules(rules_, wants_, town),
        fields=A['fields'].format(items=fields) if fields else '',
        source=''.join(blocks) or A['source_none'], workshop=workshop(obj, edit, bool(who)) if who else (A['workshop_closed'] if edit and edit.get('text') else ''),
        receipts=receipts), layout='atlas inspect')


# ---- the library: its pages, its modules; the kinds

SPELL_PAGE = re.compile(r'(delvetalk library read / page: )([A-Za-z0-9._-]+)')


def library(who, pages_):
    """/library: the library's pages (its state's `pages`), each a link, in their shelving order; the town's modules beside."""
    items = ''.join(A['library_item'].format(href=e('/library/' + quote(p['name'])), name=e(p['name']), title=e(p.get('title') or ''),
                                             kind=e(str((p.get('kind') or {}).get('tag', '') if isinstance(p.get('kind'), dict) else p.get('kind') or '')))
                    for p in pages_)
    return page('the library', who, A['library'].format(items=items), layout='atlas')


def library_page(who, p, names):
    """/library/<page>: a page of the library, verbatim, each `library read / page:` spell in it a link to that page."""
    text = e(p.get('body') or '')
    text = SPELL_PAGE.sub(lambda m: m[1] + (f'<a href="/library/{quote(m[2])}">{m[2]}</a>' if m[2] in names else m[2]), text)
    return page(p['name'], who, A['library_page'].format(name=e(p['name']), title=e(p.get('title') or ''), text=text,
                                                        spell=e(f"delvetalk library read / page: {p['name']}")), layout='atlas')


def modules(who, mods):
    """/lib: the modules the town holds, each its newest text's name, size and where it came in."""
    items = ''.join(A['module_item'].format(href=e('/lib/' + quote(m['name'])), name=e(m['name']), lines=m['text'].count('\n') + 1,
                                            height=e(str(m.get('height', ''))), first=e(next((l.lstrip('# ').strip() for l in m['text'].split('\n') if l.startswith('#')), '')[:140]))
                    for m in sorted(mods, key=lambda m: m['name'].lower()))
    return page('the modules', who, A['modules'].format(items=items), layout='atlas')


def module_page(who, m, names, versions=()):
    """/lib/<name>: one module's Bend, set in type and outlined, its imports links to theirs."""
    other = ''.join(A['version_item'].format(href=e(f"/lib/{quote(m['name'])}?cid={v['cid']}"), cid=e(v['cid'][-10:]), height=e(str(v.get('height', ''))))
                    for v in versions if v['cid'] != m['cid'])
    block = source_block(f"{m['name']}.obend", m['text'], 'src', lambda n: f'/lib/{quote(n)}' if n in names else None)
    return page(m['name'], who, A['module_page'].format(name=e(m['name']), height=e(str(m.get('height', ''))), cid=e(m['cid']), source=block,
                                                       versions=A['versions'].format(items=other) if other else ''), layout='atlas')


def kinds_page(who, kinds_):
    """/kinds: every kind the reader may see: what it makes, what it is of, who made it, how many, what it is for."""
    items = ''.join(A['kind_item'].format(href=e(href('inspect', k['id'])), id=e(k['id']), name=e(k.get('name') or k['id']),
                                          of=chain([k['of']]) if k.get('of') else '', who=e(k.get('who') or ''), count=e(str(k.get('count', 0))),
                                          about=e((k.get('about') or '').split(': delvetalk', 1)[0][:220]), body=A['kind_body'] if k.get('body') else '',
                                          make=e(f"/play/{k['id']}?say=" + quote(f"delvetalk {k['id']} make", safe='')))
                    for k in kinds_)
    return page('the kinds', who, A['kinds'].format(items=items, n=len(kinds_)), layout='atlas')
