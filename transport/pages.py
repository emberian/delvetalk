"""HTML for humans: plain markup, one stylesheet, no script needed to read."""
from html import escape as e
from urllib.parse import quote

SHELL = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="/static/style.css"><script src="/static/theme.js"></script></head><body>
<header><a href="/"><strong>DelveTalk</strong></a><span>{who} <button id="theme-toggle" type="button" hidden>theme</button></span></header>
<main>{body}</main><footer><a href="/AGENTS.md">/AGENTS.md</a>: the agent API</footer></body></html>'''


def page(title, who, body):
    return SHELL.format(title=e(title), who=e(who or 'not logged in'), body=body)


def home(status, who):
    login = '' if who else '''<section><h2>Log in</h2><p>Ask for a challenge, post its text publicly from your own delve.town account, then verify.</p>
<form method="post" action="/AGENTS.md/challenge"><label>Handle <input name="handle" placeholder="you.delve.town"></label><button>Get a challenge</button></form>
<form method="post" action="/AGENTS.md/verify"><label>Handle <input name="handle"></label><label>Post AT URI <input name="uri"></label><button>Verify</button></form></section>'''
    return page('DelveTalk', who, f'''<h1>DelveTalk</h1><section><dl><dt>journal height</dt><dd>{e(str(status.get('height')))}</dd>
<dt>objects</dt><dd>{e(str(status.get('objects')))}</dd></dl>
<form method="get" action="/o"><label>Open an object <input name="object"></label><button>Open</button></form></section>{login}''')


def value(v):
    """A typed-JSON value as readable HTML."""
    if isinstance(v, dict):
        tag = v.get('tag')
        if tag == 'record':
            return '<dl>' + ''.join(f'<dt>{e(f["name"])}</dt><dd>{value(f["value"])}</dd>' for f in v.get('fields', [])) + '</dl>'
        if tag == 'variant':
            return f'<strong>{e(str(v.get("label")))}</strong> {value(v.get("payload"))}'
        if 'value' in v:
            return e(str(v['value']))
    return f'<code>{e(str(v))}</code>'


def receipts(entries):
    rows = ''.join(
        f'<tr><td>{e(str(x.get("height")))}</td><td>{e(str((x.get("identity") or {}).get("principal")))}</td>'
        f'<td>{e(str((x.get("identity") or {}).get("intent")))}</td>'
        f'<td>{e(str((x.get("outcome") or {}).get("class") or (x.get("outcome") or {}).get("tag")))}</td>'
        f'<td><code>{e(str(x.get("hash"))[:16])}</code></td></tr>' for x in entries)
    return ('<section><h3>Last receipts</h3><table><tr><th>height</th><th>principal</th><th>intent</th><th>outcome</th><th>receipt</th></tr>'
            + rows + '</table></section>') if entries else ''


def obj(name, who, view, card, entries, result=None):
    shown = f'<div class="card">{e(card)}</div>' if card else value(view.get('state'))
    form = '' if not who else f'''<section><h3>Speak to {e(name)}</h3><form method="post" action="/o/{e(quote(name, safe=""))}/spell">
<textarea name="text" rows="5" placeholder="delvetalk card action&#10;field: value"></textarea><button>Send</button></form></section>'''
    reply = '' if result is None else f'<section class="{"refused" if result.get("status") in ("refused", "error") else ""}"><h3>Result</h3><pre>{e(result_text(result))}</pre></section>'
    return page(name, who, f'<h1>{e(name)}</h1><p>version {e(str(view.get("version")))}</p><section>{shown}</section>{reply}{form}{receipts(entries)}')


def result_text(r):
    offers = '\n'.join(o.get('text', '') for o in r.get('offers') or [])
    return offers or e_json(r)


def e_json(r):
    import json
    return json.dumps(r.get('receipt', {}).get('outcome') or r, indent=1, sort_keys=True)[:4000]


def missing(name, who, reply):
    return page('unknown object', who, f'<h1>{e(name)}</h1><section class="refused"><pre>{e(e_json(reply))}</pre></section>')
