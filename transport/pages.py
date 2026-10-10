"""HTML for people. The markup is transport/static/pages.html (named sections), the look transport/static/style.css;
no script is needed to read. Python fills the sections with escaped host facts and decides nothing. `text` reads any
page back off its own markup as plain text, so the two views cannot drift."""
import re
from html import escape as e
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

T = dict(re.findall(r'<!-- (\w+)[^>]*-->\n(.*?)(?=\n<!--|\Z)', (Path(__file__).resolve().parent / 'static' / 'pages.html').read_text(), re.S))


def page(title, who, body):
    return T['shell'].format(title=e(title), who=e(who or 'not logged in'), body=body)


STAMPS = {'admitted': '●', 'refused': '§', 'suspended': '…', 'quiet': '—'}  # a receipt's stamp: an icon beside its word, never colour alone


def stamp(fate, word=True):
    return f"{STAMPS.get(fate, '◦')} {fate}" if word else STAMPS.get(fate, '◦')


def yours(text, did):
    return T['yours'] if did and did in str(text) else ''


def home(status, who, ids=(), did=None):
    return page('the ledger', who, T['home'].format(height=e(str(status.get('height'))), objects=e(str(status.get('objects'))),
                                                    enter=T['enter'] if who else '', login='' if who else T['login'], items=items(ids, {}, did)))


def items(ids, words, did):
    """Objects as small cards: the kind's mark, the id, the door word the directory gives it, (yours)."""
    return ''.join(T['world_item'].format(id=e(i), href=e(quote(i, safe=':')), yours=yours(i, did),
                                          word=T['word'].format(word=e(words[i])) if words.get(i) else '') for i in ids)


def doors_of(links):
    return ''.join(T['link'].format(href=e(v['href']), rel=e(k)) for k, v in (links or {}).items() if isinstance(v, dict) and k != 'self')


def slip(x, did=None):
    """A receipt as a stamped ticket: its stamp's icon and word, the slug in small caps, the height as a shelf mark, a refusal's clause."""
    out, ident = x.get('outcome') or {}, x.get('identity') or {}
    clause = out.get('reason') or ' '.join(str(out[k]) for k in ('clause', 'object') if out.get(k))
    return T['slip'].format(fate=e(str(out.get('tag'))), stamp=e(stamp(str(out.get('tag')))), height=e(str(x.get('height'))), name=e(str(x.get('slug') or '')),
                            intent=e(str(ident.get('intent'))), who=e(str(ident.get('principal'))), yours=yours(ident.get('principal'), did),
                            note=T['note'].format(clause=e(f"{out.get('class')}: {clause}" if clause else str(out.get('class')))) if out.get('tag') == 'refused' else '')


def obj(name, who, view, card, entries, did=None, doors=(), seen=None, acts=()):
    """An object: its card (sacred text), its doors, a way to play it, its actions as forms from the method table, its law and
    source as code, its receipts as slips."""
    shown = T['card'].format(text=e(card)) if card else T['state'].format(state=dl(view.get('state')))
    play = T['playlink'].format(href=e(quote(name, safe='/:')), id=e(name)) if who else ''
    seen = seen if (seen or {}).get('status') == 'inspected' else None
    source = T['source'].format(law=e(seen.get('law') or ''), pin=e(str(seen.get('pinSlug') or '')), source=e(seen.get('source') or ''),
                                lines=len((seen.get('source') or '').splitlines())) if seen else ''
    forms = ''.join(form(name, a) for a in acts if a['name'] != 'receive')
    return page(name, who, T['object'].format(id=e(name), version=e(str(view.get('version'))), yours=yours(name, did), shown=shown, play=play,
                                              doors=door_nav(doors), actions=T['actions'].format(forms=forms, href=e(quote(name, safe='/:')), id=e(name)) if forms else '', source=source,
                                              ledger=T['ledger'].format(slips=''.join(slip(x, did) for x in entries)) if entries else ''))


def door_nav(doors):
    return T['doors'].format(items=''.join(T['door'].format(href=e(quote(d['to']['object'], safe='/:')), id=e(d['to']['object']), label=e(d.get('label', '')),
                                                              description=e(d.get('description', ''))) for d in doors)) if doors else ''


def form(name, act):
    """A method of the host's table as a real form: a select for a choice, a bounded text input, a number with min and max."""
    if 'fields' not in act:
        return T['f_typed'].format(method=e(act['name']), id=e(name))
    inputs = ''.join(T['f_' + f['kind']].format(name=e(f['name']), min=e(str(f['bounds'].get('min', ''))), max=e(str(f['bounds'].get('max', ''))),
                                                options=''.join(f'<option>{e(o)}</option>' for o in f['bounds'].get('options', []))) for f in act['fields'])
    return T['action'].format(href=e(quote(name, safe='/:')), method=e(act['name']), inputs=inputs,
                              spell=T['spell'].format(spell=e(act['spell'])) if act.get('spell') else '')


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
    return page('the world', who, T['world'].format(items=items(ids, words, did), more=T['more'].format(href=e(more)) if more else ''))


def rendered(kind, body, links, who, did=None):
    """An agent route's reply for a browser: a receipt as its slip, offers as slips and cards, anything else as a definition list."""
    if kind == 'receipt' and isinstance(body.get('receipt'), dict):
        rc = body['receipt']
        roots = ''.join(T['root'].format(href=e(quote(r.get('object', ''), safe=':')), id=e(str(r.get('object'))), version=e(str(r.get('version'))))
                        for r in rc.get('roots') or [])
        return page('receipt', who, T['receipt'].format(name=e(str(rc.get('slug', ''))), slip=slip(rc, did),
                                                        roots=roots, projection=dl({k: v for k, v in rc.items() if k not in ('slug', 'roots')})))
    if kind == 'offers' and isinstance(body.get('offers'), list):
        items = ''.join(T['offer_slip'].format(height=e(str(o.get('height'))), intent=e(str((o.get('identity') or {}).get('intent'))),
                                               text=e(str(o.get('text')))) for o in body['offers'] if isinstance(o, dict)) or T['quiet']
        return page('offers', who, T['offers'].format(items=items, more=T['more'].format(href=e(links['next']['href'])) if 'next' in links else ''))
    return page(kind, who, T['generic'].format(title=e(kind), body=dl(body), links=doors_of(links)))


def catalogue(api, who):
    row = lambda a, b, c, d: T['row'].format(a=e(str(a)), b=e(str(b)), c=e(str(c)), d=e(str(d)))
    return page('the catalogue', who, T['catalogue'].format(
        routes=''.join(row(r['method'], r['href'], r['auth'], r['does']) for r in api['routes']),
        errors=''.join(row(v['code'], k, v['status'], v['when']) for k, v in api['errors'].items()),
        refusals=''.join(row(k, v['transient'], v['hint'], v['means']) for k, v in api['refusals'].items()), limits=dl(api['limits'])))


def refusal(title, who, body, code_class=None):
    """An envelope (or a host refusal) as a page: its class, its words, its hint as large as the card's, its links as doors."""
    hint = T['hint'].format(hint=e(str(body['hint']))) if body.get('hint') else ''
    return page(title, who, T['refusal'].format(cls=e(str(code_class or body.get('class') or body.get('status'))), title=e(title),
                                                message=e(str(body.get('message') or f"no object {title} that you may see")), hint=hint, links=doors_of(body.get('_links')) or T['link'].format(href='/', rel='the ledger')))


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
