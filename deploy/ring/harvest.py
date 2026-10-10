#!/usr/bin/env python3
"""One playtest run -> the ring's harvest: the rehearsal's rows, then the ring's own, as Markdown (or one JSON document).
Reads the run directory only: no network, no credentials. It counts and joins; it judges nothing (docs/RING-OF-FIRE.md 5, 6).

    python3 deploy/ring/harvest.py --run ~/.delvetalk-playtest/current [--cast ~/.ring] [--json]
"""
import argparse
import collections
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rehearsal.rehearse import journal_stats  # noqa: E402

ARCS = {'garden': ('plant', 'rain', 'cistern'), 'workshop': ('check', 'propose', 'adopt'), 'rooms': ('enter', 'choose', 'leave')}
SPELL = re.compile(r'^\s*delvetalk\s+([\w:./-]+)\s+(\S+)', re.M)
CARD = re.compile(r'\b(?:garden|workshop|tide|anthology|rooms|directory|commons|play|env|wake)(?:/[\w:.-]+)+\b|\b(?:GARDEN|ROOMS|WORKSHOP|TIDE|ANTHOLOGY|STUDIO)\b')
FENCE = re.compile(r'```obend')


def when(stamp):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()


def jsonl(path):
    rows = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def observations(state):
    if not (state / 'observe.sqlite').exists():
        return []
    db = sqlite3.connect(state / 'observe.sqlite')
    try:
        return [json.loads(js) for (js,) in db.execute('SELECT json FROM observations ORDER BY seq')]
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


def harvest(run, cast_root=None):
    run, state = Path(run).resolve(), Path(run).resolve() / 'state'
    journal = next((p for p in (run / 'world.journal', state / 'world.journal') if p.exists()), None)
    entries, tags, classes, reasons = journal_stats(journal) if journal else ([], collections.Counter(), collections.Counter(), {})
    by_intent = {(e.get('identity') or {}).get('intent'): e for e in entries}
    obs = observations(state)
    drafts = [json.loads(p.read_text()) for p in sorted((state / 'outbox').glob('*.json'))] if (state / 'outbox').exists() else []
    interp = [json.loads(p.read_text()) for p in (state / 'interpretations').glob('*.json')] if (state / 'interpretations').exists() else []
    awaiting = {json.loads(p.read_text())['uri'] for p in (state / 'awaiting').glob('*.json')} if (state / 'awaiting').exists() else set()
    steps, spend, hand = jsonl(run / 'bridge.log'), jsonl(state / 'model-spend.jsonl'), jsonl(state / 'hand-log.jsonl')
    front = jsonl(run / 'front.log')
    roles = {c['handle'].lower(): c for c in (json.loads(p.read_text()) for p in Path(cast_root).glob('*/cast.json'))} if cast_root else {}
    r = {'run': str(run), 'observed': dict(collections.Counter(o['kind'] for o in obs)), 'journal': {
        'height': len(entries), 'bytes': journal.stat().st_size if journal else 0, 'outcomes': dict(tags), 'refusedByClass': dict(classes),
        'medianSuspendedBytes': getattr(journal_stats, 'sizes', {}).get('suspended', {}).get('median', 0)}}
    r['refusals'] = [{'class': c, **it} for c, items in reasons.items() for it in items]
    r['drafts'] = {'total': len(drafts), 'posted': sum(1 for d in drafts if d.get('posted')), 'skipped': sum(1 for d in drafts if d.get('skipped')),
                   'usage': sum(1 for d in drafts if d.get('usage')), 'offerless': sum(1 for d in drafts if not d.get('text') and not d.get('usage')),
                   'over1400': sum(1 for d in drafts if len(d.get('text') or '') > 1400),
                   'refusedWithoutVoice': sum(1 for d in drafts if d.get('text') and (d.get('receipt') or {}).get('outcome', {}).get('tag') == 'refused'
                                              and not d['text'].startswith('refused '))}
    held = [h for s in steps for h in s.get('held') or []]
    r['bridge'] = {'steps': len(steps), 'held': dict(collections.Counter(h.get('reason') for h in held)),
                   'failed': [f for s in steps for f in s.get('failed') or []]}
    r['interpretations'] = {'files': len(interp), 'settled': sum(1 for i in interp if i.get('settled')), 'pending': sum(1 for i in interp if not i.get('settled')),
                            'retried': sum(1 for i in interp if i.get('attempts', 1) > 1), 'modelFailed': sum(1 for i in interp if (i.get('reply') or {}).get('status') == 'failed')}
    r['spend'] = {'calls': len(spend), 'inputTokens': sum(x.get('inputTokens') or 0 for x in spend), 'outputTokens': sum(x.get('outputTokens') or 0 for x in spend)}
    r['hand'] = dict(collections.Counter(h.get('what') for h in hand))
    r['front'] = {'requests': len(front), 'status500': sum(1 for x in front if x.get('code') == 500), 'logged': bool(front)}
    answered = {d['replyTo'] for d in drafts if d.get('text') or d.get('usage')}
    addressed = [o for o in obs if o['kind'] in ('spell', 'summon') or 'delvetalk' in o['text'].lower()]
    r['noReply'] = [o['uri'] for o in addressed if o['uri'] not in answered and o['uri'] not in awaiting]
    # The ring's own rows, by handle (section 5).
    by_handle = collections.defaultdict(list)
    for o in obs:
        by_handle[o['author']['handle']].append(o)
    quoted, drafted_cards = collections.Counter(), set()
    for d in drafts:
        drafted_cards.update(CARD.findall(d.get('text') or ''))
    people, arcs = {}, {a: {'step': 0, 'by': None, 'offBrief': False, 'steps': []} for a in ARCS}
    for handle, mine in by_handle.items():
        mine.sort(key=lambda o: (o['createdAt'], o['uri']))
        role = roles.get(handle.lower(), {})
        hours = collections.Counter(o['createdAt'][:13] for o in mine)
        outcomes = [(o, by_intent.get(o['uri'])) for o in mine]
        refused = [((e.get('outcome') or {}).get('class'), (e.get('outcome') or {}).get('clause')) for _, e in outcomes if e and (e.get('outcome') or {}).get('tag') == 'refused']
        # A spell is a `delvetalk` line, as the host reads it; the observer's `kind` misses spells on child cards (garden/bell/1).
        first_spell = next((o for o, e in outcomes if SPELL.search(o['text']) and e and (e.get('outcome') or {}).get('tag') == 'admitted'), None)
        before = [o for o in mine if first_spell and o['createdAt'] < first_spell['createdAt']]
        for o in mine:
            quoted.update(CARD.findall(o['text']))
        spells = sum(1 for o in mine if SPELL.search(o['text']))
        people[handle] = {'role': role.get('role'), 'posts': len(mine), 'spells': spells, 'prose': len(mine) - spells, 'maxPerHour': max(hours.values()),
                          'usage': sum(1 for d in drafts if d.get('usage') and d.get('replyHandle') == handle),
                          'obend': sum(1 for o in mine if FENCE.search(o['text'])),
                          'refused': dict(collections.Counter(c for c, _ in refused)),
                          'recurring': [list(k) for k, n in collections.Counter(refused).items() if n > 1],
                          'minutesToFirstSpell': round((when(first_spell['createdAt']) - when(mine[0]['createdAt'])) / 60, 1) if first_spell else None,
                          'refusalsBeforeFirstSpell': sum(1 for o in before if (by_intent.get(o['uri']) or {}).get('outcome', {}).get('tag') == 'refused')}
        for o, e in outcomes:
            m = SPELL.search(o['text'])
            if not m or not e or (e.get('outcome') or {}).get('tag') != 'admitted':
                continue
            card, action = m.group(1).split('/')[0], m.group(2)
            if card in ARCS and action in ARCS[card]:
                step = ARCS[card].index(action) + 1
                told = card in (role.get('arcs') or '').split(',')
                arcs[card]['steps'].append({'step': step, 'action': action, 'by': handle, 'told': told, 'at': o['createdAt']})
                if step > arcs[card]['step']:
                    arcs[card].update(step=step, by=handle, offBrief=not told)
    r['people'], r['arcs'] = people, arcs
    r['cards'] = {'quoted': dict(quoted.most_common()), 'draftedNeverQuoted': sorted(drafted_cards - set(quoted))}
    return r


def markdown(r):
    out = [f"Run `{r['run']}`.\n", '| Measure | Count |', '| --- | --- |']
    w = out.append
    for k, v in r['observed'].items():
        w(f'| observed as `{k}` | {v} |')
    j = r['journal']
    for k, v in j['outcomes'].items():
        w(f'| journal `{k}` entries | {v} |')
    for k, v in sorted(j['refusedByClass'].items()):
        w(f'| refused `{k}` | {v} |')
    for k, v in r['drafts'].items():
        w(f'| drafts {k} | {v} |')
    for k, v in r['bridge']['held'].items():
        w(f'| drafts held `{k}` | {v} |')
    w(f"| bridge steps, failed | {r['bridge']['steps']}, {len(r['bridge']['failed'])} |")
    for k, v in r['interpretations'].items():
        w(f'| interpretations {k} | {v} |')
    w(f"| model calls, input, output tokens | {r['spend']['calls']}, {r['spend']['inputTokens']:,}, {r['spend']['outputTokens']:,} |")
    w(f"| hand actions | {r['hand'] or 'none'} |")
    w(f"| front requests logged, HTTP 500 | {r['front']['requests'] if r['front']['logged'] else 'not logged'}, {r['front']['status500'] if r['front']['logged'] else 'unread'} |")
    w(f"| addressed posts with no reply | {len(r['noReply'])} |")
    w(f"| journal height, bytes, median suspended | {j['height']}, {j['bytes']:,}, {j['medianSuspendedBytes']:,} |\n")
    w('### By principal\n')
    w('| Handle | Role | Posts | Spells | Prose | Max/hour | `?` | obend | Refused | Recurring | Minutes to first spell | Refusals before |')
    w('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for h, p in sorted(r['people'].items()):
        w(f"| {h} | {p['role'] or ''} | {p['posts']} | {p['spells']} | {p['prose']} | {p['maxPerHour']} | {p['usage']} | {p['obend']} | {p['refused'] or ''} | {p['recurring'] or ''} | {p['minutesToFirstSpell'] if p['minutesToFirstSpell'] is not None else 'none'} | {p['refusalsBeforeFirstSpell']} |")
    w('\n### Arcs\n\n| Arc | Furthest step | By | Off brief | Steps |\n| --- | --- | --- | --- | --- |')
    for a, v in r['arcs'].items():
        w(f"| {a} | {v['step']} of {len(ARCS[a])} ({ARCS[a][v['step'] - 1] if v['step'] else 'none'}) | {v['by'] or ''} | {v['offBrief']} | {', '.join(s['action'] + ' by ' + s['by'] for s in v['steps'])} |")
    w('\n### Cards quoted\n')
    w(', '.join(f'{c} {n}' for c, n in r['cards']['quoted'].items()) or 'none')
    w('\nDrafted and never quoted: ' + (', '.join(r['cards']['draftedNeverQuoted']) or 'none') + '\n')
    w('### Refusals\n')
    for x in r['refusals']:
        w(f"- `{x['class']}` {x['intent']}: {x['reason']}")
    w('\n### No reply\n')
    for u in r['noReply']:
        w(f'- {u}')
    return '\n'.join(out) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(prog='harvest.py')
    ap.add_argument('--run', required=True)
    ap.add_argument('--cast', metavar='ROOT', help="cast.sh's --state: joins handles to roles and arcs")
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    r = harvest(a.run, a.cast)
    sys.stdout.write(json.dumps(r, indent=1, ensure_ascii=False) + '\n' if a.json else markdown(r))
    return 0


if __name__ == '__main__':
    sys.exit(main())
