"""Observation validates transport bytes at the client boundary (FOUNDATION §7).

Refuted by a malformed timestamp being stored or a URI parsed differently by the observer and record client.
"""
import tempfile
import unittest
from unittest import mock

from transport import delve, observe
from transport.config import Config
from transport.state import State


def post(uri='at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/town.delve.feed.post/r1', created='2026-10-12T10:00:00Z', text='hello'):
    return {'uri': uri, 'cid': 'c', 'author': {'did': 'did:plc:' + 'a' * 24, 'handle': 'robin.delve.town'},
            'record': {'createdAt': created, 'text': text}}


class Observation(unittest.TestCase):
    def test_not_a_date_is_refused_even_without_a_since_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            st = State(directory, config=Config())
            ob = observe.Observer(st, None)
            self.addCleanup(ob.db.close)
            for stamp in ('not-a-date', '2026-02-30T10:00:00Z', '2026-10-12', '2026-10-12T10:00:00', None, 42):
                with self.subTest(stamp=stamp):
                    self.assertFalse(ob.store(post(created=stamp)))
                    with self.assertRaises(ValueError):
                        ob.before_start(stamp)
            self.assertEqual(st.observations(), [])
            with self.assertRaises(delve.Failure) as caught:
                observe.observation(post(created='not-a-date'))
            self.assertEqual(caught.exception.code, 'malformed_post')

    def test_the_maximum_post_body_and_latest_timestamp_are_observed(self):
        value = post(created='9999-12-31T23:59:59.999999Z', text='x' * observe.MAX_TEXT)
        got = observe.observation(value)
        self.assertEqual((got['createdAt'], got['text']), (value['record']['createdAt'], value['record']['text']))
        with self.assertRaises(delve.Failure) as caught:
            observe.observation(post(text='x' * (observe.MAX_TEXT + 1)))
        self.assertEqual(caught.exception.code, 'post_body_too_large')

    def test_the_observer_uses_the_client_parser_and_keeps_its_did_authority_policy(self):
        with mock.patch.object(delve, 'parse_at_uri', wraps=delve.parse_at_uri) as parser:
            self.assertEqual(observe.observation(post())['uri'], post()['uri'])
            parser.assert_called_once_with(post()['uri'])
        uri = 'at://robin.delve.town/town.delve.feed.post/r1'
        self.assertEqual(delve.parse_at_uri(uri).repo, 'robin.delve.town')
        with self.assertRaises(delve.Failure) as caught:
            observe.observation(post(uri=uri))
        self.assertEqual(caught.exception.code, 'malformed_post')


class ATUris(unittest.TestCase):
    def test_a_did_uri_and_a_handle_uri_supply_structured_record_parameters(self):
        for repo in ('did:plc:' + 'a' * 24, 'robin.delve.town', 'did:web:example.com%3A443'):
            with self.subTest(repo=repo):
                uri = f'at://{repo}/town.delve.feed.post/r~1'
                parsed = delve.parse_at_uri(uri)
                self.assertEqual((parsed.repo, parsed.collection, parsed.rkey), (repo, delve.POST, 'r~1'))
                client = delve.Client(lambda *args: self.fail('unexpected network call'))
                with mock.patch.object(client, 'get', return_value={}) as get:
                    client.record(uri)
                get.assert_called_once_with('com.atproto.repo.getRecord', repo=repo, collection=delve.POST, rkey='r~1')

    def test_maximum_record_parameters_parse_without_truncation(self):
        repo, collection, rkey = 'did:test:' + 'a' * (delve.MAX_PARAM - 9), 'a' * delve.MAX_PARAM, 'r' * 512
        uri = f'at://{repo}/{collection}/{rkey}'
        parsed = delve.parse_at_uri(uri)
        self.assertEqual(tuple(parsed), (repo, collection, rkey))
        self.assertEqual(observe.observation(post(uri=uri))['uri'], uri)

    def test_extra_paths_queries_fragments_spaces_dot_keys_and_oversized_parameters_are_not_records(self):
        base = post()['uri']
        for uri in (None, '', base + '/extra', base + '?q=1', base + '#f', base + '\n', base.replace('r1', '..'),
                    base.replace('r1', '.'), base.replace('r1', 'r' * 513),
                    f'at://did:test:{"a" * delve.MAX_PARAM}/town.delve.feed.post/r1',
                    f'at://did:test:a/{"a" * (delve.MAX_PARAM + 1)}/r1',
                    'at://bad authority/town.delve.feed.post/r1', 'at://did:test:a/town/delve/r1'):
            with self.subTest(uri=uri):
                with self.assertRaises(delve.Failure) as caught:
                    delve.parse_at_uri(uri)
                self.assertEqual(caught.exception.code, 'bad_at_uri')
                client = delve.Client(lambda *args: self.fail('unexpected network call'))
                with self.assertRaises(delve.Failure):
                    client.record(uri)
