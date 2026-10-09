"""Two authors submit exact text, check, adopt, play, revise and restore a scene.

Public record GETs alone are simulated; compilation and admissions use the native
hosts. No posts, credentials, native builds or handler Python execution occur.
"""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


helpers = module('spween_handler_posts', 'conformance/test_town_forge_journey.py')
workshop = module('spween_handler_workshop', 'protocols/spween-handler-workshop/generate.py')
adapter = module('spween_handler_adapter', 'syntaxes/spween_workshop.py')
import composite_offers
import workspace


def record_field(record, name):
    return next(field['value'] for field in record['fields'] if field['name'] == name)


def repair_count(root):
    return int(record_field(record_field(root['state']['model'], 'handler'), 'repairs')['value'])


class SourceFences(unittest.TestCase):
    def test_exact_scene_and_ordered_handlers_include_crlf_and_unicode(self):
        source = workshop.authoring_source().replace('\n', '\r\n').replace('brass', 'bräss')
        parsed = adapter.parse_source(source)
        self.assertIn('\r\n', parsed['scene'])
        self.assertIn('bräss', parsed['scene'])
        self.assertEqual(parsed['modules'][0]['name'], 'Handler')
        self.assertTrue(parsed['modules'][0]['source'].endswith('\r\n'))
        extra = '```obend Helpers\r\nedition ObjectiveBend 1\r\ndef number() -> Nat:\r\n  1n\r\n```\r\n'
        parsed = adapter.parse_source(source.replace('```obend Handler', extra + '```obend Handler'))
        self.assertEqual([m['name'] for m in parsed['modules']], ['Helpers', 'Handler'])
        self.assertEqual(parsed['modules'][0]['source'], 'edition ObjectiveBend 1\r\ndef number() -> Nat:\r\n  1n\r\n')

    def test_ambiguous_or_unclosed_source_blocks_refuse(self):
        good = workshop.authoring_source()
        invalid = [good[:-4], good + '\n```spween\n=== duplicate\n```\n',
                   good.replace('obend Handler', 'obend Kernel'),
                   good.replace('obend Handler', 'obend ../Handler'),
                   good + '\n```python\nprint("no")\n```\n',
                   good.replace('spween handler workshop 1', 'spween handler workshop 2')]
        for source in invalid:
            with self.subTest(source=source[-80:]), self.assertRaises(ValueError):
                adapter.parse_source(source)


class HandlerAuthoring(helpers.TownForgeJourneyTests):
    test_maker_checks_installs_and_revises_a_door_visitors_can_use = None

    def setUp(self):
        factory_law = helpers.forge.factory_law
        with patch.object(helpers.forge, 'build', side_effect=lambda visitors, compiler:
                          workshop.build([helpers.MAKER, helpers.VISITOR], compiler)), \
             patch.object(helpers.forge, 'factory_law', side_effect=lambda makers:
                          factory_law([helpers.MAKER, helpers.VISITOR])):
            super().setUp()

    def post(self, card, fields, *, author=helpers.MAKER, parent=None, action=None):
        if card['format'] == 'delvetalk-town-adoption-card-v1':
            return super().post(card, fields, author=author, parent=parent, action=action)
        parent = parent or self.publish([card])
        self.sequence += 1
        source = (f'at://{author}/{helpers.clerk.FEED}/reply-{self.sequence}', f'reply-cid-{self.sequence}')
        if card['format'] == 'delvetalk-town-composite-card-v1':
            offered = composite_offers.action(card['offer'])
            selector = offered['command']
        else:
            actions = card['card']['actions']
            offered = next(item for item in actions if (action is None or item['id'] == action)
                           and item.get('available') and not item.get('inspectOnly'))
            # Scene choices share the native choose method. Their captured IDs
            # distinguish bound inputs; a method name alone would be ambiguous.
            selector = helpers.town_cards.action_word(offered, actions)
        text = helpers.town_cards.spell(card['alias'], offered, fields, selector=selector)
        self.pds.records[source[0]] = (source[1], {'$type': helpers.clerk.FEED, 'text': text,
                                                'reply': {'root': parent, 'parent': parent}})
        return source

    def play(self, card, label, *, author=helpers.VISITOR, parent=None):
        action = next(item for item in card['card']['actions'] if item['label'] == label)
        return self.reply(card, {}, author=author, parent=parent, action=action['id'])

    def revision(self, target, name, revision, *, author):
        _, made = self.reply(self.capture('desks'), {'name': name}, author=author)
        self.committed(made)
        candidate = 'desks/' + name
        before = copy.deepcopy(self.root(target))
        offer = workshop.submission_offer(candidate, self.root(candidate), target, before)
        card = self.book.capture_composite(offer, alias='write-' + name)
        source, submitted = self.reply(card, {'source': workshop.authoring_source(revision),
            'scenarios': workshop.examples()}, author=author)
        self.committed(submitted)
        pending = self.root(candidate)
        self.assertEqual(pending['state']['proposal']['syntax'], workshop.SYNTAX)
        self.assertEqual(pending['state']['submitter'], author)
        self.assertEqual(pending['state']['proposal']['source'], workshop.authoring_source(revision))
        self.assertEqual(pending['state']['migration'], before['state'])
        text = self.pds.records[source[0]][1]['text']
        self.assertIn('```spween', text)
        self.assertIn('```obend Handler', text)
        ready = self.check(candidate, source)
        self.assertEqual(ready['status'], 'ready', ready)
        self.assertEqual(self.root(target), before, 'checking source must not install it')
        self.assertTrue(all(not fixture['failures'] for fixture in ready['fixtures']))
        _, installed = self.reply(ready['cards'][0], {}, author=author)
        self.committed(installed)
        self.assertEqual(self.root(target)['state'], before['state'])
        self.assertEqual(self.root(target)['law'], before['law'])
        return candidate

    def test_two_authors_preserve_handler_state_and_restore_exact_source_history(self):
        target, _ = self.make('objects', 'moth-workshop')
        first = self.revision(target, 'first-moth', 1, author=helpers.MAKER)
        _, started = self.play(self.capture(target), 'Start', author=helpers.MAKER)
        self.committed(started)
        start_card = self.capture(target)
        self.assertNotIn('Release the brass moth', [a['label'] for a in start_card['card']['actions']])
        before = self.root(target)
        start_parent = self.publish([start_card])
        _, refused = self.play(start_card, 'Try the impossible hinge', parent=start_parent)
        self.assertEqual(refused['receipt']['reply']['kind'], 'refused')
        self.assertEqual(self.root(target), before)
        _, repaired = self.play(start_card, 'Mend the brass moth', author=helpers.MAKER, parent=start_parent)
        self.committed(repaired)
        self.assertEqual(repair_count(self.root(target)), 1)
        old = self.capture(target)
        old_parent = self.publish([old])
        self.assertIn('Release the brass moth', [a['label'] for a in old['card']['actions']])
        second = self.revision(target, 'moth-chorus', 2, author=helpers.VISITOR)
        self.assertEqual(repair_count(self.root(target)), 1, 'revision preserved the previous repair')
        _, stale = self.play(old, 'Release the brass moth', parent=old_parent)
        self.assertEqual(stale['receipt']['reply']['data'], 'stale read root')
        for label in ('Release the brass moth', 'Return to the workbench', 'Mend the brass moth'):
            _, response = self.play(self.capture(target), label)
            self.committed(response)
        self.assertEqual(repair_count(self.root(target)), 3, 'new ordinary handler adds two repairs')
        final = self.root(target)
        for candidate, revision in ((first, 1), (second, 2)):
            identity = self.root(candidate)['state']['artifact']
            build = workshop.desk.load_artifact(self.home / 'artifacts', identity)
            self.assertEqual(build['sourceMaterial']['source'], workshop.authoring_source(revision))
            lowered = build['report']['candidate']['artifact']['lowered']
            parsed = adapter.parse_source(workshop.authoring_source(revision))
            self.assertEqual(lowered['spweenWorkshop']['scene'], parsed['scene'])
            self.assertEqual(lowered['spweenWorkshop']['modules'], parsed['modules'])

        exported = self.base / 'source-history'
        checkpoint = workspace.bootstrap.export_bootstrap(self.home, exported)
        restored = self.base / 'restored'
        evidence = workspace.bootstrap.restore_bootstrap(exported, restored,
            expected_genesis=checkpoint['genesis'], expected_head=checkpoint['head'])
        self.assertEqual(helpers.clerk.loads((restored / 'world.json').read_bytes()),
                         helpers.clerk.loads(self.clerk.database.read_bytes()))
        for candidate in (first, second):
            identity = self.root(candidate)['state']['artifact']
            self.assertIn(identity, evidence['builds'])
            self.assertEqual((restored / 'artifacts/builds' / (identity + '.json')).read_bytes(),
                             (self.home / 'artifacts/builds' / (identity + '.json')).read_bytes())
        client = workshop.desk.Desk(restored / 'world.json', restored / 'artifacts', profile='compiled')
        self.assertEqual(client.inspect(target), final)
        view = workspace.bootstrap.room.inspect_object(client.inspect(target), target)
        self.assertEqual(view['mode'], 'projection')
        self.assertIn('Release the brass moth', [a['text'] for a in view['data']['actions'].values()])
        before_retry = client.database.read_bytes()
        self.assertEqual(client.exchange(response['receipt']['request']), response['receipt']['reply'])
        self.assertEqual(client.database.read_bytes(), before_retry)


if __name__ == '__main__':
    unittest.main()
