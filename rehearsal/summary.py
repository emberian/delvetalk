#!/usr/bin/env python3
"""results.json from rehearsal/rehearse.py -> the measured half of REPORT.md, as Markdown."""
import collections
import json
import sys

BRIDGED = ('summon',)


def plain(v):
    """A host value as plain JSON: a record a dict, a list or a relation (`rows`) a list, a label or number its value."""
    if not isinstance(v, dict):
        return v
    tag = v.get('tag')
    if tag == 'record':
        return {f['name']: plain(f['value']) for f in v['fields']}
    if tag == 'list':
        return [plain(x) for x in v['items']]
    if tag == 'variant':
        if v.get('label') == 'rows':
            return plain(v['payload']).get('items', [])
        inner = plain(v.get('payload'))
        return v['label'] if inner in ({}, None) else {v['label']: inner}
    if tag in ('label', 'natural', 'integer', 'bool'):
        return v.get('value')
    return v


def fence(text):
    return '```\n' + (text or '').rstrip('\n') + '\n```\n'


def main(path):
    r = json.load(open(path))
    obs, j = r['observations'], r['journal']
    recorded = {x['uri']: x['object'] for x in r['recorded'] if x['status'] == 'posted'}
    out = []
    w = out.append
    w(f"Archive: {r['posts']} distinct posts, {r['first']} to {r['last']}. Wall time {r['wallSeconds']} s on hbox.\n")
    kinds = collections.Counter(o['kind'] for o in obs.values())
    considered = [u for u, o in obs.items() if o['kind'] in BRIDGED or o['replyTo']]
    routed_recorded = [u for u in considered if obs[u]['replyTo'] in recorded]
    routed_root = [u for u in considered if obs[u]['replyTo'] not in recorded and obs[u].get('root') in recorded]
    w('\n| Measure | Count |\n| --- | --- |')
    for k in ('summon', 'reply', 'post', 'wiki-page', 'wiki-edit', 'wiki-merge'):
        w(f'| observed as `{k}` | {kinds.get(k, 0)} |')
    w(f"| considered by the bridge (spell, summon, or any reply) | {len(considered)} |")
    w(f"| ... routed by reply address (parent recorded as posted) | {len(routed_recorded)} |")
    w(f"| ... routed by thread root (root recorded as posted) | {len(routed_root)} |")
    w(f"| ... skipped (no addressee, no card word) | {r['skipped']} |")
    w(f"| never considered (top-level non-spell, non-summon posts) | {len(obs) - len(considered)} |")
    outcomes = j['outcomes']
    turns = sum(outcomes.get(k, 0) for k in ('admitted', 'refused', 'suspended'))
    w(f"| turns run (journal entries admitted + refused + suspended) | {turns} |")
    for k in ('admitted', 'refused', 'suspended', 'interpreted', 'created', 'posted', 'advanced', 'settings'):
        w(f"| journal `{k}` entries | {outcomes.get(k, 0)} |")
    for cls, n in sorted(j['refusedByClass'].items()):
        w(f'| refused `{cls}` | {n} |')
    if 'reached' in r:
        asked = r.get('asked') or {}
        w(f"| archived posts the reach rule returned (a turn at a card) | {len(r['reached'])} |")
        w(f"| ... of them asked of the model | {sum(1 for u in r['reached'] if u in asked)} |")
        w(f"| posts asked of the model twice or more; asked but never reached | {sum(1 for n in asked.values() if n > 1)}; {sum(1 for u in asked if u not in r['reached'])} |")
    for v, n in sorted((r.get('verdicts') or {}).items()):
        w(f"| interpretation verdict `{v}` | {n} |")
    w(f"| outbox drafts | {len(r['drafts'])} |")
    w(f"| turns that offered nothing (no draft) | {r.get('offerless', 0)} |")
    stranded = [o for o in r.get('hostOffers', []) if not o['drafted']]
    w(f"| offers the host holds that no draft carries | {len(stranded)} |")
    w(f"| drafts over 1,400 characters | {sum(1 for d in r['drafts'] if d['chars'] > 1400)} |")
    w(f"| pending deliveries at the end | {r['pendingDeliveries'].get('count')} |")
    w(f"| interpretations still pending at the end | {len(r['interpretationsLeft'].get('pending') or [])} |")
    w(f"| journal height | {j['height']} |")
    w(f"| journal bytes | {j['bytes']:,} |")
    w(f"| journal SHA-256 | `{j.get('sha256')}` |")
    for tag, b in sorted((j.get('bytesByOutcome') or {}).items(), key=lambda kv: -kv[1]['bytes']):
        w(f"| ... `{tag}` entries: count, bytes, largest, median | {b['count']}, {b['bytes']:,}, {b['max']:,}, {b.get('median', 0):,} |")
    for obj, b in sorted((j.get('suspendedByObject') or {}).items(), key=lambda kv: -kv[1]['bytes']):
        w(f"| ... suspended on `{obj}`: count, bytes, first, largest, median | {b['count']}, {b['bytes']:,}, {b['first']:,}, {b['max']:,}, {b['median']:,} |")
    w(f"| snapshots | {len(r['snapshots'])} {r['snapshots']} |")
    w(f"| objects | {r['status'].get('objects')} |")
    w(f"| clock at the end (unix minutes) | {r['status'].get('clock')} |\n")
    w('Recorded as posted: ' + ', '.join(f"`{x['uri'].rsplit('/', 1)[-1]}` for {x['object']} ({x['status']})" for x in r['recorded'])
      + '. Planting posts recorded for their bells: ' + (', '.join(f"`{(x['uri'] or '-').rsplit('/', 1)[-1]}` ({x.get('createdAt', '?')[11:16]}) for {x['object']} at {x.get('recordedAt', '?')[11:16]} ({x['status']})" for x in r.get('plantings') or []) or 'none') + '.\n')
    made = r.get('made') or {}
    w(f"Made by kind/bell: {', '.join(made.get('kind/bell') or []) or 'none'}. By kind/cistern: {', '.join(made.get('kind/cistern') or []) or 'none'}.\n")
    a = r.get('anthology')
    if a:
        w('The anthology\'s lines (`n`, author, text; admitted by the keeper or not):\n')
        for line in a['lines']:
            w(f"- #{line['n']} {line.get('handle') or line['author']}: {line['text']}{' (admitted)' if int(line['n']) in a['admitted'] else ''}")
        w('')

    w('### Drafts by recipient\n')
    by = collections.Counter(d['to'] for d in r['drafts'])
    w(', '.join(f'{h} {n}' for h, n in by.most_common()) + '\n')
    w('### Drafts by text\n')
    texts = collections.defaultdict(list)
    for d in r['drafts']:
        key = d['text'].split('receipt:')[0]
        texts[key].append(d)
    w('| Draft (first line) | Count | Characters |\n| --- | --- | --- |')
    for key, ds in sorted(texts.items(), key=lambda kv: -len(kv[1])):
        first = key.strip().split('\n')[0]
        w(f"| {first} ... | {len(ds)} | {ds[0]['chars']} |")
    w('')

    if r.get('gate'):
        w('### The section 10 hour, post by post\n')
        w('| Post | Step | Entries (outcome, class, objects written) | First offer |\n| --- | --- | --- | --- |')
        for g in r['gate']:
            ents = '; '.join(f"{e['tag']}{' ' + e['class'] if e['class'] else ''}{' (' + e['reason'] + ')' if e['reason'] else ''} at {e.get('to')}{' by reply address' if e.get('replyTo') else ''}{', wrote ' + ','.join(x for x in e['writes'] if x) if any(e['writes']) else ''}".strip() for e in g['entries']) or 'no turn'
            offer = next((o for e in g['entries'] for o in e['offers'] if o), '')
            w(f"| `{g['uri'].rsplit('/', 1)[-1]}` | {g['step']} | {ents} | {offer.strip().replace(chr(10), ' / ')[:160]} |")
        w('')
        for obj, v in (r.get('views') or {}).items():
            w(f"- `{obj}` v{v['version']}: `{json.dumps(plain(v['state']), ensure_ascii=False)[:400]}`")
        w('')
    w('### Host errors and Python exceptions, verbatim\n')
    seen = set()
    for e in r['errors']:
        key = json.dumps({k: v for k, v in e.items() if k not in ('object', 'principal', 'what')}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        n = sum(1 for x in r['errors'] if json.dumps({k: v for k, v in x.items() if k not in ('object', 'principal', 'what')}, sort_keys=True) == key)
        w(f"- {e['kind']} ({n}x; first: {e.get('object') or e.get('uri') or e.get('post') or e.get('what')}): `{json.dumps(e.get('reply') or e.get('message') or e.get('stderr'), ensure_ascii=False)}`")
    w('')

    w('### Refusals\n')
    for cls, items in j['refusals'].items():
        for it in items:
            w(f"- `{cls}` {it['intent']}: {it['reason']}")
    w('')

    w('### Offers held by the host but never drafted\n')
    for o in stranded:
        w(f"- height {o['height']}, to {o['principal']}, answering {o['intent']}:")
        w(fence(o['text']))

    w('### Spell shapes against a copy of the final world\n')
    w('| To | Shape | Status | Reply |\n| --- | --- | --- | --- |')
    for g in r.get('grammar', []):
        said = ' / '.join(t.strip().split('\n')[0] + ('; ' + t.strip().split('\n')[2] if len(t.strip().split('\n')) > 2 else '') for t in g['offers'] if t) or g['reason'] or (g.get('usage') or '').strip().replace('\n', ' / ') or ('public: ' + json.dumps(g['public']) if g.get('public') else json.dumps(g['result']))
        w(f"| {g['object']} | {g['what']} | {g['status']}{' ' + g['class'] if g['class'] else ''} | {said[:160]} |")
    w('')
    b = r.get('burst')
    if b:
        w('### Burst probe: nine prose plantings to the garden in one poll\n')
        w('First pass: ' + ', '.join(f"{f['status']}{' ' + f['class'] if f['class'] else ''}" for f in b['first']) + '.')
        w(f"Settled {len(b['settled'])}: " + ', '.join(sorted({json.dumps(s['verdict'])[:80] for s in b['settled']})) + '.')
        w(f"Retried after capacity: {b['retried']}. Final outcomes: " + ', '.join(f"{f['outcome']}{' ' + f['class'] if f['class'] else ''}" for f in b['final']) + '.')
        offers = [f['offer'] for f in b['final'] if f['offer']]
        if offers:
            w('A resumed offer:\n')
            w(fence(offers[0]))
        w('')
    h = r.get('handle')
    if h:
        w('### Handle probe\n')
        w(f"world-principal: {h['recorded']}; plant: {h['status']}; the offer names the handle: {h['showsHandle']}; a DID fragment: {h['showsFragment']}.\n")
        w(fence(h['offer']))
    sr = r.get('snapshotReplay')
    if sr:
        w('### Replay from a snapshot\n')
        w(f"A copy of the journal ({sr['height']} entries, {sr['objects']} objects, {sr['versions']} object versions) reopened "
          f"with no snapshot ({sr['straight']['seconds']} s), against each reopen below: same means the same height, head, "
          f"clock, posts, pending work, and every object's state CID at every version, pin, law and readings.\n")
        w('| Reopen | Snapshot written (opened at) | Resumed; refused | Seconds | Same | Differs | Host stderr |\n| --- | --- | --- | --- | --- | --- | --- |')
        for name, c in sr['cases'].items():
            wr = c.get('written') or {}
            snap = c.get('snapshot') or {}
            refused = '; '.join(f"{x.get('height')}: {x.get('reason')}" for x in snap.get('refused') or []) or 'none'
            w(f"| {name} | {wr.get('height', '-')} ({wr.get('openedAt', '-')}) | {snap.get('resumed')}; {refused} | {c['seconds']} | "
              f"{c['same']} | {', '.join(c['differs'][:6]) or '-'}{' …' if len(c['differs']) > 6 else ''} | {(c.get('stderr') or '-')[:90].replace(chr(10), ' ')} |")
        w('')
    w('### Cards at the end\n')
    for obj, c in r['cards'].items():
        w(f"**{obj}** ({c['status']}, {c['chars']} characters)\n")
        w(fence(c['text'] or c['clause']))
    return '\n'.join(out)


if __name__ == '__main__':
    print(main(sys.argv[1]))
