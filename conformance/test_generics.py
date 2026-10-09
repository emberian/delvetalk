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

    def test_method_rows_and_spec_parameters_preserve_lexical_scope(self):
        source = '''edition ObjectiveBend 1
import ./List.obend as Lists
type Names = Lists.List<String>
type self = Lists.List<String>
type super = Lists.List<String>
record Door:
  answer(Names: Nat) -> Nat
spec Base for Door:
  def answer(Names: Nat) -> Nat:
    Names + 1n
  claim positive(Names: Nat): Names >= 0n
spec Grow for Door:
  def answer(Names: Nat) -> Nat:
    super.answer(Names) + 10n
def apply(worker: {m(x: Nat) -> Nat}) -> Nat:
  worker.m(4n)
def entry() -> Nat:
  apply({m: fn(x: Nat) -> Nat: x}) + fix(compose(Base, Grow), {answer: fn(Names: Nat) -> Nat: Names}).answer(2n)
'''
        result = self.compile(source)
        self.assertEqual(result['status'],'compiled',result)
        run = call({'op':'run-data-v1','artifact':result['artifact'],'arguments':[]})
        self.assertEqual(run['value']['value'],'17')

    def test_open_type_arguments_refuse_instead_of_escaping_rigid_binders(self):
        source = '''edition ObjectiveBend 1
def identity<T>(value: T) -> T:
  value
spec Open[Self has {value: Nat}, Super has {}]:
  def echo() -> Self:
    identity::<Self>(self)
def entry() -> Nat:
  0n
'''
        result = self.compile(source)
        self.assertEqual(result['status'],'error',result)
        self.assertIn('cannot lift open Self/Super',result['message'])

    def test_changing_recursive_arguments_refuse_in_both_discovery_orders(self):
        for expression in ('f::<Nat>(0n) + f::<String>("x")', 'f::<String>("x") + f::<Nat>(0n)'):
            source = '''edition ObjectiveBend 1
def f<T>(value: T) -> Nat:
  if false then f::<Nat>(0n) else 1n
def entry() -> Nat:
  ''' + expression + '\n'
            result = self.compile(source)
            self.assertEqual(result['status'],'error',result)
            self.assertIn('recursion changes type arguments',result['message'])

    def test_sealed_import_revision_changes_generic_identity(self):
        generic = '''edition ObjectiveBend 1
import ./Helper.obend as H
def chosen<T>(value: T) -> Nat:
  H.value()
'''
        source = '''edition ObjectiveBend 1
import ./Generic.obend as G
def entry() -> Nat:
  G.chosen::<Nat>(0n)
'''
        identities=[]
        for value in ('1n','2n'):
            helper = 'edition ObjectiveBend 1\ndef value() -> Nat:\n  ' + value + '\n'
            result = self.compile(source,modules=[{'name':'Helper','source':helper},{'name':'Generic','source':generic}])
            self.assertEqual(result['status'],'compiled',result)
            identities.append(result['artifact']['genericInstances'][0]['declaration'])
        self.assertNotEqual(*identities)

    def test_nested_concrete_type_identity_size_stays_bounded(self):
        nested='Nat'
        for _ in range(16): nested='L.List<' + nested + '>'
        source = 'edition ObjectiveBend 1\nimport ./List.obend as L\ndef entry() -> ' + nested + ':\n  L.List::<' + nested[len('L.List<'):-1] + '>.nil()\n'
        result = self.compile(source)
        self.assertEqual(result['status'],'compiled',result)
        instances=result['artifact']['genericInstances']
        self.assertEqual(len(instances),16)
        self.assertLess(len(json.dumps(instances)),20000)

    def test_instance_and_expanded_syntax_caps_refuse_before_typing(self):
        # Repetition here is adversarial compiler input, not application behavior.
        def workload(function, count, result='Nat'):
            return 'edition ObjectiveBend 1\n' + function + ''.join(
                f'record Element{i}:\n  value: Nat\ndef element{i}() -> {result}:\n'
                f'  expand::<Element{i}>({{value: 0n}})\n' for i in range(count))
        instance_source = workload('def expand<T>(value: T) -> Nat:\n  0n\n', 257)
        expression = '0n'
        for _ in range(10): expression = f'({expression} + {expression})'
        syntax_source = workload('def expand<T>(value: T) -> Nat:\n  ' + expression + '\n', 24)
        literal_body = ''.join(f'  let text{i} = "' + 'x' * 8192 + '"\n' for i in range(16))
        string_source = workload('def expand<T>(value: T) -> String:\n' + literal_body + '  text15\n', 80, 'String')
        for source, reason in [(instance_source, 'exceeds instance budget'),
                               (syntax_source, 'exceeds expanded AST node budget'),
                               (string_source, 'exceeds expanded string byte budget')]:
            result = call({'op':'compile','source':source,'entry':'element0'})
            self.assertEqual(result['status'],'error',result)
            diagnostic = json.loads(result['message'])
            self.assertEqual(diagnostic['stage'],'source-specialization')
            self.assertIn(reason,diagnostic['message'])

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

    def test_shared_preparation_allocation_and_emission_lists(self):
        modules = [module(name, 'world/lib/prelude/' + name + '.obend')
                   for name in ('List', 'Preparation', 'Allocation', 'Emissions')]
        source = '''edition ObjectiveBend 1
import ./Preparation.obend as P
import ./Allocation.obend as A
import ./Emissions.obend as E
def entry() -> {value: P.Value, allocations: A.Allocations, requests: P.Requests, observations: P.Observations, reads: P.Reads, effects: P.Effects, count: Nat, bounded: Bool}:
  let value = P.oneField("nested", P.Value.array({values: P.Values.cons({head: P.Value.text({value: "kept"}), tail: P.Values.nil()})}))
  let emissions = E.append(E.one({to: "a", command: "hear", recipientProgram: "", payload: value}), E.one({to: "b", command: "hear", recipientProgram: "", payload: value}))
  {value: value, allocations: A.Allocations.cons({head: {name: "child", protocol: value, law: value}, tail: A.Allocations.nil()}), requests: P.Requests.nil(), observations: P.Observations.nil(), reads: P.Reads.nil(), effects: P.Effects.nil(), count: E.length(emissions), bounded: E.within(emissions, 1n)}
'''
        result = self.compile(source, modules=modules)
        self.assertEqual(result['status'], 'compiled', result)
        run = call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': []})
        self.assertEqual(run['status'], 'finished', run)
        fields = {field['name']: field['value'] for field in run['value']['fields']}
        self.assertEqual(fields['count']['value'], '2')
        self.assertFalse(fields['bounded']['value'])
        self.assertEqual(fields['value']['label'], 'record')
        self.assertEqual(fields['allocations']['label'], 'cons')
        for name in ('requests', 'observations', 'reads', 'effects'):
            self.assertEqual(fields[name]['label'], 'nil')

    def test_exhibit_list_shared_traversals_preserve_domain_rules(self):
        modules = [module('List', 'world/lib/prelude/List.obend'),
                   module('ExhibitList', 'protocols/place-index/ExhibitList.obend')]
        source = '''edition ObjectiveBend 1
import ./ExhibitList.obend as E
def entry() -> {count: Nat, found: Bool, removed: Nat, renamed: E.Entries}:
  let entry = {object: "same", label: "before", addedBy: "author", observedVersion: 1n}
  let entries = E.append(E.append(E.Entries.nil(), entry), entry)
  {count: E.length(entries), found: E.contains(entries, "same"), removed: E.length(E.remove(entries, "same")), renamed: E.caption(entries, "same", "after")}
'''
        result = self.compile(source, modules=modules)
        self.assertEqual(result['status'], 'compiled', result)
        run = call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': []})
        self.assertEqual(run['status'], 'finished', run)
        fields = {field['name']: field['value'] for field in run['value']['fields']}
        self.assertEqual(fields['count']['value'], '2')
        self.assertTrue(fields['found']['value'])
        self.assertEqual(fields['removed']['value'], '1')
        renamed = fields['renamed']
        for _ in range(2):
            cell = {field['name']: field['value'] for field in renamed['payload']['fields']}
            entry = {field['name']: field['value'] for field in cell['head']['fields']}
            self.assertEqual(entry['label']['value'], 'after')
            renamed = cell['tail']
        self.assertEqual(renamed['label'], 'nil')

    def test_protocol_collections_share_traversals_and_keep_domain_rules(self):
        files = [('List', 'world/lib/prelude/List.obend'), ('Abi', 'world/lib/prelude/Abi.obend'),
                 ('Preparation', 'world/lib/prelude/Preparation.obend'), ('Authority', 'world/lib/prelude/Authority.obend'), ('Encounter', 'world/lib/prelude/Encounter.obend'),
                 ('Emissions', 'world/lib/prelude/Emissions.obend'), ('Document', 'world/lib/document/Document.obend'),
                 ('Relations', 'protocols/containment/Relations.obend'), ('Consent', 'protocols/resident-library/Consent.obend'),
                 ('Directory', 'protocols/root-directory/Directory.obend'), ('Commons', 'protocols/commons/Commons.obend')]
        source = '''edition ObjectiveBend 1
import ./Relations.obend as R
import ./Consent.obend as C
import ./Directory.obend as D
import ./Commons.obend as W
def entry() -> {members: Nat, occupancy: Nat, peers: Nat, first: Nat, unique: Bool, doors: Nat, available: Bool, moved: String, edge: Bool}:
  let member = R.member("a", "owner", "", "room", "", "resident")
  let members = R.Members.cons({head: member, tail: R.Members.cons({head: extend(member, {object: "b", holder: "owner"}), tail: R.Members.nil()})})
  let peers = C.insert(C.insert(C.Peers.nil(), {slot: 9n, object: "nine", program: "", generation: 1n}), {slot: 2n, object: "two", program: "", generation: 1n})
  let first = C.page({epoch: 1n, inbound: C.Peers.nil(), outbound: peers}, 0n, 1n).next
  let unique = C.unique(peers, {side: "listen", slot: 3n, enabled: true, object: "two", program: "", generation: 1n})
  let doors = D.Doors.cons({head: extend(D.blank(), {key: "a", object: "a", show: true, available: true}), tail: D.Doors.nil()})
  let people = W.Participants.cons({head: {principal: "p", entity: {format: "ref", world: "world", object: "p"}, location: "before"}, tail: W.Participants.nil()})
  let paths = W.Paths.cons({head: {source: "before", target: "after"}, tail: W.Paths.nil()})
  {members: R.size(members), occupancy: R.occupancy(members, "room"), peers: C.length(C.remove(peers, 9n)), first: first, unique: unique, doors: D.count(doors), available: D.any(doors), moved: W.participant(W.moved(people, "p", "after"), "p").location, edge: W.edge(paths, "before", "after")}
'''
        result = self.compile(source, modules=[module(name, path) for name, path in files])
        self.assertEqual(result['status'], 'compiled', result)
        run = call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': []})
        self.assertEqual(run['status'], 'finished', run)
        fields = {field['name']: field['value']['value'] for field in run['value']['fields']}
        self.assertEqual(fields, {'members': '2', 'occupancy': '1', 'peers': '1', 'first': '2',
                                  'unique': False, 'doors': '1', 'available': True, 'moved': 'after', 'edge': True})

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
                 ('Interpretation','protocols/interpretation/Interpretation.obend'),
                 ('Conversation','protocols/conversation/Conversation.obend'),
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
