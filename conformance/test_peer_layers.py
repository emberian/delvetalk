"""Exact peer-authored modules, real open recursion, posts and retained assembly custody.

Public repository GET transport alone is simulated. Source references identify
bytes; fetched post identities and operator attestations remain separate evidence.
Native hosts must already exist; this test never builds or publishes.
"""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
_spec = importlib.util.spec_from_file_location('peer_post_helpers', ROOT / 'conformance/test_town_forge_journey.py')
helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helpers)
import continuation
import source_store
import workspace

PACKAGE = ROOT / 'protocols/peer-layers'


class PeerLayers(helpers.TownForgeJourneyTests):
    test_maker_checks_installs_and_revises_a_door_visitors_can_use = None

    def setUp(self):
        original = helpers.forge.build_stateful
        def configured(visitors, compiler):
            factories = original(visitors, compiler, methods=['ring', 'stamp', 'base'],
                state_fields={'value': {'type': 'nat', 'label': 'Retained rings', 'minimum': 0, 'maximum': 10000}})
            generic = helpers.clerk.loads((ROOT / 'protocols/factories/source-desk.json').read_bytes())
            generic['initial']['compiler'] = compiler
            factories['desks'] = generic
            return factories
        with patch.object(helpers.forge, 'build', side_effect=configured):
            super().setUp()
        self.module_posts = {}

    def post(self, card, fields, *, action=None, **kwargs):
        if action is not None:
            action = next(item['id'] for item in card['card']['actions'] if item['command'] == action)
        return super().post(card, fields, action=action, **kwargs)

    def retain_module_post(self, name, filename, author):
        self.sequence += 1
        uri = f'at://{author}/{helpers.clerk.FEED}/module-{self.sequence}'
        cid = 'module-cid-' + str(self.sequence)
        source = (PACKAGE / filename).read_text()
        record = {'$type': helpers.clerk.FEED, 'text': source}
        self.pds.records[uri] = (cid, copy.deepcopy(record))
        self.clerk.verify_repository(author)
        fetched = self.clerk.fetch_record(uri, cid, (helpers.clerk.FEED,))
        self.assertEqual(fetched, record)
        evidence = {'source': {'uri': uri, 'cid': cid, 'author': author},
                    'record': fetched, 'recordSha256': helpers.clerk.digest(fetched)}
        helpers.clerk.save(self.base / 'peer-posts' / (name + '-' + cid + '.json'), evidence)
        ref = source_store.store_bytes(self.home / 'artifacts', fetched['text'].encode(), kind='source')
        self.module_posts[ref['sha256']] = evidence
        return {'name': name, 'sourceRef': ref}

    def submit_package(self, target, name, modules, examples, migration):
        candidate, _ = self.make('desks', name)
        manifest = source_store.seal_modules(modules)
        proposal = source_store.prepare_module_proposal(self.home / 'artifacts', manifest,
            (PACKAGE / examples).read_bytes())
        selected = [self.module_posts[entry['sourceRef']['sha256']]['source'] for entry in modules]
        self.sequence += 1
        uri = f'at://{helpers.MAKER}/{helpers.clerk.FEED}/assembly-{self.sequence}'
        cid = 'assembly-cid-' + str(self.sequence)
        text = 'Install this ordered score in ' + target + ':\n' + '\n'.join(
            entry['name'] + ' from ' + origin['uri'] + ' at ' + origin['cid']
            for entry, origin in zip(modules, selected))
        self.pds.records[uri] = (cid, {'$type': helpers.clerk.FEED, 'text': text})
        decision = {'status': 'act', 'interpreter': 'local assembly operator',
            'basis': 'Use these exact peer posts in their listed order; preserve the explicitly reviewed state.',
            'request': {'object': candidate, 'command': 'submit', 'expected': self.root(candidate),
                        'input': {'proposal': proposal, 'migration': migration, 'target': target}}}
        reply = self.operator.receive(uri, cid, interpretation=decision)
        self.committed(reply)
        self.assertEqual(reply['receipt']['request']['principal'], helpers.MAKER)
        self.assertEqual(reply['receipt']['interpretation']['decision'], decision)
        self.assertEqual(self.root(candidate)['state']['proposal'], proposal)
        return candidate, (uri, cid), proposal

    def play(self, target, command, expected, author=helpers.VISITOR):
        _, response = self.reply(self.capture(target), {}, action=command, author=author)
        self.committed(response)
        self.assertEqual(response['receipt']['reply']['data']['result'], expected)
        return response

    def test_peers_share_sealed_layers_without_sharing_mutation_or_authority(self):
        base = self.retain_module_post('Base', 'Base.obend', helpers.VISITOR)
        override = self.retain_module_post('Doubling', 'Doubling.obend', helpers.MAKER)
        main = self.retain_module_post('Main', 'Main.obend', helpers.MAKER)
        modules = [base, override, main]
        base_bytes = source_store.read_bytes(self.home / 'artifacts', base['sourceRef'], kind='source')
        self.assertEqual(base_bytes, (PACKAGE / 'Base.obend').read_bytes())
        first, _ = self.make('objects', 'peer-bell')
        second, _ = self.make('objects', 'second-bell')
        candidates = []
        for target, name in ((first, 'first-assembly'), (second, 'second-assembly')):
            candidate, source, proposal = self.submit_package(target, name, modules,
                'doubling.examples', {'value': 0})
            ready = self.check(candidate, source)
            self.assertEqual(ready['status'], 'ready', ready)
            build = helpers.compiler_queue.desk.load_artifact(self.home / 'artifacts',
                self.root(candidate)['state']['artifact'])
            self.assertEqual(build['sourceBindings']['manifest'], proposal['manifest'])
            self.assertEqual(build['sourceMaterial']['manifest'], proposal['manifest'])
            self.assertEqual(build['sourceMaterial']['modules'], [{**entry,
                'source': source_store.read_bytes(self.home / 'artifacts', entry['sourceRef'], kind='source').decode()}
                for entry in modules])
            _, adopted = self.reply(ready['cards'][0], {})
            self.committed(adopted)
            installed_protocol = self.root(target)['protocol']
            package_selector = installed_protocol['commands']['ring']['transition']['package']
            self.assertEqual(package_selector['format'], 'delvetalk-source-package-ref-v1')
            installed_modules = installed_protocol['sourcePackages'][package_selector['name']]['modules']
            self.assertEqual(installed_modules, [{'name': entry['name'],
                'source': source_store.read_bytes(self.home / 'artifacts', entry['sourceRef'], kind='source').decode()}
                for entry in modules])
            candidates.append(candidate)
            self.assertEqual(self.root(candidate)['state']['proposal'], proposal)
        self.play(first, 'ring', 42)
        self.play(first, 'stamp', 11)
        self.play(first, 'base', 41)
        self.play(second, 'ring', 42)
        second_before_revision = copy.deepcopy(self.root(second))

        # Ref identities and manifest order are bounded custody, not a substitute
        # for the native compiler's earlier-module import requirements.
        for changed in ('missing', 'tampered'):
            entries = copy.deepcopy(modules)
            if changed == 'missing':
                entries[0]['sourceRef']['sha256'] = '0' * 64
            else:
                entries[0]['sourceRef']['bytes'] += 1
            with self.assertRaises((ValueError, FileNotFoundError)):
                manifest = source_store.seal_modules(entries)
                source_store.prepare_module_proposal(self.home / 'artifacts', manifest,
                    (PACKAGE / 'doubling.examples').read_bytes())
        reordered = [override, base, main]
        bad, source, _ = self.submit_package(first, 'bad-order', reordered,
            'doubling.examples', copy.deepcopy(self.root(first)['state']))
        failed = self.check(bad, source)
        self.assertEqual(failed['status'], 'failed', failed)
        self.assertEqual(failed['cards'], [])
        candidates.append(bad)

        updated = self.retain_module_post('Doubling', 'Tripling.obend', helpers.MAKER)
        revised_modules = [base, updated, main]
        retained_state = copy.deepcopy(self.root(first)['state'])
        revision, source, proposal = self.submit_package(first, 'three-note-assembly', revised_modules,
            'tripling.examples', retained_state)
        ready = self.check(revision, source)
        self.assertEqual(ready['status'], 'ready', ready)
        old_adoption = ready['cards'][0]
        parent = self.publish([old_adoption], ready['body'])
        self.play(first, 'stamp', 11)  # Advances root without changing retained state.
        before_desk, before_target = self.root(revision), self.root(first)
        _, stale = self.reply(old_adoption, {}, parent=parent)
        self.assertEqual(stale['receipt']['reply']['data'], 'stale read root')
        self.assertEqual(self.root(revision), before_desk)
        self.assertEqual(self.root(first), before_target)
        fresh = self.book.capture_adoption(revision, before_desk, first, before_target, alias='current-peer-score')
        _, adopted = self.reply(fresh, {})
        self.committed(adopted)
        self.assertEqual(self.root(first)['state'], retained_state)
        self.assertEqual(self.root(second), second_before_revision)
        self.play(first, 'ring', 43)
        self.play(first, 'stamp', 11)
        self.play(first, 'base', 41)
        unchanged = self.play(second, 'ring', 42)
        candidates.append(revision)
        self.assertEqual(source_store.read_bytes(self.home / 'artifacts', base['sourceRef'], kind='source'), base_bytes)
        self.assertEqual(self.root(revision)['state']['proposal'], proposal)

        bundle, restored = self.base / 'peer-history', self.base / 'restored'
        exported = workspace.bootstrap.export_bootstrap(self.home, bundle)
        continuation.prepare(bundle, self.base / 'peer-continuation',
            expected_genesis=exported['genesis'], expected_head=exported['head'])
        workspace.bootstrap.restore_bootstrap(bundle, restored,
            expected_genesis=exported['genesis'], expected_head=exported['head'])
        self.assertEqual(helpers.clerk.loads((restored / 'world.json').read_bytes()),
                         helpers.clerk.loads(self.clerk.database.read_bytes()))
        for entry in modules + [updated]:
            self.assertEqual(source_store.read_bytes(restored / 'artifacts', entry['sourceRef'], kind='source'),
                             source_store.read_bytes(self.home / 'artifacts', entry['sourceRef'], kind='source'))
        for candidate in candidates:
            artifact = self.root(candidate)['state']['artifact']
            self.assertEqual((restored / 'artifacts/builds' / (artifact + '.json')).read_bytes(),
                             (self.home / 'artifacts/builds' / (artifact + '.json')).read_bytes())
        recovered = helpers.compiler_queue.desk.Desk(restored / 'world.json', restored / 'artifacts', profile='compiled')
        before_retry = recovered.database.read_bytes()
        self.assertEqual(recovered.exchange(unchanged['receipt']['request']), unchanged['receipt']['reply'])
        self.assertEqual(recovered.database.read_bytes(), before_retry)


class SealedManifestChecks(unittest.TestCase):
    def entries(self):
        return [{'name': name, 'sourceRef': source_store.reference(text.encode(), kind='source')}
                for name, text in [('Base', 'exact base\r\n'), ('Main', 'exact main\n')]]

    def test_manifest_order_names_and_aggregate_are_explicit_and_sealed(self):
        entries = self.entries()
        sealed = source_store.seal_modules(entries)
        reordered = copy.deepcopy(sealed)
        reordered['modules'].reverse()
        with self.assertRaisesRegex(ValueError, 'sealed module manifest|module order'):
            source_store.validate_manifest(reordered)
        with self.assertRaisesRegex(ValueError, 'distinct'):
            source_store.seal_modules([entries[0], entries[0]])
        too_large = [{'name': name, 'sourceRef': {**entries[0]['sourceRef'], 'bytes': size}}
                     for name, size in [('Base', 512 * 1024), ('More', 512 * 1024), ('Main', 1)]]
        with self.assertRaisesRegex(ValueError, 'aggregate'):
            source_store.seal_modules(too_large)

    def test_resolved_module_material_retains_exact_names_order_and_bytes(self):
        entries = self.entries()
        material = {'format': source_store.MODULE_MATERIAL, 'manifest': source_store.seal_modules(entries),
                    'modules': [{**entries[0], 'source': 'exact base\r\n'},
                                {**entries[1], 'source': 'exact main\n'}]}
        self.assertEqual(source_store.validate_module_material(material), material)
        for mutation in ('name', 'order', 'text', 'bytes', 'sha'):
            changed = copy.deepcopy(material)
            if mutation == 'name':
                changed['modules'][0]['name'] = 'Different'
            elif mutation == 'order':
                changed['modules'].reverse()
            elif mutation == 'text':
                changed['modules'][0]['source'] = 'exact base\n'  # CRLF is significant.
            elif mutation == 'bytes':
                changed['modules'][0]['sourceRef']['bytes'] += 1
            else:
                changed['modules'][0]['sourceRef']['sha256'] = '0' * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                source_store.validate_module_material(changed)


if __name__ == '__main__':
    unittest.main()
