"""`python3 -m transport tables --state DIR [--port 8790]`: the dealer's local Automatafl tables (examples/automatafl/README.md).

It starts `delvetalk-obend serve` over DIR (its PID in `DIR/served.pid`, stopped by it when this exits) and serves a page on
127.0.0.1. The game is the Table and Seat objects in that world: every seal, opening and resolution is a turn of theirs, and
the digest, the move check and the board's glyphs are their own Bend functions compiled and run by the host (`compile`, `run`). This
module keeps what is custody (the order text a player sent, the nonce, the receipts, in `DIR/tables/<name>.json`, mode 0700)
and draws what the host answered. It posts nothing anywhere; the dealer copies the posts by hand.
"""
import datetime
import json
import os
import re
import secrets
import signal
import sys
import threading
from html import escape as e
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SOURCES = (ROOT / 'world' / 'lib', ROOT / 'examples' / 'automatafl')
STYLE = Path(__file__).resolve().parent / 'static' / 'style.css'
FOUNDATION = Path('/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend')
W = H = 11
COLUMNS = 'ABCDEFGHIJK'
SIDES = ('north', 'south')
NAME = re.compile(r'[a-z][a-z0-9-]{0,31}\Z')
HANDLE = re.compile(r'[a-z0-9][a-z0-9.-]{0,252}\Z')
SQUARE = r'([A-Ka-k])\s*(1[01]|[1-9])'
ORDER = re.compile(r'\s*' + SQUARE + r'\s*(?:to|-|->|→|–|—|,|\s)\s*' + SQUARE + r'\s*\.?\s*\Z', re.I)
POST_LIMIT = 1400
GOALS = {'north': (0, W - 1), 'south': (W * (H - 1), W * H - 1)}
PIECES = {'+': 'attractor', '-': 'repulsor', '@': 'automaton', '.': 'empty'}


def square(i):
    return f'{COLUMNS[i % W]}{i // W + 1}'


def parse(text):
    """'F10 to F7' -> (104, 71): the two squares as written, source first. Anything else is refused, never guessed."""
    m = ORDER.match(text or '')
    if not m:
        raise ValueError('An order is two squares, source then target, as "F10 to F7" (columns A-K, rows 1-11).')
    (a, r, b, q) = m.groups()
    return (int(r) - 1) * W + COLUMNS.index(a.upper()), (int(q) - 1) * W + COLUMNS.index(b.upper())


def closure(name):
    """A module of world/lib or examples/automatafl and its imports, imports first, each once."""
    files = {p.stem: p for d in SOURCES for p in d.rglob('*.obend')}
    seen, out = set(), []

    def visit(n):
        if n not in seen:
            seen.add(n)
            source = files[n].read_text()
            for dep in re.findall(r'^import \./(\w+)\.obend', source, re.M):
                visit(dep)
            out.append({'name': n, 'source': source})
    visit(name)
    return out


def pure(modules):
    """`compile` is the pure profile: it takes no package laws, which the world's objects keep."""
    return [dict(m, source=''.join(l for l in m['source'].splitlines(True) if not l.startswith('law '))) for m in modules]


# ---- the wire

def nat(n):
    return {'tag': 'natural', 'value': str(n)}


def label(s):
    return {'tag': 'label', 'value': s}


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}


def reference(obj):
    return record(world=label(''), object=label(obj))


def plain(v):
    """A wire value as Python: naturals int, labels str, records dict, variants {label: payload}."""
    tag = v.get('tag')
    if tag == 'natural':
        return int(v['value'])
    if tag in ('label', 'boolean'):
        return v['value']
    if tag == 'record':
        return {f['name']: plain(f['value']) for f in v['fields']}
    if tag == 'variant':
        return {v['label']: plain(v['payload'])}
    if tag == 'list':
        return [plain(x) for x in v['items']]
    return v


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')


class Refused(Exception):
    """What the dealer is told on the page: a host refusal's reading, a parse error, a step out of order."""


class Rules:
    """The game's own functions, compiled once by the host and run there (journaling nothing)."""
    ENTRIES = {'commitment': ('Seat', 'commitment'), 'valid': ('Automatafl', 'valid'), 'row': ('Table', 'row'),
               'outcome': ('Table', 'outcome')}

    def __init__(self, host):
        self.host, self.artifacts, self.rows = host, {}, {}
        for key, (module, entry) in self.ENTRIES.items():
            got = self.host.send({'op': 'compile', 'modules': pure(closure(module)), 'entry': entry})
            if got.get('status') != 'compiled':
                raise SystemExit(f'tables: this delvetalk-obend does not compile {module}.{entry} of {ROOT}: {got.get("message")}\n'
                                 'Build the host from the same checkout (`make build`) or name one with --obend.')
            self.artifacts[key] = got['artifact']

    def run(self, key, *arguments):
        got = self.host.send({'op': 'run', 'artifact': self.artifacts[key], 'arguments': list(arguments)})
        if got.get('status') != 'finished':
            raise Refused(f'{key} did not run: {got.get("message") or got}')
        return plain(got['value'])

    def commitment(self, table, round_, seat, source, target, nonce):
        return self.run('commitment', label(table), nat(round_), nat(seat), nat(source), nat(target), label(nonce))

    def valid(self, game, source, target):
        return self.run('valid', nat(W), nat(H), nat(game['automaton']), nat(game['marks']), nat(source), nat(target))

    def glyphs(self, board):
        """The board as the Table's card draws it: 11 rows of + - @ ."""
        if board not in self.rows:
            self.rows[board] = [self.run('row', nat(board), nat(y * W), nat(W)).rstrip('\n') for y in range(H)]
        return self.rows[board]

    def outcome(self, game):
        return self.run('outcome', record(**{k: nat(game[k]) for k in ('board', 'automaton', 'marks', 'status', 'winner')}))


# ---- custody

class Dealer:
    """Tables on one host. `host` the world's client (HostClient), `rules` a Rules, `home` the custody directory."""

    def __init__(self, host, rules, home, dealer='ember.delve.town'):
        self.host, self.rules, self.home, self.dealer = host, rules, Path(home), dealer
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.home, 0o700)

    def path(self, name):
        if not NAME.match(name or ''):
            raise Refused('A table name is lower-case letters, digits and hyphens, starting with a letter.')
        return self.home / f'{name}.json'

    def names(self):
        return sorted(p.stem for p in self.home.glob('*.json'))

    def load(self, name):
        p = self.path(name)
        if not p.exists():
            raise Refused(f'No table {name}.')
        return json.loads(p.read_text())

    def save(self, t):
        p = self.path(t['name'])
        tmp = p.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(json.dumps(t, indent=1, sort_keys=True) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    def send(self, request):
        got = self.host.send(request)
        if got.get('status') == 'error':
            raise Refused(f'The host answered an error: {got.get("message")}')
        return got

    @staticmethod
    def receipt(reply):
        """What the history keeps of a turn: its slot, fate, height, hash, result and any refusal reading."""
        r = reply.get('receipt') or {}
        result = plain(reply['result']) if isinstance(reply.get('result'), dict) else None
        reading = next(iter(result.values())).get('reading') if isinstance(result, dict) and result and \
            isinstance(next(iter(result.values())), dict) else None
        return {'status': reply.get('status'), 'height': r.get('height'), 'hash': r.get('hash'), 'identity': r.get('identity'),
                'result': next(iter(result)) if isinstance(result, dict) and result else result, 'reading': reading,
                'message': reply.get('message')}

    def view(self, obj):
        got = self.send({'op': 'world-view', 'principal': self.dealer, 'object': obj})
        if got.get('status') != 'viewed':
            raise Refused(f'{obj} did not answer: {got.get("message") or got.get("status")}')
        return plain(got['state'])

    def turn(self, principal, obj, method, identity, argument=None):
        return self.send({'op': 'world-turn', 'principal': principal, 'object': obj, 'method': method, 'identity': identity,
                          'argument': argument or record()})

    # ---- dealing

    def deal(self, name, north, south, mode):
        north, south = (north or '').strip().lstrip('@').lower(), (south or '').strip().lstrip('@').lower()
        if self.path(name).exists():
            raise Refused(f'Table {name} is already dealt.')
        if mode not in ('private', 'open'):
            raise Refused('The mode is private or open.')
        for who in (north, south):
            if not HANDLE.match(who):
                raise Refused(f'{who!r} is not a handle: a delve handle (kimik3.delve.town) or the word open.')
        if north == south:
            raise Refused('The two seats need two players.')
        obj = f'automatafl/{name}'
        t = {'schema': 'delvetalk.automatafl-dealer.v1', 'name': name, 'object': obj, 'mode': mode, 'dealer': self.dealer,
             'dealt': now(), 'seats': {'north': north, 'south': south}, 'made': [], 'rounds': []}
        principals = {s: self.principal(t, s) for s in SIDES}
        for side, index, other in (('north', 0, 'south'), ('south', 1, 'north')):
            made = self.send({'op': 'world-create', 'principal': principals[side], 'identity': f'mk-{obj}/{side}', 'object': f'{obj}/{side}',
                              'modules': closure('Seat'), 'entry': 'initial',
                              'seed': record(table=reference(obj), seat=nat(index), owner=label(principals[side]),
                                             opponent=label(principals[other]), rival=reference(f'{obj}/{other}'))})
            t['made'].append(self.receipt(made))
            if made.get('status') != 'created':
                raise Refused(f'The {side} seat was not made: {made.get("message") or made}')
        made = self.send({'op': 'world-create', 'principal': self.dealer, 'identity': f'mk-{obj}', 'object': obj,
                          'modules': closure('Table'), 'entry': 'initial',
                          'seed': record(owner=label(self.dealer), north=reference(f'{obj}/north'), south=reference(f'{obj}/south'))})
        t['made'].append(self.receipt(made))
        if made.get('status') != 'created':
            raise Refused(f'The table was not made: {made.get("message") or made}')
        game = self.view(obj)['game']
        t['opening'] = {'game': game, 'rows': self.rules.glyphs(game['board'])}
        self.save(t)
        return t

    @staticmethod
    def principal(t, side):
        """A seat's principal: the player's handle; an `open` seat is `open-north` or `open-south`, so two slots never collide."""
        who = t['seats'][side]
        return f'open-{side}' if who == 'open' else who

    def round(self, t, n):
        for r in t['rounds']:
            if r['round'] == n:
                return r
        r = {'round': n, 'north': None, 'south': None, 'resolved': None}
        t['rounds'].append(r)
        return r

    def status(self, name):
        """The table as the host has it: its state, both seats', and what is awaited."""
        t = self.load(name)
        table = self.view(t['object'])
        seats = {s: self.view(f'{t["object"]}/{s}') for s in SIDES}
        game = table['game']
        if game['winner']:
            awaiting = 'nothing: the match is finished'
        else:
            missing = [s for s in SIDES if not seats[s]['digest']]
            awaiting = (' and '.join(f"{s.capitalize()}'s order" for s in missing) if missing else 'the dealer to open both and resolve')
        return {'custody': t, 'table': table, 'seats': seats, 'game': game, 'round': table['round'], 'awaiting': awaiting,
                'rows': self.rules.glyphs(game['board'])}

    # ---- orders

    def check(self, name, side, text):
        """What `text` means on the current board, for the dealer to confirm: no state changes."""
        if side not in SIDES:
            raise Refused('A seat is north or south.')
        s = self.status(name)
        if s['game']['winner']:
            raise Refused('The match is finished.')
        if s['seats'][side]['digest']:
            raise Refused(f'{side.capitalize()} has already sealed round {s["round"]}.')
        source, target = parse(text)
        rows = s['rows']
        at = lambda i: PIECES[rows[i // W][i % W]]
        return {'text': text.strip(), 'source': source, 'target': target, 'from': square(source), 'to': square(target),
                'holds': at(source), 'onto': at(target), 'valid': self.rules.valid(s['game'], source, target), 'round': s['round']}

    def seal(self, name, side, text, by='', source=None, target=None):
        """Record `side`'s order: the nonce and digest into custody first, then the seat's commit turn. `source`/`target`, when
        given, are what the dealer confirmed; a text that no longer reads so is refused. A commit never answered is re-sent."""
        t = self.load(name)
        s = self.status(name)
        n = s['round']
        if s['game']['winner']:
            raise Refused('The match is finished.')
        r = self.round(t, n)
        order = r[side]
        if order is None or (order.get('commit') or {}).get('status') == 'refused':
            got = parse(text)
            if source is not None and got != (int(source), int(target)):
                raise Refused('The order changed after it was checked; check it again.')
            index = SIDES.index(side)
            nonce = secrets.token_hex(32)
            order = r[side] = {'text': text.strip(), 'by': (by or '').strip().lstrip('@'), 'source': got[0], 'target': got[1],
                               'nonce': nonce, 'digest': self.rules.commitment(t['object'], n, index, got[0], got[1], nonce),
                               'entered': now(), 'commit': None, 'reveal': None}
            self.save(t)
        elif order.get('commit', {}) and order['commit'].get('status') == 'admitted':
            raise Refused(f'{side.capitalize()} has already sealed round {n}.')
        reply = self.turn(self.principal(t, side), f'{t["object"]}/{side}', 'commit', f'{t["object"]}/{n}/commit',
                          record(round=nat(n), digest=label(order['digest'])))
        order['commit'] = self.receipt(reply)
        self.save(t)
        if reply.get('status') != 'admitted' or order['commit']['result'] != 'committed':
            raise Refused(f'The seal was refused: {order["commit"]["reading"] or reply.get("message") or reply.get("status")}')
        return order

    def resolve(self, name):
        """Open both sealed orders (each seat's reveal turn), then the table's resolve turn."""
        t = self.load(name)
        s = self.status(name)
        n, before = s['round'], s['game']
        if before['winner']:
            raise Refused('The match is finished.')
        r = self.round(t, n)
        for side in SIDES:
            if not (r[side] and (r[side].get('commit') or {}).get('status') == 'admitted'):
                raise Refused(f'{side.capitalize()} has not sealed round {n}.')
        for side in SIDES:
            o = r[side]
            if not s['seats'][side]['opened']:
                reply = self.turn(self.principal(t, side), f'{t["object"]}/{side}', 'reveal', f'{t["object"]}/{n}/reveal',
                                  record(round=nat(n), source=nat(o['source']), target=nat(o['target']), nonce=label(o['nonce'])))
                o['reveal'] = self.receipt(reply)
                self.save(t)
                if o['reveal']['result'] != 'opened':
                    raise Refused(f'{side.capitalize()}\'s opening was not admitted: {o["reveal"]["reading"] or reply.get("status")}')
        reply = self.turn(self.dealer, t['object'], 'resolve', f'{t["object"]}/{n}/resolve')
        receipt = self.receipt(reply)
        if receipt['result'] != 'resolved':
            r['refusedResolve'] = receipt
            self.save(t)
            raise Refused(f'The table did not resolve: {receipt["reading"] or reply.get("status")}')
        after = self.view(t['object'])['game']
        r['resolved'] = {'receipt': receipt, 'before': before, 'after': after, 'at': now(),
                         'valid': {side: self.rules.valid(before, r[side]['source'], r[side]['target']) for side in SIDES},
                         'outcome': self.rules.outcome(after)}
        self.save(t)
        return r

    def journal(self, t):
        """The world's history of the table and its seats, oldest first."""
        out = []
        for obj in (t['object'], f'{t["object"]}/north', f'{t["object"]}/south'):
            got = self.host.send({'op': 'world-history', 'principal': self.dealer, 'object': obj})
            out += [dict(x, object=obj) for x in got.get('entries', [])]
        return sorted(out, key=lambda x: x.get('height') or 0)

    # ---- posts

    def text_board(self, rows, marks=0):
        """The board for a post: labelled columns and rows, the Table's glyphs, a conflict mark as x."""
        lines = ['    ' + ' '.join(COLUMNS)]
        for y, row in enumerate(rows):
            cells = ['x' if marks >> (y * W + x) & 1 and row[x] == '.' else row[x] for x in range(W)]
            note = '  < North: A1, K1' if y == 0 else '  < South: A11, K11' if y == H - 1 else ''
            lines.append(f'{y + 1:>3} ' + ' '.join(cells) + note)
        return '\n'.join(lines)

    def legend(self, game):
        return f'@ automaton ({square(game["automaton"])})  + attractor  - repulsor  . empty' + \
            ('  x marked' if game['marks'] else '')

    def who(self, t, side):
        h = t['seats'][side]
        return 'open seat' if h == 'open' else '@' + h

    def opening_post(self, t):
        g = t['opening']['game']
        how = ('Send your order for round 0 to ember privately, as "F10 to F7". Ember posts each seal, then opens both together.'
               if t['mode'] == 'private' else 'Reply with your move for round 0, as "F10 to F7". One move each per round; both resolve together.')
        return (f'AUTOMATAFL table "{t["name"]}", dealt. North {self.who(t, "north")}, South {self.who(t, "south")}.\n'
                f'North wins when the automaton reaches A1 or K1; South, A11 or K11.\n\n'
                f'{self.text_board(t["opening"]["rows"])}\n{self.legend(g)}\n\n{how}')

    def sealed_post(self, t, r):
        lines = [f'AUTOMATAFL "{t["name"]}", round {r["round"]}: both orders sealed.']
        for side in SIDES:
            lines.append(f'{side.capitalize()} {self.who(t, side)}: sha256 {r[side]["digest"][:16]}')
        lines.append('The openings and nonces come with the result, so anyone can check each seal.')
        return '\n'.join(lines)

    def result_post(self, t, r):
        res = r['resolved']
        before, after = res['before'], res['after']
        head = f'AUTOMATAFL "{t["name"]}", round {r["round"]}: '
        if after['winner']:
            side = 'north' if after['winner'] == 1 else 'south'
            head += f'{side.capitalize()} ({self.who(t, side)}) wins: the automaton reached {square(after["automaton"])}.'
        elif after['status'] == 1:
            marked = [square(i) for i in range(W * H) if (after['marks'] >> i) & 1 and not (before['marks'] >> i) & 1]
            head += f'conflict. Nothing moved; {", ".join(marked) or "the contested square"} is marked and may not be named until a round completes. Send new orders.'
        elif after['status'] == 2:
            bad = [s.capitalize() for s in SIDES if not res['valid'][s]]
            head += f'invalid ({", ".join(bad) or "the pair"}). Nothing moved; the automaton stayed. Send new orders.'
        else:
            step = 'stayed' if after['automaton'] == before['automaton'] else \
                f'stepped {square(before["automaton"])} to {square(after["automaton"])}'
            head += f'resolved. The automaton {step}.'
        lines = [head]
        for side in SIDES:
            o = r[side]
            lines.append(f'{side.capitalize()} {self.who(t, side)}: {square(o["source"])} to {square(o["target"])}')
        rb, ra = self.rules.glyphs(before['board']), self.rules.glyphs(after['board'])
        changed = [f'{square(y * W + x)} {ra[y][x]}' for y in range(H) for x in range(W) if rb[y][x] != ra[y][x]]
        if changed:
            lines.append('Squares now: ' + ', '.join(changed))
        lines += ['', self.text_board(ra, after['marks']), self.legend(after)]
        if t['mode'] == 'private':
            lines += ['', f'Openings: each seal is sha256 of the length-framed fields delvetalk.automatafl.commit.v2, {t["object"]}, '
                          f'{r["round"]}, seat, source, target, nonce:'] + \
                [f'{side.capitalize()} {SIDES.index(side)} {r[side]["source"]} {r[side]["target"]} {r[side]["nonce"]}' for side in SIDES]
        if not after['winner']:
            lines += ['', f'Round {r["round"] + 1}: ' + ('orders to ember privately.' if t['mode'] == 'private' else 'reply with your move.')]
        return '\n'.join(lines)

    def rule_posts(self):
        return RULES


RULES = [
    """AUTOMATAFL, rules 1/2 (as the table plays them)

Board 11x11: columns A-K left to right, rows 1-11 top to bottom. Pieces: + attractor, - repulsor, @ the automaton. Nobody owns a piece; either player moves any + or -.

North wins when the automaton enters A1 or K1. South wins when it enters A11 or K11.

Each round both players give one order at the same time: a source square and a target square in the same row or column, as "F10 to F7". Neither square may be the automaton's, or a marked square.

Private table: orders go to the dealer privately. The dealer posts a seal of each (a sha256 digest), opens both together, and posts the result with the openings, so each seal can be checked. The dealer never picks or changes an order.

Conflict: the same source with different targets, or one target from two occupied sources. Nothing moves; the contested square is marked until a round completes; both send new orders.
Invalid: if either order breaks the rules above, the round is void. Nothing moves and the automaton stays.""",
    """AUTOMATAFL, rules 2/2

Moving: both pieces lift at once and slide in a straight line. Any piece on the way or on the target blocks the slide, unless that piece is itself leaving this round; a blocked piece stays. If your target is the other order's source, you take that square as its piece leaves; if that square was empty, your piece rides on to the other target. A straight swap (A to B, B to A) moves nothing. An order from an empty square moves nothing.

Then the automaton steps one square, or stays. It looks along its row and its column at the nearest piece each way:
1. an attractor one way and a repulsor the other: toward the attractor;
2. otherwise a repulsor with only the edge or a farther repulsor behind it: away from the nearer repulsor;
3. otherwise an attractor with only the edge or a farther attractor behind it: toward the nearer attractor.
It steps only into an empty square; a line whose step is blocked gives nothing. Between row and column the higher rule wins, then the nearer deciding piece; a full tie goes to the column (up or down).

A round ends when the automaton has stepped. Then the win is checked.""",
]


# ---- the page

CSS = """
:root { --measure: 64rem; }
.board svg { width: 100%; max-width: 30rem; height: auto; display: block; }
.cols { display: grid; gap: 1rem 2rem; grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); }
textarea.post { font: 13px/1.45 var(--mono); white-space: pre; overflow-x: auto; }
.count { color: var(--muted); font-size: .85rem; }
.copy { margin-left: .5rem; padding: .15rem .6rem; font-size: .8rem; }
.said { padding: .5rem .8rem; border-left: 3px solid var(--terracotta); background: var(--rtint); }
.ok { border-left-color: var(--sage); background: var(--leaf); }
form.seat { border: 1px solid var(--rule); border-radius: 6px; padding: .6rem .9rem; background: var(--leaf); }
form.inline { display: inline; }
table.history td, table.history th { font-size: .85rem; vertical-align: top; padding: .2rem .4rem; }
.mono { font-family: var(--mono); font-size: .8rem; }
"""

COPY_JS = """<script>
for (const b of document.querySelectorAll('button.copy')) {
  b.hidden = false;
  b.addEventListener('click', () => {
    const t = document.getElementById(b.dataset.for);
    navigator.clipboard.writeText(t.value).then(() => { b.textContent = 'copied'; setTimeout(() => b.textContent = 'copy', 1500); });
  });
}
</script>"""


def shell(title, body):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{e(title)}</title><link rel="stylesheet" href="/style.css"><style>{CSS}</style></head><body>'
            f'<header><a class="mark" href="/">Automatafl tables</a><nav><a href="/#rules">rules</a><a href="/#deal">deal</a></nav>'
            f'<span class="who">local; posts nothing</span></header><main>{body}</main>{COPY_JS}</body></html>')


_ids = iter(range(10 ** 9))


def post(title, text):
    """A post ready to copy: a read-only textarea (select-all works without script), its length, a copy button."""
    i = f'p{next(_ids)}'
    over = ' (over the limit)' if len(text) > POST_LIMIT else ''
    return (f'<p><b>{e(title)}</b> <span class="count">{len(text)} / {POST_LIMIT} characters{over}</span>'
            f'<button type="button" class="copy" data-for="{i}" hidden>copy</button></p>'
            f'<textarea class="post" id="{i}" readonly rows="{min(28, text.count(chr(10)) + 2)}">{e(text)}</textarea>')


def svg(rows, marks=0, arrows=()):
    """The board: cells 40 units, labels A-K over the columns and 1-11 beside the rows, goal corners tinted
    (North's top, South's bottom), attractors filled, repulsors rings with a bar, the automaton a diamond, marks crossed."""
    c, o = 40, 28
    out = [f'<svg viewBox="0 0 {o + W * c + 8} {o + H * c + 8}" role="img" aria-label="Automatafl board" '
           f'xmlns="http://www.w3.org/2000/svg" font-family="ui-monospace, Menlo, monospace" font-size="14">',
           '<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
           '<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>']
    for x in range(W):
        out.append(f'<text x="{o + x * c + c / 2}" y="{o - 9}" text-anchor="middle" fill="var(--muted)">{COLUMNS[x]}</text>')
    for y in range(H):
        out.append(f'<text x="{o - 6}" y="{o + y * c + c / 2 + 5}" text-anchor="end" fill="var(--muted)">{y + 1}</text>')
    tint = {i: ('var(--violet)', 'N') for i in GOALS['north']} | {i: ('var(--sage)', 'S') for i in GOALS['south']}
    for y in range(H):
        for x in range(W):
            i, px, py = y * W + x, o + x * c, o + y * c
            fill = 'var(--leaf)'
            out.append(f'<rect x="{px}" y="{py}" width="{c}" height="{c}" fill="{fill}" stroke="var(--rule)"/>')
            if i in tint:
                col, letter = tint[i]
                out.append(f'<rect x="{px + 2}" y="{py + 2}" width="{c - 4}" height="{c - 4}" fill="none" stroke="{col}" stroke-width="3"/>'
                           f'<text x="{px + c - 5}" y="{py + 13}" text-anchor="end" font-size="10" fill="{col}">{letter}</text>')
            g, cx, cy = rows[y][x], px + c / 2, py + c / 2
            if g == '+':
                out.append(f'<circle cx="{cx}" cy="{cy}" r="12" fill="var(--amber)"/><path d="M{cx - 6},{cy}h12M{cx},{cy - 6}v12" stroke="var(--leaf)" stroke-width="3"/>')
            elif g == '-':
                out.append(f'<circle cx="{cx}" cy="{cy}" r="11" fill="none" stroke="var(--silver)" stroke-width="3"/><path d="M{cx - 6},{cy}h12" stroke="var(--silver)" stroke-width="3"/>')
            elif g == '@':
                out.append(f'<path d="M{cx},{cy - 15}L{cx + 15},{cy}L{cx},{cy + 15}L{cx - 15},{cy}z" fill="var(--terracotta)"/>')
            if marks >> i & 1:
                out.append(f'<path d="M{px + 6},{py + 6}L{px + c - 6},{py + c - 6}M{px + c - 6},{py + 6}L{px + 6},{py + c - 6}" stroke="var(--terracotta)" stroke-width="2"/>')
    for (s, t, colour) in arrows:
        x1, y1, x2, y2 = (o + (s % W) * c + c / 2, o + (s // W) * c + c / 2, o + (t % W) * c + c / 2, o + (t // W) * c + c / 2)
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" stroke-width="3" stroke-dasharray="6 4" marker-end="url(#ah)"/>')
    out.append('</svg>')
    return ''.join(out)


def said(message, ok=False):
    return f'<p class="said{" ok" if ok else ""}">{e(message)}</p>' if message else ''


def index_page(d, message=''):
    items = ''.join(f'<li><a href="/t/{quote(n)}">{e(n)}</a></li>' for n in d.names()) or '<li>None yet.</li>'
    rules = ''.join(post(f'Rules {i + 1}/{len(RULES)}', r) for i, r in enumerate(d.rule_posts()))
    body = (f'<h1>Automatafl tables</h1>{said(message)}<h2>Tables</h2><ul>{items}</ul>'
            '<h2 id="deal">Deal a table</h2><form class="seat" method="post" action="/deal">'
            '<label>Name <input name="name" placeholder="trinity-kimi" required pattern="[a-z][a-z0-9-]{0,31}"></label>'
            '<label>North (aims for A1, K1) <input name="north" placeholder="trinity.automata.garden" required></label>'
            '<label>South (aims for A11, K11) <input name="south" placeholder="kimik3.delve.town, or open" required></label>'
            '<label>Mode <select name="mode"><option value="private">private orders: commit and reveal, held by the dealer</option>'
            '<option value="open">open: moves posted publicly</option></select></label>'
            '<p><button>Deal the opening board</button></p></form>'
            f'<h2 id="rules">Rulebook</h2>{rules}')
    return shell('Automatafl tables', body)


def table_page(d, name, message='', ok=False, checking=None):
    s = d.status(name)
    t, g, n = s['custody'], s['game'], s['round']
    r = next((x for x in t['rounds'] if x['round'] == n), None)
    last = next((x for x in sorted(t['rounds'], key=lambda x: -x['round']) if x.get('resolved')), None)
    arrows = [(last[side]['source'], last[side]['target'], c) for side, c in (('north', 'var(--violet)'), ('south', 'var(--sage)'))] if last else []
    seats = ' &middot; '.join(f'{side.capitalize()} <b>{e(d.who(t, side))}</b>' for side in SIDES)
    head = (f'<h1 class="title">{e(name)}<small>{seats} &middot; {e(t["mode"])} orders</small></h1>{said(message, ok)}'
            f'<p>Round <b>{n}</b>. Awaiting <b>{e(s["awaiting"])}</b>. {e(d.rules.outcome(g))}</p>')
    if last:
        head += f'<p>Last: {e(d.result_post(t, last).split(chr(10))[0])}</p>'
    if checking and checking.get('check'):
        head += confirm(t, checking)
        arrows = [(checking['check']['source'], checking['check']['target'], 'var(--glow)')]
    board = (f'<div class="cols"><div class="board">{svg(s["rows"], g["marks"], arrows)}'
             f'<p class="count">dashed arrows: the last round\'s orders, North violet, South green. N and S: the goal corners.</p></div>'
             f'<div>{post("Board post", d.text_board(s["rows"], g["marks"]) + chr(10) + d.legend(g))}</div></div>')
    orders = '' if g['winner'] else f'<h2>Orders for round {n}</h2><div class="cols">{"".join(seat_form(d, t, s, r, side, checking) for side in SIDES)}</div>'
    resolve = ''
    if r and all(r[x] and (r[x].get('commit') or {}).get('status') == 'admitted' for x in SIDES) and not g['winner']:
        if t['mode'] == 'private':
            resolve += post('Sealed post', d.sealed_post(t, r))
        resolve += (f'<form method="post" action="/t/{quote(name)}/resolve"><p><button>Open both and resolve round {n}</button></p></form>')
    posts = post('Opening post', d.opening_post(t))
    if last:
        posts = post(f'Result post, round {last["round"]}', d.result_post(t, last)) + posts
    body = head + board + orders + resolve + '<h2>Posts</h2>' + posts + history(d, t)
    return shell(f'{name}: Automatafl', body)


def seat_form(d, t, s, r, side, checking):
    who = d.who(t, side)
    o = r and r[side]
    if o and (o.get('commit') or {}).get('status') == 'admitted':
        shown = f'<p>Order: <b>{e(o["text"])}</b> ({square(o["source"])} = {o["source"]}, {square(o["target"])} = {o["target"]})</p>' \
            if t['mode'] == 'open' else '<p>Order held in custody.</p>'
        return (f'<div class="seat"><h3>{side.capitalize()} {e(who)}</h3><p>Sealed: sha256 <span class="mono">{o["digest"][:16]}</span>'
                f' at height {o["commit"]["height"]}.</p>{shown}</div>')
    action = f'/t/{quote(t["name"])}'
    what = 'the order the player sent privately' if t['mode'] == 'private' else 'the move as posted'
    by = '' if t['mode'] == 'private' else (f'<label>Posted by <input name="by" value="{e((checking or {}).get("by", ""))}" '
                                             f'placeholder="{e(t["seats"][side] if t["seats"][side] != "open" else "handle")}"></label>')
    text = (checking or {}).get('text', '') if (checking or {}).get('side') == side else ''
    return (f'<div id="{side}"><h3>{side.capitalize()} {e(who)}</h3><form class="seat" method="post" action="{action}/check">'
            f'<input type="hidden" name="side" value="{side}"><label>Paste {what} <input name="text" value="{e(text)}" placeholder="F10 to F7" required></label>'
            f'{by}<p><button>Check</button></p></form></div>')


def confirm(t, checking):
    """The checked order, as the game reads it, with the one button that seals exactly that."""
    c, side = checking['check'], checking['side']
    verdict = ('The game accepts this order.' if c['valid'] else
               'The game will judge this order invalid: the whole round would be void. Ask the player before sealing.')
    return (f'<div class="said{" ok" if c["valid"] else ""}"><p>{side.capitalize()}: &ldquo;{e(c["text"])}&rdquo; reads as <b>{c["from"]} to {c["to"]}</b>: '
            f'source {c["source"]} ({c["holds"]}), target {c["target"]} ({c["onto"]}); the amber arrow. {verdict}</p>'
            f'<form method="post" action="/t/{quote(t["name"])}/seal"><input type="hidden" name="side" value="{side}">'
            f'<input type="hidden" name="text" value="{e(c["text"])}"><input type="hidden" name="by" value="{e(checking.get("by", ""))}">'
            f'<input type="hidden" name="source" value="{c["source"]}"><input type="hidden" name="target" value="{c["target"]}">'
            f'<button>Confirm and seal {side.capitalize()}\'s order</button> <a href="/t/{quote(t["name"])}">not this</a></form></div>')


def short(h):
    return (h or '')[-10:]


def history(d, t):
    rows = []
    for r in sorted(t['rounds'], key=lambda x: x['round']):
        for side in SIDES:
            o = r[side]
            if not o:
                continue
            opened = r.get('resolved') or o.get('reveal')
            move = f'{e(o["text"])} = {o["source"]} to {o["target"]}' if (opened or t['mode'] == 'open') else '(held)'
            receipts = ' '.join(f'{k} {e(str(o[k].get("status")))} h{o[k].get("height")} &hellip;{short(o[k].get("hash"))}'
                                for k in ('commit', 'reveal') if o.get(k))
            nonce = f'<br>nonce <span class="mono">{o["nonce"]}</span>' if opened else ''
            rows.append(f'<tr><td>{r["round"]}</td><td>{side}{" by " + e(o["by"]) if o.get("by") else ""}</td><td>{move}</td>'
                        f'<td class="mono">{o["digest"]}{nonce}</td><td class="mono">{receipts}</td></tr>')
        if r.get('resolved'):
            x = r['resolved']
            a = x['after']
            rows.append(f'<tr><td>{r["round"]}</td><td>table</td><td>{e(x["outcome"])} status {a["status"]}, winner {a["winner"]}, '
                        f'automaton {square(x["before"]["automaton"])} to {square(a["automaton"])}</td><td></td>'
                        f'<td class="mono">resolve h{x["receipt"]["height"]} &hellip;{short(x["receipt"]["hash"])}</td></tr>')
    journal = ''.join(f'<tr><td>{x.get("height")}</td><td>{e(x["object"])}</td><td>{e(str((x.get("identity") or {}).get("principal")))}</td>'
                      f'<td>{e(str((x.get("identity") or {}).get("intent")))}</td><td>{e(str((x.get("outcome") or {}).get("tag")))}</td>'
                      f'<td class="mono">{e(x.get("hash") or "")}</td></tr>' for x in d.journal(t))
    return (f'<h2>History</h2><table class="history"><tr><th>round</th><th>seat</th><th>order</th><th>digest</th><th>receipts</th></tr>'
            f'{"".join(rows) or "<tr><td colspan=5>No orders yet.</td></tr>"}</table>'
            f'<details><summary>The journal of this table and its seats</summary><table class="history">'
            f'<tr><th>height</th><th>object</th><th>principal</th><th>intent</th><th>outcome</th><th>receipt</th></tr>{journal}</table></details>')


class Handler(BaseHTTPRequestHandler):
    """Threaded, so a browser's idle preconnection never holds the page; one lock, so the dealer's steps never interleave."""
    dealer = None  # set on the server's class
    port = None
    timeout = 30
    lock = threading.Lock()

    def do_GET(self):
        with self.lock:
            self.serve_get()

    def do_POST(self):
        with self.lock:
            self.serve_post()

    def log_message(self, *a):
        pass

    def reply(self, code, body, kind='text/html; charset=utf-8', location=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        if location:
            self.send_header('Location', location)
        self.end_headers()
        self.wfile.write(data)

    def local(self):
        """Only this machine's browser at this address: the Host (against rebinding) and, on a POST, the Origin or Referer."""
        ok = {f'127.0.0.1:{self.port}', f'localhost:{self.port}'}
        if self.headers.get('Host') not in ok:
            return False
        if self.command == 'POST':
            origin = self.headers.get('Origin') or self.headers.get('Referer')
            return bool(origin) and urlsplit(origin).netloc in ok
        return True

    def serve_get(self):
        if not self.local():
            return self.reply(403, 'local only')
        path = urlsplit(self.path).path
        q = parse_qs(urlsplit(self.path).query)
        msg = (q.get('said') or [''])[0]
        try:
            if path == '/':
                return self.reply(200, index_page(self.dealer, msg))
            if path == '/style.css':
                return self.reply(200, STYLE.read_bytes(), 'text/css; charset=utf-8')
            m = re.fullmatch(r'/t/([a-z][a-z0-9-]{0,31})', path)
            if m:
                return self.reply(200, table_page(self.dealer, m[1], msg, ok=bool((q.get('ok') or [''])[0])))
        except Refused as x:
            return self.reply(404, index_page(self.dealer, str(x)))
        self.reply(404, 'not found', 'text/plain')

    def serve_post(self):
        if not self.local():
            return self.reply(403, 'local only')
        length = int(self.headers.get('Content-Length') or 0)
        if length > 65536:
            return self.reply(413, 'too long')
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode('utf-8', 'replace')).items()}
        path = urlsplit(self.path).path
        d = self.dealer
        try:
            if path == '/deal':
                d.deal(form.get('name', ''), form.get('north', ''), form.get('south', ''), form.get('mode', 'private'))
                return self.reply(303, '', location=f'/t/{form["name"]}?ok=1&said=' + quote('Dealt. Post the opening and the rules.'))
            m = re.fullmatch(r'/t/([a-z][a-z0-9-]{0,31})/(check|seal|resolve)', path)
            if not m:
                return self.reply(404, 'not found', 'text/plain')
            name, step = m[1], m[2]
            back = f'/t/{name}'
            try:
                if step == 'check':
                    c = d.check(name, form.get('side', ''), form.get('text', ''))
                    return self.reply(200, table_page(d, name, checking={'side': form['side'], 'text': form.get('text', ''),
                                                                          'by': form.get('by', ''), 'check': c}))
                if step == 'seal':
                    side = form.get('side', '')
                    if side not in SIDES:
                        raise Refused('A seat is north or south.')
                    d.seal(name, side, form.get('text', ''), form.get('by', ''), form.get('source'), form.get('target'))
                    return self.reply(303, '', location=f'{back}?ok=1&said=' + quote(f'{side.capitalize()}\'s order is sealed.'))
                d.resolve(name)
                return self.reply(303, '', location=f'{back}?ok=1&said=' + quote('Resolved. The result post is below.'))
            except (Refused, ValueError) as x:
                return self.reply(200, table_page(d, name, str(x), checking={'side': form.get('side'), 'text': form.get('text', ''),
                                                                           'by': form.get('by', '')}))
        except (Refused, ValueError) as x:
            return self.reply(200, index_page(d, str(x)))


def binary(given=None):
    """The host binary: --obend, DELVETALK_OBEND, this checkout's build, the foundation checkout's build."""
    for p in (given, os.environ.get('DELVETALK_OBEND'), ROOT / '.lake' / 'build' / 'bin' / 'delvetalk-obend', FOUNDATION):
        if p and Path(p).exists():
            return str(Path(p).resolve())
    raise SystemExit('tables: no delvetalk-obend; build one with `make build` in the checkout, or name one with --obend')


def command(st, a, out):
    """Start serve over the state, then the page until ^C or SIGTERM; serve is stopped by its PID file on the way out."""
    from deploy.serve import Served
    from transport.host import HostClient
    root = Path(st.root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    pidfile = root / 'tables.pid'
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
            raise SystemExit(f'tables already running over {root} (pid {pidfile.read_text().strip()})')
        except (ProcessLookupError, ValueError):
            pass
    pidfile.write_text(f'{os.getpid()}\n')
    stops = []
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        served = Served(root, binary(a.obend), sync='fsync', cleanup=stops.append)
        rules = Rules(HostClient(served.sock, world=None))
        Handler.dealer = Dealer(HostClient(served.sock, world='town'), rules, root / 'tables', a.dealer)
        Handler.port = a.port
        server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
        out.write(f'tables: http://127.0.0.1:{a.port}/ over {root} (serve pid {served.proc.pid} in {served.pidfile}; this pid {os.getpid()} in {pidfile})\n')
        out.flush()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        for stop in stops:
            stop()
        pidfile.unlink(missing_ok=True)
    return 0
