"""HTML for people (docs/WEB.md). The markup is transport/static/pages.html (named sections), the look
transport/static/style.css, the one stylesheet; reading and acting need no script. Python fills the sections with escaped
host facts and decides nothing. `text` reads any page back off its own markup as plain text, so the two views cannot drift."""
import re
import textwrap
from html import escape as e
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from transport.host import plain

STATIC = Path(__file__).resolve().parent / 'static'


def sections(name):
    """A markup file of static/ as its named sections: `<!-- name: what it is -->` then the markup, up to the next."""
    return dict(re.findall(r'<!-- (\w+)[^>]*-->\n(.*?)(?=\n<!--|\Z)', (STATIC / name).read_text(), re.S))


T = sections('pages.html')
SUGGESTIONS = 6  # spells offered under the box, at most


def page(title, who, body, *, site='DelveTalk', home='/', head=None, nav='', foot=None):
    """The one skeleton. The hand passes its own `head` (the stylesheet inlined), `nav` and `foot`."""
    return T['shell'].format(title=e(title), site=e(site), home=e(home), head=T['head'] if head is None else head, nav=nav,
                             who=e(who or ''), body=body, foot=T['foot'] if foot is None else foot)


STAMPS = {'admitted': '●', 'refused': '§', 'suspended': '…', 'quiet': '—'}  # a receipt's stamp: an icon beside its word, never colour alone


def stamp(fate, word=True):
    return f"{STAMPS.get(fate, '◦')} {fate}" if word else STAMPS.get(fate, '◦')


def yours(text, did):
    return T['yours'] if did and did in str(text) else ''


def resident(i):
    """An id that is a resident's avatar (a DID, or an invited guest), not a place or a thing."""
    return i.startswith(('did:', 'guest:'))


def home(status, who, ids=(), did=None):
    """What the town is, one way in, and its places; residents are counted, not listed."""
    places = [i for i in ids if not resident(i)]
    items = ' '.join(T['place_item'].format(id=e(i), href=e(quote(i, safe=':')), yours=yours(i, did)) for i in places)
    n = len(ids) - len(places)
    shown = T['places'].format(items=items, residents=T['residents'].format(n=n) if n else '') if ids else ''
    return page('a town of things that answer', who, T['home'].format(height=e(str(status.get('height'))), objects=e(str(status.get('objects'))),
                                                  enter=T['enter'] if who else '', login='' if who else T['login'], places=shown))


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


def door_rows(view):
    """The doors a record cites (its `cites` list, in the owner's order), those with an object."""
    state = plain(view.get('state') or {})
    doors = (state.get('cites') if isinstance(state, dict) else None) or []
    return [d for d in doors if isinstance(d, dict) and (d.get('to') or {}).get('object')]


def door_line(doors, href):
    items = ' · '.join(T['door'].format(href=e(href(d['to']['object'])), label=e(d.get('label') or d['to']['object']), description=e(d.get('description', '')))
                       for d in doors)
    return T['doors'].format(items=items) if items else ''


def place(card, paint=None, wants=(), doors=(), href=None):
    """A card as the place speaking: the paint first; the exact card folded beneath it, open when nothing is painted."""
    href = href or (lambda o: '/play/' + quote(o, safe='/:'))
    return T['place'].format(paint=painting(paint), open='' if paint else ' open', card=e(card),
                             wants=''.join(T['wants'].format(reading=e(w.get('reading') or w.get('name', ''))) for w in wants),
                             doors=door_line(doors, href))


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


def play(name, who, path, card, *, answer='', offered=(), paint=None, wants=(), doors=(), said='', told=None):
    """An object to play: a place's telling when the reply just sent entered it, what came back, the place, the one box,
    and its suggestions: the reply's spells, then what the thing wants, then the card's own."""
    wanted = [(' '.join(w['asks'].split()[1:3]), w['asks']) for w in wants if w.get('asks')]
    return page(name, who, T['play'].format(name=e(name), path=e(path), reply=telling(told) + answer, said=e(said),
                                            place=place(card, paint, wants, doors) if card is not None else '',
                                            suggestions=suggestions(path, [*offered, *wanted, *(speech(card)[1] if card else [])], f'delvetalk {name} ?')))


BRIEF = 5  # receipts the brief text view keeps


def obj(name, who, view, card, entries, did=None, doors=(), seen=None, wants=(), brief=None, paint=None, told=None):
    """An object as anyone may read it: a place's telling for a signed-in reader, the place (paint, exact card, wants,
    doors), a way to speak to it, then its law, source and journal on demand. `brief` (the text view's default, the href
    of the whole page): the place, the doors and the newest BRIEF entries; the law and the source are a link away."""
    shown = telling(told) + (place(card, paint, wants, doors, lambda o: '/o/' + quote(o, safe=':')) if card else T['state'].format(state=dl(view.get('state'))))
    play = T['playlink'].format(href=e(quote(name, safe='/:'))) if who else ''
    seen = seen if (seen or {}).get('status') == 'inspected' else None
    source = T['source'].format(law=e(seen.get('law') or ''), pin=e(str(seen.get('pinSlug') or '')), source=e(seen.get('source') or ''),
                                lines=len((seen.get('source') or '').splitlines())) if seen else ''
    if brief:
        source, entries = T['whole'].format(href=e(brief)), entries[:BRIEF]
    return page(name, who, T['object'].format(id=e(name), yours=yours(name, did), shown=shown, play=play, source=source,
                                              receipts=T['receipts'].format(n=len(entries), slips=''.join(slip(x, did) for x in entries)) if entries else ''))


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
