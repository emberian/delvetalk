#!/usr/bin/env python3
"""Conformance for the LOCAL host fixture and agent-proposed JSON scenarios."""
import concurrent.futures
import copy
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('world_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'world.json'

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, request):
        return world.exchange(self.db, request)

    def create(self, name='welcome-once', authority=None, protocol=None):
        protocol = protocol or json.loads((ROOT / 'protocols' / name / 'protocol.json').read_text())
        return self.call({'op':'create','object':'door','principal':'owner','intent':'create',
                          'protocol':protocol,'law':authority or ['a','b','owner']})['data']['root']

    def invoke(self, root, intent='knock', principal='a', message='hello'):
        return {'op':'invoke','object':'door','principal':principal,'intent':intent,
                'expected':root,'command':'knock','input':{'message':message}}

    def inspect(self):
        return self.call({'op':'inspect','object':'door','principal':'local'})

    def test_protocol_scenarios(self):
        for path in sorted((ROOT / 'protocols').glob('*/scenarios.json')):
            protocol = json.loads((path.parent / 'protocol.json').read_text())
            for scenario in json.loads(path.read_text()):
                with self.subTest(protocol=path.parent.name, scenario=scenario['name']):
                    self.db = Path(self.tmp.name) / (path.parent.name + scenario['name'] + '.json')
                    initial = self.create(protocol=protocol, authority=scenario['law'])
                    for index, step in enumerate(scenario['steps']):
                        root = initial if step['root'] == 'initial' else self.inspect()
                        response = self.call({'op':'invoke','object':'door','intent':str(index),
                            'principal':step['principal'],'expected':root,
                            'command':step['command'],'input':step['input']})
                        self.assertEqual(response['kind'], step['kind'])
                        if 'state' in step:
                            self.assertEqual(response['data']['root']['state'], step['state'])
                        if 'error' in step:
                            self.assertEqual(response['data'], step['error'])

    def test_retry_restart_identity_and_new_intent(self):
        root = self.create()
        request = self.invoke(root)
        receipt = self.call(request)
        # Separate OS process loads the committed world, simulating lost reply/restart.
        proc = subprocess.run([sys.executable, str(ROOT/'scripts/world.py'),str(self.db),'-'],
                              input=json.dumps(request),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(proc.stdout),receipt)
        changed = copy.deepcopy(request)
        changed['input']['message'] = 'different'
        self.assertEqual(self.call(changed)['data'],'intent reused for different request')
        self.assertEqual(self.call(self.invoke(self.inspect(),intent='new'))['data'],'precondition failed')
        self.assertEqual(self.inspect()['version'],1)
        receipts = json.loads(self.db.read_text())['receipts']
        self.assertEqual(sum(len(r['receipt']['data'].get('outbox',[]))
                             for r in receipts if isinstance(r['receipt']['data'],dict)),1)

    def test_current_law_and_historical_receipt(self):
        root = self.create(name='section-edit')
        old = {'op':'invoke','object':'door','principal':'a','intent':'edit',
               'expected':root,'command':'edit','input':{'text':'A'}}
        receipt = self.call(old)
        current = self.inspect()
        update = {'op':'law','object':'door','principal':'owner','intent':'remove-a',
                  'expected':current,'law':['owner']}
        self.assertEqual(self.call(update)['kind'],'committed')
        self.assertEqual(self.call(old),receipt)
        denied = {**old,'intent':'edit-again','expected':self.inspect()}
        self.assertEqual(self.call(denied)['data'],'unauthorized')
        # Deliberate lockout is possible; there is no special owner recovery bypass.
        self.assertEqual(self.call({**update,'intent':'lockout','expected':self.inspect(),'law':[]})['kind'],'committed')
        self.assertEqual(self.call({**update,'intent':'recover','expected':self.inspect()})['data'],'unauthorized')

    def test_exact_root_and_atomic_evaluation(self):
        root = self.create(name='section-edit')
        request = {'op':'invoke','object':'door','principal':'a','intent':'edit',
                   'expected':copy.deepcopy(root),'command':'edit','input':{'text':'A'}}
        request['expected']['state']['text'] = 'unread'
        self.assertEqual(self.call(request)['data'],'stale read root')
        request.update(intent='missing-input',expected=root,input={})
        self.assertEqual(self.call(request)['kind'],'refused')
        self.assertEqual(self.inspect(),root)
        request.update(intent='bare-section',expected='Doors',input={'text':'A'})
        self.assertEqual(self.call(request)['data'],'stale read root')
        request.update(intent='wrong-program',expected=copy.deepcopy(root))
        request['expected']['protocol']['name']='another'
        self.assertEqual(self.call(request)['data'],'stale read root')

    def test_generic_program_simultaneous_writes(self):
        p={'profile':'delvetalk-local-v1','initial':{'x':1,'y':2},'commands':{
            'swap':{'require':[],'set':{'x':['state','y'],'y':['state','x']},
                    'result':['array',[['state','x'],['state','y']]],'outbox':[]}}}
        root=self.create(protocol=p)
        r=self.call({'op':'invoke','object':'door','principal':'a','intent':'swap',
                     'expected':root,'command':'swap','input':{}})
        self.assertEqual(r['data']['root']['state'],{'x':2,'y':1})
        self.assertEqual(r['data']['result'],[1,2])

    def test_lossless_decimal_roots(self):
        number=Decimal('0.12345678901234567890123456789')
        p={'profile':'delvetalk-local-v1','initial':{'precise':number},'commands':{
            'touch':{'require':[],'set':{},'result':['state','precise'],'outbox':[]}}}
        root=self.create(protocol=p)
        self.assertEqual(root['state']['precise'],number)
        altered=copy.deepcopy(root)
        altered['state']['precise']=Decimal('0.12345678901234567890123456788')
        request={'op':'invoke','object':'door','principal':'a','intent':'touch',
                 'expected':altered,'command':'touch','input':{}}
        self.assertEqual(self.call(request)['data'],'stale read root')
        request.update(intent='exact',expected=root)
        self.assertEqual(self.call(request)['data']['result'],number)
        self.assertEqual(world.wire_loads(self.db.read_text())['objects']['door']['state']['precise'],number)

    def test_bend_budget_shared_across_writes(self):
        # ifZero's successor branch binds the predecessor at index 0.
        burn=['fix',['lam',['lam',['lam',['ifZero',['bound',0],['nat','0'],
                  ['app',['bound',3],['bound',0]]]]]],['record',[]]]
        expression=['bend',burn,[['literal',1000]]]
        for count in [1,2]:
            self.db=Path(self.tmp.name)/('budget'+str(count)+'.json')
            p={'profile':'delvetalk-local-v1','initial':{},'commands':{
                'run':{'require':[],'set':{str(k):expression for k in range(count)},
                       'result':['literal',0],'outbox':[]}}}
            root=self.create(protocol=p)
            r=self.call({'op':'invoke','object':'door','principal':'a','intent':'run',
                         'expected':root,'command':'run','input':{}})
            if count==1:
                self.assertEqual(r['kind'],'committed')
                self.assertEqual(r['data']['root']['state'],{'0':0})
            else:
                self.assertEqual(r['data'],'invocation budget exhausted')
                self.assertEqual(self.inspect(),root)

    def test_pure_bend_boundary_and_atomic_refusal(self):
        omega=['lam',['app',['bound',0],['bound',0]]]
        examples=[
            ('effect',['perform',['label','post']], 'Bend effects are forbidden'),
            ('lazy-effect',['record',[['later',['perform',['label','post']]]]], 'Bend effects are forbidden'),
            ('closure',['lam',['bound',0]], 'Bend result must be'),
            ('stuck',['bound',0], 'Bend expression stuck'),
            ('divergence',['app',omega,omega], 'invocation budget exhausted')]
        for name,term,error in examples:
            with self.subTest(name=name):
                self.db=Path(self.tmp.name)/(name+'.json')
                p={'profile':'delvetalk-local-v1','initial':{'kept':1},'commands':{
                    'run':{'require':[],'set':{'kept':['literal',2]},
                           'result':['bend',term,[]],'outbox':[]}}}
                root=self.create(protocol=p)
                r=self.call({'op':'invoke','object':'door','principal':'a','intent':'run',
                             'expected':root,'command':'run','input':{}})
                self.assertEqual(r['kind'],'refused')
                self.assertIn(error,r['data'])
                self.assertEqual(self.inspect(),root)

    def test_malformed_definition_and_request_limits(self):
        p={"profile":"delvetalk-local-v1","initial":{},"commands":{
            "bad":{"require":[],"set":{},"result":["network","https://example.com"],"outbox":[]}}}
        refused=self.call({"op":"create","object":"bad","principal":"a","intent":"bad",
                           "protocol":p,"law":["a"]})
        self.assertEqual(refused["kind"],"refused")
        self.assertEqual(json.loads(self.db.read_text())["objects"],{})
        with self.assertRaisesRegex(ValueError,"request exceeds 64 KiB"):
            self.call({"op":"create","principal":"a","intent":"large","payload":"x"*66000})

    def test_concurrent_scanners(self):
        self.assertTrue((ROOT/'.lake/build/bin/delvetalk-world').exists(),
                        'Build delvetalk-world first: concurrency test must not spawn Lean compiler seats')
        root=self.create()
        def scan(index):
            req=self.invoke(root,intent='scan-'+str(index),principal='a' if index%2 else 'b')
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/world.py'),str(self.db),'-'],
                                input=json.dumps(req),text=True,capture_output=True,check=True)
            return json.loads(proc.stdout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(scan,range(12)))
        self.assertEqual(sum(r['kind']=='committed' for r in results),1)
        self.assertEqual(self.inspect()['version'],1)


if __name__=='__main__':
    unittest.main()
