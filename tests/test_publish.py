"""A published page reaches the outbox as a draft, is recorded when posted, and a reply to it
routes back to its object.

Evidence for FOUNDATION §5, §7 (layer: transport).

publish end to end: an object's published page reaches the outbox as a
draft marked like a reply draft and never posted by the bridge; post.py --object records the post's
page and section; a reply to the recorded page post routes to the object by reply-is-address.

Refuted by: a garden's page draft (the host's default page: its card and how to reply) without those two sections in order; the bridge drafting a
publication twice; a reply to the page post going anywhere but the garden.
"""
import tempfile
import unittest

from tests.test_bridge import BridgeCase
from tests.test_chain import town_garden
from tests.test_transport import DID, mk
from tests.test_turn_world import closure, label, record
from tests.town import Town
from transport import bridge, observe, post


class Publishing(BridgeCase):
    def test_a_gardens_page_is_drafted_recorded_and_a_reply_routes_to_the_garden(self):
        town_garden(lambda **q: self.host.send(q))
        for i in range(20):
            r = self.host.send({'op': 'world-turn', 'principal': 'glm', 'object': 'garden', 'method': 'plant',
                                'argument': record(colour=label('silver'), seed=label('bell %02d' % i)), 'identity': f'plant-{i}'})
            self.assertEqual(r['result']['label'], 'made', r)
        r = self.host.send({'op': 'world-turn', 'principal': 'glm', 'object': 'garden', 'method': 'publishPage',
                            'argument': record(page=label('')), 'identity': 'publish-1'})
        self.assertEqual(r['status'], 'admitted', r)
        ran = self.run_bridge()
        self.assertEqual(ran['published'], [r['result']['value']], ran)
        [draft] = [d for d in self.drafts() if 'publication' in d]
        self.assertEqual((draft['posted'], draft['page'], draft['section'], draft['replyTo']), (False, 'garden', '', None))
        header, *sections = draft['text'].split('\n## ')
        self.assertEqual(header, 'wiki: garden\n')
        titles = [s.split('\n', 1)[0] for s in sections]
        self.assertTrue(all(len(s) < 2000 for s in sections), [len(s) for s in sections])
        self.assertEqual(titles, ['Card', 'How to reply'])
        self.assertNotIn('published', self.run_bridge())               # drafted once
        self.assertEqual(len([d for d in self.drafts() if 'publication' in d]), 1)
        # A human posts it with post.py --text-file ... --object garden; the record carries page and section.
        page_uri = f'at://{DID}/town.delve.feed.post/page1'
        target = observe.wiki_target(draft['text'])
        self.assertEqual(target, ('garden', ''))
        reserved = self.host.send({'op': 'world-post-reserve', 'principal': post.CLOCK, 'intent': page_uri, 'source': 'delve'})
        self.assertEqual(reserved['status'], 'reserved', reserved)
        recorded = post.record_posted(self.host, {'uri': page_uri, 'cid': 'bafypage'}, 'garden', None, target, intent=page_uri)
        self.assertEqual(recorded['status'], 'posted', recorded)
        self.assertEqual(recorded['receipt']['outcome']['page'], 'garden')
        self.state.mark_posted(next(self.state.outbox.glob('*-pub-*.json')))
        self.observe([mk(9, 'thank you for the page', parent=page_uri)])
        ran = self.run_bridge()
        self.assertEqual(ran['turns'], [mk(9, '')['uri']], ran)
        receipt = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': mk(9, '')['uri']})['receipt']
        self.assertEqual(receipt['roots'][0]['object'], 'garden', receipt)


class Drafts(BridgeCase):
    def test_a_section_edit_drafted_before_its_page_post_gets_the_reply_to_later(self):
        class Host:
            def __init__(self):
                self.reply_to = None

            def send(self, req):
                if req['op'] == 'world-publications':
                    p = {'height': 3, 'ordinal': 0, 'id': 'f' * 64, 'object': 'teller', 'page': 'teller',
                         'section': 'Notes', 'body': 'rang'}
                    return {'status': 'publications', 'more': False,
                            'publications': [dict(p, **({'replyTo': self.reply_to} if self.reply_to else {}))]}
                return {'status': 'ok', 'count': 0}
        host = Host()
        bridge.run(self.state, host)
        [d] = self.drafts()
        self.assertEqual((d['text'], d['replyTo'], d['posted']), ('edit: teller › Notes\n\nrang', None, False))
        host.reply_to = 'at://page'
        self.assertNotIn('published', bridge.run(self.state, host))
        [d] = self.drafts()
        self.assertEqual(d['replyTo'], 'at://page')


class DefaultPage(BridgeCase):
    """WORLD-REVIEW finding 16: a card that declares no `publishPage` has the host's default page, the card
    as a stranger sees it and how to reply, under the given page or its id."""

    def test_a_card_without_publish_page_gets_the_default_page(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-counter', 'object': 'c',
                            'modules': closure('Counter'), 'entry': 'initial', 'seed': record()})
        self.assertEqual(r['status'], 'created', r)
        r = self.host.send({'op': 'world-turn', 'principal': 'ember', 'object': 'c', 'method': 'publishPage',
                            'argument': record(page=label('')), 'identity': 'page-1'})
        self.assertEqual(r['status'], 'admitted', r)
        [published] = self.host.send({'op': 'world-publications', 'principal': 'ember'})['publications']
        self.assertEqual((published['object'], published['page'], published['section']), ('c', 'c', ''), published)
        self.assertEqual(r['result'], label(published['id']))
        body = published['body']
        self.assertTrue(body.startswith('## Card\n\n'), body)
        self.assertIn('\n## How to reply\n\n', body)
        self.assertIn('delvetalk c bump', body)
        named = self.host.send({'op': 'world-turn', 'principal': 'ember', 'object': 'c', 'method': 'publishPage',
                                'argument': record(page=label('Counter')), 'identity': 'page-2'})
        self.assertEqual(named['status'], 'admitted', named)
        self.assertEqual([p['page'] for p in self.host.send({'op': 'world-publications', 'principal': 'ember'})['publications']],
                         ['c', 'Counter'])

    def test_a_card_only_some_may_read_gets_no_default_page(self):
        # codex host 2: the host's page is public, so a card whose read policy names principals has none.
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-counter', 'object': 'c',
                            'modules': closure('Counter'), 'entry': 'initial', 'seed': record(),
                            'read': {'principals': ['ember']}})
        self.assertEqual(r['status'], 'created', r)
        for who in ('mallory', 'ember'):
            r = self.host.send({'op': 'world-turn', 'principal': who, 'object': 'c', 'method': 'publishPage',
                                'argument': record(page=label('')), 'identity': 'page-' + who})
            self.assertEqual((r['status'], r['receipt']['outcome']['class']), ('refused', 'noMethod'), r)
        self.assertEqual(self.host.send({'op': 'world-publications', 'principal': 'ember'})['publications'], [])


class PublishPageShape(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.town = Town(tmp.name, cleanup=self.addCleanup, furnished=False)

    def test_publish_page_accepts_missing_empty_named_and_maximum_titles_on_every_card(self):
        made = self.town.send(op='world-turn', principal=self.town.opener, object='kind/room',
                              method='receive', identity='publish-shape-make-room',
                              argument=record(text=label('delvetalk kind/room make / name: the page room'),
                                              post=label('')))
        self.assertEqual(made['status'], 'admitted', made)
        [created] = made['receipt']['outcome']['creates']
        room = created['object']
        for thing, default in ((room, room), ('kind/room', 'kinds'),
                               ('workshop', 'workshop'), ('register', 'register')):
            for shape, argument, title in (('missing', record(), default),
                                            ('empty', record(page=label('')), default),
                                            ('named', record(page=label('A resident page')), 'A resident page'),
                                            ('maximum', record(page=label('é' * 128)), 'é' * 128)):
                with self.subTest(object=thing, shape=shape):
                    reply = self.town.send(op='world-turn', principal=self.town.opener, object=thing,
                                           method='publishPage', argument=argument,
                                           identity=f'publish-shape-{thing}-{shape}')
                    self.assertEqual(reply['status'], 'admitted', reply)
                    publications = self.town.send(op='world-publications', principal=self.town.opener)['publications']
                    matching = [p for p in publications if p['id'] == reply['result']['value']]
                    self.assertEqual(len(matching), 1, publications)
                    published = matching[0]
                    self.assertEqual((published['object'], published['page'], published['section']),
                                     (thing, title, ''), published)
                    self.assertTrue(published['body'].startswith('## Card\n\n'), published)
        before = self.town.send(op='world-publications', principal=self.town.opener)['publications']
        self.town.reopen()
        self.assertEqual(self.town.send(op='world-publications', principal=self.town.opener)['publications'], before)


if __name__ == '__main__':
    unittest.main()
