"""The automatic moderation (docs/ROOT.md section 2.4), over a genesis town and a front: residents' public texts
admitted as ever, then screened by the worker (transport/automod.py) with a mocked classifier, the host deciding what
each verdict does and journaling it. Evidence for docs/ROOT.md section 2.4 (layer: host).

Refuted by: a flagged line still on the porch's card, view or paint strokes; a flagged feed post still in the feed's
page or JSON; a high-confidence flag's author still acting; a low-confidence flag hiding anything; a dark-but-fine
line hidden; the wordlist not acting while the classifier is down, or the classifier being asked while nothing is new;
a restore not showing the text again, not lifting the quiet, or not journaled; a replay that derives other screened
texts; the moderation's own public entry quoting the words it hid; a resident reaching the moderation's ops.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.test_http import FrontCase, HANDLE
from tests.town import Town
from tests.wire import label, record
from transport import automod, hand
from transport.config import Config
from transport.feed import Feed
from transport.host import CLOCK, PUBLIC, HostClient
from transport.state import State

PLACEHOLDER = '[hidden by moderation]'
FOUL = 'the porch is for FOUL-SLUR-MARKER people only, get out'
DARK = 'In the parlour the candles guttered; something under the floorboards breathed, and the blood on the stair was old.'
MAYBE = 'this one is MAYBE-MARKER borderline'


def verdict(text, system):
    if 'FOUL' in text:
        return {'flag': True, 'category': 'hate', 'confidence': 'high', 'reason': 'a slur aimed at people'}
    if 'MEDIUM' in text:
        return {'flag': True, 'category': 'harassment', 'confidence': 'medium', 'reason': 'degrades a resident'}
    if 'MAYBE' in text:
        return {'flag': True, 'category': 'harassment', 'confidence': 'low', 'reason': 'unclear'}
    if 'SPAMFLOOD' in text:
        return {'flag': True, 'category': 'spam', 'confidence': 'high', 'reason': 'identical advertising and link dumping'}
    handle = text in ('y02', 'j3rry', 'coinanole', '014')
    if ('THE RELAY GAME' in text or 'Number-tag chain:' in text or handle) and 'relay' not in system.lower():
        return {'flag': True, 'category': 'spam', 'confidence': 'low' if handle else 'medium', 'reason': 'repeated short turns'}
    return {'flag': False}


class Classifier:
    """A mocked GLM: answers each numbered text by `verdict`, or fails while `down`; counts its calls."""

    def __init__(self):
        self.calls, self.systems, self.down = [], [], False

    def __call__(self, system, user):
        texts = [json.loads(line) for line in user.splitlines()[1:]]
        self.calls.append(texts)
        self.systems.append(system)
        if self.down:
            return {'status': 'failed', 'reason': 'transport', 'detail': 'http 503'}
        return {'status': 'replied', 'model': 'mock', 'usage': {'input_tokens': 10, 'output_tokens': 5},
                'raw': '```json\n' + json.dumps({'verdicts': [{'i': t['i'], **(named(t, system) or verdict(t['text'], system))} for t in texts]}) + '\n```'}


def named(t, system):
    """gsb 10-14's live misreading of a domain-shaped name, unless the text is marked a name and the policy says what
    a name is."""
    if '.' in t['text'] and ' ' not in t['text'] and not (t.get('kind') == 'name' and 'a name is never a link' in system):
        return {'flag': True, 'category': 'spam', 'confidence': 'low', 'reason': 'a bare link'}
    return None


class Town_(unittest.TestCase):
    """Lines said on the porch, screened."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.st = State(cls.town.state, config=Config(root_socket=cls.town.process.root, host_socket=cls.town.process.sock,
                                                     opener=cls.town.opener, origin='https://obend.example', zai_key_file='/nonexistent'))
        cls.hand = hand.Hand(cls.st, cls.town.client, token='t')
        cls.n = 0

    def arrive(self, name):
        got = self.hand.invite_guest(name)
        self.hand.identity.accept(got['code'])
        self.town.send(op='world-arrive', principal=CLOCK, did=got['principal'], handle=name)
        entered = self.town.send(op='world-turn', principal=got['principal'], object='porch', method='enter', identity=f'{name}-enter', argument=record())
        self.assertEqual(entered['status'], 'admitted', entered)
        return got['principal']

    def say(self, who, line):
        type(self).n += 1
        r = self.town.send(op='world-turn', principal=who, object='porch', method='say', identity=f'say-{self.n}', argument=record(line=label(line)))
        return r

    def worker(self, ask, now):
        return automod.Worker(self.st, self.town.client, ask=ask, clock=lambda: now[0])

    def public(self, op, **more):
        return json.dumps(self.town.send(op=op, principal=PUBLIC, object='porch', **more), ensure_ascii=False)

    def run_worker(self, w, now):
        w.step()  # collects
        now[0] += automod.WINDOW + 1
        w.step()  # the window passed: one call

    def test_the_workers_host_policy_exempts_play_and_handles_and_narrows_spam(self):
        w = self.worker(Classifier(), [time.time() + 1])
        w.collect()
        head = self.town.send(op='world-screen', principal=self.town.opener, after=w.height)
        self.assertEqual(head['status'], 'screen', head)
        self.assertEqual(w.policy, head['policy'])
        policy = w.policy.lower()
        for word in ('relay', 'game', 'chain', 'handle'):
            with self.subTest(exemption=word):
                self.assertIn(word, policy)
        spam = next(line for line in policy.splitlines() if line.startswith('- spam:'))
        for definition in (r'(?:same|identical) text', r'repeat|again', r'(?:repeated|identical) (?:promotion|advertis)',
                           r'scam', r'link[- ]dump'):
            with self.subTest(definition=definition):
                self.assertRegex(spam, definition)

    def test_an_accounts_name_is_marked_a_name_and_a_domain_shaped_one_is_no_link(self):
        """gsb 10-14: four of automod's five flags were account names (hy3.delve.town as a bare link,
        siliconsupremacy.delve.town as a supremacist name), all left in review. A name recorded at arrival goes to the
        classifier marked `kind: name`, under a policy that says what a name is; a line with the same words is a line."""
        name = 'hy3-' + str(type(self).n) + '.delve.town'
        type(self).n += 1
        self.town.send(op='world-arrive', principal=CLOCK, did='did:plc:' + 'h' * 24, handle=name)
        line = 'link-' + name  # the same shape said as a line (a known name said again is not screened again)
        speaker = self.arrive('liner')
        self.assertEqual(self.say(speaker, line)['status'], 'admitted')
        now, glm = [time.time() + 1], Classifier()
        w = self.worker(glm, now)
        self.run_worker(w, now)
        sent = {t['text']: t.get('kind', 'line') for batch in glm.calls for t in batch if t['text'] in (name, line)}
        self.assertEqual(sent, {name: 'name', line: 'line'}, sent)
        flagged = {i['text'] for state in ('hidden', 'review') for i in self.hand.automod(state)['items']}
        self.assertNotIn(name, flagged)
        self.assertIn(line, flagged)  # a line is a line: the classifier's to judge as before
        self.assertIn('a name is never a link, spam or a data dump', w.policy)

    def test_relay_rounds_number_tag_chains_and_short_handles_pass_but_a_spam_flood_is_hidden(self):
        player, spammer = self.arrive('relay-player'), self.arrive('flood-poster')
        play = [f"THE RELAY GAME - round 7: tag, you're it: {n} -> {n + 1}" for n in range(14, 17)]
        play += ['Number-tag chain: 17 -> 18, @j3rry next', 'y02', 'j3rry', 'coinanole']
        flood = 'SPAMFLOOD buy now https://spam.example/buy https://spam.example/buy https://spam.example/buy'
        for line in play:
            self.assertEqual(self.say(player, line)['status'], 'admitted')
        self.assertEqual(self.say(spammer, flood)['status'], 'admitted')
        now, glm = [time.time() + 1], Classifier()
        w = self.worker(glm, now)
        self.run_worker(w, now)
        asked = {t['text'] for batch in glm.calls for t in batch}
        self.assertTrue(set(play + [flood]) <= asked, asked)
        self.assertEqual(glm.systems, [w.policy] * len(glm.calls))
        shown = self.public('world-view')
        self.assertNotIn('SPAMFLOOD', shown)
        hidden = self.hand.automod('hidden')['items']
        (item,) = [i for i in hidden if i['text'] == flood]
        self.assertEqual((item['category'], item['confidence']), ('spam', 'high'))
        flagged = hidden + self.hand.automod('review')['items']
        for line in play:
            with self.subTest(play=line):
                self.assertIn(line, shown)
                self.assertFalse(any(i['text'] == line for i in flagged), flagged)
        self.assertEqual(self.say(player, 'the relay continues')['status'], 'admitted')

    def test_a_foul_line_leaves_the_card_the_view_and_the_paint_and_its_author_is_quieted(self):
        ann, bo = self.arrive('ann'), self.arrive('bo')
        self.assertEqual(self.say(ann, FOUL)['status'], 'admitted')
        self.assertEqual(self.say(bo, DARK)['status'], 'admitted')
        self.assertIn('FOUL-SLUR-MARKER', self.public('world-view'))  # admitted as ever, before the worker runs
        now, glm = [time.time() + 1], Classifier()
        w = self.worker(glm, now)
        w.step()
        self.assertEqual(glm.calls, [], 'a text waits its window before the call')
        now[0] += 6
        w.step()
        self.assertEqual(len(glm.calls), 1, 'one call for the batch')
        self.assertTrue(any('FOUL' in t['text'] for t in glm.calls[0]) and any('floorboards' in t['text'] for t in glm.calls[0]))
        for op, more in (('world-view', {}), ('world-card', {}), ('world-strokes', {}), ('world-history', {'limit': 50})):
            shown = self.public(op, **more)
            self.assertNotIn('FOUL-SLUR-MARKER', shown, op)
        self.assertIn(PLACEHOLDER, self.public('world-view'))
        self.assertIn('floorboards breathed', self.public('world-view'), 'the dark parlour line passes')
        strokes = self.town.send(op='world-strokes', principal=PUBLIC, object='porch')
        self.assertNotIn('FOUL-SLUR-MARKER', strokes['text'])  # the painter never reads it
        self.assertIn('floorboards', strokes['text'])
        self.town.send(op='world-render', principal=PUBLIC, object='porch')  # a paint asked for: the model's request
        renders = json.dumps(self.town.send(op='world-renders'), ensure_ascii=False)
        self.assertIn('porch', renders)
        self.assertNotIn('FOUL-SLUR-MARKER', renders)
        again = self.say(ann, 'hello again')
        refusal = (again.get('receipt') or {}).get('outcome', {}).get('class') or again.get('class')
        self.assertEqual(refusal, 'quiet', again)
        self.assertEqual(self.say(bo, 'still here')['status'], 'admitted')
        # The opener reads the bytes; the public reads the act without them.
        whole = self.hand.automod('hidden')['items']
        (item,) = [i for i in whole if i['author'] == ann]
        self.assertEqual((item['text'], item['category'], item['confidence'], item['by']), (FOUL, 'hate', 'high', 'mock'))
        entries = self.town.send(op='world-entries', principal=PUBLIC, reverse=True, limit=20)['entries']
        screens = [e for e in entries if (e.get('outcome') or {}).get('power') == 'screen']
        self.assertTrue(screens)
        self.assertNotIn('FOUL-SLUR-MARKER', json.dumps(entries))
        self.assertEqual(screens[0]['outcome']['key'], item['key'])
        status = automod.status(self.st)
        self.assertEqual((status['glm'], status['pending']), ('ok', 0))
        # Nothing new: the worker asks the host and calls no model.
        now[0] += 60
        w.step()
        self.assertEqual(len(glm.calls), 1)

    def test_a_low_confidence_flag_hides_nothing_and_waits_for_review_and_restore_is_journaled(self):
        cy = self.arrive('cy')
        self.say(cy, MAYBE)
        now = [time.time() + 2]
        self.run_worker(self.worker(Classifier(), now), now)
        self.assertIn('MAYBE-MARKER', self.public('world-view'))
        (r,) = [i for i in self.hand.automod('review')['items'] if i['author'] == cy]
        self.assertEqual(self.say(cy, 'not quieted')['status'], 'admitted')
        self.hand.automod_review(r['key'], 'hide', 'on reflection')
        self.assertNotIn('MAYBE-MARKER', self.public('world-view'))
        self.hand.automod_review(r['key'], 'restore', 'it was fine')
        self.assertIn('MAYBE-MARKER', self.public('world-view'))
        page = self.hand.handle('GET', '/hand/town/automod', f'{hand.HAND_COOKIE}=t')[1]
        self.assertIn('MAYBE-MARKER', page)
        self.assertIn('restored', page)
        acts = [e['outcome'] for e in self.town.send(op='world-entries', principal=self.town.opener, reverse=True, limit=10)['entries']
                if (e.get('outcome') or {}).get('power') == 'screen' and e['outcome'].get('key') == r['key']]
        self.assertEqual([a['after'] for a in acts], ['restored', 'hidden', 'review'])
        self.assertEqual(acts[0]['reading'], 'it was fine')
        # A restored text is never screened again: the same words said again are not asked about.
        glm = Classifier()
        self.say(self.arrive('cy2'), MAYBE)
        self.run_worker(self.worker(glm, now), now)
        self.assertFalse(any('MAYBE' in t['text'] for c in glm.calls for t in c))

    def test_the_wordlist_acts_while_the_classifier_is_down_and_restore_lifts_the_quiet(self):
        dee = self.arrive('dee')
        slur = 'n i g g e r'  # spaced out, the list still reads it
        self.say(dee, f'hey {slur} over there')
        self.say(dee, 'a MEDIUM line the list does not know')
        now, glm = [time.time() + 3], Classifier()
        glm.down = True
        w = self.worker(glm, now)
        w.step()
        self.assertNotIn(slur, self.public('world-view'), 'the wordlist acts at the first step, before any call')
        refused = self.say(dee, 'more')
        self.assertEqual((refused.get('receipt') or {}).get('outcome', {}).get('class') or refused.get('class'), 'quiet')
        now[0] += 6
        w.step()
        self.assertEqual(len(glm.calls), 1)
        self.assertIn('MEDIUM line', self.public('world-view'), 'a failed call hides nothing')
        s = automod.status(self.st)
        self.assertEqual(s['glm'], 'down')
        self.assertTrue(any('MEDIUM' in i['text'] for i in w.pending), w.pending)
        o = self.hand.overview()
        self.assertIn('down', o['automod']['state'])
        w.step()
        self.assertEqual(len(glm.calls), 1, 'backing off: no second call at once')
        glm.down = False
        now[0] += automod.BACKOFF_MAX + 1
        w.step()
        self.assertNotIn('MEDIUM line', self.public('world-view'))
        (listed,) = [i for i in self.hand.automod('hidden')['items'] if i['by'] == 'wordlist' and i['author'] == dee]
        got = self.hand.automod_review(listed['key'], 'restore', 'quoted, not meant')
        self.assertTrue(got['unquieted'])
        self.assertEqual(self.say(dee, 'thank you')['status'], 'admitted')

    def test_replay_derives_the_same_screened_texts(self):
        eve = self.arrive('eve')
        self.say(eve, 'FOUL again from eve')
        now = [time.time() + 4]
        self.run_worker(self.worker(Classifier(), now), now)
        before = self.town.send(op='world-screened', principal=self.town.opener, limit=500)
        card = self.public('world-card')
        self.town.reopen()  # serve again: the journal replayed from its snapshot and tail
        after = self.town.send(op='world-screened', principal=self.town.opener, limit=500)
        self.assertEqual(before['items'], after['items'])
        self.assertEqual(before['counts'], after['counts'])
        self.assertNotIn('FOUL again', self.public('world-card'))
        self.assertNotIn('FOUL again', card)

    def test_a_resident_cannot_reach_the_moderation(self):
        public = HostClient(self.town.process.sock)
        try:
            for op in ('world-screen', 'world-screen-verdicts', 'world-screen-review'):
                r = public.send({'op': op, 'principal': self.town.opener, 'after': 0})
                self.assertEqual(r['status'], 'error', (op, r))
            r = self.town.send(op='world-screen', principal='guest:obend.example:mallory', after=0)
            self.assertEqual(r['status'], 'error', r)
            listed = public.send({'op': 'world-screened', 'principal': PUBLIC})
            self.assertTrue(all(set(i) == {'key', 'source', 'state'} for i in listed['items']), listed)
            forged = self.town.send(op='world-screen-verdicts', principal=self.town.opener, items=[{'key': 'bafy-not-its-key', 'text': 'x'}],
                                    reply={'status': 'replied', 'raw': '{"verdicts": []}'})
            self.assertEqual(forged['status'], 'error', forged)
        finally:
            public.close()

    def test_an_offered_text_at_its_bound_is_taken_and_one_past_it_refused(self):
        big = 'a' * (64 * 1024)
        ok = self.town.send(op='world-screen', principal=self.town.opener, after=10**9, external=[{'source': 'feed:x', 'text': big}])
        self.assertEqual(ok['status'], 'screen', str(ok)[:200])
        self.assertEqual(len(ok['items'][0]['text']), 64 * 1024)
        past = self.town.send(op='world-screen', principal=self.town.opener, after=10**9, external=[{'source': 'feed:y', 'text': big + 'a'}])
        self.assertEqual(past['status'], 'error')
        self.assertTrue(len(automod.user_text([{'text': big}]).encode()) < automod.CLIP + 100, 'the classifier reads a clip')

    def test_a_short_hidden_word_is_hidden_only_where_it_stands_as_a_word(self):
        r = self.town.send(op='world-redact', principal=PUBLIC, items=[{'text': 'class'}])
        self.assertEqual(r['texts'], ['class'])


class Logs(unittest.TestCase):
    """The worker's container log: one line per batch and per error, never a text. Refuted by a batch with no line, a line with
    a text, a key or a reason's words in it, an error repeated every step, or a start with no line."""

    def run_batches(self, answers):
        import contextlib
        import io
        import tempfile
        from transport.state import State
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(err):
            host = type('H', (), {'send': lambda s, req: {'status': 'verdicts', 'acted': [], 'unanswered': []}, 'close': lambda s: None})()
            replies = iter(answers)
            w = automod.Worker(State(d), host, ask=lambda system, user: next(replies), clock=lambda: 100.0)
            for _ in answers:
                w.classify([{'key': 'secret-key', 'text': 'secret-text', 'source': 's', 'author': 'a', 'at': 1, 'seen': 0}])
                w.wait_until = 0
        return err.getvalue().splitlines()

    def test_a_batch_is_one_line_and_an_error_one_line_until_it_changes(self):
        down = {'status': 'failed', 'reason': 'secret-reason', 'detail': 'secret-detail', 'seconds': 0.5}
        lines = self.run_batches([down, down, down, {'status': 'replied', 'model': 'm', 'usage': {}, 'seconds': 0.2, 'raw': '[]'}])
        self.assertEqual([l.rsplit(' seconds=', 1)[0] for l in lines if 'batch' in l], ['automod: batch texts=1 status=failed'] * 3 + ['automod: batch texts=1 status=replied'])
        self.assertEqual([l for l in lines if 'error' in l], ['automod: error classifier failed'])
        for secret in ('secret-key', 'secret-text', 'secret-reason', 'secret-detail'):
            self.assertNotIn(secret, '\n'.join(lines))

    def test_the_worker_says_it_started(self):
        import contextlib
        import io
        import tempfile
        from transport.state import State
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(err):
            st = State(d, world='gsb')
            with mock.patch.object(st, 'root_host', lambda: type('H', (), {'send': lambda s, r: {}, 'close': lambda s: None})()), \
                    mock.patch.object(st, 'daemon', lambda *a, **k: None):
                automod.command(st, type('A', (), {'once': False, 'backfill': False})(), io.StringIO())
        self.assertEqual(err.getvalue().splitlines(), ['automod: started world=gsb'])


class Wire(unittest.TestCase):
    """ask_glm over a fake transport: the Anthropic-compatible endpoint's answers, the key read from its file and sent as x-api-key."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, 'zai.key').write_text('k' * 49 + '\n')
        self.st = State(self.tmp.name, config=Config(zai_key_file=str(Path(self.tmp.name, 'zai.key'))))
        self.sent = []

    def answers(self, *replies):
        replies = list(replies)
        def transport(method, url, headers, body):
            self.sent.append((url, headers, json.loads(body)))
            status, payload = replies.pop(0)
            return status, json.dumps(payload).encode(), {}
        return transport

    def test_a_batch_is_one_messages_call_with_thinking_off_and_the_text_blocks_are_the_answer(self):
        ok = {'model': 'glm-5.3-flash', 'content': [{'type': 'thinking', 'thinking': 'hm'}, {'type': 'text', 'text': '{"verdicts": []}'}],
              'stop_reason': 'end_turn', 'usage': {'input_tokens': 3, 'output_tokens': 2}}
        got = automod.ask_glm(self.st, 'policy', 'Texts:', self.answers((200, ok)))
        self.assertEqual((got['status'], got['model'], got['raw'], got['usage']['input_tokens']), ('replied', 'glm-5.3-flash', '{"verdicts": []}', 3))
        url, headers, body = self.sent[0]
        self.assertEqual(url, 'https://api.z.ai/api/anthropic/v1/messages')
        self.assertEqual((headers['x-api-key'], headers['anthropic-version']), ('k' * 49, '2023-06-01'))
        self.assertNotIn('Authorization', headers)
        self.assertEqual((body['model'], body['system'], body['thinking']), ('glm-5.3-flash', 'policy', {'type': 'disabled'}))
        self.assertEqual(body['messages'], [{'role': 'user', 'content': 'Texts:'}])

    def test_a_loaded_or_refused_provider_fails_and_nothing_else_is_asked(self):
        for status, reason in ((429, 'rate'), (401, 'refused'), (500, 'transport')):
            self.sent.clear()
            got = automod.ask_glm(self.st, 'p', 'u', self.answers((status, {'error': {'code': '1305'}})))
            self.assertEqual((got['status'], got['reason']), ('failed', reason))
            self.assertEqual(len(self.sent), 1)  # no second model, no second API shape

    def test_the_providers_own_filter_is_blocked_and_no_key_sends_nothing(self):
        self.assertEqual(automod.ask_glm(self.st, 'p', 'u', self.answers((400, {'error': {'code': '1301'}})))['status'], 'blocked')
        sensitive = {'content': [], 'stop_reason': 'sensitive'}
        self.assertEqual(automod.ask_glm(self.st, 'p', 'u', self.answers((200, sensitive)))['status'], 'blocked')
        none = State(self.tmp.name, config=Config(zai_key_file=''))
        self.assertEqual(automod.ask_glm(none, 'p', 'u', self.answers())['reason'], 'refused')
        self.assertEqual(len(self.sent), 2)


class Feed_(FrontCase):
    """A foul post in the town's own feed, hidden from its page and its JSON once screened."""

    def test_a_foul_feed_post_is_hidden_from_the_feed_and_the_dark_one_stays(self):
        st = State(self.tmp.name, config=Config(host_socket=self.socket, root_socket=self.root_socket, opener=self.OPENER, zai_key_file='/nonexistent'))
        feed = Feed(st)
        foul = feed.post({'did': 'did:plc:' + 'f' * 24, 'handle': 'foul.example'}, 'FOUL post: ' + FOUL)
        dark = feed.post({'did': 'did:plc:' + 'd' * 24, 'handle': 'dark.example'}, DARK)
        feed.close()
        tok = self.login()
        s, before = self.call('GET', '/AGENTS.md/feed', token=tok)
        self.assertIn('FOUL-SLUR-MARKER', json.dumps(before))
        now, glm = [time.time() + 5], Classifier()
        w = automod.Worker(st, self.root, ask=glm, clock=lambda: now[0])
        w.step()
        now[0] += 6
        w.step()
        sources = {t['text'][:9] for c in glm.calls for t in c}
        self.assertIn('FOUL post', sources)
        s, after = self.call('GET', '/AGENTS.md/feed', token=tok)
        self.assertEqual(s, 200)
        shown = json.dumps(after)
        self.assertNotIn('FOUL-SLUR-MARKER', shown)
        self.assertIn(PLACEHOLDER, shown)
        self.assertIn('floorboards breathed', shown)
        s, _, page = self.request('GET', '/feed', headers={'Accept': 'text/html'})
        self.assertNotIn(b'FOUL-SLUR-MARKER', page)
        self.assertIn(b'floorboards breathed', page)
        hidden = self.root.send({'op': 'world-screened', 'principal': self.OPENER})['items']
        self.assertEqual([i['source'] for i in hidden], ['feed:' + foul['uri']])
        self.assertNotEqual(dark['uri'], foul['uri'])


class Line(unittest.TestCase):
    """The deploy of edition 16: the overview's line read "idle" where the docs promised "the classifier answers". It says
    what is true: idle and healthy, starting, working (with its last call's time), down, spent."""

    def test_the_overview_line_says_what_is_true(self):
        import json as json_
        import types
        from transport import overview
        from transport.config import Config
        with tempfile.TemporaryDirectory() as d:
            st = State(d, config=Config())
            h = types.SimpleNamespace(st=st, owner='o', host=types.SimpleNamespace(send=lambda req: {}))
            st.home.mkdir(parents=True, exist_ok=True)
            def line(**note):
                (st.home / 'automod-status.json').write_text(json_.dumps({'at': time.time(), 'pending': 0, **note}))
                return overview.automod_of(h)['state']
            self.assertEqual(line(glm='idle'), 'idle and healthy: nothing has needed the classifier since the worker started')
            self.assertEqual(line(glm='idle', pending=3), 'starting: 3 waiting for the first batch')
            self.assertTrue(line(glm='ok', lastCall={'at': 60, 'texts': 2}).startswith('working: the classifier answered its last batch at 00:01 UTC'))
            self.assertIn('down', line(glm='down', lastError='transport: x'))


class Past(unittest.TestCase):
    """The deploy of edition 16: the worker screens what the host's own journal holds, so a carried town's past was never
    screened. A backfill reads the ancestor journals the carried genesis cites through the host, a dry run first: its
    report names what it would hide and nothing changes; with the owner's word it hides them, quieting nobody. Refuted
    by a dry run that hides or journals anything, a past text missing from its report, an act that misses one, or a
    pass that cannot resume."""

    def test_a_carried_towns_past_is_reported_by_a_dry_run_then_hidden_on_the_owners_word(self):
        import os
        import subprocess
        from tests.host import binary
        from transport.host import HostProcess
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        town = Town(tmp.name, cleanup=self.addCleanup, furnished=False)
        kim = 'did:plc:kimkimkimkimkimkimkimkimk'
        town.send(op='world-arrive', principal=CLOCK, did=kim, handle='kim')
        self.assertEqual(town.send(op='world-turn', principal=kim, object='porch', method='enter', identity='e', argument=record())['status'], 'admitted')
        for n, line in enumerate((FOUL, DARK)):
            self.assertEqual(town.send(op='world-turn', principal=kim, object='porch', method='say', identity=f's{n}', argument=record(line=label(line)))['status'], 'admitted')
        self.assertEqual(town.send(op='world-snapshot')['status'], 'snapshot')
        journal, opener = town.journal, town.opener
        town.close()
        out = os.path.join(tmp.name, 'carried.journal')
        p = subprocess.run([binary(), 'carry', '--from', journal, '--out', out, '--reason', 'a newer host'], capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        host = HostProcess(binary(), out)
        self.addCleanup(host.close)
        st = State(os.path.join(tmp.name, 'worker'), config=Config(opener=opener, zai_key_file='/nonexistent'))
        public = lambda: json.dumps(host.send({'op': 'world-view', 'principal': PUBLIC, 'object': 'porch'}))  # noqa: E731
        glm = Classifier()
        height = host.send({'op': 'world-status'})['height']
        dry = automod.backfill(st, host, ask=glm, entries=8)  # bounded: a first pass stops early and resumes
        self.assertEqual((dry['status'], dry['start']), ('dryRun', 1), dry)
        while not dry.get('done'):
            dry = automod.backfill(st, host, ask=glm, entries=8)
            self.assertIn(dry['status'], ('dryRun',), dry)
        lines = [json.loads(l) for l in (st.home / 'automod-backfill.jsonl').read_text().splitlines()]
        self.assertEqual([(l['text'], l['state'], l['would']) for l in lines], [(FOUL, 'hidden', True)])
        self.assertIn('FOUL-SLUR-MARKER', public())  # a dry run hides nothing
        self.assertEqual(host.send({'op': 'world-status'})['height'], height)  # and journals nothing
        (st.home / 'automod-backfill.json').unlink()
        done = automod.backfill(st, host, ask=glm, act=True, entries=100000)
        self.assertEqual((done['status'], done['hidden'], done['done']), ('acted', 1, True), done)
        self.assertNotIn('FOUL-SLUR-MARKER', public())
        self.assertNotIn(kim, json.dumps(host.send({'op': 'world-status'}).get('quiets') or {}))  # nobody quieted for the past


if __name__ == '__main__':
    unittest.main()
