#!/usr/bin/env python3
"""The watch: one probe (`transport.hand status --json`) against the thresholds of docs/OPERATIONS.md section b, one
Zulip line per crossed threshold, at most once per condition per six hours; the host unhealthy and a failed backup verify
repeat hourly. Every probe is appended to <state>/watch.jsonl, which is also the history the hour-long thresholds read.

    python3 -m deploy.watch --state /data/state --probe probe.json --zuliprc RC [--stream delvetalk-ops --topic watch]
        [--unhealthy SERVICE ...] [--dry-run]

deploy/watch.sh runs it every five minutes from deploy/delvetalk-watch.timer (docs/DEPLOY.md "Watching").
"""
import argparse
import json
import sys
from pathlib import Path

DEDUPE, URGENT = 6 * 3600, 3600  # seconds between two lines for one condition; for the two that page


def conditions(p, history, unhealthy=()):
    """[(condition, line, playbook)] for every threshold the probe crosses. `history` is the earlier probes, oldest first."""
    out, hour = [], p.get('hour') or {}
    refused, turns = hour.get('refused') or {}, hour.get('turns') or 0
    add = lambda key, line, book: out.append((key, line, book))
    if unhealthy:
        add('unhealthy', f"unhealthy: {', '.join(unhealthy)}", 'A')
    if p['front']['5xx5m']:
        add('5xx', f"the front answered {p['front']['5xx5m']} 5xx in five minutes", 'A')
    if refused.get('capacity'):
        add('capacity', f"{refused['capacity']} refused capacity ({hour.get('window', 'this hour')})", '')
    if refused.get('quota', 0) > 5:
        add('quota', f"{refused['quota']} refused quota ({hour.get('window', 'this hour')})", 'D')
    if turns and refused.get('staleRoot', 0) > turns / 10:
        add('staleRoot', f"{refused['staleRoot']} of {turns} turns refused staleRoot", '')
    if p['model']['hour']['calls'] > 120:
        add('model', f"{p['model']['hour']['calls']} model calls in the last hour (${p['model']['hour']['dollars']})", 'D')
    r = p.get('reservations') or {}
    held = [q for q in history if p['at'] - q['at'] <= 7200]
    if r.get('quota') and r.get('used', 0) >= r['quota'] and held and p['at'] - held[0]['at'] >= 7000 and \
            all((q.get('reservations') or {}).get('used', 0) >= r['quota'] for q in held):
        add('reservations', f"{r['used']} of {r['quota']} posts reserved for two hours", 'D')
    before = next((q for q in reversed(history) if p['at'] - q['at'] >= 3600), None)
    if before and before['journal']['height'] == p['journal']['height'] and p['observed'] > before['observed']:
        add('stalled', f"journal height {p['journal']['height']} for an hour while {p['observed'] - before['observed']} posts were observed", 'A')
    if (p['journal']['bytes'] or 0) > 200 << 20:
        add('journal', f"the journal is {p['journal']['bytes'] >> 20} MiB", 'F')
    if (p['journal']['medianSuspendedBytes'] or 0) > 8192:
        add('suspension', f"the median suspension is {p['journal']['medianSuspendedBytes']} bytes", '')
    if p['clock']['behindMinutes'] > 3:
        add('clock', f"the clock is {p['clock']['behindMinutes']} minutes behind: the bridge is not ticking", 'A')
    i = p['interpretations']
    if i['pending'] > 20 or i['maxAttempts'] >= 8:
        add('interpretations', f"{i['pending']} interpretations pending, the oldest at attempt {i['maxAttempts']}", 'C')
    b = p['backup']
    if b['verify'] != 'ok' or b['ageSeconds'] is None or b['ageSeconds'] > 7 * 3600:
        add('backup', f"backup: last verify {b['verify'] or 'never'}, newest {b['newest'] or 'none'}"
            + (f", {b['ageSeconds'] // 3600} h old" if b['ageSeconds'] is not None else ''), 'F')
    for where, free in (p.get('freeFraction') or {}).items():
        if free < 0.2:
            add('disk:' + where, f'{where} is {round((1 - free) * 100)}% full', 'F')
    return out


def due(alerted, key, now):
    return now - alerted.get(key, 0) >= (URGENT if key in ('unhealthy', 'backup') else DEDUPE)


def main(argv=None, out=None, send=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='watch.py')
    ap.add_argument('--state', required=True)
    ap.add_argument('--probe', required=True, help='the JSON `transport.hand status --json` printed')
    ap.add_argument('--zuliprc', help="the bot's .zuliprc the lines are posted with")
    ap.add_argument('--stream', default='delvetalk-ops')
    ap.add_argument('--topic', default='watch')
    ap.add_argument('--unhealthy', nargs='*', default=[], metavar='SERVICE', help='compose services not running or unhealthy')
    ap.add_argument('--dry-run', action='store_true', help='print the lines; post nothing, remember nothing')
    a = ap.parse_args(argv)
    state = Path(a.state)
    probe = json.loads(Path(a.probe).read_text())
    log, mark = state / 'watch.jsonl', state / 'alerted.json'
    history = [json.loads(l) for l in log.read_text().splitlines()[-48:]] if log.exists() else []  # four hours at five minutes
    alerted = json.loads(mark.read_text()) if mark.exists() else {}
    lines = [(k, line + (f' (playbook {book})' if book else '')) for k, line, book in conditions(probe, history, a.unhealthy) if due(alerted, k, probe['at'])]
    if a.dry_run:
        out.write(''.join(l + '\n' for _, l in lines))
        return 0
    with open(log, 'a') as f:
        f.write(json.dumps(probe, sort_keys=True) + '\n')
    if lines:
        if send is None:
            from transport.zulip import Client
            client = Client(a.zuliprc)
            send = lambda text: client.send(a.stream, a.topic, text)
        for key, line in lines:
            send(line)
            alerted[key] = probe['at']
        mark.write_text(json.dumps(alerted, sort_keys=True) + '\n')
    out.write(f'watch: {len(lines)} line(s) sent\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
