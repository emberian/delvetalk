"""Native template expansion, checked source composition and structured results.

No model or renderer is involved in constructing these values. The binary must
already have been built from the matching hosted frontend; tests never build it.
"""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEMPLATE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))


def call(request):
    reply = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
                           text=True, capture_output=True, timeout=60, check=True)
    return json.loads(reply.stdout)


def data(value):
    if isinstance(value, bool):
        return {'tag': 'boolean', 'value': value}
    if isinstance(value, int):
        return {'tag': 'natural', 'value': str(value)}
    if isinstance(value, str):
        return {'tag': 'label', 'value': value}
    return {'tag': 'record', 'fields': [{'name': k, 'value': data(v)} for k, v in value.items()]}


def records(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


def modules():
    files = [('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'),
             ('Encounter', 'world/lib/prelude/Encounter.obend'),
             ('Document', 'world/lib/document/Document.obend'),
             ('Phrasebook', 'world/lib/document/templates/Phrasebook.obend')]
    return [{'name': name, 'source': (ROOT / path).read_text()} for name, path in files]


CONTEXT = {'participant': 'Moss 🌿', 'subject': 'moth', 'count': 3,
           'detailed': True, 'utterance': '{% invitation(context) %} {{ 42 }} <script> "🌙"',
           'capture': {'object': 'workshop', 'revision': 7, 'meaning': 'captured-meaning',
                       'entry': 'lend', 'token': 'offer-moth'}}


class DocumentTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for entry in ('plain', 'render', 'sourcePrompt', 'quotation', 'literal', 'headed'):
            reply = call({'op': 'compile', 'modules': modules(), 'entry': entry})
            if reply.get('status') != 'compiled':
                raise AssertionError(reply)
            cls.artifacts[entry] = reply['artifact']

    def run_entry(self, entry, context=None):
        reply = call({'op': 'run-data-v1', 'artifact': self.artifacts[entry],
                      'arguments': [] if entry == 'literal' else [data(context or CONTEXT)]})
        self.assertEqual(reply.get('status'), 'finished', reply)
        return reply['value']

    def test_dynamic_list_inherited_slot_and_conditional(self):
        value = self.run_entry('plain')
        self.assertEqual(value, data('Workshop · Hello, Moss 🌿.\n'
                                    '• moth 1\n• moth 2\n• moth 3\n'
                                    'Bring your own impossible example.\nLend this moth'))
        value = self.run_entry('plain', {**CONTEXT, 'detailed': False})
        self.assertEqual(value, data('Workshop · Hello, Moss 🌿.\nDetails folded.\nLend this moth'))
        self.assertEqual(self.run_entry('headed')['value'],
                         'A shared preface.\n' + self.run_entry('plain')['value'])

    def test_typed_offer_stays_structured(self):
        value = self.run_entry('render')
        captures = [v for v in records(value) if v == data(CONTEXT['capture'])]
        self.assertEqual(len(captures), 1, value)
        self.assertTrue(any(v.get('tag') == 'variant' and v.get('label') == 'offer'
                            for v in records(value)), value)

    def test_prompt_keeps_quoted_data_and_separate_offer(self):
        value = self.run_entry('sourcePrompt')
        self.assertTrue(any(v == data(CONTEXT['utterance']) for v in records(value)), value)
        self.assertEqual(sum(v.get('tag') == 'variant' and v.get('label') == 'offer'
                             for v in records(value)), 1, value)
        self.assertEqual(sum(v.get('tag') == 'variant' and v.get('label') == 'quote'
                             for v in records(value)), 1, value)
        quotation = self.run_entry('quotation')
        self.assertFalse(any(v.get('tag') == 'variant' and v.get('label') == 'offer'
                             for v in records(quotation)), quotation)
        malformed = {**CONTEXT, 'utterance': {'offer': CONTEXT['capture']}}
        reply = call({'op': 'run-data-v1', 'artifact': self.artifacts['quotation'],
                      'arguments': [data(malformed)]})
        self.assertNotEqual(reply.get('status'), 'finished', reply)

    def test_whitespace_unicode_and_literal_delimiters(self):
        self.assertEqual(self.run_entry('literal'), data('  🌙 é "quoted" \'single\'\n'
                         '\tkeep this tab; {{not a hole}}; {%not a splice%}; """; \\.\n'))

    def test_wrong_hole_types_and_missing_import_fail(self):
        for literal in ('doc"""{{ 42 }}"""', 'doc"""{% "not a document" %}"""'):
            package = modules()[:-1] + [{'name': 'Bad', 'source':
                'edition ObjectiveBend 1\nimport ./Document.obend as Document\n'
                'def bad() -> Document.Document:\n  ' + literal + '\n'}]
            reply = call({'op': 'compile', 'modules': package, 'entry': 'bad'})
            self.assertNotEqual(reply.get('status'), 'compiled', reply)
        reply = call({'op': 'compile', 'source':
                      'edition ObjectiveBend 1\ndef bad() -> String:\n  doc"""hello"""\n', 'entry': 'bad'})
        self.assertNotEqual(reply.get('status'), 'compiled', reply)

    def test_quoted_marker_does_not_enable_templates(self):
        source = 'edition ObjectiveBend 1\ndef literal() -> String:\n  "doc\\"\\"\\"{{ untouched }}"\n'
        compiled = call({'op': 'compile', 'source': source, 'entry': 'literal'})
        self.assertEqual(compiled.get('status'), 'compiled', compiled)
        reply = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(reply['value'], data('doc"""{{ untouched }}'))

    def test_expansion_is_inspectable_ordinary_source(self):
        package = modules()
        expanded = call({'op': 'template-expand', 'source': package[-1]['source']})
        self.assertEqual(expanded.get('status'), 'expanded', expanded)
        self.assertNotIn('doc"""', expanded['source'])
        self.assertIn('__document_template_0.concat(', expanded['source'])
        self.assertIn('import ./Document.obend as __document_template_0', expanded['source'])
        package[-1]['source'] = expanded['source']
        compiled = call({'op': 'compile', 'modules': package, 'entry': 'plain'})
        self.assertEqual(compiled.get('status'), 'compiled', compiled)
        result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'],
                       'arguments': [data(CONTEXT)]})
        self.assertEqual(result['value'], self.run_entry('plain'))

    def test_nested_record_holes_and_original_diagnostic_line(self):
        source = ('edition ObjectiveBend 1\nimport ./Document.obend as Document\n'
                  'def entry() -> String:\n'
                  '  Document.plain(doc"""{{ ({value: "}} / %}"}).value }}""")\n')
        package = modules()[:-1] + [{'name': 'Nested', 'source': source}]
        compiled = call({'op': 'compile', 'modules': package, 'entry': 'entry'})
        self.assertEqual(compiled.get('status'), 'compiled', compiled)
        result = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result['value'], data('}} / %}'))
        source = ('edition ObjectiveBend 1\nimport ./Document.obend as Document\n'
                  'def entry() -> Document.Document:\n  doc"""one\ntwo\nthree"""\n'
                  'bad declaration\n')
        package[-1]['source'] = source
        reply = call({'op': 'compile', 'modules': package, 'entry': 'entry'})
        self.assertNotEqual(reply.get('status'), 'compiled', reply)
        diagnostic = json.loads(reply['message'])
        self.assertEqual(diagnostic['span']['line'], 7, diagnostic)
        self.assertEqual(diagnostic['span']['start'], source.index('bad declaration'), diagnostic)

    def test_aliases_and_lexical_shadowing_are_hygienic(self):
        for declaration in ('import ./Document.obend as D', 'import D from "./Document.obend"'):
            source = ('edition ObjectiveBend 1\n' + declaration + '\n'
                      'def render(D: String, __document_template_0: String) -> D.Document:\n'
                      '  let Document = "local"\n'
                      '  doc"""  {{ D }} / {{ Document }} / {{ __document_template_0 }}\n🌙"""\n'
                      'def entry() -> String:\n  D.plain(render("argument", "user binding"))\n')
            package = modules()[:-1] + [{'name': 'Shadow', 'source': source}]
            compiled = call({'op': 'compile', 'modules': package, 'entry': 'entry'})
            self.assertEqual(compiled.get('status'), 'compiled', compiled)
            self.assertEqual(compiled['artifact']['modules'][-1]['source'], source)
            result = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
            self.assertEqual(result['value'], data('  argument / local / user binding\n🌙'))
            expanded = call({'op': 'template-expand', 'source': source})
            self.assertIn('import ./Document.obend as __document_template_1', expanded['source'])
            package[-1]['source'] = expanded['source']
            again = call({'op': 'compile', 'modules': package, 'entry': 'entry'})
            self.assertEqual(again.get('status'), 'compiled', again)
            self.assertEqual(call({'op': 'run', 'artifact': again['artifact'], 'arguments': []})['value'],
                             result['value'])

    def test_missing_or_misleading_dependency_has_clear_diagnostic(self):
        for dependency in ('', 'import ./OtherDocument.obend as Document\n',
                           'import ./other/Document.obend as D\n'):
            source = ('edition ObjectiveBend 1\n' + dependency +
                      'def entry() -> String:\n  doc"""literal"""\n')
            package = modules()[:-1]
            package[-1]['name'] = 'OtherDocument'
            package.append({'name': 'Missing', 'source': source})
            reply = call({'op': 'compile', 'modules': package, 'entry': 'entry'})
            self.assertNotEqual(reply.get('status'), 'compiled', reply)
            diagnostic = json.loads(reply['message'])
            self.assertEqual(diagnostic['stage'], 'document-template', diagnostic)
            self.assertIn('explicit import of ./Document.obend', diagnostic['message'])
        source = 'edition ObjectiveBend 1\n# doc""" only a comment\ndef entry() -> String:\n  "no dependency"\n'
        compiled = call({'op': 'compile', 'source': source, 'entry': 'entry'})
        self.assertEqual(compiled.get('status'), 'compiled', compiled)

    def test_many_occupied_generated_names(self):
        count = 12000
        occupied = ' '.join('__document_template_' + str(i) for i in range(count))
        argument = '__document_template_' + str(count + 1)
        literal = '__document_template_' + str(count)
        source = ('edition ObjectiveBend 1\nimport ./Document.obend as D\n# ' + occupied + '\n'
                  'def render(' + argument + ': String) -> D.Document:\n'
                  '  doc"""{{ ' + argument + ' }}"""\n'
                  'def entry() -> String:\n  D.plain(render("' + literal + '"))\n')
        self.assertLess(len(source.encode()), 512 * 1024)
        expanded = call({'op': 'template-expand', 'source': source})
        self.assertEqual(expanded.get('status'), 'expanded', expanded)
        self.assertTrue(expanded['source'].startswith(
            'import ./Document.obend as __document_template_' + str(count + 2) + '\n'))
        package = modules()[:-1] + [{'name': 'Occupied', 'source': source}]
        compiled = call({'op': 'compile', 'modules': package, 'entry': 'entry'})
        self.assertEqual(compiled.get('status'), 'compiled', compiled)
        result = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result['value'], data(literal))


if __name__ == '__main__':
    unittest.main()
