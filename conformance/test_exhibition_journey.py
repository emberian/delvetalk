#!/usr/bin/env python3
"""Source exhibition composition, arrangement-bound approval and exact replay."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'protocols/shared-exhibition'
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import source_store
import propose
import world


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


package = module('exhibition_package_test', PACKAGE / 'package.py')


class ExhibitionSource(unittest.TestCase):
    def test_reusable_modules_and_authored_domain_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            modules = package.modules()
            entries = [{'name': item['name'], 'sourceRef': source_store.store_bytes(directory, item['source'].encode())}
                       for item in modules]
            material = source_store.resolve_modules(directory, source_store.seal_modules(entries))
            report = propose.propose('objective-bend-spell@3', b'', (PACKAGE / 'exhibition.examples').read_bytes(),
                                     profile='compiled', modules=material)
            self.assertTrue(report['passed'], report)
            program = report['candidate']['artifact']['lowered']
            other = package.build({'north':'moss','south':'iris','curator':'requester'})
            self.assertEqual(other['sourcePackages'], program['sourcePackages'])
            self.assertEqual(source_object.plain(other['initial']['model'])['participants'],
                             {'north':'moss','south':'iris','curator':'requester'})
            self.assertIn('approved', next(m['source'] for m in modules if m['name']=='Agreement'))

    def test_old_approval_cannot_open_a_different_arrangement_or_confer_a_grant(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'world.json'
            program = package.build()
            serial = 0
            def call(request):
                nonlocal serial
                serial += 1
                return world.exchange(db, {'principal':'curator','intent':'agreement-'+str(serial),**request}, profile='compiled')
            made = call({'op':'create','object':'room','protocol':program,
                         'law':{'profile':'delvetalk-scoped-law-v1',
                                'invoke':{'open':['curator'],'consentNorth':['north'],'consentSouth':['south']},
                                'reprogram':['curator'],'law':['curator']}})
            self.assertEqual(made['kind'], 'committed', made)
            root = made['data']['root']
            model = copy.deepcopy(root['state']['model'])
            fields = {f['name']:f for f in model['fields']}
            fields['arranged']['value'] = source_object.data(True)
            fields['arrangement']['value'] = source_object.data({'revision':2,'caption':'A different arrangement','first':'south'})
            fields['northConsent']['value'] = source_object.variant('approved',source_object.data({'revision':1}))
            fields['southConsent']['value'] = source_object.variant('approved',source_object.data({'revision':2}))
            revised = call({'op':'reprogram','object':'room','expected':root,'protocol':program,'state':{'model':model}})
            self.assertEqual(revised['kind'], 'committed', revised)
            root = revised['data']['root']
            refused = call({'op':'invoke','object':'room','expected':root,'command':'open','input':{}})
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertIn('exact arrangement', refused['data'])
            self.assertEqual(call({'op':'inspect','object':'room'}),root)
            renewed = call({'op':'invoke','object':'room','principal':'north','expected':root,'command':'consentNorth','input':{}})
            self.assertEqual(renewed['kind'], 'committed', renewed)
            root = renewed['data']['root']
            # Both source approval proofs now match, but current management can
            # revoke the curator's grant; an approval is still not authority.
            law = copy.deepcopy(root['law']); law['invoke']['open']=[]
            revised = call({'op':'law','object':'room','expected':root,'law':law})
            root = revised['data']['root']
            denied = call({'op':'invoke','object':'room','expected':root,'command':'open','input':{}})
            self.assertEqual(denied['data'],'unauthorized')
            self.assertEqual(call({'op':'inspect','object':'room'}),root)


class ExhibitionJourney(unittest.TestCase):
    def test_three_roles_build_inhabit_and_export_their_exact_world(self):
        journey = module('exhibition_journey', PACKAGE / 'run.py')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'exhibition'
            result = journey.run(directory)
            self.assertTrue(result['state']['opened'])
            self.assertEqual(result['version'], 7)
            self.assertEqual(result['verification']['status'], 'verified-offline')
            self.assertEqual(result['verification']['objects'], 2)
            self.assertEqual(result['verification']['proofScope'], 'exact-artifact-replay')
            snapshot = json.loads((directory / 'world.json').read_text())
            refused = [item for item in snapshot['receipts'] if item['receipt']['kind'] == 'refused']
            self.assertEqual(len(refused), 5)
            self.assertEqual(result['continuation']['admissions'], len(snapshot['receipts']))
            build = next((directory / 'artifacts/builds').glob('*.json'))
            artifact = json.loads(build.read_text())
            self.assertTrue(artifact['report']['passed'])
            self.assertEqual(artifact['sourceBindings']['syntax'],'objective-bend-spell@3')
            self.assertEqual([item['name'] for item in artifact['sourceMaterial']['modules']],
                             ['Abi','Encounter','Agreement','Exhibition'])
            self.assertEqual(result['state']['northConsent']['payload']['revision'],
                             result['state']['arrangement']['revision'])
            events = [json.loads(path.read_text()) for path in (directory / 'events').glob('*.json')]
            malformed = next(item for item in events if item['event'] == 'typed-token-rejects-boolean-nat')
            self.assertEqual(malformed['result']['status'], 'clarify')


if __name__ == '__main__': unittest.main()
