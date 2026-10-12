"""The town's own principal (docs/GENESIS.md "The town"): the world's opener is the town, and every surface names it so,
never as a person. A fresh genesis runs as the world's did:web and no surface shows the owner; a carried town whose
opener was the owner's DID (the live town's journal) shows the town for it, whatever handle its state kept, with no
rewrite; the owner's DID acting as a resident in a town it did not open is named by its handle like anyone's.

Evidence for the opener lane, 2026-10-12 (layer: host). Refuted by: an owner handle or DID in a fresh town's cards,
strokes, tellings, books, chronicle, map or pages; a carried DID opener shown by its handle; a resident owner shown
as the town.
"""
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from deploy import genesis
from deploy.seed import create
from tests.host import binary
from tests.town import Town
from transport import pages
from transport.host import PUBLIC, TOWN, HostProcess, handles

OWNER, OWNER_HANDLE = 'did:plc:6amo7col5h4ciq2gpm5eur7b', 'ember.delve.town'  # the owner, the live town's opener
GLM = 'did:plc:glm'


def ids(send, reader=PUBLIC):
    out, after = [], {}
    while True:
        got = send(op='world-objects', principal=reader, **after)
        out += got.get('ids') or []
        if not got.get('more') or not got.get('ids'):
            return out
        after = {'after': out[-1]}


def surfaces(send, town, reader=GLM):
    """{where: text} of every surface a reader meets: each object's card and strokes (a place's telling too) and its
    web page, the town's book, the chronicle and the door map."""
    out = {}
    for obj in ids(send):
        card = send(op='world-card', principal=PUBLIC, object=obj)
        out[f'card {obj}'] = card.get('whole') or card.get('text') or ''
        out[f'strokes {obj}'] = json.dumps(send(op='world-strokes', principal=reader, object=obj).get('strokes') or {})
        told = send(op='world-strokes', principal=reader, object=obj, telling={})
        if told.get('status') == 'strokes':
            out[f'telling {obj}'] = json.dumps(told.get('strokes') or {})
        view = send(op='world-view', principal=PUBLIC, object=obj)
        body = pages.obj(obj, None, view, out[f'card {obj}'], [], town=town)
        out[f'page {obj}'] = pages.named(body, handles(Sender(send), PUBLIC, pages.A_DID.findall(body), {}))
    for read, obj in (('chronicle', None), ('map', None), ('book', town)):
        got = send(op='world-surface', principal=PUBLIC, read=read, **({'object': obj} if obj else {}))
        out[read] = got.get('whole') or got.get('text') or json.dumps(got)
    return out


class Sender:
    """A keyword `send` as transport's helpers call a host: `send(request)`."""

    def __init__(self, send):
        self.send = lambda request: send(**request)


class Fresh(unittest.TestCase):
    """A fresh genesis, furnished: the town's opener is the world's did:web, and the owner is nowhere."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        cls.town.send(op='world-arrive', principal='transport', did=GLM, handle='glm.delve.town')

    def test_the_opener_is_the_worlds_did_web_and_named_the_town(self):
        self.assertTrue(genesis.OPENER.startswith('did:web:'), genesis.OPENER)
        self.assertEqual(self.town.send(op='world-status')['opener'], genesis.OPENER)
        porch = self.town.send(op='world-view', principal=PUBLIC, object='porch')
        self.assertIn('made by the town', pages.heading('porch', porch, town=genesis.OPENER))
        self.assertEqual(self.town.send(op='world-strokes', principal=GLM, object='porch')['strokes']['maker'], TOWN)
        self.assertIn('planted by the town', self.town.send(op='world-card', principal=PUBLIC, object='bell/2')['text'])

    def test_no_surface_shows_the_owner(self):
        got = surfaces(self.town.send, genesis.OPENER)
        self.assertTrue({'telling porch', 'page porch', 'card bell/1', 'chronicle', 'map', 'book'} <= set(got), sorted(got))
        self.assertIn(TOWN, got['page porch'] + got['telling porch'])
        for where, text in got.items():
            with self.subTest(where=where):
                self.assertNotIn(OWNER, text)
                self.assertNotRegex(text, r'\bember\b')

    def test_the_owner_acting_as_a_resident_is_named_by_their_handle(self):
        self.town.send(op='world-arrive', principal='transport', did=OWNER, handle=OWNER_HANDLE)
        got = self.town.send(op='world-turn', principal=OWNER, object='kind/bell', method='receive', identity='owner-bell',
                             argument={'tag': 'record', 'fields': [
                                 {'name': 'text', 'value': {'tag': 'label', 'value': 'delvetalk kind/bell make\ncolour: amber\nseed: a bell of the owner'}},
                                 {'name': 'post', 'value': {'tag': 'label', 'value': f'at://{OWNER}/town.delve.feed.post/1'}}]})
        self.assertEqual(got['status'], 'admitted', got)
        made = got['receipt']['outcome']['creates'][0]['object']
        self.assertIn(f'planted by {OWNER_HANDLE}', self.town.send(op='world-card', principal=PUBLIC, object=made)['text'])
        self.assertEqual(self.town.send(op='world-strokes', principal=GLM, object=made)['strokes']['maker'], OWNER_HANDLE)
        self.assertNotIn(TOWN, self.town.send(op='world-card', principal=PUBLIC, object=OWNER)['text'])


class CarriedFromAPerson(unittest.TestCase):
    """A town opened by the owner's DID, as the live town's journal names it, whose state kept the owner's handle where
    the opener made and kept things, then carried: every surface shows the town for it, its history unrewritten."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        with mock.patch.object(genesis, 'OPENER', OWNER):
            town = Town(cls.tmp.name, run_genesis=False, cleanup=cls.addClassCleanup)
        made, refusal = genesis.run(town.client, OWNER)
        assert refusal is None, refusal
        # The registry and the state as the live town holds them: the opener arrived by its handle, and what it kept
        # stores that handle.
        town.send(op='world-arrive', principal='transport', did=OWNER, handle=OWNER_HANDLE)
        town.send(op='world-arrive', principal='transport', did=GLM, handle='glm.delve.town')
        kept = create(town.client, OWNER, 'anthology', 'Record', 'old-anthology',
                      genesis.rec(owner=genesis.lab(OWNER), keeper=genesis.lab(OWNER), keeperHandle=genesis.lab(OWNER_HANDLE),
                                  head=genesis.lab('THE ANTHOLOGY')), genesis.RECORD_LAW)
        assert kept['status'] == 'created', kept
        cls.before = town.send(op='world-card', principal=PUBLIC, object='anthology')['text']
        assert town.send(op='world-snapshot')['status'] == 'snapshot'
        journal = town.journal
        town.close()
        cls.out = os.path.join(cls.tmp.name, 'carried.journal')
        p = subprocess.run([binary(), 'carry', '--from', journal, '--out', cls.out, '--reason', 'a newer host'],
                           capture_output=True, text=True, timeout=600)
        assert p.returncode == 0, p.stderr
        cls.host = HostProcess(binary(), cls.out)
        cls.addClassCleanup(cls.host.close)

    def send(self, **request):
        return self.host.send(request)

    def test_the_carried_settings_name_the_owner_as_opener_and_the_registry_keeps_their_handle(self):
        self.assertEqual(self.send(op='world-status')['opener'], OWNER)
        self.assertEqual(genesis.opener_of(self.out), OWNER)

    def test_the_kept_handle_is_shown_as_the_town(self):
        self.assertIn('the town', self.before)
        self.assertNotIn(OWNER_HANDLE, self.before)
        self.assertEqual(self.send(op='world-strokes', principal=GLM, object='anthology')['strokes']['keeper'], TOWN)

    def test_no_surface_shows_the_owner(self):
        got = surfaces(self.send, OWNER)
        self.assertIn('keeper the town', got['card anthology'])
        self.assertIn('made by the town', got['page porch'])
        for where, text in got.items():
            with self.subTest(where=where):
                self.assertNotIn(OWNER_HANDLE, text)

    def test_the_paint_verifier_credits_the_town_and_not_the_owner(self):
        check = lambda text: self.send(op='world-render-check', principal=GLM, object='anthology', text=text)
        self.assertEqual(check('THE ANTHOLOGY, kept by the town.')['status'], 'verified')
        self.assertEqual(check(f'THE ANTHOLOGY, kept by {OWNER_HANDLE}.')['clause'], 'handles')


if __name__ == '__main__':
    unittest.main()
