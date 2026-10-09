#!/usr/bin/env python3
"""Admitted two-player table journeys; all gameplay and authority execute in Lean."""
# Smaller boards below are isolated algorithm fixtures, never offered game layouts.
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


world = load('table_world_transport', 'scripts/world.py')
table = load('table_protocol', 'game/table/protocol.py')
client = load('table_client', 'game/table/client.py')
SEATS = ['did:plc:table-alice', 'did:plc:table-bob']
CASES = {c['id']: c for c in json.loads((ROOT/'game/automatafl/cases.json').read_text())}
REFERENCE = {c['id']: c for c in map(json.loads, (ROOT/'game/automatafl/reference-bend.jsonl').read_text().splitlines())}


def reference(name):
    return {f['name']: int(f['value']['value']) for f in REFERENCE[name]['result']['fields']}


class GameTable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name)/'world.json'
        self.identity = 'table:repair-cafe'
        self.serial = 0

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def new(self, fixture='independent'):
        request = table.create_request(self.identity, *SEATS, principal='did:plc:host', intent='create')
        case = CASES[fixture]
        initial = table.source_object.plain(request['protocol']['initial']['model'])
        initial.update(width=case['w'], height=case['h'])
        initial['game'].update(board=sum(p*4**i for i,p in enumerate(case['cells'])),
                               automaton=case['a'],marks=sum(2**i for i in case['marks']))
        request['protocol']['initial'] = {'model': table.source_object.data(initial)}
        response = self.call(request)
        self.assertEqual(response['kind'],'committed', response)
        return response['data']['root']

    def root(self):
        return self.call({'op':'inspect','object':self.identity,'principal':SEATS[0]})

    def request(self, command, input, seat=0, expected=None, intent=None):
        self.serial += 1
        return {'op':'invoke','object':self.identity,'principal':SEATS[seat],
                'intent':intent or 'turn-'+str(self.serial),
                'expected':self.root() if expected is None else expected,
                'command':command,'input':input}

    def act(self, command, input, seat=0, kind='committed', **kwargs):
        response = self.call(self.request(command,input,seat,**kwargs))
        self.assertEqual(response['kind'],kind,response)
        return response

    def pair(self, fixture='independent', round_number=0):
        moves = CASES[fixture]['moves']
        return [client.prepare(self.identity,round_number,seat,*move,
                               nonce=('%064x' % (seat+1)))
                for seat,move in enumerate(moves)]

    def ready(self, fixture='independent'):
        pair = self.pair(fixture)
        for seat in (0,1):
            self.act('commit'+str(seat),pair[seat]['commit'],seat)
        for seat in (0,1):
            self.act('reveal'+str(seat),pair[seat]['reveal'],seat)
        return pair

    def test_private_nonce_custody_cli(self):
        private = Path(self.tmp.name)/'opening.private.json'
        command=[sys.executable,str(ROOT/'game/table/client.py'),'prepare',
                 '--table',self.identity,'--round','0','--seat','0',
                 '--source','0','--target','5','--private',str(private)]
        result=subprocess.run(command,text=True,capture_output=True,check=True)
        secret=json.loads(private.read_text())
        self.assertEqual(json.loads(result.stdout),secret['commit'])
        self.assertEqual(len(secret['reveal']['nonce']),64)
        self.assertNotIn(secret['reveal']['nonce'],result.stdout)
        self.assertEqual(os.stat(private).st_mode & 0o777,0o600)
        before=private.read_bytes()
        duplicate=subprocess.run(command,text=True,capture_output=True)
        self.assertNotEqual(duplicate.returncode,0)
        self.assertEqual(private.read_bytes(),before)

    def test_source_framing_and_seat_checks_survive_broad_host_grants(self):
        identity = 'table:framing:🐇\n0:'
        values = ['delvetalk.automatafl.commit.v2', identity, '7', '1', '104', '71', 'a' * 64]
        expected = hashlib.sha256(''.join(str(len(v)) + ':' + v for v in values).encode()).hexdigest()
        prepared = client.prepare(identity, 7, 1, 104, 71, nonce='a' * 64)
        self.assertEqual(prepared['commit']['digest'], expected)
        request = table.create_request(self.identity, *SEATS, principal='host', intent='source-seat-check')
        request['law']['invoke']['commit0'] = list(SEATS)
        self.assertEqual(self.call(request)['kind'], 'committed')
        before = self.root()
        self.act('commit0', {'round': 0, 'digest': '0' * 64}, seat=1, kind='refused')
        self.assertEqual(self.root(), before)
        self.act('commit0', {'round': 0, 'digest': '0' * 64}, seat=0)

    def test_actual_game_round_and_retained_resolution(self):
        self.new()
        self.ready()
        request = self.request('resolve',{'round':0})
        receipt = self.call(request)
        self.assertEqual(receipt['kind'],'committed',receipt)
        current = self.root()
        self.assertEqual(client.state(current)['game'],reference('independent'))
        self.assertEqual(client.state(current)['round'],1)
        self.assertEqual(client.state(current)['commit0'],'')
        self.assertEqual(client.state(current)['commit1'],'')
        before = self.db.read_bytes()
        self.assertEqual(self.call(request),receipt)
        self.assertEqual(self.db.read_bytes(),before)
        self.act('resolve',{'round':0},kind='refused')
        self.assertEqual(self.root(),current)

    def test_current_law_withdraws_seat_command_and_retains_refusal(self):
        request = table.create_request(self.identity, *SEATS, principal='host', intent='managed-test')
        request['law']['law'] = ['host']
        self.assertEqual(self.call(request)['kind'], 'committed')
        pair = self.pair()
        pending = self.request('commit0', pair[0]['commit'])
        revised = copy.deepcopy(request['law'])
        revised['invoke']['commit0'] = []
        self.assertEqual(self.call({'op': 'law', 'object': self.identity, 'principal': 'host',
            'intent': 'withdraw-seat-command', 'expected': self.root(), 'law': revised})['kind'], 'committed')
        pending['expected'] = self.root()
        refusal = self.call(pending)
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assertEqual(client.state(self.root())['commit0'], '')
        self.assertEqual(self.call({'op': 'law', 'object': self.identity, 'principal': 'host',
            'intent': 'restore-seat-command', 'expected': self.root(), 'law': request['law']})['kind'], 'committed')
        self.assertEqual(self.call(pending), refusal)
        self.act('commit0', pair[0]['commit'])

    def test_scoped_seats_and_no_plaintext_before_reveal(self):
        original = self.new()
        pair = self.pair()
        self.act('commit1',pair[1]['commit'],seat=0,kind='refused')
        self.assertEqual(self.root(),original)
        self.act('commit0',pair[0]['commit'])
        data = self.db.read_text()
        for prepared in pair:
            self.assertNotIn(prepared['reveal']['nonce'],data)
        self.assertEqual(client.state(self.root())['source0'],0)
        self.act('reveal0',pair[0]['reveal'],kind='refused')
        self.assertFalse(client.state(self.root())['revealed0'])
        self.act('commit1',pair[1]['commit'],seat=1)
        self.act('reveal1',pair[1]['reveal'],seat=0,kind='refused')
        self.act('reveal0',pair[0]['reveal'])
        self.act('reveal0',pair[0]['reveal'],kind='refused')
        # A seated player cannot reprogram the referee or alter seat grants.
        root = self.root()
        denied = self.call({'op':'law','object':self.identity,'principal':SEATS[0],
                            'intent':'takeover','expected':root,'law':[SEATS[0]]})
        self.assertEqual(denied['kind'],'refused')
        self.assertEqual(self.root(),root)

    def test_hash_format_and_domain_binding(self):
        self.new()
        for digest in ['', 'x'*64, 'A'*64, '0'*63]:
            self.act('commit0',{'round':0,'digest':digest},kind='refused')
        pair = self.pair()
        for seat in (0,1):
            self.act('commit'+str(seat),pair[seat]['commit'],seat)
        before = self.root()
        self.act('reveal1',{**pair[1]['reveal'],'round':1},seat=1,kind='refused')
        self.act('reveal1',{**pair[1]['reveal'],'nonce':'f'*64},seat=1,kind='refused')
        self.act('reveal1',{**pair[1]['reveal'],'source':3},seat=1,kind='refused')
        self.assertEqual(self.root(),before)
        self.act('reveal1',pair[1]['reveal'],seat=1)

    def test_commitment_binds_table_round_and_seat(self):
        for label, other_table, other_round, other_seat in [
                ('table','table:elsewhere',0,0),
                ('round',self.identity,1,0),
                ('seat',self.identity,0,1)]:
            with self.subTest(domain=label):
                self.db = Path(self.tmp.name)/(label+'.json')
                self.new()
                pair = self.pair()
                wrong = client.prepare(other_table,other_round,other_seat,0,5,
                                       nonce=pair[0]['reveal']['nonce'])
                self.act('commit0',{**wrong['commit'],'round':0})
                self.act('commit1',pair[1]['commit'],seat=1)
                before = self.root()
                self.act('reveal0',pair[0]['reveal'],kind='refused')
                self.assertEqual(self.root(),before)

    def test_canonical_unicode_and_escaped_table_identity(self):
        self.identity = 'table:Doors/"\\\n\b\t\f🐇'
        self.new()
        self.ready()
        self.act('resolve',{'round':0})
        self.assertEqual(client.state(self.root())['game'],reference('independent'))

    def test_copied_logical_id_cannot_shadow_receiver_identity(self):
        request = table.create_request('table:original',*SEATS,principal='did:plc:host',intent='copy')
        request['object'] = self.identity
        created = self.call(request)
        self.assertEqual(created['kind'],'committed',created)
        root = self.root()
        for domain in ['table:original', self.identity]:
            prepared=client.prepare(domain,0,0,0,5,nonce='0'*64)
            self.act('commit0',prepared['commit'],kind='refused')
            self.assertEqual(self.root(),root)

    def test_simultaneous_commit_cas_retry(self):
        initial = self.new()
        pair = self.pair()
        requests = [self.request('commit'+str(seat),pair[seat]['commit'],seat,expected=initial)
                    for seat in (0,1)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(self.call,requests))
        self.assertEqual(sum(r['kind']=='committed' for r in replies),1)
        loser = next(i for i,r in enumerate(replies) if r['kind']=='refused')
        self.assertEqual(replies[loser]['data'],'stale read root')
        # The failed identity stays failed; a new identity with a new root can commit.
        self.assertEqual(self.call(requests[loser]),replies[loser])
        self.act('commit'+str(loser),pair[loser]['commit'],loser)
        self.assertTrue(all(client.state(self.root())['commit'+str(i)] for i in (0,1)))

    def test_conflict_invalid_and_terminal_preserve_game_results(self):
        for fixture in ['fork','diagonal-refused','win-top']:
            with self.subTest(fixture=fixture):
                self.db = Path(self.tmp.name)/(fixture+'.json')
                self.new(fixture)
                self.ready(fixture)
                self.act('resolve',{'round':0})
                current = self.root()
                self.assertEqual(client.state(current)['game'],reference(fixture))
                self.assertEqual(client.state(current)['round'],1)
                if fixture == 'win-top':
                    self.act('commit0',{'round':1,'digest':'0'*64},kind='refused')
                    self.assertEqual(self.root(),current)

    def test_late_atomic_failure_rolls_back_actual_resolution(self):
        self.new()
        self.ready()
        initial = self.root()
        request = {'op':'transaction','principal':SEATS[0],'intent':'rollback',
                   'reads':{self.identity:initial},'calls':[
                       {'object':self.identity,'command':'resolve','input':{'round':0}},
                       {'object':self.identity,'command':'reveal0','input':{'round':0}}]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'],'refused',receipt)
        self.assertEqual(self.root(),initial)
        self.assertEqual(self.call(request),receipt)
        self.act('resolve',{'round':0})
        self.assertEqual(client.state(self.root())['game'],reference('independent'))


if __name__ == '__main__':
    unittest.main()
