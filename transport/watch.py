"""The probe and the watch (docs/OPERATIONS.md section b). `status` prints one probe of a world, plain numbers, or with
`--health` answers a compose healthcheck by its exit status; `watch` probes, appends the probe to the world's watch log
(the history the hour-long thresholds read) and posts one Zulip line per crossed threshold, at most once per condition
per six hours, the host unhealthy and a failed backup verify hourly. deploy/watch.sh runs it every five minutes.
"""
import calendar
import json
import os
import re
import shutil
import time
import urllib.request
from pathlib import Path

from transport import journal as chain, model
from transport.bridge import all_observations

DEDUPE, URGENT = 6 * 3600, 3600  # seconds between two lines for one condition; for the two that page


def probe(st, host, clock=time.time):
    """Every number a threshold reads: the front's 5xx, the host's hour, the model's spend, reservations, interpretations,
    the journal, the clock, the backups and the disks."""
    now, status, c = clock(), host.send({'op': 'world-status'}), st.config
    rows = [l.split() for p in (st.access_log.with_name(st.access_log.name + '.1'), st.access_log) if p.exists() for l in p.read_text().splitlines()]
    when = lambda x: calendar.timegm(time.strptime(x[0], '%Y-%m-%dT%H:%M:%SZ'))
    recent = lambda secs: [x for x in rows if len(x) >= 4 and now - when(x) < secs]
    waiting = host.send({'op': 'world-interpretations'}).get('pending') or []
    # The newest 4,000 entries are enough for a median: each weighs its record in the block store.
    sizes = sorted(e['bytes'] for e in chain.tail(st.journal, 4000) if (e.get('outcome') or {}).get('tag') == 'suspended')
    backups = Path(c.backups)
    tars = sorted(backups.glob('delvetalk-*.tar.gz')) if backups.is_dir() else []
    verify = (backups / 'last-verify').read_text().split() if (backups / 'last-verify').exists() else []
    disk = {str(p): round(shutil.disk_usage(p).free / shutil.disk_usage(p).total, 3) for p in (st.root, backups) if p.exists()}
    return {'at': int(now), 'world': st.world,
            'front': {'requests5m': len(recent(300)), '5xx5m': sum(1 for x in recent(300) if x[3].startswith('5')),
                      '5xxHour': sum(1 for x in recent(3600) if x[3].startswith('5'))},
            'hour': status.get('hour'), 'model': {'hour': model.spent(st, now - 3600)['all'], 'day': model.spent(st, now - 86400)['all']},
            'reservations': next((s for s in (status.get('posts') or {}).get('sources') or [] if s.get('source') == 'delve'), {}),
            'interpretations': {'pending': len(waiting), 'maxAttempts': max([p.get('attempts') or 0 for p in waiting] or [0])},
            'journal': {'height': status.get('height'), 'bytes': chain.size(st.journal) if st.journal.exists() else None,
                        'medianSuspendedBytes': sizes[len(sizes) // 2] if sizes else None},
            'clock': {'world': status.get('clock'), 'behindMinutes': int(now // 60) - (status.get('clock') or 0)},
            'observed': len(all_observations(st)),
            'backup': {'newest': tars[-1].name if tars else None, 'ageSeconds': int(now - tars[-1].stat().st_mtime) if tars else None,
                       'verify': verify[0] if verify else None},
            'freeFraction': disk}


def healthy(st, service):
    """The compose healthcheck of each long-running service: the host answers its journal height; the front serves the
    guide and a home page showing `entry <n>` (the height, from the host); a daemon finished a step within three polls."""
    if service == 'host':
        return isinstance(st.host().send({'op': 'world-status'}).get('height'), int)
    if service == 'http':
        base = f'http://127.0.0.1:{st.config.http_port}'
        urllib.request.urlopen(base + '/AGENTS.md', timeout=5).read()
        return bool(re.search(rb'class=.code.>entry [0-9]+<', urllib.request.urlopen(base + '/', timeout=30).read()))
    pidfile = st.pidfile(service)
    os.kill(int(pidfile.read_text()), 0)
    return time.time() - pidfile.stat().st_mtime <= 3 * st.config.poll


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


def status(st, a, out):
    """`status`: one probe as JSON, or with `--health SERVICE` the exit status of its healthcheck."""
    if a.health:
        try:
            return 0 if healthy(st, a.health) else 1
        except (OSError, ValueError):
            return 1
    host = st.host()
    try:
        out.write(json.dumps(probe(st, host), indent=1, sort_keys=True) + '\n')
    finally:
        host.close()
    return 0


def watch(st, a, out, send=None):
    """`watch`: probe, remember, and post what crossed a threshold to the watch's stream."""
    host = st.host()
    try:
        p = probe(st, host)
    finally:
        host.close()
    history = [json.loads(l) for l in st.watch_log.read_text().splitlines()[-48:]] if st.watch_log.exists() else []  # four hours at five minutes
    alerted = json.loads(st.alerted.read_text()) if st.alerted.exists() else {}
    lines = [(k, line + (f' (playbook {book})' if book else '')) for k, line, book in conditions(p, history, a.unhealthy) if due(alerted, k, p['at'])]
    if a.dry_run:
        out.write(''.join(l + '\n' for _, l in lines))
        return 0
    st.append(st.watch_log, json.dumps(p, sort_keys=True))
    if lines:
        if send is None:
            from transport.zulip import Client
            client, c = Client(st.config.watch_zuliprc), st.config
            send = lambda text: client.send(c.watch_stream, c.watch_topic, text)
        for key, line in lines:
            send(line)
            alerted[key] = p['at']
        st.write(st.alerted, alerted)
    out.write(f'watch: {len(lines)} line(s) sent\n')
    return 0
