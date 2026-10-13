"""The lexicons under lexicons/online/fg-goose/gsb/ are documents the reference validator takes, and a record checks against
them (docs/ATPROTO.md §5).

Evidence for docs/ATPROTO.md §5 (layer: transport).

Refuted by: an object type inline below a definition's top (the reference validator takes a nested object only by
`ref`), a `ref` naming no definition, a required property its object does not declare, or `validate` passing a value
that misses a required field or carries a field of the wrong type.
"""
import ast
import json
import unittest
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
    if kind not in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
        return problems + ['$.kind: not a projection kind']
    return list(dict.fromkeys(problems + validate(value.get('value'), doc['defs'][kind], doc, '$.value')))


class Lexicons(unittest.TestCase):
    def test_every_lexicon_id_matches_its_path_and_one_authority(self):
        root = Path(__file__).resolve().parent.parent / 'lexicons'
        files = sorted(root.rglob('*.json'))
        self.assertTrue(files, 'no lexicons found')
        for path in files:
            with self.subTest(path=path.relative_to(root)):
                nsid = json.loads(path.read_text())['id']
                self.assertEqual(nsid, '.'.join(path.relative_to(root).with_suffix('').parts))
                self.assertTrue(nsid.startswith('online.fg-goose.gsb.'), nsid)

    def test_old_prefix_is_absent_from_lexicons_and_transport_string_literals(self):
        root = Path(__file__).resolve().parent.parent
        old_prefix = 'town' + '.delvetalk'
        for path in sorted((root / 'lexicons').rglob('*')):
            if path.is_file():
                with self.subTest(path=path.relative_to(root)):
                    self.assertNotIn(old_prefix, path.read_text())
        for path in sorted((root / 'transport').glob('*.py')):
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(path=path.relative_to(root), line=node.lineno):
                        self.assertNotIn(old_prefix, node.value)

    def test_every_document_takes_nested_objects_only_by_ref_and_every_ref_resolves(self):
        problems = []

        def walk(node, path, top, doc):
            if not isinstance(node, dict):
                return
            if node.get('type') == 'object':
                if not top:
                    problems.append(f'{path}: an inline object; name it in defs and ref it')
                undeclared = set(node.get('required', [])) - set(node.get('properties') or {})
                problems.extend(f'{path}: requires undeclared {k}' for k in undeclared)
            if node.get('type') == 'ref':
                try:
                    resolve(node['ref'], doc)
                except KeyError:
                    problems.append(f"{path}: ref {node['ref']} names nothing")
            if node.get('type') == 'union':
                for ref in node['refs']:
                    try:
                        resolve(ref, doc)
                    except KeyError:
                        problems.append(f'{path}: union ref {ref} names nothing')
            for k, v in node.items():
                if k == 'properties':
                    for name, sub in v.items():
                        walk(sub, f'{path}.{name}', False, doc)
                elif k == 'items':
                    walk(v, path + '[]', False, doc)
                elif k in ('record', 'schema', 'input', 'output', 'parameters', 'message'):
                    walk(v, f'{path}.{k}', True, doc)
        for nsid, doc in DOCS.items():
            self.assertEqual(doc['lexicon'], 1, nsid)
            for name, d in doc['defs'].items():
                walk(d, f'{nsid}#{name}', True, doc)
        self.assertEqual(problems, [])

    def test_projection_values_are_definitions_and_queries_share_one_envelope(self):
        doc = DOCS['online.fg-goose.gsb.getProjection']
        self.assertEqual(doc['defs']['main']['type'], 'query')
        self.assertEqual(doc['defs']['main']['output']['schema'], {'type': 'ref', 'ref': '#projection'})
        for kind in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
            self.assertNotIn('online.fg-goose.gsb.' + kind, DOCS)
            self.assertEqual(doc['defs'][kind]['type'], 'object')
        listing = DOCS['online.fg-goose.gsb.listProjections']
        self.assertEqual(listing['defs']['main']['type'], 'query')
        self.assertEqual(listing['defs']['main']['output']['schema']['properties']['projections']['items'],
                         {'type': 'ref', 'ref': doc['id'] + '#projection'})
        good = {'kind': 'receipt', 'key': 'babab-babab', 'of': 'bafy', 'value': {'height': 1, 'hash': 'bafy'}}
        self.assertEqual(record_problems(good), [])
        self.assertEqual(record_problems({**good, 'value': {'hash': 'bafy'}}), ['$.value.height: required'])
        self.assertEqual(record_problems({**good, 'value': {'height': '1', 'hash': 'bafy'}}), ['$.value.height: not a integer'])

    def test_the_validator_refuses_a_missing_field_and_a_wrong_type(self):
        good = {'$type': 'online.fg-goose.gsb.answer', 'source': {'$type': 'online.fg-goose.gsb.answer#request',
                'request': {'uri': 'at://did:plc:x/online.fg-goose.gsb.request/3a', 'cid': 'bafy'}},
                'outcome': {'status': 'admitted', 'line': 'admitted'}, 'height': 3, 'receipt': {'slug': 'a-b', 'height': 3, 'entry': {'$link': 'bafy'}}}
        self.assertEqual(record_problems(good), [])
        self.assertEqual(record_problems({**good, 'outcome': {'status': 'admitted'}}), ['$.outcome.line: required'])
        self.assertEqual(record_problems({**good, 'receipt': {**good['receipt'], 'entry': 'bafy'}}), ['$.receipt.entry: not a cid-link'])
        self.assertEqual(record_problems({**good, 'height': 0}), ['$.height: below 1'])

    def test_answer_source_requires_either_a_request_ref_or_xrpc_provenance(self):
        good = {'$type': 'online.fg-goose.gsb.answer', 'source': {'$type': 'online.fg-goose.gsb.answer#provenance',
                'iss': 'did:plc:x', 'intent': 'one'}, 'outcome': {'status': 'admitted', 'line': 'admitted'}}
        self.assertEqual(record_problems(good), [])
        for key in ('iss', 'intent'):
            value = {**good, 'source': {k: v for k, v in good['source'].items() if k != key}}
            self.assertEqual(record_problems(value), [f'$.source.{key}: required'])
        self.assertEqual(record_problems({k: v for k, v in good.items() if k != 'source'}), ['$.source: required'])
        self.assertTrue(record_problems({**good, 'source': {'iss': 'did:plc:x', 'intent': 'one'}}))

    def test_previews_and_turn_answers_have_separate_discriminants_and_schemas(self):
        doc = DOCS['online.fg-goose.gsb.defs']
        preview = doc['defs']['previewView']
        self.assertNotIn('receipt', preview['properties'])
        self.assertEqual(preview['properties']['$type']['const'], doc['id'] + '#previewView')
        self.assertEqual(preview['properties']['outcome']['ref'], '#previewOutcome')
        self.assertEqual(doc['defs']['previewOutcome']['properties']['status']['const'], 'previewed')
        self.assertNotIn('previewed', doc['defs']['outcome']['properties']['status']['enum'])
        self.assertTrue(validate({'$type': doc['id'] + '#previewView', 'outcome': {'status': 'previewed', 'line': 'preview'}},
                                 doc['defs']['answerView'], doc))

    def test_checkpoint_built_by_mirror_requires_source_did_rev_commit_and_positive_entry_height(self):
        from transport import mirror
        good = mirror.checkpoint_record('did:web:gsb.fg-goose.online', '3aaaaaaaaaaa2', 'bafyreia', 7)
        self.assertEqual(set(good), {'$type', 'did', 'rev', 'commit', 'height'})
        self.assertEqual(record_problems(good), [])
        for field in ('did', 'rev', 'commit', 'height'):
            self.assertEqual(record_problems({k: v for k, v in good.items() if k != field}), [f'$.{field}: required'])
        for field in ('did', 'rev', 'commit'):
            self.assertEqual(record_problems({**good, field: 1}), [f'$.{field}: not a string'])
        for height, problem in [(0, '$.height: below 1'), (True, '$.height: not a integer')]:
            self.assertEqual(record_problems({**good, 'height': height}), [problem])


if __name__ == '__main__':
    unittest.main()
