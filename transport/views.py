"""A card's view as HTML (docs/VIEWS.md). A body's `view` (world/lib/View.obend) is data the host derives for one
reader (`world-derived`); this draws it from a closed vocabulary and nothing else: every word is escaped text, every
attribute is a number this module computed, a class from its own tables, or an escaped string it built; an unknown
tag, field or shape draws nothing, a value of the wrong type draws as empty. There is no path from a view to markup,
style, script, an event handler or an address but a `data:image` (or a host the town allows). A button or a tile casts
one of the thing's own forms that the reader is offered, by name, with its fields checked against the form's bounds
here and judged again by the host: a form posting `do` to `/play/<id>` (no script), or with say.js one click.

The view decides what is shown and what can be done; this module only encodes it, as pages.py encodes a card."""
import math
import re
from html import escape as e
from urllib.parse import quote, urlencode

from transport.host import plain

# Every tone a view may name (View.tones): a CSS class each, `t-` for words and `f-` for fills, defined in style.css.
TONES = frozenset(('ink soft muted paper leaf tint rule amber violet silver terracotta sage glow red orange yellow green cyan blue '
                   'purple magenta white black grey grass forest hills mountain water shallows sand snow cave village castle keep road').split())
SIZES = {'small': 'z-small', 'large': 'z-large'}
TEXT_MAX, LABEL_MAX, TILE_LABEL, TITLE_MAX = 4000, 80, 8, 200  # characters drawn of a text, a button, a tile's label, a title
DEPTH_MAX, COLUMNS_MAX, TABLE_ROWS, TABLE_COLUMNS, UNITS_MAX, PATH_TOKENS, IMAGE_BYTES = 24, 64, 200, 16, 4096, 2000, 65536
IMAGE_HOSTS = ()  # https hosts an image may come from; none: a view's images are its own data (and the page's CSP says so)
ACTION = re.compile(r'[a-z][A-Za-z0-9_-]{0,63}\Z')
FIELD = re.compile(r'[a-z][A-Za-z0-9_]{0,63}\Z')
DATA_IMAGE = re.compile(r'data:image/(?:png|gif|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}\Z')
PATH = re.compile(r'[MLHVCSQTAZmlhvcsqtaz]|\d{1,5}(?:\.\d{1,2})?')
HEX = 20  # a hex tile's radius, in the drawing's units; a square tile is 2 * HEX


def tone(word, prefix):
    """The class of a named tone, or none."""
    return f'{prefix}-{word}' if isinstance(word, str) and word in TONES else ''


def text(d, k, limit=TEXT_MAX):
    v = d.get(k) if isinstance(d, dict) else None
    return v[:limit] if isinstance(v, str) else ''


def number(d, k, top=UNITS_MAX):
    v = d.get(k) if isinstance(d, dict) else None
    return max(0, min(v, top)) if isinstance(v, int) and not isinstance(v, bool) else 0


def items(d, k):
    v = d.get(k) if isinstance(d, dict) else None
    return v if isinstance(v, list) else []


def cls(*names):
    names = ' '.join(n for n in names if n)
    return f' class="{names}"' if names else ''


class Drawing:
    """One view drawn for one reader of one thing: `obj` its id, `forms` {action: {field: kind}} the forms the host
    offers this reader (world-inspect `forms`, filtered by `offered`), `nodes` the host's `maxViewNodes`."""

    def __init__(self, obj, forms, nodes):
        self.obj, self.forms, self.left, self.cut = obj, forms, nodes, False

    def spend(self):
        if self.left <= 0:
            self.cut = True
            return False
        self.left -= 1
        return True

    # ---- acts: a form of the thing's own, offered to this reader, its fields within the form's bounds

    def act(self, a, typed=()):
        """-> (do, spell) for an Act, `do` the value the front reads back (`action?field=value&…`) and `spell` the same
        as a typed spell, or None when this reader may not cast it as given. `typed`: fields the reader fills (an ask)."""
        action = text(a, 'action', 64)
        if not ACTION.match(action) or action not in self.forms:
            return None
        declared, given = self.forms[action], []
        for f in items(a, 'fields'):
            name, value = text(f, 'name', 64), text(f, 'value', 1400)
            if not FIELD.match(name) or name not in declared or name in typed or not fits(declared[name], value):
                return None
            given.append((name, value))
        if any(n not in declared for n in typed) or not whole(declared, [n for n, _ in given] + list(typed)):
            return None
        spell = '\n'.join([f'delvetalk {self.obj} {action}', *(f'{n}: {v}' for n, v in given)])
        return action + ('?' + urlencode(given) if given else ''), spell

    def say(self, spell):
        """A suggestion's link: the play page with the box holding the spell (no script needed, nothing sent)."""
        return '/play/' + quote(self.obj, safe='/:') + '?say=' + quote(spell, safe='') + '#say'

    def form(self, inner, do, spell):
        return (f'<form class="v-act" method="post" action="/play/{e(quote(self.obj, safe="/:"))}" title="{e(spell)}">'
                f'<input type="hidden" name="do" value="{e(do)}">{inner}</form>')

    # ---- views

    def view(self, v, depth=0):
        if not isinstance(v, dict) or depth > DEPTH_MAX or not self.spend():
            return ''
        draw = VIEWS.get(v.get('tag')) if isinstance(v.get('tag'), str) else None
        return draw(self, v, depth) if draw else ''

    def draw_text(self, v, depth):
        return f'<p{cls("v-text", tone(v.get("tone"), "t"), SIZES.get(v.get("size"), ""))}>{e(text(v, "value"))}</p>'

    def draw_heading(self, v, depth):
        return f'<h2 class="v-heading">{e(text(v, "value", LABEL_MAX))}</h2>'

    def draw_stack(self, v, depth):
        return '<div class="v-stack">' + ''.join(self.view(x, depth + 1) for x in items(v, 'items')) + '</div>'

    def draw_row(self, v, depth):
        return '<div class="v-row">' + ''.join(self.view(x, depth + 1) for x in items(v, 'items')) + '</div>'

    def draw_rule(self, v, depth):
        return '<hr class="v-rule">'

    def draw_button(self, v, depth):
        label, act = e(text(v, 'label', LABEL_MAX)), self.act(v.get('act'))
        if act is None:
            return f'<span{cls("v-button", "v-off", tone(v.get("tone"), "t"))} title="not yours to do here">{label}</span>'
        return self.form(f'<button{cls("v-button", tone(v.get("tone"), "t"))}>{label}</button>', *act)

    def draw_ask(self, v, depth):
        name = text(v, 'field', 64)
        act = self.act(v.get('act'), typed=(name,)) if FIELD.match(name) else None
        label = e(text(v, 'label', LABEL_MAX))
        if act is None:
            return f'<p class="v-text v-off">{label}</p>'
        do, spell = act
        box = (f'<label class="v-ask">{label}<input name="f.{e(name)}" placeholder="{e(text(v, "placeholder", LABEL_MAX))}" '
               f'maxlength="{e(str(bound(self.forms[do.split("?")[0]][name])))}" autocomplete="off"></label>'
               f'<button class="v-button">{label or "Send"}</button> '
               '<button class="quiet-button" name="try" value="1" title="see what it would do; nothing is written">Try it first</button>')
        return self.form(box, do, spell + f'\n{name}: <yours>')

    def draw_progress(self, v, depth):
        top = max(1, number(v, 'max', 10 ** 9))
        value = min(number(v, 'value', 10 ** 9), top)
        return (f'<p{cls("v-progress", tone(v.get("tone"), "t"))}><span class="v-label">{e(text(v, "label", LABEL_MAX))}</span> '
                f'<progress max="{top}" value="{value}">{value} of {top}</progress> <span class="v-of">{value} of {top}</span></p>')

    def draw_table(self, v, depth):
        head = [e(c[:LABEL_MAX]) for c in items(v, 'head')[:TABLE_COLUMNS] if isinstance(c, str)]
        rows = [[e(c[:LABEL_MAX]) for c in r[:TABLE_COLUMNS] if isinstance(c, str)] for r in items(v, 'rows')[:TABLE_ROWS] if isinstance(r, list)]
        rows = [r for r in rows if self.spend()]
        return ('<table class="v-table">' + ('<thead><tr>' + ''.join(f'<th>{c}</th>' for c in head) + '</tr></thead>' if head else '') +
                '<tbody>' + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table>')

    def draw_image(self, v, depth):
        source, alt = text(v, 'source', IMAGE_BYTES + 64), e(text(v, 'alt', LABEL_MAX))
        allowed = DATA_IMAGE.match(source) or any(source.startswith(f'https://{h}/') for h in IMAGE_HOSTS)
        if not allowed or len(source) > IMAGE_BYTES:
            return f'<p class="v-text v-off">{alt}</p>' if alt else ''
        width = number(v, 'width', 1024)
        return f'<img class="v-image" src="{e(source)}" alt="{alt}"' + (f' width="{width}"' if width else '') + '>'

    # ---- tiles: square or hex, drawn as SVG; a tile that acts is a link to its spell, one click with say.js

    def tile(self, t, shape, cx, cy):
        fill = tone(t.get('fill'), 'f') if isinstance(t, dict) else ''
        mark = tone(t.get('mark'), 'f') if isinstance(t, dict) else ''
        label, title = text(t, 'label', TILE_LABEL), text(t, 'title', TITLE_MAX)
        body = f'<{shape}{cls("v-ground", fill)}/>'
        body += f'<circle{cls("v-disc", mark)} cx="{cx}" cy="{cy}" r="{round(HEX * 0.55, 1)}"/>' if mark else ''
        body += f'<text x="{cx}" y="{cy}" class="v-tile-label">{e(label)}</text>' if label else ''
        body = (f'<title>{e(title)}</title>' if title else '') + body
        act = self.act(t.get('act')) if isinstance(t, dict) and text(t.get('act'), 'action') else None
        if act is None:
            return f'<g class="v-tile">{body}</g>'
        do, spell = act
        return f'<a class="v-tile v-acts" href="{e(self.say(spell))}" data-do="{e(do)}">{body}</a>'

    def tiles(self, v):
        columns = max(1, min(number(v, 'columns', COLUMNS_MAX), COLUMNS_MAX))
        shown = [t for t in items(v, 'tiles') if self.spend()]
        return columns, shown, max(1, math.ceil(len(shown) / columns))

    def draw_hexes(self, v, depth):
        """Pointy-top hexes, odd rows half a tile to the right (`odd-r`), numbered along each row from the top left."""
        columns, shown, rows = self.tiles(v)
        w, pad = math.sqrt(3) * HEX, 2
        out = []
        for i, t in enumerate(shown):
            r, c = divmod(i, columns)
            cx, cy = round(pad + w / 2 + w * (c + 0.5 * (r % 2)), 1), round(pad + HEX + 1.5 * HEX * r, 1)
            points = ' '.join(f'{round(cx + HEX * math.cos(math.radians(60 * k - 90)), 1)},{round(cy + HEX * math.sin(math.radians(60 * k - 90)), 1)}'
                              for k in range(6))
            out.append(self.tile(t, f'polygon points="{points}"', cx, cy))
        width, height = round(2 * pad + w * (columns + 0.5), 1), round(2 * pad + 2 * HEX + 1.5 * HEX * (rows - 1), 1)
        return f'<svg class="v-board v-hexes" viewBox="0 0 {width} {height}" role="group">{"".join(out)}</svg>'

    def draw_grid(self, v, depth):
        columns, shown, rows = self.tiles(v)
        side, out = 2 * HEX, []
        for i, t in enumerate(shown):
            r, c = divmod(i, columns)
            out.append(self.tile(t, f'rect x="{c * side}" y="{r * side}" width="{side}" height="{side}"', c * side + HEX, r * side + HEX))
        return f'<svg class="v-board v-grid" viewBox="0 0 {columns * side} {rows * side}" role="group">{"".join(out)}</svg>'

    # ---- drawings: shapes in the drawing's own units

    def draw_drawing(self, v, depth):
        width, height = max(1, number(v, 'width')), max(1, number(v, 'height'))
        shapes = ''.join(self.shape(s) for s in items(v, 'shapes') if isinstance(s, dict) and self.spend())
        return f'<svg class="v-drawing" viewBox="0 0 {width} {height}" role="img">{shapes}</svg>'

    def shape(self, s):
        n = lambda k: number(s, k)
        paint = lambda: cls('v-shape', tone(s.get('fill'), 'f'), tone(s.get('stroke'), 's'))
        tag = s.get('tag')
        if tag == 'circle':
            return f'<circle{paint()} cx="{n("x")}" cy="{n("y")}" r="{n("r")}"/>'
        if tag == 'rect':
            return f'<rect{paint()} x="{n("x")}" y="{n("y")}" width="{n("width")}" height="{n("height")}"/>'
        if tag == 'line':
            return f'<line{cls("v-shape", tone(s.get("stroke"), "s") or "s-ink")} x1="{n("x1")}" y1="{n("y1")}" x2="{n("x2")}" y2="{n("y2")}" stroke-width="{max(1, min(n("width"), 64))}"/>'
        if tag == 'path':
            d = ' '.join(PATH.findall(text(s, 'd', 20000))[:PATH_TOKENS])
            return f'<path{paint()} d="{e(d)}"/>' if d else ''
        if tag == 'label':
            return f'<text{cls("v-shape-label", tone(s.get("tone"), "f"))} x="{n("x")}" y="{n("y")}">{e(text(s, "text", LABEL_MAX))}</text>'
        return ''


# The views this front draws, by their tag in View.View: nothing else is drawn.
VIEWS = {tag: getattr(Drawing, 'draw_' + tag) for tag in
         ('text', 'heading', 'stack', 'row', 'rule', 'button', 'ask', 'progress', 'table', 'image', 'hexes', 'grid', 'drawing')}


def fits(kind, value):
    """Whether a value fills a form field of `kind` (the form's `{tag, min, max, options}`) as a typed spell would."""
    tag = kind.get('tag') if isinstance(kind, dict) else None
    if tag == 'natural':
        return value.isascii() and value.isdigit() and len(value) <= 18 and kind.get('min', 0) <= int(value) <= kind.get('max', 10 ** 18)
    if tag == 'text':
        return '\n' not in value and '\r' not in value and kind.get('min', 0) <= len(value) <= kind.get('max', 1400)
    if tag == 'choice':
        return value in (kind.get('options') or [])
    return False


def whole(declared, names):
    """Whether `names` fill every field of a form a spell must name (all but a text that may be empty)."""
    return all(n in names or (k.get('tag') == 'text' and k.get('min', 0) == 0) for n, k in declared.items() if isinstance(k, dict))


def bound(kind):
    return kind.get('max', 1400) if isinstance(kind, dict) and kind.get('tag') == 'text' else 18


def forms_of(inspected):
    """{action: {field: kind}} of the forms world-inspect says this reader is offered."""
    offered = set(inspected.get('offered') or [])
    forms = plain(inspected.get('forms') or {'tag': 'list', 'items': []})
    return {f['action']: {x['name']: x['kind'] for x in f.get('fields') or [] if isinstance(x, dict)}
            for f in forms if isinstance(f, dict) and f.get('action') in offered}


def render(value, obj, forms, nodes):
    """A view (`world-derived`'s typed `value`) as HTML for one reader: `forms` (`forms_of`) what they may cast, `nodes`
    the host's `maxViewNodes`; past that bound the first nodes are drawn and the view says it was cut."""
    d = Drawing(obj, forms, nodes)
    out = d.view(plain(value))
    return out + ('<p class="v-text v-off">This view is larger than a page draws; the rest is not shown.</p>' if d.cut else '')


def chosen(do, forms, typed=None):
    """The action and fields a `do` (`action?field=value&…`, from a view's form or tile) and any fields the reader typed
    (`f.<name>`) ask for, checked as the view's own acts are: -> (action, {field: value}) or None. Naturals as ints."""
    from urllib.parse import parse_qsl
    action, _, query = str(do or '').partition('?')
    if not ACTION.match(action) or action not in forms:
        return None
    try:
        given = parse_qsl(query, keep_blank_values=True, strict_parsing=bool(query), max_num_fields=32)
    except ValueError:
        return None
    given += list((typed or {}).items())
    declared, fields = forms[action], {}
    for name, value in given:
        if not FIELD.match(name) or name not in declared or name in fields or not fits(declared[name], value):
            return None
        fields[name] = int(value) if declared[name].get('tag') == 'natural' else value
    return (action, fields) if whole(declared, fields) else None
