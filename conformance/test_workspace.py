#!/usr/bin/env python3
"""Independent explicit seeds, generic views, and source-complete reconstruction."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workspace_test_module', ROOT / 'scripts/workspace.py')
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)
b = workspace.bootstrap


def protocol(title='A quiet entry'):
    return {'profile':'delvetalk-local-v1','name':'entry','initial':{'title':title,'message':'Ready'},
            'commands':{'write':{'require':[],'set':{'message':['input','message']},
                                'result':['state','message'],'outbox':[]}}}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def seed(self, destination, **kwargs):
        return workspace.initialize(destination, [{'id':'entry:one','syntax':'protocol-json@1',
            'source':b.canonical(protocol()),'law':['builder']}], entry_objects=['entry:one'],
            principal='builder', title='An independent world', **kwargs)

    def test_fresh_independent_worlds_share_empty_genesis_not_private_history(self):
        one, two = self.directory/'one', self.directory/'two'
        first = self.seed(one)
        second = workspace.initialize(two,[{'id':'somewhere:else','syntax':'protocol-json@1',
            'source':b.canonical(protocol('Elsewhere')),'law':[]}], entry_objects=['somewhere:else'], principal='other')
        self.assertEqual(first['genesis'],second['genesis'])
        self.assertNotEqual(first['head'],second['head'])
        self.assertNotEqual(first['worldId'],second['worldId'])
        self.assertEqual(first['entries'],1)
        self.assertEqual(second['entries'],1)
        state = b.loads((one/'world.json').read_bytes())
        self.assertEqual(list(state['objects']),['entry:one'])
        self.assertEqual(len(state['receipts']),1)
        metadata = b.loads((one/'manifest.json').read_bytes())
        self.assertEqual(metadata['genesis']['world'],{'objects':{},'receipts':[]})
        self.assertEqual(b.default_object(metadata),'entry:one')
        self.assertEqual(b.world_id(metadata),first['worldId'])
        self.assertIn(first['worldId'],state['receipts'][0]['request']['intent'])
        self.assertNotIn('cafe',metadata)
        self.assertEqual(b.inspect_view(one)['object'],'entry:one')
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.seed(one)
        self.assertEqual(b.loads((one/'world.json').read_bytes()),state)

    def test_failed_seed_and_invalid_entry_never_publish_partial_world(self):
        invalid = protocol()
        invalid['commands']['write']['result']=['unsafe-shell','no']
        destination=self.directory/'bad'
        with self.assertRaisesRegex(ValueError,'seed refused'):
            workspace.initialize(destination,[{'id':'bad','syntax':'protocol-json@1',
                'source':b.canonical(invalid),'law':['builder']}],entry_objects=['bad'],principal='builder')
        self.assertFalse(destination.exists())
        with self.assertRaisesRegex(ValueError,'entry objects'):
            workspace.initialize(destination,[{'id':'good','syntax':'protocol-json@1',
                'source':b.canonical(protocol()),'law':[]}],entry_objects=['missing'],principal='builder')
        self.assertFalse(destination.exists())

    def test_generic_room_and_projection_restore_without_demo_objects(self):
        original=self.directory/'original'
        scene=b'---\nid: garden\ntitle: A garden\n---\n=== gate\nAn unclaimed path.\n* [Walk]\n  -> END\n'
        workspace.initialize(original,[
            {'id':'garden','syntax':'spween-scene-i64@1','source':scene,'law':['visitor']},
            {'id':'sign','syntax':'protocol-json@1','source':(ROOT/'scene/projections/sign-v1.json').read_bytes(),'law':['visitor']}],
            entry_objects=['garden','sign'],default_object='sign',principal='builder',title='A garden and sign')
        bundle=self.directory/'bundle'
        evidence=b.export_bootstrap(original,bundle)
        shutil.rmtree(original)
        restored=self.directory/'restored'
        result=b.restore_bootstrap(bundle,restored,expected_genesis=evidence['genesis'],expected_head=evidence['head'])
        self.assertEqual(result['format'],'delvetalk-workspace-reconstruction-v1')
        self.assertEqual(result['defaultObject'],'sign')
        self.assertEqual(b.world_id(b.loads((restored/'manifest.json').read_bytes())),result['worldId'])
        self.assertEqual(b.inspect_view(restored)['mode'],'projection')
        room=b.inspect_view(restored,'garden')
        self.assertEqual(room['mode'],'room')
        self.assertEqual(room['source'].encode(),scene)
        request=b.room.start_request(room,'visitor','enter-restored')
        desk=b.desk_module.Desk(restored/'world.json',restored/'artifacts')
        self.assertEqual(desk.exchange(request)['kind'],'committed')
        self.assertEqual(set(b.loads((restored/'world.json').read_bytes())['objects']),{'garden','sign'})
        self.assertTrue((restored/'index.html').is_file())

    def test_index_changes_cannot_relabel_anchored_history(self):
        destination=self.directory/'indexed'
        self.seed(destination)
        path=destination/'manifest.json'
        manifest=b.loads(path.read_bytes())
        manifest['title']='A different claimed world'
        path.write_bytes(b.canonical(manifest))
        with self.assertRaisesRegex(ValueError,'index differs'):
            b.export_bootstrap(destination,self.directory/'relabeled')

    def test_namespace_tamper_refuses_even_when_index_is_rehashed(self):
        destination=self.directory/'namespaced'
        seed=self.seed(destination,world_id='urn:example:original')
        path=destination/'manifest.json'
        manifest=b.loads(path.read_bytes())
        self.assertEqual(seed['worldId'],'urn:example:original')
        manifest['worldId']='urn:example:impostor'
        path.write_bytes(b.canonical(manifest))
        with self.assertRaisesRegex(ValueError,'worldId differs'):
            b.export_bootstrap(destination,self.directory/'impostor-bundle')
        records=b.loads((destination/'world.json').read_bytes())['receipts']
        with self.assertRaisesRegex(ValueError,'worldId differs'):
            b.validate_workspace_identity(manifest,records)

    def test_pending_reference_sources_restore_exactly_before_compilation(self):
        source_store=b.module('workspace_source_store_test','scripts/source_store.py')
        destination=self.directory/'source-workspace'
        source_protocol=(ROOT/'protocols/source-desk/protocol.json').read_bytes()
        workspace.initialize(destination,[{'id':'desk','syntax':'protocol-json@1','source':source_protocol,
            'law':['author','compiler']}],entry_objects=['desk'],principal='builder')
        source=b'# A large source card\n' + b'annotation remains opaque\n'*3000 + b'```delvetalk-protocol\n'+b.canonical(protocol())+b'\n```\n'
        scenarios=b.canonical([{'name':'write','law':['author'],'steps':[
            {'principal':'author','command':'write','input':{'message':'Hello'},'root':'initial','kind':'committed'}]}])
        proposal=source_store.prepare_proposal(destination/'artifacts','protocol-markdown@1',source,scenarios)
        desk=b.desk_module.Desk(destination/'world.json',destination/'artifacts')
        receipt=desk.exchange({'op':'invoke','object':'desk','principal':'author','intent':'submit-large',
            'expected':desk.inspect('desk'),'command':'submit','input':{'proposal':proposal,'migration':{},'target':'later'}})
        self.assertEqual(receipt['kind'],'committed')
        self.assertGreater(len(source),65536)
        self.assertLess(len(b.canonical(receipt['data']['root'])),65536)
        bundle=self.directory/'source-bundle'
        anchors=b.export_bootstrap(destination,bundle)
        shutil.rmtree(destination)
        restored=self.directory/'source-restored'
        b.restore_bootstrap(bundle,restored,expected_genesis=anchors['genesis'],expected_head=anchors['head'])
        pending=b.desk_module.Desk(restored/'world.json',restored/'artifacts').inspect('desk')
        self.assertEqual(pending['state']['status'],'pending')
        exact_source,exact_scenarios=source_store.validate_proposal(restored/'artifacts',pending['state']['proposal'])
        self.assertEqual(exact_source,source)
        self.assertEqual(exact_scenarios,scenarios)
        self.assertTrue(source_store.declared_dependencies(pending))

    def test_restored_workspace_reuses_original_seed_for_clerk_and_service(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import clerk, service
        original=self.directory/'service-origin'
        seed=self.seed(original)
        desk=b.desk_module.Desk(original/'world.json',original/'artifacts')
        receipt=desk.exchange({'op':'invoke','object':'entry:one','principal':'builder','intent':'post-seed-work',
            'expected':desk.inspect('entry:one'),'command':'write','input':{'message':'Continued'}})
        self.assertEqual(receipt['kind'],'committed')
        evidence=b.export_bootstrap(original,self.directory/'service-bundle')
        restored=self.directory/'service-restored'
        b.restore_bootstrap(self.directory/'service-bundle',restored,
            expected_genesis=evidence['genesis'],expected_head=evidence['head'])
        restored_seed=b.loads((restored/'seed.json').read_bytes())
        self.assertEqual(restored_seed['head'],seed['head'])
        self.assertEqual(restored_seed['entries'],1)
        self.assertNotEqual(restored_seed['head'],evidence['head'])
        roots=b.loads((restored/'world.json').read_bytes())['objects']
        receiver=clerk.Clerk(self.directory/'attached-clerk')
        receiver.attach(restored,roots,[clerk.delve.DID],expected_genesis=seed['genesis'],
                        expected_seed_head=seed['head'],runtime_profile='transactions')
        app=service.Service(self.directory/'attached-service')
        configured=app.initialize(restored,receiver.state,'compiler',public_genesis=seed['genesis'])
        self.assertEqual(configured['status'],'configured')
        # An extra initial-looking admission must not enlarge the original seed.
        metadata=b.loads((restored/'manifest.json').read_bytes())
        self.assertEqual(metadata['seedObjects'],['entry:one'])
        extended_desk=b.desk_module.Desk(restored/'world.json',restored/'artifacts')
        extra=extended_desk.exchange({'op':'create','object':'extra','principal':'builder',
            'intent':'workspace-seed:'+seed['worldId']+':1','protocol':protocol(),'law':['builder']})
        self.assertEqual(extra['kind'],'committed')
        b.preserve_lowering(restored,b.canonical(protocol()))
        extended=b.export_bootstrap(restored,self.directory/'extra-bundle')
        again=self.directory/'again'
        b.restore_bootstrap(self.directory/'extra-bundle',again,expected_genesis=extended['genesis'],expected_head=extended['head'])
        self.assertEqual(b.loads((again/'seed.json').read_bytes())['head'],seed['head'])

    def test_ordinary_compiled_command_has_no_source_desk_artifact_obligation(self):
        program=protocol()
        program['commands']['compiled']=program['commands'].pop('write')
        destination=self.directory/'ordinary'
        workspace.initialize(destination,[{'id':'ordinary','syntax':'protocol-json@1',
            'source':b.canonical(program),'law':['builder']}],entry_objects=['ordinary'],principal='builder')
        desk=b.desk_module.Desk(destination/'world.json',destination/'artifacts')
        receipt=desk.exchange({'op':'invoke','object':'ordinary','principal':'builder','intent':'ordinary-command',
            'expected':desk.inspect('ordinary'),'command':'compiled',
            'input':{'message':'ok','artifact':'application-defined-label'}})
        self.assertEqual(receipt['kind'],'committed')
        evidence=b.export_bootstrap(destination,self.directory/'ordinary-export')
        self.assertEqual(evidence['entries'],2)

    def test_cli_plan_is_explicit_and_inspect_uses_selected_entry(self):
        (self.directory/'entry.json').write_bytes(b.canonical(protocol()))
        plan={'title':'CLI world','entryObjects':['home'],'defaultObject':'home','objects':[
            {'id':'home','syntax':'protocol-json@1','source':'entry.json','law':['builder']}]}
        (self.directory/'plan.json').write_bytes(b.canonical(plan))
        destination=self.directory/'cli-world'
        command=[sys.executable,str(ROOT/'scripts/workspace.py')]
        result=subprocess.run(command+['init',str(destination),'--plan',str(self.directory/'plan.json'),
            '--principal','builder'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(b.loads(result.stdout)['entries'],1)
        viewed=subprocess.run(command+['inspect',str(destination)],capture_output=True,text=True)
        self.assertEqual(viewed.returncode,0,viewed.stderr)
        self.assertEqual(b.loads(viewed.stdout)['object'],'home')


if __name__=='__main__':
    unittest.main()
