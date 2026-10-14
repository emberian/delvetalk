"""Refresh regressions using wire-shaped journals and an in-memory host, without Lean."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import genesis
from tests.wire import cid_of, field, record, relation, write_journal


class RefreshHost:
    """The refresh ops; admitted identities replay their receipt without writing again."""

    def __init__(self):
        self.objects = {}
        self.receipts = {}
        self.requests = []
        self.entries = []
        self.fail = None
        self.wings = set()
        self.ignore_shelve = False

    def put(self, obj, own_law='', **state):
        self.objects[obj] = {'version': 0, 'law': own_law, 'state': state}

    def send(self, request):
        self.requests.append(copy.deepcopy(request))
        op, obj = request['op'], request.get('object')
        held = self.objects.get(obj)
        if op == 'world-objects':
            return {'status': 'listed', 'ids': sorted(self.objects)}
        if op == 'world-object':
            return {'status': 'object', 'record': {k: v for k, v in held.items() if k != 'state'}} if held else {'status': 'unknown'}
        if op == 'world-view':
            return {'status': 'viewed', 'state': record(**held['state'])} if held else {'status': 'unknown'}
        if op == 'world-rules':
            return {'status': 'rules', 'object': obj, 'rows': held.get('rules', [])} if held else {'status': 'unknown'}
        identity = request['identity']
        if identity == self.fail:
            self.fail = None
            return {'status': 'refused', 'message': 'injected before admission'}
        digest = json.dumps(request, sort_keys=True)
        if identity in self.receipts:
            before, reply = self.receipts[identity]
            return copy.deepcopy(reply) if before == digest else {'status': 'refused', 'message': 'duplicateIdentity'}
        outcome = {'tag': 'admitted'}
        status = 'admitted'
        if op == 'world-amend':
            outcome['amendments'] = [{'object': obj, 'old': held['law'], 'new': request['law']}]
            held['law'] = request['law']
            held['version'] += 1
        elif op == 'world-propose':
            for write in request['writes']:
                for edit in write['edits']:
                    for f in edit['fields']:
                        self.objects[write['object']]['state'][f['name']] = field(f['value']['payload'], 'value')
                self.objects[write['object']]['version'] += 1
            outcome['writes'] = request['writes']
        elif op == 'world-create':
            self.put(obj, **{f['name']: f['value'] for f in request['seed']['fields']})
            status = 'created'
        elif op == 'world-turn' and request['method'] == 'reshape':
            held['state']['form'] = field(request['argument'], 'form')
            held['version'] += 1
        elif op == 'world-turn' and request['method'] == 'shelve':
            if not self.ignore_shelve:
                page = {f['name']: f['value'] for f in request['argument']['fields']}
                name = page['name']['value']
                pages = field(held['state']['pages']['payload'], 'items')['items']
                pages[:] = [p for p in pages if field(p, 'name')['value'] != name]
                pages.append(record(**page, place=genesis.nat(len(pages) + 1)))
                held['version'] += 1
        elif op == 'world-turn':
            text = field(request['argument'], 'text')['value'] if request['method'] == 'receive' else ''
            action = text.split('\n', 1)[0].split()[-1] if text else request['method']
            if action == 'make':
                seed = {f['name']: f['value'] for f in request['argument']['fields']}
                made = 'kind/' + seed['name']['value']
                if made in self.objects:
                    return {'status': 'refused', 'message': 'nameTaken'}
                self.put(made, **seed)
            elif action == 'place':
                fields = dict(line.split(': ', 1) for line in text.splitlines()[1:])
                if fields['id'] in self.objects:
                    return {'status': 'refused', 'message': 'nameTaken'}
                self.put(fields['id'], cites=genesis.lst(), marks=relation())
            elif action == 'stitch':
                self.wings.add(identity)
                marks = field(held['state']['marks']['payload'], 'items')['items']
                previous = field(marks[-1], 'name')['value'][14:78] if marks else ''
                scene_digest = hashlib.sha256((previous + field(request['argument'], 'spween')['value']).encode()).hexdigest()
                height = len(self.entries) + 1
                marks.append(record(name=genesis.lab(f'station-scene-{scene_digest}-{height}'),
                                    who=genesis.lab(request['principal']), handle=genesis.lab(''), at=genesis.nat(height)))
                held['version'] += 1
            elif action == 'door':
                fields = dict(line.split(': ', 1) for line in text.splitlines()[1:])
                held['state']['cites']['items'].append(genesis.door(fields['label'], fields['to'], []))
            elif action == 'rule':  # the commonplace's first-line rule (genesis FIRST_LINE), placed once
                held.setdefault('rules', []).append({'name': dict(line.split(': ', 1) for line in text.splitlines()[1:])['name']})
            elif action not in ('drop', 'grow', 'want'):
                raise AssertionError(request)
        else:
            raise AssertionError(request)
        self.entries.append({'identity': {'principal': request['principal'], 'intent': identity}, 'outcome': outcome})
        reply = {'status': status, 'receipt': {'outcome': outcome}}
        self.receipts[identity] = digest, copy.deepcopy(reply)
        return reply


class RefreshRegressions(unittest.TestCase):
    def setUp(self):
        self.host = RefreshHost()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'town.journal'

    def journal(self, entries):
        previous = ''
        chain = []
        for height, e in enumerate(entries, 1):
            e = {**e, 'height': height, 'previous': previous}
            previous = e['hash'] = cid_of(e)
            chain.append(e)
        write_journal(self.path, chain)
        return [str(self.path)]

    def refresh(self, today=None, journals=(), station=False):
        with patch.multiple(genesis, texts=lambda _: today or {}, MOTION=[], listed=lambda *_: [], shelved=lambda *_: [], harmonic=lambda *_: [],
                            placed_register=lambda *_: [], placed_mending=lambda *_: []):  # tests/test_register.py Placed carries the register, test_mending the basket
            return genesis.refresh(self.host, genesis.OPENER, journals, station=station)

    def test_unknown_carried_baseline_preserves_kind_law_form_voice_and_about(self):
        obj = 'kind/bell'
        custom = {name: genesis.lab('owner ' + name) for name in ('law', 'form', 'voice', 'about')}
        self.host.put(obj, **custom)
        journals = self.journal([{'outcome': {'tag': 'carried', 'made': [
            {'object': obj, 'identity': {'principal': genesis.OPENER, 'intent': 'genesis-kind-bell'}, 'height': 12}]}}])
        today = {(obj, '.' + name): 'image ' + name for name in custom}
        result = self.refresh(today, journals)
        self.assertEqual(self.host.objects[obj]['state'], custom)
        self.assertEqual({r['status'] for r in result}, {'left'}, result)
        self.assertTrue(all('baseline is unknown' in r['reading'] for r in result), result)
        self.assertFalse([r for r in self.host.requests if r['op'] in ('world-propose', 'world-turn')])

    def carried_with(self, rows):
        return self.journal([{'outcome': {'tag': 'carried', 'made': [
            {'object': 'kind/bell', 'identity': {'principal': genesis.OPENER, 'intent': 'genesis-kind-bell'}, 'height': 12}],
            'baseline': [{'object': 'kind/bell', 'slot': slot, 'text': text} for slot, text in rows.items()]}}])

    def test_a_carried_baseline_is_the_text_last_given_and_refresh_needs_no_ancestor(self):
        obj = 'kind/bell'
        self.host.put(obj, **{name: genesis.lab('old ' + name) for name in ('law', 'form', 'voice', 'about')})
        journals = self.carried_with({'.' + name: 'old ' + name for name in ('law', 'form', 'voice', 'about')})
        self.assertEqual(genesis.given(journals, genesis.OPENER)[(obj, '.form')], 'old form')
        result = self.refresh({(obj, '.' + name): 'image ' + name for name in ('law', 'form', 'voice', 'about')}, journals)
        self.assertEqual({r['status'] for r in result}, {'refreshed'}, result)
        self.assertEqual(self.host.objects[obj]['state'], {name: genesis.lab('image ' + name) for name in ('law', 'form', 'voice', 'about')})

    def test_a_slot_the_owner_amended_since_the_baseline_is_left_and_the_rest_are_given(self):
        obj = 'kind/bell'
        self.host.put(obj, law=genesis.lab('old law'), form=genesis.lab('owner form'))
        journals = self.carried_with({'.law': 'old law', '.form': 'old form'})
        result = {r['slot']: r for r in self.refresh({(obj, '.law'): 'image law', (obj, '.form'): 'image form'}, journals)}
        self.assertEqual((result['.law']['status'], result['.form']['status'], result['.form']['reading']),
                         ('refreshed', 'left', 'changed since genesis gave it'), result)
        self.assertEqual(self.host.objects[obj]['state']['form'], genesis.lab('owner form'))

    def test_unknown_carried_baseline_reports_matching_slots_current_without_writes(self):
        obj = 'kind/bell'
        texts = {name: 'image ' + name for name in ('law', 'form', 'voice', 'about')}
        self.host.put(obj, **{name: genesis.lab(text) for name, text in texts.items()})
        journals = self.journal([{'outcome': {'tag': 'carried', 'made': [
            {'object': obj, 'identity': {'principal': genesis.OPENER, 'intent': 'genesis-kind-bell'}, 'height': 12}]}}])
        before = copy.deepcopy(self.host.objects)
        result = self.refresh({(obj, '.' + name): text for name, text in texts.items()}, journals)
        self.assertEqual([r['status'] for r in result], ['current'] * 4, result)
        self.assertEqual(self.host.objects, before)
        self.assertFalse(self.host.entries)

    def test_unknown_carried_empty_slot_is_preserved_but_unwritten_empty_slot_is_given(self):
        self.host.put('kind/bell', voice=genesis.lab(''))
        journals = self.journal([{'outcome': {'tag': 'carried', 'made': [
            {'object': 'kind/bell', 'identity': {'principal': genesis.OPENER, 'intent': 'genesis-kind-bell'}, 'height': 12}]}}])
        self.assertEqual(self.refresh({('kind/bell', '.voice'): 'bell voice'}, journals)[0]['status'], 'left')
        self.assertEqual(self.refresh({('kind/bell', '.voice'): ''}, journals)[0]['status'], 'current')
        self.assertEqual(self.host.objects['kind/bell']['state']['voice'], genesis.lab(''))
        self.host.put('kind/resident', voice=genesis.lab(''))
        self.assertEqual(self.refresh({('kind/resident', '.voice'): 'new voice'})[0]['status'], 'refreshed')
        self.assertEqual(self.host.objects['kind/resident']['state']['voice'], genesis.lab('new voice'))

    def test_non_record_custom_kind_citation_and_owner_amendment_are_preserved(self):
        citation = 'law kind "kind/custom\'s law holds": under "kind/custom"'
        self.host.put('resident/counter', own_law=citation, owner=genesis.lab('resident'), count=genesis.nat(0))
        self.host.put('resident/amended', own_law=citation + '\nlaw mine "my guard": unchanged(owner)',
                      owner=genesis.lab('resident'), lines=relation(), admitted=relation(), marks=relation())
        before = copy.deepcopy(self.host.objects)
        self.assertEqual(genesis.rebased(self.host, genesis.OPENER), [])
        self.assertEqual(self.host.objects, before)

    def test_partial_station_retries_complete_wings_register_and_both_doors(self):
        for failure in ('refresh-station-wing-2', 'refresh-station-register'):
            with self.subTest(failure=failure):
                self.host = RefreshHost()
                self.host.put('kinds')
                self.host.put('porch', cites=genesis.lst())
                self.host.fail = failure
                first = self.refresh(station=True)
                self.assertIn('station', self.host.objects)
                self.assertTrue(any(r['status'] == 'refused' for r in first), first)
                again = self.refresh(station=True)
                self.assertTrue(all(r['status'] == ('current' if r['slot'] == 'scene' else 'refreshed') for r in again), again)
                self.assertEqual(self.host.wings, {f'refresh-station-wing-{k}' for k in range(1, len(genesis.station_wings()) + 1)} |
                                 {f'refresh-station-parlour-wing-{k}' for k in range(1, len(genesis.parlour_wings()) + 1)})
                self.assertTrue({obj for obj, _, _ in genesis.STATION_THINGS} | {'station/register'} <= self.host.objects.keys())
                inhabitants = [dict(fields)['id'] for _, fields, _ in genesis.STATION_INHABITANTS]
                self.assertTrue({'station/coin', *inhabitants, *('kind/' + name for name in genesis.STATION_KINDS)} <= self.host.objects.keys())
                parlour = dict(genesis.PARLOUR[1])['id']
                self.assertTrue({parlour, dict(genesis.PLANCHETTE[1])['id'], *('kind/' + name for name in genesis.PARLOUR_KINDS)} <= self.host.objects.keys())
                for obj, destinations in [('station', ['porch'] + inhabitants + [parlour]), ('porch', ['station'])] + [(obj, ['station']) for obj in inhabitants]:
                    doors = self.host.objects[obj]['state']['cites']['items']
                    self.assertEqual([field(field(d, 'to'), 'object')['value'] for d in doors], destinations)
                admitted = len(self.host.entries)
                self.assertEqual(self.refresh(station=True), [{'object': 'station', 'slot': 'placed', 'status': 'current'},
                                                            {'object': 'station', 'slot': 'scene', 'status': 'current'},
                                                            {'object': parlour, 'slot': 'scene', 'status': 'current'}])
                self.assertEqual(len(self.host.entries), admitted)

    def station_manifest(self):
        for obj in ['kind/station', 'station', 'station/register', 'porch'] + [obj for obj, _, _ in genesis.STATION_THINGS]:
            self.host.put(obj)
        self.host.objects['station']['state']['cites'] = genesis.lst(genesis.door('the road back', 'porch', []))
        self.host.objects['porch']['state']['cites'] = genesis.lst(genesis.door('the lit station', 'station', []))

    def test_station_completion_reuses_the_shared_door_reader_and_all_manifest_pages(self):
        from transport.host import door_rows
        self.station_manifest()
        self.host.put('unrelated')
        send = self.host.send

        def paged(request):
            if request['op'] != 'world-objects':
                return send(request)
            self.host.requests.append(copy.deepcopy(request))
            ids = sorted(self.host.objects)
            after = request.get('after')
            start = ids.index(after) + 1 if after else 0
            return {'status': 'listed', 'ids': ids[start:start + 2], 'more': start + 2 < len(ids)}

        with patch.object(self.host, 'send', side_effect=paged), patch('transport.host.door_rows', wraps=door_rows) as read_doors:
            self.assertTrue(genesis.station_complete(self.host, genesis.OPENER))
            self.assertEqual(read_doors.call_count, 2)
        lists = [r for r in self.host.requests if r['op'] == 'world-objects']
        self.assertGreater(len(lists), 1)
        self.assertTrue(all('after' in r for r in lists[1:]))
        del self.host.objects['station/register']
        self.assertFalse(genesis.station_complete(self.host, genesis.OPENER))

    def test_station_completion_rejects_a_foreign_world_door_with_the_same_destination_id(self):
        self.station_manifest()
        self.assertTrue(genesis.station_complete(self.host, genesis.OPENER))
        door = self.host.objects['station']['state']['cites']['items'][0]
        for f in field(door, 'to')['fields']:
            if f['name'] == 'world':
                f['value'] = genesis.lab('another-world')
        self.assertFalse(genesis.station_complete(self.host, genesis.OPENER))

    def test_successive_law_refreshes_use_admitted_amendments_new(self):
        obj = 'commonplace'
        self.host.put(obj, own_law='A')
        initial = [{'identity': {'principal': genesis.OPENER, 'intent': 'genesis-commonplace'},
                    'outcome': {'tag': 'created', 'object': obj, 'law': 'A'}}]
        self.assertEqual(self.refresh({(obj, 'law'): 'B'}, self.journal(initial))[0]['status'], 'refreshed')
        journals = self.journal(initial + self.host.entries + [
            {'identity': {'principal': genesis.OPENER, 'intent': 'refresh-refused'},
             'outcome': {'tag': 'refused', 'amendments': [{'object': obj, 'old': 'B', 'new': 'refused text'}]}}])
        self.assertEqual(self.refresh({(obj, 'law'): 'C'}, journals)[0]['status'], 'refreshed')
        self.assertEqual(self.host.objects[obj]['law'], 'C')

    def shelve(self, page):
        with patch.object(genesis, 'shelf', return_value=[page]):
            return genesis.shelved(self.host, genesis.OPENER)

    def test_library_title_and_kind_only_changes_have_distinct_identities(self):
        self.host.put('library', pages=relation())
        for kind, title in (('page', 'first'), ('page', 'second'), ('walk', 'second')):
            result = self.shelve(('sample', kind, title, 'same body'))
            self.assertEqual(result[0]['status'], 'refreshed', result)
            from transport.mirror import library_pages
            [page] = library_pages(self.host, genesis.OPENER)
            self.assertEqual((page['kind'], page['title'], page['body']), (kind, title, 'same body'))

    def test_library_A_B_A_writes_the_rollback_instead_of_replaying_old_receipt(self):
        self.host.put('library', pages=relation())
        from transport.mirror import library_pages
        for body in ('A', 'B', 'A'):
            result = self.shelve(('sample', 'page', 'title', body))
            self.assertEqual(result[0]['status'], 'refreshed', result)
            self.assertEqual(library_pages(self.host, genesis.OPENER)[0]['body'], body)
        self.assertEqual(len(self.host.entries), 3)

    def test_library_admitted_receipt_without_requested_page_is_reported_as_refused(self):
        self.host.put('library', pages=relation())
        self.host.ignore_shelve = True
        result = self.shelve(('sample', 'page', 'title', 'requested body'))
        self.assertEqual(result[0]['status'], 'refused', result)
        self.assertIn('page', result[0]['reading'])

    def test_library_version_is_read_once_and_only_reread_after_admitted_shelves(self):
        current = ('current', 'page', 'title', 'already here')
        self.host.put('library', pages=relation(record(name=genesis.lab(current[0]),
            kind={'tag': 'variant', 'label': current[1], 'payload': record()}, title=genesis.lab(current[2]),
            body=genesis.lab(current[3]), place=genesis.nat(1))))
        self.host.objects['library']['version'] = 17
        pages = [current] + [(name, 'page', 'title', name) for name in ('refused-one', 'refused-two', 'one', 'two', 'refused-three')]
        send = self.host.send

        def refusing(request):
            if request['op'] == 'world-turn' and request['method'] == 'shelve' and field(request['argument'], 'name')['value'].startswith('refused-'):
                self.host.requests.append(copy.deepcopy(request))
                return {'status': 'refused', 'message': 'shelf refused'}
            return send(request)

        with patch.object(genesis, 'shelf', return_value=pages), patch.object(self.host, 'send', side_effect=refusing):
            result = genesis.shelved(self.host, genesis.OPENER)
        self.assertEqual([r['status'] for r in result], ['current', 'refused', 'refused', 'refreshed', 'refreshed', 'refused'])
        reads = [r for r in self.host.requests if r['op'] == 'world-object']
        self.assertEqual(len(reads), 3, self.host.requests)
        versions = [17, 17, 17, 18, 19]
        turns = [r for r in self.host.requests if r['op'] == 'world-turn']
        for request, version in zip(turns, versions):
            name = field(request['argument'], 'name')['value']
            self.assertTrue(request['identity'].startswith(f'refresh-shelve-{name}-{version}-'), request)
        self.assertEqual([r['op'] for r in self.host.requests if r['op'] != 'world-view'],
                         ['world-object', 'world-turn', 'world-turn', 'world-turn', 'world-object',
                          'world-turn', 'world-object', 'world-turn'])

    def test_a_missing_library_record_is_read_once_for_all_pages(self):
        pages = [(name, 'page', 'title', 'body') for name in ('one', 'two', 'three')]
        with patch.object(genesis, 'shelf', return_value=pages):
            result = genesis.shelved(self.host, genesis.OPENER)
        self.assertEqual([r['status'] for r in result], ['absent'] * 3)
        self.assertEqual(len([r for r in self.host.requests if r['op'] == 'world-object']), 1)


if __name__ == '__main__':
    unittest.main()
