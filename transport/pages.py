"""HTML for people (docs/WEB.md). The markup is transport/static/pages.html (named sections), the look
transport/static/style.css, the one stylesheet; reading and acting need no script. Python fills the sections with escaped
host facts and decides nothing. `text` reads any page back off its own markup as plain text, so the two views cannot drift."""
import re
import textwrap
from html import escape as e
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from transport.host import door_rows, plain

STATIC = Path(__file__).resolve().parent / 'static'


def sections(name):
    """A markup file of static/ as its named sections: `<!-- name: what it is -->` then the markup, up to the next."""
    return dict(re.findall(r'<!-- (\w+)[^>]*-->\n(.*?)(?=\n<!--|\Z)', (STATIC / name).read_text(), re.S))


T = sections('pages.html')
SUGGESTIONS = 6  # spells offered under the box, at most


def page(title, who, body, *, site='DelveTalk', home='/', head=None, nav=None, foot=None, wide=False):
    """The one skeleton. The front's header links the town's day and its map from every page, and the reader's book and
    signing out (or the way in); the hand passes its own `head` (the stylesheet inlined), `nav` and `foot`, and its
    header names the world it shows. `wide`: a page laid out in columns on a wide screen (the front page)."""
    front = nav is None
    you = (T['who_in'].format(who=e(who), book=e(quote(who, safe=''))) if who else T['who_out']) if front else T['who'].format(who=e(who or ''))
    return T['shell'].format(title=e(title), site=e(site), home=e(home), head=T['head'] if head is None else head, nav=T['nav'] if front else nav,
                             who=you, wide=' class="wide"' if wide else '', body=body, foot=T['foot'] if foot is None else foot)


STAMPS = {'admitted': '●', 'refused': '§', 'suspended': '…', 'quiet': '—'}  # a receipt's stamp: an icon beside its word, never colour alone


def stamp(fate, word=True):
    return f"{STAMPS.get(fate, '◦')} {fate}" if word else STAMPS.get(fate, '◦')


def yours(text, did):
    return T['yours'] if did and did in str(text) else ''


def resident(i):
    """An id that is a resident's avatar (a DID, or an invited guest), not a place or a thing."""
    return i.startswith(('did:', 'guest:'))


def guest_name(principal):
    """An invited guest's principal (`guest:<host>:<name>`) as a person reads it: the name it registered."""
    return principal.rsplit(':', 1)[-1] if principal.startswith('guest:') else principal


def home(status, who, ids=(), did=None, *, doors=(), today=None, wanting=(), newest=()):
    """What the town is and how to come in, then the town alive: today's chronicle painted (its text folded beneath), the
    commonplace's doors as its places, what wants a hand, the newest makings; residents are counted, not listed.
    `today` {text, paint}; `wanting` world-wanting's rows; `newest` [(object, principal, height)], newest first."""
    n = sum(1 for i in ids if resident(i))
    items = ''.join(T['place_item'].format(href=e(quote(d['to']['object'], safe=':')), label=e(d.get('label') or d['to']['object']),
                                           yours=yours(d['to']['object'], did), about=e(d.get('description') or d.get('head') or d['to']['object'])) for d in doors)
    places = T['places'].format(items=items, residents=T['residents'].format(n=n)) if doors or n else ''
    go = (lambda o: '/play/' + quote(o, safe='/:')) if who else (lambda o: '/o/' + quote(o, safe=':'))
    wants = T['wanting'].format(items=''.join(T['wanting_item'].format(href=e(go(w['object'])), object=e(w['object']), reading=e(w.get('reading') or w.get('name', '')))
                                              for w in wanting)) if wanting else ''
    made = T['newest'].format(items=''.join(T['newest_item'].format(href=e('/o/' + quote(o, safe=':')), object=e(o), who=e(guest_name(p)), height=e(str(h)))
                                            for o, p, h in newest)) if newest else ''
    told = T['today'].format(paint=painting((today or {}).get('paint')), open='' if (today or {}).get('paint') else ' open',
                             text=e(today['text'])) if (today or {}).get('text') else ''
    return page('a town of things that answer', who, T['home'].format(
        height=e(str(status.get('height'))), objects=e(str(status.get('objects'))), enter=T['enter'].format(book=e(quote(who or '', safe=''))) if who else '',
        login='' if who else T['login'], today=told, places=places, wanting=wants, newest=made), wide=True)


def items(ids, words, did):
    """Objects as a list: the id, the door word the commonplace gives it, (yours)."""
    return ''.join(T['world_item'].format(id=e(i), href=e(quote(i, safe=':')), yours=yours(i, did),
                                          word=T['word'].format(word=e(words[i])) if words.get(i) else '') for i in ids)


def doors_of(links):
    return ' '.join(T['link'].format(href=e(v['href']), rel=e(k)) for k, v in (links or {}).items() if isinstance(v, dict) and k != 'self')


def slip(x, did=None):
    """A receipt as a ticket: its stamp's icon and word, the slug, the entry, a refusal's clause."""
    out, ident = x.get('outcome') or {}, x.get('identity') or {}
    clause = out.get('reason') or ' '.join(str(out[k]) for k in ('clause', 'object') if out.get(k))
    return T['slip'].format(fate=e(str(out.get('tag'))), stamp=e(stamp(str(out.get('tag')))), height=e(str(x.get('height'))), name=e(str(x.get('slug') or '')),
                            intent=e(str(ident.get('intent'))), who=e(str(ident.get('principal'))), yours=yours(ident.get('principal'), did),
                            note=T['note'].format(clause=e(f"{out.get('class')}: {clause}" if clause else str(out.get('class')))) if out.get('tag') == 'refused' else '')


A_DID = re.compile(r'did:plc:[a-z2-7]{24}')


def named(markup, names):
    """A page as a person reads it: each DID in its text as the handle the host's registry gave its avatar, else `a
    stranger` and the DID's last four (VOICE: a DID is never shown to a person). Never in a tag, where an href keeps the
    id, nor in a <pre>: a card, a law and a source are verbatim."""
    out, verbatim = [], 0
    for part in re.split(r'(<[^>]*>)', markup):
        verbatim += part.startswith('<pre') - part.startswith('</pre')
        out.append(part if part.startswith('<') or verbatim else A_DID.sub(lambda m: e(names.get(m[0]) or f'a stranger …{m[0][-4:]}'), part))
    return ''.join(out)


def hobbed(text):
    """A card's text and hob's lines at its head or tail, apart: hob's are beside the card, never in it."""
    lines = text.split('\n')
    head = next((i for i, l in enumerate(lines) if not l.startswith('hob:')), len(lines))
    tail = len(lines) - next((i for i, l in enumerate(reversed(lines[head:])) if l and not l.startswith('hob:')), len(lines) - head)
    tail = tail if any(l.startswith('hob:') for l in lines[tail:]) else len(lines)  # the card keeps its own blank tail
    return [l for l in lines[:head] + lines[tail:] if l], '\n'.join(lines[head:tail])


A_SPELL = re.compile(r'\s+delvetalk \S')


def speech(card):
    """An exact card read as speech: its first paragraph of prose, and its spells as (label, spell). A spell is an indented
    line beginning `delvetalk`, with the more indented lines under it; its label is the line that introduces it (`Rain on
    it:`, or the last clause of `…; 10 made. Make one:`), else its card and action. `»` lines say what a spell gives back."""
    prose, spells, lines, i = [], [], card.split('\n'), 0
    while i < len(lines):
        line = lines[i]
        if A_SPELL.match(line):
            indent, j = len(line) - len(line.lstrip()), i + 1
            while j < len(lines) and lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) >= indent \
                    and not lines[j].lstrip().startswith(('delvetalk ', '»')):
                j += 1
            spell, label = textwrap.dedent('\n'.join(lines[i:j])).strip(), None
            k = next((k for k in range(len(prose) - 1, -1, -1) if prose[k].strip()), None)
            if k is not None and prose[k].rstrip().endswith(':') and k >= len(prose) - 2:
                said = prose[k].rstrip()[:-1]
                m = re.match(r'(.*[.;])\s+([^.;]+)$', said)
                label, prose[k] = (m[2], m[1]) if m else (said, '')
            spells.append((label if label and len(label) <= 40 else ' '.join(spell.split()[1:3]), spell))
            i = j
            while i < len(lines) and lines[i].lstrip().startswith('»'):
                i += 1
            continue
        prose.append(line)
        i += 1
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', '\n'.join(prose)) if p.strip()]
    first = next((p for p in paragraphs if re.search('[a-z]', p)), paragraphs[0] if paragraphs else '')
    return first, spells


def painting(text):
    """A card's paint, above its exact card (never inside it), or nothing."""
    return T['paint'].format(text=e(text)) if text else ''


def telling(told):
    """A place's telling above the reply and the card: the host's frame, the paint, and the exact lines it draws on folded
    beneath (open when nothing is painted). Nothing when there is nothing to tell (`quiet`, `notAPlace`, no telling)."""
    t = (told or {}).get('telling')
    if not t or not (told.get('text') or t.get('exact')):
        return ''
    return T['telling'].format(frame=e(t.get('frame') or ''), paint=painting(told.get('text')), open='' if told.get('text') else ' open',
                               lines=e('\n'.join(t.get('exact') or [])))


def place(card, paint=None, wants=()):
    """A card as the place speaking: the paint first; the exact card folded beneath it, open when nothing is painted."""
    return T['place'].format(paint=painting(paint), open='' if paint else ' open', card=e(card),
                             wants=''.join(T['wants'].format(reading=e(w.get('reading') or w.get('name', ''))) for w in wants))


def state_of(view):
    """A view's state as plain JSON, a dict or nothing."""
    s = plain((view or {}).get('state') or {})
    return s if isinstance(s, dict) else {}


def rows(value):
    """A relation's rows (`{tag: rows, items}`) or a list, as dicts."""
    items = value.get('items') if isinstance(value, dict) else value
    return [r for r in items or [] if isinstance(r, dict)]


def heading(name, view, did=None):
    """A place's name as its state calls it (`head`), else its id; above it, small, its id, its kind and its maker."""
    s = state_of(view)
    head = s.get('head') if isinstance(s.get('head'), str) and s.get('head').strip() else None
    kind = s.get('kind') if isinstance(s.get('kind'), str) and s.get('kind') else None
    maker = s.get('makerHandle') or s.get('keeperHandle')
    about = ' · '.join(x for x in (name if head else None, f"a {kind.rpartition('/')[2]}" if kind else None,
                                   f'made by {maker}' if isinstance(maker, str) and maker else None) if x)
    return T['heading'].format(about=e(about), name=e(head or name), yours=yours(name, did))


LATELY, LOCAL_DOORS = 6, 8  # lines shown under a place; doors drawn on its local map


def lately(view, entries=()):
    """The place's newest lines (its `lines` relation: who, the verb, what they wrote), newest first; with none, the newest
    admitted entries that touched it (who, the verbs their writes name)."""
    shown = sorted(rows(state_of(view).get('lines')), key=lambda r: r.get('at') or 0, reverse=True)[:LATELY]
    items = [T['line'].format(who=e(r.get('handle') or guest_name(str(r.get('author', '')))), verb=e(str(r.get('verb') or 'wrote')),
                              text=T['line_text'].format(text=e(r['text'])) if r.get('text') else '', at=e(str(r.get('at', ''))))
             for r in shown]
    if not items:
        for x in entries:
            out = x.get('outcome') or {}
            if out.get('tag') not in ('admitted', 'created') or len(items) >= LATELY:
                continue
            verbs = sorted({v for w in out.get('writes') or [] for v in w.get('verbs') or []})
            items.append(T['line'].format(who=e(guest_name(str((x.get('identity') or {}).get('principal', '')))),
                                          verb=e(', '.join(verbs) or ('made it' if out.get('tag') == 'created' else 'acted')), text='', at=e(str(x.get('height')))))
    return T['lately'].format(items=''.join(items)) if items else ''


def around(name, view, ways=(), entries=(), href=None):
    """What is around a place: who is here now, what lies here, its newest lines; beside them its doors as a small local
    map (the ways in above, the doors out below) and the same doors as links."""
    href = href or (lambda o: '/play/' + quote(o, safe='/:'))
    s = state_of(view)
    present = [r.get('handle') or guest_name(str(r.get('who', ''))) for r in rows(s.get('presence'))]
    things = [r['object'] for r in rows(s.get('things')) if isinstance(r.get('object'), str) and r.get('object')]
    here = (T['present'].format(names=e(', '.join(present)), verb='is' if len(present) == 1 else 'are') if present else '') + \
        (T['things'].format(items=', '.join(T['link'].format(href=e(href(t)), rel=e(t)) for t in things)) if things else '') + lately(view, entries)
    out = [w for w in ways if w.get('from') == name and w.get('to') != name]
    into = [w for w in ways if w.get('to') == name and w.get('from') != name]
    if not out:  # a place whose doors the map does not reach: the doors its own state cites
        out = [{'from': name, 'label': d.get('label') or d['to']['object'], 'to': d['to']['object']} for d in door_rows(view)]
    link = lambda w, end: T['door'].format(href=e(href(w[end])), label=e(w.get('label') if end == 'to' else w[end]) or e(w[end]), description=e(w[end]))
    doors = (T['doors'].format(items=' · '.join(link(w, 'to') for w in out)) if out else T['no_doors']) + \
        (T['way_in'].format(items=' · '.join(link(w, 'from') for w in into)) if into else '')
    if not (here or out or into):
        return ''
    return T['around'].format(here=here, drawing=local_map(name, into, out[:LOCAL_DOORS]) if out or into else '', doors=doors)


def local_map(name, into, out):
    """A place and its doors drawn small: the ways in above it, the place, its doors fanned below; plain SVG in the text
    colour, a picture beside the links (the links are the doors' list), so it is decoration to a screen reader."""
    w, top, mid, low = 320, 22, 78, 150
    span = lambda n, i: w / 2 if n == 1 else 34 + i * (w - 68) / (n - 1)
    label = lambda t: e(t if len(t) <= 16 else t[:15] + '…')
    parts = [f'<line x1="{span(len(into), i):.0f}" y1="{top}" x2="{w / 2:.0f}" y2="{mid}" class="in"/>' for i in range(len(into))]
    parts += [f'<line x1="{w / 2:.0f}" y1="{mid}" x2="{span(len(out), i):.0f}" y2="{low}"/>' for i in range(len(out))]
    parts += [f'<circle cx="{span(len(into), i):.0f}" cy="{top}" r="3.5" class="away"/><text x="{span(len(into), i):.0f}" y="{top - 9}">{label(x["from"])}</text>'
              for i, x in enumerate(into)]
    parts += [f'<circle cx="{w / 2:.0f}" cy="{mid}" r="7" class="here"/><text x="{w / 2 + 14:.0f}" y="{mid + 4}" text-anchor="start" class="name">{label(name)}</text>']
    parts += [f'<circle cx="{span(len(out), i):.0f}" cy="{low}" r="4.5" class="away"/><text x="{span(len(out), i):.0f}" y="{low + 18 + (i % 2) * 13 * (len(out) > 4)}">{label(x.get("label") or x["to"])}</text>'
              for i, x in enumerate(out)]
    height = low + 26 + 13 * (len(out) > 4) if out else mid + 16
    return T['local_map'].format(width=w, height=height, y0=0 if into else top + 2, parts=''.join(parts))


def suggestions(path, offered, usage):
    """Spells to edit in the box, each once, at most SUGGESTIONS, then the card's usage; choosing one sends nothing."""
    seen, out = set(), []
    for label, spell in [*offered[:SUGGESTIONS * 4]]:
        if spell not in seen and len(seen) < SUGGESTIONS:
            seen.add(spell)
            out.append((label, spell))
    return ' '.join(T['suggestion'].format(path=e(path), spell=e(quote(spell, safe='')), label=e(label)) for label, spell in out + [('how to say it', usage)])


def reply(turns, offers=(), usage=None):
    """What came back: a refusal or a wait first, as the answer; each offer as speech with its exact text folded, hob's
    lines beside them, or the quiet line; then an admission's line, on demand. -> (markup, the offers' spells)."""
    line = lambda which, fate, text: T[which].format(cls=e(str(fate)), icon=stamp(fate, word=False), line=e(text))
    answers = ''.join(line('turn', fate, text) for fate, text in turns if fate != 'admitted')
    receipts = ''.join(line('receipt', fate, text) for fate, text in turns if fate == 'admitted')
    said, spells = [], []
    for text in offers:
        hob, card = hobbed(text)
        said += [T['hob'].format(text=e(h)) for h in hob]
        if card.strip():
            first, found = speech(card)
            said.append(T['spoken'].format(text=e(first), card=e(card)))
            spells += found
    body = T['exact'].format(text=e(usage)) if usage is not None else ''.join(said) or T['quiet']
    return T['reply'].format(lines=answers, offers=body + receipts), spells


def play(name, who, path, card, *, answer='', offered=(), paint=None, wants=(), view=None, ways=(), entries=(), said='', told=None, did=None):
    """An object to play: its name, a place's telling when the reply just sent entered it, what came back, the place, the
    one box and its suggestions (the reply's spells, then what the thing wants, then the card's own), then what is around it."""
    wanted = [(' '.join(w['asks'].split()[1:3]), w['asks']) for w in wants if w.get('asks')]
    return page(name, who, T['play'].format(heading=heading(name, view, did), name=e(name), path=e(path), reply=telling(told) + answer, said=e(said),
                                            place=place(card, paint, wants) if card is not None else '',
                                            suggestions=suggestions(path, [*offered, *wanted, *(speech(card)[1] if card else [])], f'delvetalk {name} ?'),
                                            around=around(name, view, ways, entries) if card is not None else ''))


BRIEF = 5  # receipts the brief text view keeps


def obj(name, who, view, card, entries, did=None, ways=(), seen=None, wants=(), brief=None, paint=None, told=None):
    """An object as anyone may read it: its name, a place's telling for a signed-in reader, the place (paint, exact card,
    wants), a way to speak to it (or in), what is around it, then its law, source and journal on demand. `brief` (the text
    view's default, the href of the whole page): the place, the doors and the newest BRIEF entries; the law and the source
    are a link away."""
    shown = telling(told) + (place(card, paint, wants) if card else T['state'].format(state=dl(view.get('state'))))
    play = T['playlink'].format(href=e(quote(name, safe='/:'))) if who else T['comein'] if card else ''
    seen = seen if (seen or {}).get('status') == 'inspected' else None
    source = T['source'].format(law=e(seen.get('law') or ''), pin=e(str(seen.get('pinSlug') or '')), source=e(seen.get('source') or ''),
                                lines=len((seen.get('source') or '').splitlines())) if seen else ''
    if brief:
        source, entries = T['whole'].format(href=e(brief)), entries[:BRIEF]
    return page(name, who, T['object'].format(heading=heading(name, view, did), shown=shown, play=play, source=source,
                                              around=around(name, view, ways, entries, lambda o: '/o/' + quote(o, safe=':')) if card else '',
                                              receipts=T['receipts'].format(n=len(entries), slips=''.join(slip(x, did) for x in entries)) if entries else ''))


def surface(title, who, text, paint=None, drawing=''):
    """A read as a page (the book, the history, the map): its paint above, the exact text a post of its spell carries,
    a drawing of it beside when it has one."""
    return page(title, who, T['surface'].format(title=e(title), paint=painting(paint), text=e(text), drawing=drawing))


MAP_WIDTH, MAP_ROW, MAP_PER_ROW, MAP_NODES = 360, 56, 3, 36


def door_map(ways, root):
    """The doors as a small drawing (docs/VOICE.md "The map"): the cards reached from `root` through `ways` (the host's
    `world-surface` doors, each `{from, label, to}`), a row for each step away, three to a row, at most MAP_NODES, each a
    link to its card's map; a line for each door between two drawn. Plain SVG, `currentColor`, fits a phone's width."""
    depth, order = {root: 0}, [root]
    for card in order:
        for w in ways:
            if w['from'] == card and w['to'] not in depth and len(order) < MAP_NODES:
                depth[w['to']] = depth[card] + 1
                order.append(w['to'])
    rows, place = [], {}
    for d in range(max(depth.values()) + 1):
        layer = [c for c in order if depth[c] == d]
        rows += [(k, layer[i:i + MAP_PER_ROW]) for k, i in enumerate(range(0, len(layer), MAP_PER_ROW))]
    cell = MAP_WIDTH / (MAP_PER_ROW + 0.5)
    for r, (k, row) in enumerate(rows):  # a layer's second row sits half a cell over, so no line runs through a card
        for i, card in enumerate(row):
            place[card] = ((i + 0.5 + 0.5 * (k % 2)) * cell + (MAP_WIDTH - cell * (MAP_PER_ROW + 0.5)) / 2
                           if len(row) == MAP_PER_ROW or k else (i + 0.5) * MAP_WIDTH / len(row), r * MAP_ROW + 20)
    lines = ''.join(f'<line x1="{place[w["from"]][0]:.0f}" y1="{place[w["from"]][1] - 4:.0f}" x2="{place[w["to"]][0]:.0f}" y2="{place[w["to"]][1] - 4:.0f}"/>'
                    for w in ways if w['from'] in place and w['to'] in place and w['from'] != w['to'])
    href = lambda c: '/map' + ('' if c == 'commonplace' else '?from=' + quote(c, safe=''))
    nodes = ''.join(f'<a href="{e(href(c))}"><circle cx="{x:.0f}" cy="{y - 4:.0f}" r="4"/><text x="{x:.0f}" y="{y + 14:.0f}">{e(c if len(c) <= 18 else c[:17] + "…")}</text></a>'
                    for c, (x, y) in place.items())
    return T['door_map'].format(width=MAP_WIDTH, height=len(rows) * MAP_ROW + 12, lines=lines, nodes=nodes)


def dl(v):
    """Plain JSON as semantic HTML: a record a definition list, a list an ordered list, typed data its value."""
    if isinstance(v, dict) and v.get('tag') in ('record', 'list'):  # typed data: its fields, its items
        v = {f['name']: f['value'] for f in v.get('fields') or []} if v['tag'] == 'record' else v.get('items') or []
    if isinstance(v, dict) and 'tag' in v and set(v) <= {'tag', 'value', 'label', 'payload'}:
        return e(str(v.get('value', v.get('label', ''))))
    if isinstance(v, dict):
        return '<dl>' + ''.join(f'<dt>{e(str(k))}</dt><dd>{dl(x)}</dd>' for k, x in v.items() if k not in ('_links', '_actions')) + '</dl>'
    return '<ol>' + ''.join(f'<li>{dl(x)}</li>' for x in v) + '</ol>' if isinstance(v, list) else e(str(v))


def listing(ids, words, who, did, more=None):
    return page('the town', who, T['world'].format(items=items(ids, words, did), more=T['more'].format(href=e(more)) if more else ''))


def exact(text):
    """A card's text verbatim, hob's lines beside it."""
    hob, card = hobbed(text)
    return ''.join(T['hob'].format(text=e(h)) for h in hob) + (T['exact'].format(text=e(card)) if card.strip() else '')


def rendered(kind, body, links, who, did=None):
    """An agent route's reply for a browser: a receipt as its slip, offers as slips and cards, anything else as a definition list."""
    if kind == 'receipt' and isinstance(body.get('receipt'), dict):
        rc = body['receipt']
        roots = ' '.join(T['root'].format(href=e(quote(r.get('object', ''), safe=':')), id=e(str(r.get('object'))), version=e(str(r.get('version'))))
                         for r in rc.get('roots') or [])
        offers = ''.join(exact(str(o['text'])) for o in rc.get('offers') or [] if isinstance(o, dict) and 'text' in o)
        return page('receipt', who, T['receipt_page'].format(name=e(str(rc.get('slug', ''))), slip=slip(rc, did), offers=offers,
                                                             roots=roots, projection=dl({k: v for k, v in rc.items() if k not in ('slug', 'roots', 'offers' if offers else '')})))
    if kind == 'offers' and isinstance(body.get('offers'), list):
        items = ''.join(T['offer_slip'].format(height=e(str(o.get('height'))), intent=e(str((o.get('identity') or {}).get('intent'))),
                                               offer=exact(str(o.get('text')))) for o in body['offers'] if isinstance(o, dict)) or T['quiet']
        return page('offers', who, T['offers'].format(items=items, more=T['more'].format(href=e(links['next']['href'])) if 'next' in links else ''))
    return page(kind, who, T['generic'].format(title=e(kind), body=dl(body), links=doors_of(links)))


def challenged(handle, text, note=''):
    """The word to post, and the one button that says it was posted."""
    return page('post this one word', None, T['challenged'].format(handle=e(handle), text=e(text), note=T['claim_note'].format(note=e(note)) if note else ''))


def enter(note='', code='', name=''):
    """The guest door (`/enter`): an invitation's code and a name of the guest's choosing, or the key from before; what
    went wrong, in plain words, above the forms, which keep what was typed (never a key)."""
    return page('come in', None, T['enter_page'].format(note=T['enter_note'].format(note=e(note)) if note else '', code=e(code), name=e(name)))


def welcome(handle, credential):
    """A guest just in: their key shown this once, and the way on."""
    return page('welcome', handle, T['welcome'].format(handle=e(handle), credential=e(credential), book=e(quote(handle, safe=''))))


def leave(handle):
    """Signing out, or (nobody signed in) that this browser speaks for nobody."""
    return page('sign out', handle, T['leave_page'].format(handle=e(handle)) if handle else T['left'])


def catalogue(api, who):
    row = lambda a, b, c, d: T['row'].format(a=e(str(a)), b=e(str(b)), c=e(str(c)), d=e(str(d)))
    return page('the catalogue', who, T['catalogue'].format(
        routes=''.join(row(r['method'], r['href'], r['auth'], r['does']) for r in api['routes']),
        errors=''.join(row(v['code'], k, v['status'], v['when']) for k, v in api['errors'].items()),
        refusals=''.join(row(k, v['transient'], v['hint'], v['means']) for k, v in api['refusals'].items()), limits=dl(api['limits'])))


def refusal(title, who, body, code_class=None):
    """An envelope (or a host refusal) as a page: its class, its words, its hint, its links."""
    hint = T['hint'].format(hint=e(str(body['hint']))) if body.get('hint') else ''
    return page(title, who, T['refusal'].format(cls=e(str(code_class or body.get('class') or body.get('status'))), title=e(title),
                                                message=e(str(body.get('message') or f"no object {title} that you may see")), hint=hint, links=doors_of(body.get('_links')) or T['link'].format(href='/', rel='the town')))


VOID = {'input', 'br', 'img', 'meta', 'link', 'hr', 'source', 'wbr', 'col', 'area', 'base'}
BLOCKS = {'header', 'main', 'footer', 'nav', 'section', 'div', 'p', 'figure', 'figcaption', 'aside', 'details', 'summary', 'h1', 'h2', 'h3',
          'li', 'tr', 'dt', 'ol', 'ul', 'dl', 'table', 'br'}


class Plain(HTMLParser):
    """A page as plain text, read off the markup the browser gets: each link a door (`[ GARDEN ] /play/garden`, `label <href>`),
    each form its method, action and fields as spell slots, each card, spell, law and listing verbatim between fences, each
    receipt its ticket line (stamp, clause, height, slug, who), the quiet line as it stands. Decoration (svg, CSS marks) is not text."""
    def __init__(self):
        super().__init__()
        self.out, self.bufs, self.lists, self.skip, self.form, self.prefix, self.options, self.spans = [], [['line', '', {}]], [], 0, None, '', [], []

    def add(self, text):
        self.bufs[-1][1] += text

    def soft(self):
        if self.bufs[-1][1] and not self.bufs[-1][1].endswith(' '):
            self.add('  ')

    def flush(self):
        text = re.sub(' {3,}', '  ', self.bufs[0][1]).strip()
        if text:
            self.out.append('  ' * max(0, len(self.lists) - 1) + self.prefix + text)
        self.bufs[0][1], self.prefix = '', ''

    def emit(self, *lines):
        self.flush()
        self.out += [*lines, '']

    def control(self, line):
        self.form.append('  ' + line) if self.form is not None else (self.soft(), self.add(line))

    def slot(self, a, value=''):
        """A control as a spell's line: `name: value` when it is fixed, `name: <what goes here>` when it is yours to fill."""
        name, label = a.get('name', ''), next((b[1] for b in reversed(self.bufs) if b[0] == 'label'), '').strip()
        bare = name.split(':')[-1]
        label = label[len(bare):].strip() if label.lower().startswith(bare.lower()) else label
        hint = '; '.join(x for x in (label, a.get('placeholder')) if x) or a.get('type') or 'text'
        return f'{name}: {value}' if value or a.get('type') == 'hidden' else f'{name}: <{hint}>'

    def handle_starttag(self, tag, attrs):
        a, top = dict(attrs), self.bufs[-1]
        cls = (a.get('class') or '').split()
        if self.skip or tag in ('head', 'script', 'style', 'svg', 'template') or 'hidden' in a:
            self.skip += tag not in VOID
        elif top[0] == 'pre':
            pass
        elif tag in ('pre', 'a', 'button', 'option', 'textarea', 'label'):
            if tag == 'pre':
                self.flush()
            self.bufs.append([tag, '', {**a, 'cls': cls, 'kind': cls[-1] if cls else 'text'}])
        elif tag == 'form':
            self.flush()
            self.form = [f"{(a.get('method') or 'get').upper()} {a.get('action') or '.'}"]
        elif tag == 'input':
            self.control(self.slot(a, a.get('value', '') if a.get('type') == 'hidden' else ''))
        elif tag == 'select':
            self.options = []
            self.bufs.append(['select', '', a])
        elif tag == 'span':
            self.spans.append(bool(cls))
            if cls:
                self.soft()
        elif tag in ('td', 'th') and top[1].strip():
            self.add(' | ')
        elif tag == 'dd':
            self.add(': ')
        elif tag == 'small' and self.prefix == '# ':
            self.add(' · ')
        elif tag in BLOCKS:
            self.flush()
            if tag in ('ol', 'ul', 'dl'):
                self.lists.append([tag, 0])
            elif tag == 'li' and self.lists:
                self.lists[-1][1] += 1
                self.prefix = '' if 'slip' in cls else f'{self.lists[-1][1]}. ' if self.lists[-1][0] == 'ol' else '- '
            elif tag in ('h1', 'h2', 'h3'):
                self.prefix = '#' * int(tag[1]) + ' '

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= tag not in VOID
            return
        kind, text, a = self.bufs[-1]
        if kind == tag:
            self.bufs.pop()
            text = text.strip('\n') if tag in ('pre', 'textarea') else re.sub(r'\s+', ' ', text).strip()
            if tag == 'pre':
                self.emit(f"--- {a['kind']} ---", text, '---')
            elif tag == 'a':
                self.soft()
                href = a.get('href', '')
                self.add(f'[ {text} ] {href}' if 'door' in a['cls'] else f'<{href}>' if text == href else f'{text} <{href}>')
            elif tag == 'button':
                self.control(f'[ {text} ]' + (f" {a['name']}={a.get('value', '')}" if a.get('name') else ''))
            elif tag == 'option':
                self.options.append(text)
            elif tag == 'textarea':
                self.control(self.slot(a, text))
            elif tag == 'select':
                self.control(f"{a.get('name', '')}: <one of: {' | '.join(self.options)}>")
        elif kind == 'pre':
            pass
        elif tag == 'span' and self.spans:
            if self.spans.pop():
                self.soft()
        elif tag == 'form' and self.form is not None:
            form, self.form = self.form, None
            self.emit(*form)
        elif tag in BLOCKS:
            self.flush()
            if tag in ('ol', 'ul', 'dl') and self.lists:
                self.lists.pop()

    def handle_data(self, data):
        if not self.skip:
            self.add(data if self.bufs[-1][0] in ('pre', 'textarea') else re.sub(r'\s+', ' ', data))


def text(markup):
    """A page as plain text: every action and rule the HTML carries, from the HTML itself (`?text=1`, or Accept: text/plain)."""
    p = Plain()
    p.feed(markup)
    p.close()
    p.flush()
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(p.out)).strip() + '\n'
