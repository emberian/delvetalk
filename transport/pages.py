"""HTML for people. The markup is transport/static/pages.html (named sections), the look transport/static/style.css;
no script is needed to read. Python fills the sections with escaped host facts and decides nothing."""
import json
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
    items = ''.join(T['item'].format(id=e(i), href=e(quote(i, safe=':')), yours=yours(i, did)) for i in ids)
    return page('the ledger', who, T['home'].format(height=e(str(status.get('height'))), objects=e(str(status.get('objects'))),
                                                    enter=T['enter'] if who else '', login='' if who else T['login'], items=items))


def slips(entries, did=None):
    """Receipts as library slips: the slug in small caps, the height as a shelf mark, a refusal's clause in the margin."""
    def slip(x):
        out, ident = x.get('outcome') or {}, x.get('identity') or {}
        clause = out.get('reason') or ' '.join(str(out[k]) for k in ('clause', 'object') if out.get(k))
        return T['slip'].format(fate=e(str(out.get('tag'))), height=e(str(x.get('height'))), name=e(str(x.get('slug') or '')),
                                intent=e(str(ident.get('intent'))), who=e(str(ident.get('principal'))), yours=yours(ident.get('principal'), did),
                                note=T['note'].format(clause=e(f"{out.get('class')}: {clause}" if clause else str(out.get('class')))) if out.get('tag') == 'refused' else '')
    return T['ledger'].format(slips=''.join(slip(x) for x in entries)) if entries else ''


def obj(name, who, view, card, entries, did=None):
    shown = T['card'].format(text=e(card)) if card else T['state'].format(state=e(json.dumps(view.get('state'), indent=1)[:4000]))
    play = T['playlink'].format(href=e(quote(name, safe='/:')), id=e(name)) if who else ''
    return page(name, who, T['object'].format(id=e(name), version=e(str(view.get('version'))), yours=yours(name, did), shown=shown,
                                              play=play, ledger=slips(entries, did)))


def refusal(title, who, body, code_class=None):
    """An envelope (or a host refusal) as a page: its class, its words, its hint as large as the card's, its links as doors."""
    links = ''.join(T['link'].format(href=e(v['href']), rel=e(k)) for k, v in (body.get('_links') or {}).items()
                    if isinstance(v, dict) and k != 'self')
    hint = T['hint'].format(hint=e(str(body['hint']))) if body.get('hint') else ''
    return page(title, who, T['refusal'].format(cls=e(str(code_class or body.get('class') or body.get('status'))), title=e(title),
                                                message=e(str(body.get('message') or json.dumps(body, sort_keys=True)[:2000])), hint=hint, links=links))


def missing(name, who, reply):
    return refusal(name, who, {**reply, 'message': reply.get('message') or f'no object {name} that you may see',
                               '_links': {'the ledger': {'href': '/'}}}, reply.get('status'))
