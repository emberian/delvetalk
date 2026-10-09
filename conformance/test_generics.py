"""Bounded native rank-1 specialization and the concrete list consumer cuts."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEMPLATE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))

def call(request):
    done = subprocess.run([str(BINARY)], input=json.dumps(request)+'\n', text=True,
                          capture_output=True, check=True, timeout=60)
    return json.loads(done.stdout)

def module(name, path):
    return {'name': name, 'source': (ROOT / path).read_text()}

class GenericTests(unittest.TestCase):
    def compile(self, source, entry='entry', modules=None):
        return call({'op': 'compile', 'modules': (modules or [module('List', 'world/lib/prelude/List.obend')]) +
                     [{'name': 'Main', 'source': source}], 'entry': entry})

    def test_list_sums_and_functions(self):
        source = (ROOT / 'conformance/fixtures/generics/Basic.obend').read_text()
        for entry in ('count', 'childCount'):
            result = self.compile(source, entry)
            self.assertEqual(result['status'], 'compiled', result)
            self.assertEqual(len(result['artifact']['genericInstances']), 6)
            run = call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': []})
            self.assertEqual(run['value'], {'tag': 'natural', 'value': '2'}, run)

    def test_aliases_share_instances_and_authored_names_remain_hygienic(self):
        result = self.compile('''edition ObjectiveBend 1
import ./List.obend as A
import ./List.obend as B
type Names = A.List<String>
def __generic_0() -> Nat:
  11n
def entry() -> Nat:
  A.length::<String>(Names.nil()) + B.length::<String>(B.List::<String>.nil()) + __generic_0()
''')
        self.assertEqual(result['status'], 'compiled', result)
        self.assertEqual(len(result['artifact']['genericInstances']), 2)
        run = call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': []})
        self.assertEqual(run['value']['value'], '11')

    def test_independent_same_named_generics_are_distinct(self):
        library = 'edition ObjectiveBend 1\ndef chosen<T>(value: T) -> Nat:\n  1n\n'
        other = library.replace('1n', '2n')
        result = self.compile('''edition ObjectiveBend 1
import ./First.obend as A
import ./Second.obend as B
def entry() -> Nat:
  A.chosen::<Nat>(0n) + B.chosen::<Nat>(0n)
''', modules=[{'name':'First','source':library},{'name':'Second','source':other}])
        self.assertEqual(result['status'], 'compiled', result)
        instances = result['artifact']['genericInstances']
        self.assertEqual(len({i['declaration'] for i in instances}), 2)
        run = call({'op':'run-data-v1','artifact':result['artifact'],'arguments':[]})
        self.assertEqual(run['value']['value'], '3')

    def test_arity_unresolved_and_expanding_recursion_refuse(self):
        sources = [
            ('generic type arity', '''edition ObjectiveBend 1
import ./List.obend as L
def entry() -> Nat:
  L.length::<String, Nat>(L.List::<String>.nil())
'''),
            ('unknown source type', '''edition ObjectiveBend 1
import ./List.obend as L
def entry() -> Nat:
  L.length::<Missing>(L.List::<Missing>.nil())
'''),
            ('recursion changes type arguments', '''edition ObjectiveBend 1
sum Nest<T>:
  nil: {}
  next: {tail: Nest<Nest<T>>}
def entry() -> Nest<Nat>:
  Nest::<Nat>.nil()
''')]
        for reason, source in sources:
            result = self.compile(source)
            self.assertEqual(result['status'], 'error', result)
            self.assertIn(reason, result['message'])

    def test_checker_preserves_payload_and_quantity_refusals(self):
        source = '''edition ObjectiveBend 1
import ./List.obend as L
def entry() -> L.List<String>:
  L.List::<String>.cons({head: 7n, tail: L.List::<String>.nil()})
'''
        self.assertEqual(self.compile(source)['status'], 'error')
        for quantity in ('affine', 'linear'):
            source = '''edition ObjectiveBend 1
def duplicate<T>(''' + quantity + ''' value: T) -> {left: T, right: T}:
  {left: value, right: value}
def entry() -> {left: Nat, right: Nat}:
  duplicate::<Nat>(7n)
'''
            result = self.compile(source)
            self.assertEqual(result['status'], 'error', result)
            self.assertIn('checker refused', result['message'])

    def test_real_names_and_paged_children_keep_wire_and_policy(self):
        modules = [module('List','world/lib/prelude/List.obend'),
                   module('Preparation','world/lib/prelude/Preparation.obend'),
                   module('Encounter','world/lib/prelude/Encounter.obend'),
                   module('EncounterPages','world/lib/prelude/EncounterPages.obend')]
        source = '''edition ObjectiveBend 1
import ./Preparation.obend as P
import ./Encounter.obend as E
import ./EncounterPages.obend as Pages
def question() -> P.Preparation:
  P.Preparation.question({message: "Which gesture?", needs: P.Names.cons({head: "gesture", tail: P.Names.nil()})})
def fill(index: Nat, pages: Pages.Pages) -> Pages.Pages:
  if index == 18n then pages else fill(index + 1n, Pages.offer(pages, {key: natText(index), label: "moth", object: "moth", panel: "view"}, 18n).pages)
def entry() -> {count: Nat, pages: Nat, first: Nat, second: Nat, duplicate: Bool, full: Bool}:
  let pages = fill(0n, Pages.Pages.nil())
  {count: Pages.length(pages), pages: Pages.pageCount(pages), first: E.childrenLength(Pages.page(pages, 0n)), second: E.childrenLength(Pages.page(pages, 1n)), duplicate: Pages.offer(pages, {key: "0", label: "duplicate", object: "other", panel: "view"}, 18n).accepted, full: Pages.offer(pages, {key: "new", label: "extra", object: "other", panel: "view"}, 18n).accepted}
'''
        result = self.compile(source, 'question', modules)
        self.assertEqual(result['status'], 'compiled', result)
        run = call({'op':'run-data-v1','artifact':result['artifact'],'arguments':[]})
        self.assertEqual(run['value']['label'], 'question')
        fields = {f['name']:f['value'] for f in run['value']['payload']['fields']}
        needs = fields['needs']
        self.assertEqual(needs['label'], 'cons')
        self.assertEqual([f['name'] for f in needs['payload']['fields']], ['head','tail'])
        result = self.compile(source, modules=modules)
        self.assertEqual(result['status'], 'compiled', result)
        run = call({'op':'run-data-v1','artifact':result['artifact'],'arguments':[]})
        fields = {f['name']:f['value']['value'] for f in run['value']['fields']}
        self.assertEqual(fields, {'count':'18','pages':'2','first':'16','second':'2','duplicate':False,'full':False})

    def test_previous_list_wire_is_accepted_by_generic_codec(self):
        previous = call({'op':'compile','source':'''edition ObjectiveBend 1
sum Names:
  nil: {}
  cons: {head: String, tail: Names}
def entry() -> Names:
  Names.cons({head: "moth", tail: Names.nil()})
''','entry':'entry'})
        self.assertEqual(previous['status'],'compiled',previous)
        old = call({'op':'run-data-v1','artifact':previous['artifact'],'arguments':[]})
        self.assertEqual(old['status'],'finished',old)
        current = self.compile('''edition ObjectiveBend 1
import ./List.obend as Lists
type Names = Lists.List<String>
def entry(items: Names) -> Names:
  items
''')
        self.assertEqual(current['status'],'compiled',current)
        new = call({'op':'run-data-v1','artifact':current['artifact'],'arguments':[old['value']]})
        self.assertEqual(new['status'],'finished',new)
        self.assertEqual(new['value'],old['value'])
        comparison = call({'op':'compare-data-types-v1',
            'left':{'artifact':previous['artifact'],'path':[]},
            'right':{'artifact':current['artifact'],'path':['domain']}})
        self.assertTrue(comparison.get('equal'),comparison)

    def test_actual_conversation_roundtrips_retained_history_and_offers(self):
        files = [('List','world/lib/prelude/List.obend'),
                 ('Abi','world/lib/prelude/Abi.obend'),
                 ('Preparation','world/lib/prelude/Preparation.obend'),
                 ('Encounter','world/lib/prelude/Encounter.obend'),
                 ('Document','world/lib/document/Document.obend'),
                 ('Conversation','protocols/conversation/Conversation.obend'),
                 ('Interpretation','protocols/interpretation/Interpretation.obend'),
                 ('ModelEncounter','protocols/interpretation/Encounter.obend'),
                 ('ConversationModel','protocols/interpretation/ConversationModel.obend'),
                 ('Notebook','protocols/conversation/Notebook.obend'),
                 ('MothNotebook','protocols/conversation/MothNotebook.obend')]
        modules = [module(name,path) for name,path in files]
        def compile_entry(entry):
            result = call({'op':'compile','modules':modules,'entry':entry})
            self.assertEqual(result['status'],'compiled',result)
            return result['artifact']
        def run(entry, arguments):
            result = call({'op':'run-data-v1','artifact':compile_entry(entry),'arguments':arguments})
            self.assertEqual(result['status'],'finished',result)
            return result['value']
        def data(value):
            if isinstance(value,bool): return {'tag':'boolean','value':value}
            if isinstance(value,int): return {'tag':'natural','value':str(value)}
            if isinstance(value,str): return {'tag':'label','value':value}
            return {'tag':'record','fields':[{'name':k,'value':data(v)} for k,v in value.items()]}
        state = run('initial',[])
        utterance = 'Lend the amber moth; {{ quoted source }} 🌙'
        decision = run('answer',[state,data({'original':utterance,'target':'moth:amber','recipient':'moss'}),
            data({'object':'conversation','principal':'iris','inputOrigin':{'kind':'literal','object':'','command':'','immediatelyPrevious':False}})])
        fields = {f['name']:f['value'] for f in decision['fields']}
        self.assertTrue(fields['accepted']['value'])
        retained = json.loads(json.dumps(fields['state']))
        document = run('document',[retained,data(0),data(16),data('Choose a moth')])
        def values(value):
            if isinstance(value,dict):
                yield value
                for child in value.values(): yield from values(child)
            elif isinstance(value,list):
                for child in value: yield from values(child)
        nodes = list(values(document))
        self.assertIn(data(utterance),nodes)
        self.assertIn(data('iris'),nodes)
        self.assertTrue(any(v.get('tag')=='variant' and v.get('label')=='quote' for v in nodes))
        self.assertTrue(any(v.get('tag')=='variant' and v.get('label')=='offer' for v in nodes))

if __name__ == '__main__': unittest.main()
