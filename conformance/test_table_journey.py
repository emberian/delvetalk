"""One inhabited world plus a complete match through the actual PDS receiving path."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


journey=load('table_journey_test','scripts/table_journey.py')
clerk=load('table_journey_clerk','scripts/clerk.py')
manage=load('table_journey_manage','scripts/manage.py')


class AuthoredPDS:
    """Read-only transport fixture: the ordinary clerk verifies these responses."""
    def __init__(self):
        self.records={}
        self.calls=[]
        self.wrong_cid=False

    def record(self,author,key,payload):
        uri=f'at://{author}/{clerk.COLLECTION}/{key}'
        value={'$type':clerk.COLLECTION,'profile':'delvetalk-live-v1',
               'requestJson':clerk.world.wire_dumps(payload)}
        cid='mock-cid-'+hashlib.sha256(clerk.canonical(value)).hexdigest()
        self.records[uri]=(cid,value)
        return uri,cid

    def __call__(self,method,base,nsid,*,params):
        assert method=='GET' and base==clerk.PDS
        self.calls.append((method,nsid,params))
        author=params['repo']
        if nsid.endswith('describeRepo'):
            return {'did':author,'didDoc':{'id':author,'service':[{
                'id':'#atproto_pds','type':'AtprotoPersonalDataServer','serviceEndpoint':clerk.PDS}]}}
        uri=f'at://{author}/{params["collection"]}/{params["rkey"]}'
        cid,record=self.records[uri]
        return {'uri':uri,'cid':'wrong-cid' if self.wrong_cid else cid,'value':copy.deepcopy(record)}


class TableJourney(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def test_same_bootstrap_world_full_match_and_restart(self):
        world=self.base/'cafe'
        journey.bootstrap.run_bootstrap(world,profile='compiled')
        before=journey.bootstrap.loads((world/'world.json').read_bytes())
        report=journey.run(world)
        self.assertEqual(report['object'],journey.bootstrap.TABLE)
        self.assertEqual(report['finalRoot']['state']['game']['winner'],1)
        self.assertEqual(report['finalRoot']['state']['round'],len(journey.MATCH))
        self.assertEqual(report['cafeAfter'],report['cafeBefore'])
        after=journey.bootstrap.loads((world/'world.json').read_bytes())
        for identity,root in before['objects'].items():
            if identity!=report['object']:
                self.assertEqual(after['objects'][identity],root)
        self.assertEqual(set(before['objects']),set(after['objects']))
        self.assertEqual(journey.run(world),report)
        bundle=self.base/'table-history'
        exported=journey.bootstrap.export_bootstrap(world,bundle)
        restored=self.base/'reconstructed'
        evidence=journey.bootstrap.restore_bootstrap(bundle,restored,
            expected_genesis=exported['genesis'],expected_head=exported['head'])
        self.assertEqual(evidence['head'],exported['head'])
        rebuilt=journey.bootstrap.loads((restored/'world.json').read_bytes())
        self.assertEqual(rebuilt,after)
        self.assertEqual(journey.bootstrap.inspect_view(restored),report['cafeAfter'])
        self.assertEqual(rebuilt['objects'][report['object']],report['finalRoot'])
        self.assertTrue(any(value==report['finalRoot']['protocol']
            for path in (world/'artifacts/lowerings').glob('*.json')
            for value in journey.bootstrap.artifact_envelopes(journey.bootstrap.loads(path.read_bytes()))))

    def test_noncompiled_world_never_implicitly_migrates(self):
        directory=self.base/'old'
        directory.mkdir()
        manifest={'runtime':{'name':'transactions'}}
        (directory/'manifest.json').write_bytes(journey.bootstrap.canonical(manifest))
        with self.assertRaisesRegex(ValueError,'explicitly compiled'):
            journey.run(directory)
        self.assertFalse((directory/'world.json').exists())
        self.assertFalse((directory/'table-journey').exists())

    def test_complete_match_via_source_bound_pds_receiving(self):
        state=self.base/'clerk'
        pds=AuthoredPDS()
        receiving=clerk.Clerk(state,pds)
        seats=journey.SEATS
        cafe='cafe:repair'
        table_id='table:cafe-game'
        room=journey.bootstrap.room
        artifact=room.compile_artifact((ROOT/'examples/inhabited-bootstrap/cafe.scene').read_text())
        authority={'profile':'delvetalk-scoped-law-v1','invoke':{'start':seats},'reprogram':[],'law':[]}
        self.assertEqual(receiving.bootstrap(cafe,artifact['protocol'],authority,seats,
                                             runtime_profile='compiled')['kind'],'committed')
        added=manage.Management(state).add_object(table_id,seats[0],'add-cafe-table','protocol-json@1',
            clerk.canonical(journey.table.protocol(table_id)),journey.table.law(*seats))
        self.assertEqual(added['reply']['kind'],'committed',added)
        receipts=[]

        def authored(key,command,input,seat=0,kind='committed',object_id=table_id):
            payload={'object':object_id,'command':command,'input':input,
                     'expected':receiving.snapshot(object_id)['root']}
            uri,cid=pds.record(seats[seat],key,payload)
            result=receiving.receive(uri,cid)
            self.assertEqual(result['reply']['kind'],kind,result)
            self.assertEqual(result['request']['principal'],seats[seat])
            self.assertEqual(result['request']['intent'],'delve:'+uri)
            self.assertEqual(result['source']['cid'],cid)
            self.assertEqual(result['source']['author'],seats[seat])
            receipts.append((uri,cid,result))
            return result

        authored('enter-cafe','start',{},object_id=cafe)
        cafe_before=room.room_view(receiving.snapshot(cafe)['root'],artifact,cafe)
        self.assertEqual(cafe_before['mode'],'room')
        # A forged content CID is rejected by custody before Lean admission.
        payload={'object':table_id,'command':'commit0','input':{'round':0,'digest':'0'*64},
                 'expected':receiving.snapshot(table_id)['root']}
        uri,cid=pds.record(seats[0],'bad-cid',payload)
        pds.wrong_cid=True
        with self.assertRaisesRegex(ValueError,'CID mismatch'):
            receiving.receive(uri,cid)
        pds.wrong_cid=False
        authored('foreign-seat','commit0',{'round':0,'digest':'0'*64},seat=1,kind='refused')
        for number,moves in enumerate(journey.MATCH):
            pair=[journey.client.prepare(table_id,number,seat,*move) for seat,move in enumerate(moves)]
            for seat in (0,1):
                authored(f'r{number}-commit{seat}','commit'+str(seat),pair[seat]['commit'],seat)
            if number==len(journey.MATCH)-1:
                before=receiving.snapshot(table_id)['root']
                bad=authored('late-bad-opening','reveal1',
                    {**pair[1]['reveal'],'nonce':'f'*64},seat=1,kind='refused')
                self.assertEqual(receiving.snapshot(table_id)['root'],before)
                self.assertEqual(bad['reply']['data'],'precondition failed')
            for seat in (0,1):
                authored(f'r{number}-reveal{seat}','reveal'+str(seat),pair[seat]['reveal'],seat)
            authored(f'r{number}-resolve','resolve',{'round':number})
        final=receiving.snapshot(table_id)
        self.assertEqual(final['root']['state']['game']['winner'],1)
        self.assertEqual(final['root']['state']['game']['automaton'],0)
        self.assertEqual(final['root']['state']['round'],len(journey.MATCH))
        self.assertEqual(final['root']['version'],5*len(journey.MATCH))
        self.assertEqual(room.room_view(receiving.snapshot(cafe)['root'],artifact,cafe),cafe_before)
        authored('terminal-commit','commit0',{'round':len(journey.MATCH),'digest':'0'*64},kind='refused')
        # Restart recovers every original receipt without touching the mock network,
        # including an early refused turn and the final committed resolution.
        pds.records.clear()
        count=len(pds.calls)
        restarted=clerk.Clerk(state,pds)
        for uri,cid,result in receipts:
            self.assertEqual(restarted.receive(uri,cid),result)
        self.assertEqual(len(pds.calls),count)
        self.assertEqual(restarted.snapshot(table_id),final)
        database=clerk.loads(receiving.database.read_text())
        self.assertEqual(set(database['objects']),{cafe,table_id})


if __name__=='__main__':
    unittest.main()
