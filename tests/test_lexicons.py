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
    return []


def record_problems(value):
    """A record's problems under the lexicon its `$type` names."""
    doc = DOCS[value['$type']]
    return validate(value, doc['defs']['main'], doc)


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

    def test_the_validator_refuses_a_missing_field_and_a_wrong_type(self):
        good = {'$type': 'online.fg-goose.gsb.answer', 'request': {'uri': 'at://did:plc:x/online.fg-goose.gsb.request/3a', 'cid': 'bafy'},
                'outcome': {'status': 'admitted', 'line': 'admitted'}, 'height': 3, 'receipt': {'slug': 'a-b', 'height': 3, 'entry': {'$link': 'bafy'}}}
        self.assertEqual(record_problems(good), [])
        self.assertEqual(record_problems({**good, 'outcome': {'status': 'admitted'}}), ['$.outcome.line: required'])
        self.assertEqual(record_problems({**good, 'receipt': {**good['receipt'], 'entry': 'bafy'}}), ['$.receipt.entry: not a cid-link'])
        self.assertEqual(record_problems({**good, 'height': 0}), ['$.height: below 1'])


if __name__ == '__main__':
    unittest.main()
