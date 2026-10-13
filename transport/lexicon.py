"""Structural Lexicon v1 validation shared by repository writes and the record tests."""
import json
from datetime import datetime
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / 'lexicons' / 'online' / 'fg-goose' / 'gsb'
DOCS = {json.loads(p.read_text())['id']: json.loads(p.read_text()) for p in sorted(DIR.glob('*.json'))}
EXTERNAL = {'com.atproto.repo.strongRef#main': {'type': 'object', 'required': ['uri', 'cid'],
                                                'properties': {'uri': {'type': 'string', 'format': 'at-uri'}, 'cid': {'type': 'string', 'format': 'cid'}}}}


def resolve(ref, doc):
    """A `ref` as its definition: `#x` in `doc`, `<nsid>` or `<nsid>#x` in another document."""
    nsid, _, name = (doc['id'] + ref if ref.startswith('#') else ref).partition('#')
    name = name or 'main'
    if f'{nsid}#{name}' in EXTERNAL:
        return EXTERNAL[f'{nsid}#{name}'], None
    target = DOCS[nsid]
    return target['defs'][name], target


def validate(value, schema, doc, at='$'):
    """-> the problems with `value` under `schema` (a lexicon definition), each with its path; [] when it checks."""
    kind = schema['type']
    if kind == 'ref':
        target, owner = resolve(schema['ref'], doc)
        return validate(value, target, owner or doc, at)
    if kind == 'union':
        if not isinstance(value, dict):
            return [f'{at}: not a tagged union object']
        tag = value.get('$type')
        refs = [doc['id'] + r if r.startswith('#') else r for r in schema['refs']]
        if tag not in refs:
            return [f'{at}.$type: not a union variant']
        target, owner = resolve(tag, doc)
        return validate(value, target, owner or doc, at)
    if kind == 'record':
        return validate(value, schema['record'], doc, at)
    if kind == 'unknown':
        return []
    if kind == 'cid-link':
        return [] if isinstance(value, dict) and set(value) == {'$link'} and isinstance(value['$link'], str) else [f'{at}: not a cid-link']
    if kind == 'object':
        if not isinstance(value, dict):
            return [f'{at}: not an object']
        out = [f'{at}.{k}: required' for k in schema.get('required', []) if k not in value]
        for k, sub in (schema.get('properties') or {}).items():
            if k in value:
                out += validate(value[k], sub, doc, f'{at}.{k}')
        return out
    if kind == 'array':
        if not isinstance(value, list) or len(value) > schema.get('maxLength', len(value)) or len(value) < schema.get('minLength', 0):
            return [f'{at}: not an array within its bounds']
        return [p for i, v in enumerate(value) for p in validate(v, schema['items'], doc, f'{at}[{i}]')]
    python = {'string': str, 'integer': int, 'boolean': bool}[kind]
    if not isinstance(value, python) or (kind == 'integer' and isinstance(value, bool)):
        return [f'{at}: not a {kind}']
    if kind == 'integer' and value < schema.get('minimum', value):
        return [f'{at}: below {schema["minimum"]}']
    if 'const' in schema and value != schema['const']:
        return [f'{at}: not {schema["const"]}']
    if 'enum' in schema and value not in schema['enum']:
        return [f'{at}: not an enum value']
    if kind == 'string':
        fmt = schema.get('format')
        if fmt == 'did' and not re.fullmatch(r'did:[a-z0-9]+:[A-Za-z0-9._:%-]+', value):
            return [f'{at}: not a did']
        if fmt == 'datetime':
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value):
                    raise ValueError('datetime')
                datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return [f'{at}: not a datetime']
        n = len(value.encode('utf-8'))
        if n < schema.get('minLength', n) or n > schema.get('maxLength', n):
            return [f'{at}: string outside byte bounds']
    return []


def record_problems(value):
    """Record or projection problems under its record NSID or projection kind."""
    if '$type' in value:
        doc = DOCS[value['$type']]
        return validate(value, doc['defs']['main'], doc)
    doc = DOCS['online.fg-goose.gsb.getProjection']
    problems = validate(value, doc['defs']['projection'], doc)
    kind = value.get('kind')
    if kind not in doc['defs']['projection']['properties']['kind']['enum']:
        return problems + ['$.kind: not a projection kind']
    subject = value.get('value')
    shape = 'carriedReceipt' if kind == 'receipt' and isinstance(subject, dict) and 'carried' in subject else kind
    return list(dict.fromkeys(problems + validate(subject, doc['defs'][shape], doc, '$.value')))


