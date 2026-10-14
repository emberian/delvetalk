"""The hand's overview of a town (`/hand/<world>/overview`, `hand overview`): who arrived in the last day and how they
stand, the busiest hands by turns, the refusals by class in the last hour and day, what the day's budgets have spent,
the moderation as it stands (slow, quiets, flags, held arrivals, the hand's last acts), what waits for the town's own
hand (`Hand.requests`: lines pending on the records it keeps, proposals held for its things) and the newest feed posts.

Read only. Its sources are the journal (a turn's wall time is the world's clock at it: the bridge advances the clock to
unix minutes, so an entry is placed by the `advanced` entry before it), the identity store (how each guest came in and
how it stands), the hand's log (who the owner let in or turned away), the feed's store, and `world-status` (the host's
own counts: this clock hour's refusals, hob's readings and the paints of the clock day). The journals of its carried chain
are read once whole (`ancestors`), the world's own then only its new entries; the rows older than a day are let go, the
quiets kept.
"""
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path

from transport import automod, journal, model
from transport.host import CLOCK
from transport.measure import counted

HOUR, DAY = 60, 1440  # clock minutes
BUSIEST, FEED, ACTS, REQUESTS = 10, 10, 12, 12  # rows shown


CHAIN = 32  # journals a carried chain is followed back through, at most


def ancestors(path):
    """The journals the world at `path` was carried from, oldest first: each carried genesis's `carriedFrom.world`, as
    it is given (the host's `/towns/vN/state/town.journal`, which the hand mounts at the same path) or beside the journal,
    while it is on this disk (transport/carry.py; the host's `Carry.givenMakings` follows it the same way)."""
    out, at, seen = [], Path(path), set()
    for _ in range(CHAIN):
        links = journal.links(at)
        if not links:
            break
        genesis = journal.read(at, links[:1])[0]
        origin = (genesis.get('outcome') or {}).get('carriedFrom') if (genesis.get('outcome') or {}).get('tag') == 'carried' else None
        world = origin.get('world') if isinstance(origin, dict) and isinstance(origin.get('world'), str) else None
        found = next((p for p in (Path(world), at.parent / world) if p.exists()), None) if world else None
        if found is None or found.resolve() in seen:
            break
        seen.add(found.resolve())
        out.insert(0, found)
        at = found
    return out


class Ledger:
    """A world's rows of the last day across its carried chain (`ancestors`: obend 10-14, the overview read only the
    journal since the 09:00 carry and said nobody had arrived), kept across calls: (height, clock, principal, tag, class,
    direct), the principals' handles as their arrivals named them, every arrival of the day, and the quiets as they
    stand. An ancestor is read once, whole; the world's own journal, then only its new entries."""

    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()
        self.reset()

    def reset(self):
        self.first, self.height, self.clock, self.chain = None, 0, 0, []
        self.rows, self.arrivals, self.names, self.quiets = [], [], {}, {}

    def read(self):
        with self.lock:
            links = journal.links(self.path)
            if not links:
                self.reset()
                return self
            if self.first != links[0]['hash'] or links[-1]['height'] < self.height:  # a new journal (a carry): start again
                self.reset()
                self.first = links[0]['hash']
                self.chain = ancestors(self.path)
                for old in self.chain:
                    for x in journal.entries(old):
                        if x.get('height', 0) < links[0]['height']:  # the world's own journal from its genesis on
                            self.take(x)
            fresh = [link for link in links if link['height'] > self.height]
            for n in range(0, len(fresh), 512):
                for x in journal.read(self.path, fresh[n:n + 512]):
                    self.take(x)
            self.height = links[-1]['height']
            keep = self.clock - DAY
            self.rows = [r for r in self.rows if r[1] >= keep]
            self.arrivals = [a for a in self.arrivals if a['clock'] >= keep]
            return self

    def take(self, x):
        out, who = x.get('outcome') or {}, (x.get('identity') or {}).get('principal')
        tag = out.get('tag')
        if tag == 'advanced':
            self.clock = max(self.clock, out.get('to') or 0)
        elif tag in ('carried', 'forked'):
            self.clock = max(self.clock, (out.get('state') or {}).get('clock') or 0)
        if tag == 'principal' and out.get('did'):
            self.names[out['did']] = out.get('handle') or out['did']
            self.arrivals.append({'did': out['did'], 'handle': out.get('handle') or out['did'], 'clock': self.clock, 'height': x.get('height')})
        quiet = quiet_of(out)
        if quiet:
            principal, until, reading = quiet
            if until:
                self.quiets[principal] = {'until': until, 'reading': reading, 'height': x.get('height')}
            else:
                self.quiets.pop(principal, None)
        self.rows.append((x.get('height'), self.clock, who, tag, out.get('class'), 'delivery' not in x))


def quiet_of(out):
    """(principal, until or None, reading) when an outcome sets or lifts a quiet: the `quiet` power (moderated) or root's
    `quiet` act; None otherwise."""
    if not ((out.get('tag') == 'moderated' and out.get('power') in ('quiet', 'unquiet')) or (out.get('tag') == 'root' and out.get('kind') == 'quiet')):
        return None
    after = out.get('after') if isinstance(out.get('after'), dict) else {}
    until = after.get('until') if out.get('power') != 'unquiet' else None
    return out.get('principal'), until or None, after.get('reading') or out.get('reading') or out.get('reason') or ''


_ledgers, _made = {}, threading.Lock()


def ledger(st):
    with _made:
        got = _ledgers.setdefault(str(st.journal), Ledger(st.journal))
    return got.read()


def feed_posts(st, n=FEED):
    """The feed's newest posts, the town's own replies with them, read only (no feed: none)."""
    path = st.home / 'feed.sqlite'
    if not path.exists():
        return []
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
    try:
        rows = db.execute('SELECT handle, created, text, town, parent FROM feed ORDER BY seq DESC LIMIT ?', (n,)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        db.close()
    return [{'handle': h, 'created': c, 'text': t, 'town': bool(town), 'reply': bool(parent)} for h, c, t, town, parent in rows]


def overview(h):
    """The overview of `h`'s world (h a transport.hand.Hand) as plain data."""
    st, c = h.st, h.st.config
    status = h.host.send({'op': 'world-status'})
    led = ledger(st)
    now = status.get('clock') or led.clock
    staff = {h.owner, CLOCK, 'world', *c.owner_principals.split()}
    guests = h.guests() if st.identity.exists() else []
    by_principal = {g['principal']: g for g in guests if g.get('principal')}
    acts = [l for l in st.lines(st.hand_log) if l.get('at', 0) >= (now - DAY) * 60] if st.hand_log.exists() else []
    let_in = {l.get('name') for l in acts if l.get('what') == 'let-in'}
    turned = {l.get('name') for l in st.lines(st.hand_log) if l.get('what') == 'turn-away'} if st.hand_log.exists() else set()

    def name(p):
        return led.names.get(p) or (by_principal.get(p) or {}).get('name') or h.handle_of(p)

    def standing(g, did):
        if not g:
            return 'in (a delve.town account)' if did.startswith('did:') else 'in'
        if g['name'] in turned:
            return 'turned away'
        return {'held': 'held at the door', 'revoked': 'revoked'}.get(g['state']) or \
            ('let in by the hand' if g['name'] in let_in else 'in')

    def came(g):
        return 'by invitation' if g and not g.get('address') else f"at the door, from {g['address']}" if g else 'by its account'

    arrivals = [{'name': a['handle'], 'principal': a['did'], 'at': clock_text(a['clock']), 'came': came(by_principal.get(a['did'])),
                 'standing': standing(by_principal.get(a['did']), a['did'])} for a in led.arrivals if a['clock'] >= now - DAY]
    seen = {a['principal'] for a in arrivals}
    for g in guests:  # held at the door: no arrival in the world yet
        if g['state'] == 'held' and g.get('principal') not in seen and (g.get('created') or 0) >= (now - DAY) * 60:
            arrivals.append({'name': g['name'], 'principal': g['principal'], 'at': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(g['created'])),
                             'came': came(g), 'standing': 'held at the door'})
    arrivals.reverse()

    day = [r for r in led.rows if r[1] >= now - DAY]
    hour = [r for r in day if r[1] >= now - HOUR]
    turns = lambda rows: Counter(r[2] for r in rows if r[5] and r[2] and r[2] not in staff and r[3] in ('admitted', 'refused', 'suspended', 'created'))
    refusals = lambda rows: dict(Counter(r[4] or '?' for r in rows if r[3] == 'refused').most_common())
    by_day, by_hour = turns(day), turns(hour)
    refused_by = Counter(r[2] for r in day if r[5] and r[3] == 'refused')
    last = {}
    for r in day:
        last[r[2]] = r[1]
    busiest = [{'name': name(p), 'principal': p, 'turns': n, 'lastHour': by_hour.get(p, 0), 'refused': refused_by.get(p, 0),
                'last': clock_text(last.get(p))} for p, n in by_day.most_common(BUSIEST)]

    quota = lambda k: {'used': (status.get(k) or {}).get('used', 0), 'quota': (status.get(k) or {}).get('quota')} if isinstance(status.get(k), dict) else {'used': None, 'quota': status.get(k)}
    spend = model.spent(st, start=(now - DAY) * 60).get('all', {})
    month = model.spent(st).get(time.strftime('%Y-%m', time.gmtime(now * 60)), {})
    quiets = [{'name': name(p), 'principal': p, 'until': clock_text(q['until']), 'reading': q['reading'], 'entry': q['height']}
              for p, q in sorted(led.quiets.items(), key=lambda kv: kv[1]['until']) if q['until'] > now]
    flagged = h.flagged()
    turn_quota = status.get('turnQuota')
    return {
        'world': st.world, 'height': status.get('height'), 'clock': now, 'at': clock_text(now), 'arrival': c.arrival,
        'journals': [str(p) for p in led.chain] + [str(st.journal)],  # what the day was read from, oldest first
        'arrivals': arrivals,
        'busiest': busiest,
        'refusals': {'lastHour': refusals(hour), 'lastDay': refusals(day), 'thisClockHour': (status.get('hour') or {}).get('refused') or {}},
        'budgets': {'hob': quota('modelQuota'), 'paints': quota('paintQuota'), 'interpretations an hour': status.get('interpretQuota'),
                    'model spend, last day': f"${spend.get('dollars', 0):.4f}, {counted(spend.get('calls', 0), 'call')}",
                    'model spend, this month': f"${month.get('dollars', 0):.4f} of ${c.grant:.2f}"},
        'moderation': {'slow': bool(turn_quota) and turn_quota == c.slow_turns, 'turnQuota': turn_quota or None, 'quiets': quiets,
                       'flagged': flagged['config'] + flagged['hand'], 'held': [g['name'] for g in guests if g['state'] == 'held']},
        'acts': [{'what': l.get('what'), 'at': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(l.get('at', 0))),
                  'about': l.get('name') or l.get('address') or l.get('reason') or l.get('draft') or ''} for l in acts[-ACTS:]][::-1],
        'feed': feed_posts(st),
        'automod': automod_of(h),
        'requests': h.requests(),
    }


def automod_of(h, n=8):
    """The automatic moderation as it stands: the worker's status (whether the classifier answers, what waits, the day's
    calls), the host's counts of screened texts and the newest of them."""
    screened = h.host.send({'op': 'world-screened', 'principal': h.owner, 'limit': n})
    s = automod.status(h.st)
    if s is None:
        state = 'off: the worker never ran' if h.st.config.automod else 'off in the config'
    elif s['stale']:
        state = f"stopped: no step since {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(s['at']))}"
    else:
        last = time.strftime('%H:%M UTC', time.gmtime(s['lastCall']['at'])) if (s.get('lastCall') or {}).get('at') else None
        state = {'ok': 'working: the classifier answered its last batch' + (f' at {last}' if last else ''),
                 'idle': ('idle and healthy: nothing has needed the classifier since the worker started' if not s.get('pending')
                          else f"starting: {s['pending']} waiting for the first batch"), 'down': f"the classifier is down ({s.get('lastError')}); texts wait, the wordlist still acts",
                 'budget': "the day's calls are spent; texts wait, the wordlist still acts", 'no key': 'no key: only the wordlist acts'}.get(s['glm'], s['glm'])
    return {'state': state, 'status': s, 'counts': screened.get('counts') or {}, 'newest': screened.get('items') or []}


def clock_text(minute):
    return time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(minute * 60)) if minute else 'never'


def summary(o):
    """The overview's strip: one line a part."""
    m = o['moderation']
    b = o['budgets']
    used = lambda q: f"{q['used']} of {q['quota']}" if q.get('quota') else f"{q['used'] or 0} (no cap)"
    return [f"entry {o['height']}", f"clock {o['at']}", counted(len(o['arrivals']), 'arrival') + ' in a day',
            f"{sum(o['refusals']['lastHour'].values())} refused in the hour, {sum(o['refusals']['lastDay'].values())} in the day",
            f"hob's readings today {used(b['hob'])}", f"paints today {used(b['paints'])}",
            'slow on' if m['slow'] else 'slow off', counted(len(m['quiets']), 'quiet'), counted(len(m['flagged']), 'flag'),
            counted(len(m['held']), 'held arrival'),
            f"automod: {o['automod']['state']}" + (f", {o['automod']['status']['pending']} waiting" if o['automod']['status'] else ''),
            f"{o['automod']['counts'].get('hidden', 0)} hidden, {o['automod']['counts'].get('review', 0)} for review",
            counted(len(o['requests']), 'request') + ' waiting for the town']
