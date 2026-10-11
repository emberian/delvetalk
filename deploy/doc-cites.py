#!/usr/bin/env python3
"""Check every path and file:line cited in docs/ (and README.md) against the tree.

A cite is a markdown link target, or a backticked token that looks like a path (has a '/' or a known
extension), optionally followed by :N, :N-M or :N,M,... A path resolves if it exists relative to the
repository root, to the citing document's directory, or (bare file names and short tails) to a unique
file of that name or tail in the tree. A line cite is false when the file is shorter than the line.
Output: per document, the unresolved paths and the line cites past the end, then totals.
usage: python3 deploy/doc-cites.py . [doc ...]  (a measurement: it exits 0 and decides nothing)"""
import os, re, sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
EXT = r'(?:md|py|lean|obend|txt|json|sh|html|css|c|h|yml|yaml|toml|cbor|service|timer|js|key)'
TOK = re.compile(r'`([^`\s]+?)`')
LINK = re.compile(r'\]\(([^)\s#]+)(?:#[^)]*)?\)')
BARE = re.compile(r'(?<![\w/.`-])((?:[\w.-]+/)*[\w.-]+\.(?:lean|obend|py|md|txt|c|sh|json|html|css):\d[\d,\-]*)')
PATHLIKE = re.compile(r'^(?:\.\./|\./)?[A-Za-z0-9_.\-/{}*<>]+\.' + EXT + r'(?::[0-9][0-9,\-~ ]*)?$|^(?:\.\./|\./)?[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?(?::[0-9][0-9,\-]*)?$')
SKIP = re.compile(r'[<>{}*]|^https?:|^at://|^did:|^/AGENTS|^/xrpc|^/o/|^/play|^/world|^/receipt|^/scratch|^/etc/|^/var/|^/run/|^/data|^~|^\$|^hbox:|^zulip:|^kind/|^garden/|^porch/|^bell/|^rooms/|^env/|^wake/|^lamp/|^sealed/|^moss/|^room/|^anthology/|^deal/|^town\.delvetalk|^lane/|^refs/|^origin/|^\.\.\.|^DIR/|^J\.|^text/|^application/')

index = {}
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in ('.git', '.lake', 'node_modules', '__pycache__')]
    for f in fns + dns:
        rel = os.path.relpath(os.path.join(dp, f), ROOT)
        index.setdefault(f, []).append(rel)
allpaths = set(p for v in index.values() for p in v)

def resolve(path, doc):
    p = path.rstrip('/')
    for base in (ROOT, doc.parent):
        if (base / p).exists():
            return base / p
    tail = p.lstrip('./')
    hits = [q for q in allpaths if q == tail or q.endswith('/' + tail)]
    if hits:
        return ROOT / sorted(hits, key=len)[0]
    return None

def lines_of(f):
    try:
        return sum(1 for _ in open(f, 'rb'))
    except (IsADirectoryError, OSError):
        return None

docs = [Path(a) for a in sys.argv[2:]] or sorted(list((ROOT / 'docs').rglob('*.md')) + [ROOT / 'README.md'])
tot_cites = tot_bad = tot_lines = tot_badlines = 0
for doc in docs:
    text = doc.read_text()
    cites = set(LINK.findall(text)) | {t for t in TOK.findall(text) if PATHLIKE.match(t)} | {b.rstrip(',-') for b in BARE.findall(text)}
    bad, badlines, n = [], [], 0
    for c in sorted(cites):
        if SKIP.search(c.split(':')[0]):
            continue
        path, _, lines = c.partition(':')
        if not path or path.startswith('-'):
            continue
        n += 1
        f = resolve(path, doc)
        if f is None:
            bad.append(c)
            continue
        if lines:
            tot_lines += 1
            nums = [int(x) for x in re.findall(r'\d+', lines)]
            have = lines_of(f)
            if have is not None and nums and max(nums) > have:
                badlines.append(f'{c} (file has {have} lines)')
    tot_cites += n; tot_bad += len(bad); tot_badlines += len(badlines)
    rel = doc.relative_to(ROOT)
    print(f'{rel}: {n} path cites, {len(bad)} unresolved, {len(badlines)} line cites past the end')
    for b in bad:
        print(f'  unresolved: {b}')
    for b in badlines:
        print(f'  past end:   {b}')
print(f'TOTAL: {tot_cites} path cites in {len(docs)} documents; {tot_bad} unresolved; {tot_lines} with a line, {tot_badlines} past the end')
