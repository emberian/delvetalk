"""A published page reaches the outbox as a draft, is recorded when posted, and a merge reply to it
routes back to its object.

Evidence for FOUNDATION §5, §7 (layer: transport).

publish end to end: an object's published page reaches the outbox as a
draft marked like a reply draft and never posted by the bridge; post.py --record records the post's
page and section; a `merge` reply to the recorded page post routes to the object by reply-is-address.

Refuted by: a Garden page draft without its eighteen sections in order; the bridge drafting a
publication twice; a merge reply to the page post going anywhere but the garden.
"""
import unittest

from tests.test_bridge import BridgeCase
from tests.test_chain import garden_state
from tests.test_transport import DID, mk
from tests.test_turn_world import closure, label, record
from transport import bridge, post


class Publishing(BridgeCase):
    def test_a_gardens_page_is_drafted_recorded_and_a_merge_reply_routes_to_the_garden(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-garden', 'object': 'garden',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state()})
        self.assertEqual(r['status'], 'created', r)
        for i in range(20):
            r = self.host.send({'op': 'world-turn', 'principal': 'glm', 'object': 'garden', 'method': 'plant',
                                'argument': record(colour=label('silver'), seed=label('bell %02d' % i)), 'identity': f'plant-{i}'})
            self.assertEqual(r['result']['label'], 'planted', r)
        r = self.host.send({'op': 'world-turn', 'principal': 'glm', 'object': 'garden', 'method': 'publish',
                            'argument': record(), 'identity': 'publish-1'})
        self.assertEqual(r['status'], 'admitted', r)
        ran = self.run_bridge()
        self.assertEqual(ran['published'], [r['result']['value']], ran)
        [draft] = [d for d in self.drafts() if 'publication' in d]
        self.assertEqual((draft['posted'], draft['page'], draft['section'], draft['replyTo']), (False, 'garden', '', None))
        header, *sections = draft['text'].split('\n## ')
        self.assertEqual(header, 'wiki: garden\n')
        titles = [s.split('\n', 1)[0] for s in sections]
        self.assertEqual(titles, ['Card', 'How to reply'] + [f'garden/bell/{n}' for n in range(20, 4, -1)])
        self.assertNotIn('published', self.run_bridge())               # drafted once
        self.assertEqual(len([d for d in self.drafts() if 'publication' in d]), 1)
        # A human posts it with post.py --text-file ... --record garden; the record carries page and section.
        page_uri = f'at://{DID}/town.delve.feed.post/page1'
        target = post.wiki_target(draft['text'])
        self.assertEqual(target, ('garden', ''))
        recorded = post.record_posted(self.host, {'uri': page_uri, 'cid': 'bafypage'}, 'garden', None, target)
        self.assertEqual(recorded['status'], 'posted', recorded)
        self.assertEqual(recorded['receipt']['outcome']['page'], 'garden')
        bridge.mark_posted(next((self.state / 'outbox').glob('*-pub-*.json')))
        self.observe([mk(9, 'merge', parent=page_uri)])
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
    as a stranger sees it and how to reply, under the given page or its door word."""

    def test_a_card_without_publish_page_gets_the_default_page(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-counter', 'object': 'c',
                            'modules': closure('Counter'), 'entry': 'initial', 'seed': record()})
        self.assertEqual(r['status'], 'created', r)
        r = self.host.send({'op': 'world-turn', 'principal': 'ember', 'object': 'c', 'method': 'publishPage',
                            'argument': record(page=label('')), 'identity': 'page-1'})
        self.assertEqual(r['status'], 'admitted', r)
        [published] = self.host.send({'op': 'world-publications', 'principal': 'ember'})['publications']
        self.assertEqual((published['object'], published['page'], published['section']), ('c', 'counter', ''), published)
        self.assertEqual(r['result'], label(published['id']))
        body = published['body']
        self.assertTrue(body.startswith('## Card\n\n'), body)
        self.assertIn('\n## How to reply\n\n', body)
        self.assertIn('delvetalk c bump', body)
        named = self.host.send({'op': 'world-turn', 'principal': 'ember', 'object': 'c', 'method': 'publishPage',
                                'argument': record(page=label('Counter')), 'identity': 'page-2'})
        self.assertEqual(named['status'], 'admitted', named)
        self.assertEqual([p['page'] for p in self.host.send({'op': 'world-publications', 'principal': 'ember'})['publications']],
                         ['counter', 'Counter'])


if __name__ == '__main__':
    unittest.main()
