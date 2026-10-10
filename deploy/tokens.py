#!/usr/bin/env python3
"""What DelveTalk costs a model agent in tokens: a measurement, not a decision (docs/TOKENS.md reads its output).

Two halves. `capture` runs where the host binary runs (stdlib only): it drives deploy/capture-examples.py's four
sessions over a real stack with nothing cut, records each reply's wire bytes, then reads every card the town holds,
a usage block, refusals and the plain-text view of an object page. The other modes need the toks package
(~/src/toks/python) and tokenizer files, given as NAME=PATH (a tokenizer.json, or a directory holding one or a
tiktoken.model); they count with `encode_ordinary`, so no BOS, template or chat wrapping is counted.

  python3 deploy/tokens.py capture --root . --binary $DELVETALK_OBEND --out cap.json
  python3 deploy/tokens.py table   --tok glm53=tok/glm53 ... --capture cap.json [--offering old.json]
  python3 deploy/tokens.py ledger  --tok ... --capture cap.json [--offering old.json]
  python3 deploy/tokens.py glyphs  --tok ...
  python3 deploy/tokens.py lexicon --tok ... --capture cap.json --map lexicon.json [--map ...]
  python3 deploy/tokens.py --compare A B --tok ...      (A, B: files, or literal text with --literal)

Every number printed is a count of the texts named beside it; nothing here chooses a spelling.
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---- capture (stdlib only) ------------------------------------------------------------------------------------------

def capture(root, binary, out):
    """The examples' sessions, uncut, plus every card and a few refusals; -> [{n, section, method, path, body, status, wire}]."""
    import http.client
    import importlib.util
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location('capture_examples', root / 'deploy' / 'capture-examples.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.CUT = 10 ** 12
    log, last = [], []
    read = http.client.HTTPResponse.read

    def reading(self, *a, **k):
        data = read(self, *a, **k)
        last.append(data)
        return data
    http.client.HTTPResponse.read = reading
    fetch = m.Capture.fetch

    def fetching(self, method, href, body=None, token=None):
        last.clear()
        status, reply = fetch(self, method, href, body, token)
        section = next((line[3:] for line in reversed(self.out) if line.startswith('## ')), '')
        log.append({'n': len(log) + 1, 'section': section, 'method': method, 'path': href, 'body': body,
                    'status': status, 'wire': b''.join(last).decode('utf-8', 'replace')})
        return status, reply
    m.Capture.fetch = fetching
    login = m.Capture.login

    def logging_in(self, handle):  # a proof post is consumed once, so the town section reuses each session's credential
        did = login(self, handle)
        self.tokens = {**getattr(self, 'tokens', {}), handle: self.token}
        return did
    m.Capture.login = logging_in
    stranger = m.stranger

    def stranger_then_town(cap):
        stranger(cap)
        cap.plain = []
        extras(m, cap)
        for e in cap.plain:
            log.append({'n': len(log) + 1, **e})
    m.stranger = stranger_then_town
    m.main(['--out', str(Path(out).with_suffix('.md')), '--binary', binary])
    Path(out).write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(f'{len(log)} replies, {sum(len(e["wire"].encode()) for e in log):,} wire bytes -> {out}', file=sys.stderr)


def extras(m, cap):
    """The town's other cards, read after the four sessions (section `town`)."""
    from deploy.genesis import lab, lst, rec, ref
    from deploy.seed import create
    from transport.hostproc import HostClient
    cap.say('## town')
    made = create(HostClient(cap.sock), m.OPENER, 'yard', 'Place', 'tokens-yard',
                  rec(owner=lab(m.OPENER), name=lab('The moss yard'), description=lab('A quiet yard behind the gate.'),
                      exits=lst(rec(label=lab('garden'), to=ref('garden')))))
    print('place:', made.get('status'), made.get('message') or '', file=sys.stderr)
    moth = m.PEOPLE['moth.delve.town']
    cap.token = cap.tokens['moth.delve.town']
    for obj in ('directory', 'garden', 'garden/bell/1', 'tide', 'anthology', 'workshop', 'rooms', 'commons', 'cistern',
                'policy', 'play', 'yard', f'env/{moth}', f'wake/{moth}', moth):
        cap.step('GET', f'/world/{obj}/card')
    cap.step('GET', '/world/directory')
    for href in ('/world/garden?text=1', '/world/garden/bell/1?text=1', ''):
        plain(cap, '/AGENTS.md' + href)
    cap.step('POST', '/world/garden/receive', {'intent': 'usage-1', 'spell': 'delvetalk garden ?'})
    cap.step('POST', '/world/garden/receive', {'intent': 'bad-1', 'spell': 'delvetalk garden plant\ncolour: green\nseed: a moss bell'})
    cap.step('POST', '/world/tide/receive', {'intent': 'tick-1', 'spell': 'delvetalk tide tick'})
    cap.step('POST', '/world/tide/receive', {'intent': 'tick-2', 'spell': 'delvetalk tide tick'})
    cap.token = cap.tokens['owl.delve.town']
    cap.step('POST', '/world/garden/bell/1/receive', {'intent': 'strike-1', 'spell': 'delvetalk garden/bell/1 strike'})
    cap.step('GET', '/api')


def plain(cap, href):
    """A reply that is not JSON (the plain-text view, the guide), recorded as it came."""
    import http.client
    c = http.client.HTTPConnection('127.0.0.1', cap.port, timeout=60)
    c.request('GET', href, None, {'Authorization': 'Bearer ' + cap.token})
    r = c.getresponse()
    got = r.read()
    c.close()
    cap.plain.append({'section': 'town', 'method': 'GET', 'path': href, 'body': None, 'status': r.status,
                      'wire': got.decode('utf-8', 'replace')})


# ---- counting -------------------------------------------------------------------------------------------------------

def load(specs):
    import toks
    out = {}
    for spec in specs:
        name, _, path = spec.partition('=')
        out[name] = toks.Tokenizer.from_file(path)
    return out


try:
    import regex
    def graphemes(s): return len(regex.findall(r'\X', s))
except ImportError:  # the capture side never counts
    def graphemes(s): return len(s)


def count(tok, text):
    return len(tok.encode_ordinary(text)) if text else 0


def row(label, text, toks_):
    b = len(text.encode())
    return [label, b, graphemes(text)] + [count(t, text) for t in toks_.values()]


def show(rows, toks_, head='text', ratio=False):
    names = list(toks_)
    w = max([len(head)] + [len(str(r[0])) for r in rows])
    cols = ['bytes', 'graph'] + names
    print(f'{head:<{w}}  ' + '  '.join(f'{c:>8}' for c in cols))
    for r in rows:
        print(f'{r[0]:<{w}}  ' + '  '.join(f'{v:>8,}' if isinstance(v, int) else f'{v:>8}' for v in r[1:]))
        if ratio and r[1]:
            print(f'{"  tokens/byte":<{w}}  {"":>8}  {"":>8}  ' + '  '.join(f'{v / r[1]:>8.3f}' for v in r[3:]))


# ---- the texts ------------------------------------------------------------------------------------------------------

def read_capture(path):
    return json.loads(Path(path).read_text()) if path else []


def pick(cap, section=None, method=None, path=None, intent=None, nth=0):
    hits = [e for e in cap if (section is None or e['section'].startswith(section)) and (method is None or e['method'] == method)
            and (path is None or (re.fullmatch(path, e['path']))) and (intent is None or (e['body'] or {}).get('intent') == intent)]
    return hits[nth] if -len(hits) <= nth < len(hits) else None


def field(entry, *keys):
    if not entry:
        return ''
    v = json.loads(entry['wire'])
    for k in keys:
        v = v.get(k, '') if isinstance(v, dict) else ''
    return v if isinstance(v, str) else json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def without(entry, *keys):
    """The wire reply with some top-level keys dropped, re-serialized as the front does (canonical)."""
    v = json.loads(entry['wire'])
    return json.dumps({k: x for k, x in v.items() if k not in keys}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def welcome():
    w = (ROOT / 'docs' / 'previews' / 'gsb-welcome-v4.txt').read_text()
    return w, w.split('--- (the clipped')[0]


def posts():
    return [p['record']['text'] for p in json.loads((ROOT / 'rehearsal' / 'fixtures' / 'posts.json').read_text())]


CARDS = ('directory', 'garden', 'garden/bell/1', 'tide', 'anthology', 'workshop', 'rooms', 'commons', 'cistern', 'policy', 'play', 'yard')


def town_cards(cap):
    """{label: card text} for every card read in the `town` section (the avatar, env and wake by kind)."""
    out = {}
    for e in cap:
        mt = re.fullmatch(r'/AGENTS\.md/world/(.+)/card', e['path'])
        if e['section'] == 'town' and mt and e['status'] == 200:
            obj = mt.group(1)
            label = 'env' if obj.startswith('env/') else 'wake' if obj.startswith('wake/') else 'avatar' if obj.startswith('did:') else \
                'place' if obj == 'yard' else 'bell' if '/bell/' in obj else obj
            out[label] = field(e, 'text')
    return out


def texts(cap):
    """[(label, text)]: the set docs/TOKENS.md measures."""
    whole, clipped = welcome()
    out = [('welcome v4 (whole)', whole), ('welcome v4 (before clip)', clipped),
           ('root menu v2', (ROOT / 'docs' / 'previews' / 'gsb-root-menu-v2.txt').read_text())]
    out += [(f'capsule {p.stem}', p.read_text()) for p in sorted((ROOT / 'capsules').glob('*.txt'))]
    out += [(f'card {k}', v) for k, v in town_cards(cap).items()]
    plant = pick(cap, 'A planter', 'POST', r'.*/garden/receive', 'plant-1')
    if plant:
        out += [('a DID', field(pick(cap, 'A planter', 'POST', r'.*/verify'), 'did')),
                ('a CID (receipt hash)', field(pick(cap, 'A planter', 'GET', r'.*/receipt/plant-1'), 'receipt', 'hash'))]
        out += [('receipt line', field(plant, 'line')), ('receipt slug', field(plant, 'receipt', 'slug')),
                ('turn reply (wire)', plant['wire'])]
    page = (ROOT / 'docs' / 'AGENTS-EXAMPLES.md').read_text().split('\n')
    shown = next((page[i + 1].strip()[4:] for i, l in enumerate(page) if '"intent": "plant-1"' in l and '/receive' in l), '')
    out.append(('turn reply (examples page)', shown))
    e = pick(cap, 'town', 'POST', None, 'bad-1')
    if e:
        out += [('refusal line (badSpell)', field(e, 'line')), ('refusal reply (wire)', e['wire'])]
    e = pick(cap, 'A forger', 'POST', None, 'propose-2')
    if e:
        out.append(('held line (workshop propose)', (json.loads(e['wire']).get('offers') or [''])[0].split('\n')[0]))
    e = pick(cap, 'town', 'POST', None, 'usage-1')
    if e:
        out.append(('usage block (garden ?)', field(e, 'text') or field(e, 'line')))
    for label, path in (('object page text (garden)', r'.*/world/garden\?text=1'), ('object page text (bell)', r'.*/garden/bell/1\?text=1')):
        e = pick(cap, 'town', 'GET', path)
        if e:
            out.append((label, e['wire']))
    return out


# ---- the ledger: OFFERING section 2's units -------------------------------------------------------------------------

def units(cap):
    """[(unit, text it needs, reply it gets)] by the same selection OFFERING section 2 made, on this capture."""
    u = []
    whole, clipped = welcome()
    u.append(('welcome (v4)', clipped, whole))
    d = pick(cap, 'town', 'GET', r'.*/world/directory/card')
    dobj = pick(cap, 'town', 'GET', r'.*/world/directory')
    u.append(('root menu', field(d, 'text'), dobj['wire'] if dobj else ''))
    g = pick(cap, 'A planter', 'GET', r'.*/world/garden/card')
    u.append(('card: garden, 0 planted', field(g, 'text'), g['wire'] if g else ''))
    b = pick(cap, 'A planter', 'GET', r'.*/garden/bell/1/card')
    u.append(('card: bell', field(b, 'text'), b['wire'] if b else ''))
    w0, w1 = pick(cap, 'A wake', 'GET', r'.*/wake/.*/card', nth=0), pick(cap, 'A wake', 'GET', r'.*/wake/.*/card', nth=-1)
    u.append(('card: own wake (first)', field(w0, 'text'), w0['wire'] if w0 else ''))
    u.append(('card: own wake (last)', field(w1, 'text'), w1['wire'] if w1 else ''))
    sp = pick(cap, 'A stranger', 'POST', r'.*/world/garden/plant')
    sr = pick(cap, 'A stranger', 'GET', r'.*/receipt/[a-z]+-[a-z]+')
    u.append(('receipt: planting, by slug', field(sp, 'line') or field(sp, 'status'), sr['wire'] if sr else ''))
    u.append(('receipt: its slug', field(sp, 'receipt', 'slug'), ''))
    hb = pick(cap, 'A forger', 'POST', r'.*/heap/world/tally/bump')
    u.append(('receipt: heap bump', field(hb, 'line') or field(hb, 'status'), hb['wire'] if hb else ''))
    ck = next((e for e in cap if e['section'].startswith('A forger') and e['path'].endswith('/check') and 'hint' in e['wire']), None)
    u.append(('refusal: check', field(ck, 'hint'), ck['wire'] if ck else ''))
    tk = pick(cap, 'town', 'POST', None, 'bad-1')
    u.append(('refusal: turn (badSpell)', field(tk, 'line'), tk['wire'] if tk else ''))
    us = pick(cap, 'town', 'POST', None, 'usage-1')
    u.append(('usage block (garden ?)', field(us, 'text') or field(us, 'line'), us['wire'] if us else ''))
    s, o = pick(cap, 'A planter', 'POST', None, 'plant-3'), pick(cap, 'A planter', 'GET', r'.*/offers\?after=\d+')
    u.append(('interpretation round trip', field(o, 'offers'), (s['wire'] if s else '') + (o['wire'] if o else '')))
    p1 = pick(cap, 'A planter', 'POST', None, 'plant-1')
    u.append(('planting by spell', field(p1, 'offers'), p1['wire'] if p1 else ''))
    bs = pick(cap, 'A forger', 'GET', r'.*/garden/bell/\d+/source')
    ws = pick(cap, 'A wake', 'GET', r'.*/wake/.*/source')
    u.append(('source: bell', field(bs, 'law'), bs['wire'] if bs else ''))
    u.append(('source: wake', field(ws, 'law'), ws['wire'] if ws else ''))
    api = pick(cap, 'A forger', 'GET', r'/AGENTS\.md/api') or pick(cap, None, 'GET', r'/AGENTS\.md/api')
    u.append(('catalogue /api', '', api['wire'] if api else ''))
    wl = pick(cap, 'A planter', 'GET', r'/AGENTS\.md/world')
    u.append(('world listing', ' '.join(json.loads(wl['wire']).get('ids', [])) if wl else '', wl['wire'] if wl else ''))
    walk = [e for e in cap if e['section'].startswith('A stranger')]
    u.append((f'stranger walk ({len(walk)} replies)', '', ''.join(e['wire'] for e in walk)))
    return u


def actions_share(cap, toks_):
    """Tokens of `_actions` on each card/object reply of the sessions, against the whole reply."""
    rows = []
    for e in cap:
        if e['status'] != 200 or e['section'] == 'town' or not e['wire'].startswith('{'):
            continue
        v = json.loads(e['wire'])
        if '_actions' in v:
            a = json.dumps(v['_actions'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            rows.append((e['n'], e['path'].replace('/AGENTS.md', ''), a, e['wire']))
    return rows


# ---- glyphs ---------------------------------------------------------------------------------------------------------

STAMPS = [('●', 'admitted'), ('§', 'refused'), ('…', 'suspended'), ('—', 'quiet')]
MARKS = [('⁕', 'thing'), ('✾', 'garden'), ('⚘', 'bell'), ('❦', 'env'), ('☙', 'wake'), ('❧', 'tide'), ('✤', 'deal'),
         ('❁', 'rooms'), ('✿', 'place'), ('❃', 'thing'), ('❋', 'anthology'), ('✥', 'workshop'), ('❖', 'directory')]
PUNCT = [('»', 'next'), ('⟲', 'again'), ('·', 'and')]
CJK = [('雨', 'rain'), ('鐘', 'bell'), ('園', 'garden'), ('潮', 'tide'), ('門', 'door'), ('書', 'book'), ('火', 'fire'),
       ('水', 'water'), ('待', 'wait'), ('拒', 'refuse'), ('許', 'admit'), ('見', 'see'), ('聽', 'hear'), ('言', 'say'),
       ('人', 'person'), ('家', 'home'), ('時', 'time'), ('數', 'count'), ('新', 'new'), ('舊', 'old')]
EMOJI = [('🌧', 'rain'), ('🔔', 'bell'), ('🌱', 'garden'), ('🌊', 'tide'), ('🚪', 'door'), ('📖', 'book'), ('🔥', 'fire'),
         ('💧', 'water'), ('⏳', 'wait'), ('🚫', 'refuse'), ('✅', 'admit'), ('👀', 'see'), ('👂', 'hear'), ('💬', 'say'),
         ('👤', 'person'), ('🏠', 'home'), ('⏰', 'time'), ('🔢', 'count'), ('🆕', 'new'), ('📜', 'old')]
CARRIER = ('Reply on its', ' to act.')


def marginal(tok, s):
    """Tokens the string adds in running English: `Reply on its <s> to act.` less `Reply on its to act.`"""
    a, b = CARRIER
    return count(tok, f'{a} {s}{b}') - count(tok, a + b)


def at_line_start(tok, s):
    """Tokens the string adds at the head of a line, before a word: `ok\\n<s> GARDEN` less `ok\\nGARDEN`."""
    return count(tok, f'ok\n{s} GARDEN') - count(tok, 'ok\nGARDEN')


def glyphs(toks_):
    names = list(toks_)
    print('Each cell: bare / after a space / marginal in "Reply on its _ to act." (tokens). Word columns are the English word.')
    print(f'{"glyph":<6} {"word":<10}  ' + '  '.join(f'{n:>15}' for n in names))
    wins = {n: [0, 0, 0] for n in names}  # glyph cheaper, equal, dearer (marginal)
    for group, items in (('stamp', STAMPS), ('mark', MARKS), ('punct', PUNCT), ('cjk', CJK), ('emoji', EMOJI)):
        print(f'-- {group}')
        for g, w in items:
            cg = [(count(t, g), count(t, ' ' + g), marginal(t, g)) for t in toks_.values()]
            cw = [(count(t, w), count(t, ' ' + w), marginal(t, w)) for t in toks_.values()]
            print(f'{g:<6} {"":<10}  ' + '  '.join(f'{f"{x}/{y}/{z}":>15}' for x, y, z in cg))
            print(f'{"":<6} {w:<10}  ' + '  '.join(f'{f"{x}/{y}/{z}":>15}' for x, y, z in cw))
            for n, (a, b) in zip(names, zip(cg, cw)):
                wins[n][0 if a[2] < b[2] else 1 if a[2] == b[2] else 2] += 1
    print('-- marginal tokens, glyph vs word: cheaper / equal / dearer, over all pairs')
    for n, (c, e, d) in wins.items():
        print(f'{n:<14} {c:>3} / {e:>3} / {d:>3}')
    print('-- as the head mark of a line, tokens added before "GARDEN" (where the cards and the welcome put them)')
    print(f'{"glyph":<6}  ' + '  '.join(f'{n:>8}' for n in names))
    for g, _ in STAMPS + MARKS + PUNCT + CJK[:4] + EMOJI[:4]:
        print(f'{g:<6}  ' + '  '.join(f'{at_line_start(t, g):>8}' for t in toks_.values()))
    print('-- per group, summed marginal tokens: glyphs vs words')
    print(f'{"group":<6}  ' + '  '.join(f'{n:>15}' for n in names))
    for group, items in (('stamp', STAMPS), ('mark', MARKS), ('punct', PUNCT), ('cjk', CJK), ('emoji', EMOJI)):
        cells = [f'{sum(marginal(t, g) for g, _ in items)}/{sum(marginal(t, w) for _, w in items)}' for t in toks_.values()]
        print(f'{group:<6}  ' + '  '.join(f'{c:>15}' for c in cells))


# ---- a lexicon applied to the cards ---------------------------------------------------------------------------------

SPELL = re.compile(r'delvetalk [^\n/;,.]*(?:/ [^\n]*)?|<[^>\n]*>|`[^`\n]*`|“[^”]*”')


def relexicon(text, mapping, raw=False):
    """Words of the card's prose become symbols; a spell, a blank, a quoted seed or code span stays as the grammar reads it
    (raw: everywhere, the spells too, as a change of grammar would)."""
    pat = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, mapping), key=len, reverse=True)) + r')\b', re.I)
    if raw:
        return pat.sub(lambda w: mapping.get(w.group(0), mapping.get(w.group(0).lower(), w.group(0))), text)
    out, at = [], 0
    for m in SPELL.finditer(text):
        out.append(pat.sub(lambda w: mapping.get(w.group(0), mapping.get(w.group(0).lower(), w.group(0))), text[at:m.start()]))
        out.append(m.group(0))
        at = m.end()
    out.append(pat.sub(lambda w: mapping.get(w.group(0), mapping.get(w.group(0).lower(), w.group(0))), text[at:]))
    return ''.join(out)


def teaching(mapping):
    """The welcome's one line that teaches the lexicon: `✾ garden · ⚘ bell · …`."""
    seen, pairs = set(), []
    for w, g in mapping.items():
        if g not in seen:
            seen.add(g)
            pairs.append(f'{g} {w.lower()}')
    return 'symbols: ' + ' · '.join(pairs) + '\n'


def lexicon(toks_, cap, maps, show_cards=False, raw=False):
    cards = town_cards(cap)
    for path in maps:
        mapping = json.loads(Path(path).read_text())
        teach = teaching(mapping)
        print(f'== {Path(path).name}: {len(set(mapping.values()))} symbols for {len(mapping)} words; the teaching line is {len(teach.encode())} B')
        print(f'   {teach.strip()}')
        print(f'{"tokenizer":<14} {"teach":>6} {"median before":>14} {"median after":>13} {"saved/card":>11} {"mean saved":>11} {"break-even N":>13} {"cards changed":>14}')
        for n, t in toks_.items():
            before = {k: count(t, v) for k, v in cards.items()}
            after = {k: count(t, relexicon(v, mapping, raw)) for k, v in cards.items()}
            mb, ma = statistics.median(before.values()), statistics.median(after.values())
            saved = statistics.mean(before[k] - after[k] for k in cards)
            changed = sum(1 for k in cards if relexicon(cards[k], mapping, raw) != cards[k])
            tc = count(t, teach)
            be = f'{tc / saved:,.1f}' if saved > 0 else 'never'
            print(f'{n:<14} {tc:>6} {mb:>14} {ma:>13} {mb - ma:>11} {saved:>11.2f} {be:>13} {changed:>9}/{len(cards)}')
        if show_cards:
            for k, v in cards.items():
                r = relexicon(v, mapping, raw)
                if r != v:
                    print(f'--- {k}\n{r}')


# ---- main -----------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog='tokens.py', description=__doc__.split('\n')[0])
    ap.add_argument('mode', nargs='?', default='table', choices=('capture', 'table', 'ledger', 'glyphs', 'lexicon'))
    ap.add_argument('--tok', action='append', default=[], metavar='NAME=PATH')
    ap.add_argument('--capture', help="a capture's JSON (this tree's stack)")
    ap.add_argument('--offering', help="a capture's JSON at the tree OFFERING section 2 measured (3a0cd75)")
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'), help='two spellings of one card: files, or text with --literal')
    ap.add_argument('--literal', action='store_true')
    ap.add_argument('--map', action='append', default=[], help='lexicon mode: a JSON {word: symbol}')
    ap.add_argument('--show', action='store_true', help='lexicon mode: print each rewritten card')
    ap.add_argument('--raw', action='store_true', help='lexicon mode: rewrite inside spells too (a grammar change)')
    ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--binary')
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    if a.mode == 'capture':
        return capture(a.root, a.binary, a.out) or 0
    toks_ = load(a.tok)
    if a.compare:
        x, y = (s if a.literal else Path(s).read_text() for s in a.compare)
        rows = [row('A', x, toks_), row('B', y, toks_)]
        rows.append(['B - A'] + [q - p for p, q in zip(rows[0][1:], rows[1][1:])])
        show(rows, toks_, 'spelling')
        return 0
    cap = read_capture(a.capture)
    if a.mode == 'table':
        show([row(k, v, toks_) for k, v in texts(cap)], toks_)
        ps = posts()
        print(f'-- the {len(ps):,} town posts (rehearsal/fixtures/posts.json)')
        per = {n: sorted(count(t, p) for p in ps) for n, t in toks_.items()}
        b = sorted(len(p.encode()) for p in ps)
        for stat, f in (('median', statistics.median), ('mean', lambda xs: round(statistics.mean(xs), 1)),
                        ('p90', lambda xs: xs[int(len(xs) * 0.9)]), ('total', sum)):
            print(f'{"posts " + stat:<26}  {f(b):>8,}  {"":>8}  ' + '  '.join(f'{f(v):>8,}' for v in per.values()))
        print(f'{"posts tokens/byte":<26}  {"":>8}  {"":>8}  ' + '  '.join(f'{sum(v) / sum(b):>8.3f}' for v in per.values()))
    elif a.mode == 'ledger':
        for label, path in (('this tree', a.capture), ('OFFERING tree (3a0cd75)', a.offering)):
            if not path:
                continue
            print(f'== {label}: {path}')
            rows = []
            for unit, need, got in units(read_capture(path)):
                rows.append(row(unit + ' | needs', need, toks_))
                if got:
                    rows.append(row(unit + ' | gets', got, toks_))
            show(rows, toks_, 'unit', ratio=True)
            print(f'-- _actions on each session reply ({label}): tokens of _actions / tokens of the reply')
            for n_, path_, act, wire in actions_share(read_capture(path), toks_):
                print(f'#{n_:<3} {path_[:44]:<44} ' + '  '.join(f'{count(t, act):>5}/{count(t, wire):<6}' for t in toks_.values()))
    elif a.mode == 'glyphs':
        glyphs(toks_)
    elif a.mode == 'lexicon':
        lexicon(toks_, cap, a.map, a.show, a.raw)
    return 0


if __name__ == '__main__':
    sys.exit(main())
