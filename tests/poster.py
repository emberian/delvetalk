"""A resident who only posts (docs/POSTING.md): the bridge's fake Delve over a town. `say(text)` is a post on the town's
feed, or a reply under `reply_to`; the bridge's step (observe, turn, settle, draft) runs as it does live, and `say`
answers the drafts that step wrote, which are the replies the hand would post. `posted(draft)` posts one as the hand
does (its parts each a post in the thread, recorded with the host), so a reply under it reaches its card."""
import copy
import itertools
import json
from pathlib import Path

from transport import bridge, delve, observe, post
from transport.config import Config
from transport.state import State

BASE = {'uri': '', 'cid': '', 'author': {}, 'record': {}, 'indexedAt': '2026-10-09T10:00:00.000Z'}
BOT = 'did:plc:livedelvetalk'


class Poster:
    def __init__(self, directory, host, did='did:plc:poster', handle='poster.delve.town'):
        self.st = State(Path(directory) / 'state', config=Config(origin='http://127.0.0.1:8765'))
        self.host, self.did, self.handle, self.posts, self.bots, self.seen, self.others, self.threads = host, did, handle, [], [], set(), [], []
        self.n = itertools.count(1)

    def _post(self, text, reply_to=None, did=None, handle=None):
        n = next(self.n)
        p = copy.deepcopy(BASE)
        did, handle = did or self.did, handle or self.handle
        p['uri'], p['cid'] = f'at://{did}/town.delve.feed.post/p{n:06d}', f'bafy{n}'
        p['author'] = {'did': did, 'handle': handle}
        p['record'] = {'$type': 'town.delve.feed.post', 'createdAt': f'2026-10-12T10:{n // 60:02d}:{n % 60:02d}.000Z', 'text': text}
        if reply_to:
            root = next((q['record'].get('reply', {}).get('root', {}).get('uri') for q in self.posts + self.bots if q['uri'] == reply_to), None) or reply_to
            p['record']['reply'] = {'parent': {'uri': reply_to, 'cid': 'x'}, 'root': {'uri': root, 'cid': 'x'}}
        (self.bots if did == BOT else self.posts).append(p)  # the hand's own posts are not observed back
        return p

    def step(self):
        from tests.test_transport import Script
        ob = observe.Observer(self.st, delve.Client(Script(**{'town.delve.feed.searchPosts': lambda q: (200, {'posts': list(self.posts)}),
                                                               'town.delve.feed.getFeed': lambda q: (200, {'feed': []})})))
        ob.poll()
        ob.db.close()
        return bridge.run(self.st, self.host)

    def say(self, text, reply_to=None):
        """Post `text` (under `reply_to`); -> the drafts the step wrote in answer to it, oldest first (what else it
        drafted, a publication or another post's answer, is kept in `others`)."""
        p = self._post(text, reply_to)
        self.step()
        drafts = self.new()
        self.others += [d for d in drafts if d.get('replyTo') != p['uri']]
        return [d for d in drafts if d.get('replyTo') == p['uri']]

    def new(self):
        out = []
        for path in sorted(self.st.outbox.glob('*.json'), key=lambda q: (int(q.name.split('-')[0]), q.name)):
            if path.name not in self.seen:
                self.seen.add(path.name)
                out.append({**json.loads(path.read_text()), 'path': str(path)})
        return out

    def posted(self, draft):
        """Post a draft as the hand does (`post.thread`): each of its parts (`post.parts`) a post, the first under the
        post it answers and each next under the one before, recorded with the host. -> the parts' uris."""
        under, uris = draft.get('replyTo'), []
        for text in post.parts(draft['text']):
            bot = self._post(text, under, BOT, 'livedelvetalk.delve.town')
            under = bot['uri']
            uris.append(under)
            obj = post.draft_object(draft)
            if obj:
                post.record_posted(self.host, {'uri': bot['uri'], 'cid': bot['cid']}, obj, draft.get('slot'))
        self.threads.append([b for b in self.bots if b['uri'] in uris])
        return uris
