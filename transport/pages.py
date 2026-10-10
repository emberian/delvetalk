"""HTML for people. The markup is transport/static/pages.html (named sections), the look transport/static/style.css;
no script is needed to read. Python fills the sections with escaped host facts and decides nothing."""
import re
from html import escape as e
from pathlib import Path
from urllib.parse import quote

T = dict(re.findall(r'<!-- (\w+)[^>]*-->\n(.*?)(?=\n<!--|\Z)', (Path(__file__).resolve().parent / 'static' / 'pages.html').read_text(), re.S))


def page(title, who, body):
    return T['shell'].format(title=e(title), who=e(who or 'not logged in'), body=body)


def yours(text, did):
    return T['yours'] if did and did in str(text) else ''


def home(status, who, ids=(), did=None):
    return page('the ledger', who, T['home'].format(height=e(str(status.get('height'))), objects=e(str(status.get('objects'))),
                                                    enter=T['enter'] if who else '', login='' if who else T['login'], items=items(ids, {}, did)))


def items(ids, words, did):
    """Objects as small cards: the kind's mark, the id, the door word the directory gives it, (yours)."""
    return ''.join(T['world_item'].format(id=e(i), href=e(quote(i, safe=':')), yours=yours(i, did),
                                          word=T['word'].format(word=e(words[i])) if words.get(i) else '') for i in ids)


def doors_of(links):
    return ''.join(T['link'].format(href=e(v['href']), rel=e(k)) for k, v in (links or {}).items() if isinstance(v, dict) and k != 'self')


def slip(x, did=None):
    """A receipt as a library slip: the slug in small caps, the height as a shelf mark, a refusal's clause in the margin."""
    out, ident = x.get('outcome') or {}, x.get('identity') or {}
    clause = out.get('reason') or ' '.join(str(out[k]) for k in ('clause', 'object') if out.get(k))
    return T['slip'].format(fate=e(str(out.get('tag'))), height=e(str(x.get('height'))), name=e(str(x.get('slug') or '')),
                            intent=e(str(ident.get('intent'))), who=e(str(ident.get('principal'))), yours=yours(ident.get('principal'), did),
                            note=T['note'].format(clause=e(f"{out.get('class')}: {clause}" if clause else str(out.get('class')))) if out.get('tag') == 'refused' else '')


def obj(name, who, view, card, entries, did=None, doors=(), seen=None, acts=()):
    """An object: its card (sacred text), its doors, a way to play it, its actions as forms from the method table, its law and
    source as code, its receipts as slips."""
    shown = T['card'].format(text=e(card)) if card else T['state'].format(state=dl(view.get('state')))
    play = T['playlink'].format(href=e(quote(name, safe='/:')), id=e(name)) if who else ''
    seen = seen if (seen or {}).get('status') == 'inspected' else None
    source = T['source'].format(law=e(seen.get('law') or ''), pin=e(str(seen.get('pinSlug') or '')), source=e(seen.get('source') or ''),
                                lines=len((seen.get('source') or '').splitlines())) if seen else ''
    forms = ''.join(form(name, a) for a in acts if a['name'] != 'receive')
    return page(name, who, T['object'].format(id=e(name), version=e(str(view.get('version'))), yours=yours(name, did), shown=shown, play=play,
                                              doors=door_nav(doors), actions=T['actions'].format(forms=forms) if forms else '', source=source,
                                              ledger=T['ledger'].format(slips=''.join(slip(x, did) for x in entries)) if entries else ''))


def door_nav(doors):
    return T['doors'].format(items=''.join(T['door'].format(href=e(quote(d['to']['object'], safe='/:')), id=e(d['to']['object']), label=e(d.get('label', '')),
                                                              description=e(d.get('description', ''))) for d in doors)) if doors else ''


def form(name, act):
    """A method of the host's table as a real form: a select for a choice, a bounded text input, a number with min and max."""
    if 'fields' not in act:
        return T['f_typed'].format(method=e(act['name']), id=e(name))
    inputs = ''.join(T['f_' + f['kind']].format(name=e(f['name']), min=e(str(f['bounds'].get('min', ''))), max=e(str(f['bounds'].get('max', ''))),
                                                options=''.join(f'<option>{e(o)}</option>' for o in f['bounds'].get('options', []))) for f in act['fields'])
    return T['action'].format(href=e(quote(name, safe='/:')), method=e(act['name']), inputs=inputs,
                              spell=T['spell'].format(spell=e(act['spell'])) if act.get('spell') else '')


def dl(v):
    """Plain JSON as semantic HTML: a record a definition list, a list an ordered list, typed data its value."""
    if isinstance(v, dict) and v.get('tag') in ('record', 'list'):  # typed data: its fields, its items
        v = {f['name']: f['value'] for f in v.get('fields') or []} if v['tag'] == 'record' else v.get('items') or []
    if isinstance(v, dict) and 'tag' in v and set(v) <= {'tag', 'value', 'label', 'payload'}:
        return e(str(v.get('value', v.get('label', ''))))
    if isinstance(v, dict):
        return '<dl>' + ''.join(f'<dt>{e(str(k))}</dt><dd>{dl(x)}</dd>' for k, x in v.items() if k not in ('_links', '_actions')) + '</dl>'
    return '<ol>' + ''.join(f'<li>{dl(x)}</li>' for x in v) + '</ol>' if isinstance(v, list) else e(str(v))


def listing(ids, words, who, did, more=None):
    return page('the world', who, T['world'].format(items=items(ids, words, did), more=T['more'].format(href=e(more)) if more else ''))


def rendered(kind, body, links, who, did=None):
    """An agent route's reply for a browser: a receipt as its slip, offers as slips and cards, anything else as a definition list."""
    if kind == 'receipt' and isinstance(body.get('receipt'), dict):
        rc = body['receipt']
        roots = ''.join(T['root'].format(href=e(quote(r.get('object', ''), safe=':')), id=e(str(r.get('object'))), version=e(str(r.get('version'))))
                        for r in rc.get('roots') or [])
        return page('receipt', who, T['receipt'].format(name=e(str(rc.get('slug', ''))), slip=slip(rc, did),
                                                        roots=roots, projection=dl({k: v for k, v in rc.items() if k not in ('slug', 'roots')})))
    if kind == 'offers' and isinstance(body.get('offers'), list):
        items = ''.join(T['offer_slip'].format(height=e(str(o.get('height'))), intent=e(str((o.get('identity') or {}).get('intent'))),
                                               text=e(str(o.get('text')))) for o in body['offers'] if isinstance(o, dict)) or T['quiet']
        return page('offers', who, T['offers'].format(items=items, more=T['more'].format(href=e(links['next']['href'])) if 'next' in links else ''))
    return page(kind, who, T['generic'].format(title=e(kind), body=dl(body), links=doors_of(links)))


def catalogue(api, who):
    row = lambda a, b, c, d: T['row'].format(a=e(str(a)), b=e(str(b)), c=e(str(c)), d=e(str(d)))
    return page('the catalogue', who, T['catalogue'].format(
        routes=''.join(row(r['method'], r['href'], r['auth'], r['does']) for r in api['routes']),
        errors=''.join(row(v['code'], k, v['status'], v['when']) for k, v in api['errors'].items()),
        refusals=''.join(row(k, v['transient'], v['hint'], v['means']) for k, v in api['refusals'].items()), limits=dl(api['limits'])))


def refusal(title, who, body, code_class=None):
    """An envelope (or a host refusal) as a page: its class, its words, its hint as large as the card's, its links as doors."""
    hint = T['hint'].format(hint=e(str(body['hint']))) if body.get('hint') else ''
    return page(title, who, T['refusal'].format(cls=e(str(code_class or body.get('class') or body.get('status'))), title=e(title),
                                                message=e(str(body.get('message') or f"no object {title} that you may see")), hint=hint, links=doors_of(body.get('_links')) or T['link'].format(href='/', rel='the ledger')))
