"""Validated preparation of every Lexicon v1 schema for its DNS authority (ATPROTO §5).

Refuted by: a missing/extra NSID, altered document, wrong DAG-CBOR CID/size, a socket or file write
in a dry run (except injected public GETs), an unchanged record written twice, a failed write remembered, a removed file deleted
from the account, or a credential session belonging to another DID allowed to write.
"""
import json
import os
import shutil
import tempfile
import unittest
from functools import wraps
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from transport import post
from transport.__main__ import main, parser
from transport.atproto.cbor import block, from_json
from transport.config import Config
from transport.delve import Failure, canonical
from transport.lexicon import DIR, reference_problems
from transport.state import State

AUTHORITY = 'did:plc:6amo7col5h4ciq2gpm5eur7b'
COLLECTION = 'com.atproto.lexicon.schema'
TXT_CHECK = 'dig +short TXT _lexicon.gsb.fg-goose.online'


def needs_reference(test):
    @wraps(test)
    def run(self):
        if self.reference_unavailable:
            self.skipTest('reference validator unavailable: ' + self.reference_unavailable)
        return test(self)
    return run


class Writer:
    """A record writer with no network; values of None would expose a deletion."""
    def __init__(self):
        self.calls = []

    def __call__(self, collection, rkey, value):
        self.calls.append((collection, rkey, value))


class Client:
    """A credential's session and putRecord responses, without sockets."""
    def __init__(self, did=AUTHORITY):
        self.did, self.calls = did, []

    def write(self, nsid, body, token=None):
        self.calls.append((nsid, body, token))
        if nsid == 'com.atproto.server.createSession':
            return {'did': self.did, 'accessJwt': 'jwt'}
        if nsid != 'com.atproto.repo.putRecord':
            raise AssertionError(nsid)
        return {'uri': f'at://{body["repo"]}/{body["collection"]}/{body["rkey"]}', 'cid': 'c'}


class Publication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.reference_unavailable, cls.reference_validator = reference_problems()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / 'schemas'
        shutil.copytree(DIR, self.directory)
        self.credential = self.root / 'credential.json'
        self.credential.write_text(canonical({'identifier': 'owner', 'password': 'fake'}))
        self.state = self.root / 'state'
        self.state.mkdir()
        (self.state / 'delvetalk.toml').write_text(f'credentials = {json.dumps(str(self.credential))}\n')
        env = {name: os.environ[name] for name in ('PATH', 'ATPROTO_LEXICON_PACKAGE') if name in os.environ}
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, authorized=False, **seams):
        output = StringIO()
        argv = ['lexicons', '--state', str(self.state)] + (['--authorized'] if authorized else [])
        seams.setdefault('fetch', self.offline)
        with patch('socket.socket', side_effect=AssertionError('socket opened')):
            code = main(argv, output, directory=self.directory, **seams)
        return code, output.getvalue()

    @staticmethod
    def offline(*args):
        raise OSError('offline test')

    @needs_reference
    def test_published_values_compare_by_dag_cbor_cid_at_the_resolved_pds_across_pages(self):
        values = list(sorted(self.values().items()))
        calls = []
        def fetch(method, url, headers, body):
            from urllib.parse import parse_qs, urlsplit
            calls.append(url)
            self.assertEqual(method, 'GET')
            self.assertIsNone(body)
            self.assertNotIn('Authorization', headers)
            if url == 'https://plc.directory/' + AUTHORITY:
                response = {'id': AUTHORITY, 'service': [{'id': '#atproto_pds',
                            'serviceEndpoint': 'https://owner.example/'}]}
            else:
                parts = urlsplit(url)
                self.assertEqual(parts.netloc, 'owner.example')
                self.assertEqual(parts.path, '/xrpc/com.atproto.repo.listRecords')
                query = parse_qs(parts.query)
                self.assertEqual(query['repo'], [AUTHORITY])
                self.assertEqual(query['collection'], [COLLECTION])
                index = 1 if 'cursor' in query else 0
                nsid, value = values[index]
                # Advertised cid is deliberately wrong; compare the actual value, with reordered keys.
                value = dict(reversed(list(value.items()))) if index == 0 else {**value, 'description': 'different'}
                response = {'records': [{'uri': f'at://{AUTHORITY}/{COLLECTION}/{nsid}',
                                        'cid': 'untrusted', 'value': value}],
                            **({'cursor': 'next'} if index == 0 else {})}
            return 200, json.dumps(response).encode(), {}
        code, output = self.invoke(fetch=fetch)
        self.assertEqual(code, 2)
        rows = [json.loads(line) for line in output.splitlines()[1:-1]]
        self.assertEqual([r['published'] for r in rows], ['same', 'differs'] + ['new'] * (len(values) - 2))
        self.assertEqual(len(calls), 3)
        writer = Writer()
        with patch.object(post, 'record_writer', return_value=writer):
            code, output = self.invoke(True, fetch=fetch)
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line)['published'] for line in output.splitlines()[1:-1]],
                         ['same', 'differs'] + ['new'] * (len(values) - 2))

    @needs_reference
    def test_invalid_nested_schema_refuses_authorized_before_reads_credentials_or_writes(self):
        path = self.directory / 'card.json'
        doc = json.loads(path.read_text())
        doc['defs']['main']['record']['properties']['doors']['items'] = {'type': 'object', 'properties': {}}
        path.write_text(canonical(doc))
        before = {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        with patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')):
            code, output = self.invoke(True, fetch=lambda *a: self.fail('network read before validation'))
        self.assertEqual(code, 1)
        self.assertIn('lexicon_validation', output)
        self.assertIn('card', output)
        self.assertEqual({p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}, before)

    @needs_reference
    def test_reference_only_syntax_error_in_the_last_file_refuses_the_whole_batch(self):
        path = self.directory / 'try.json'
        doc = json.loads(path.read_text())
        doc['defs']['main']['input']['schema']['properties']['intent']['format'] = 'not-a-format'
        path.write_text(canonical(doc))
        with patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')):
            code, output = self.invoke(True, fetch=lambda *a: self.fail('network read before validation'))
        self.assertEqual(code, 1)
        self.assertIn('try.json', output)
        self.assertIn('not-a-format', output)
        self.assertFalse(State(self.state).lexicon_ledger.exists())

    def test_authorized_refuses_when_reference_validator_cannot_run_but_dry_run_explains_it(self):
        with patch('transport.lexicon.reference_problems', return_value=([], 'node missing', None)), \
                patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')):
            self.assertEqual(self.invoke(True)[0], 1)
            code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.splitlines()[-1])['reference'], 'unavailable (node missing)')
        self.assertEqual(len(output.splitlines()[1:-1]), len(self.values()))

    def test_status_uses_the_validator_identity_returned_by_the_reference_script(self):
        with patch('transport.lexicon.reference_problems', return_value=([], None, 'reported validator')), \
                patch.object(post, 'record_writer', return_value=Writer()):
            for authorized in (False, True):
                with self.subTest(authorized=authorized):
                    code, output = self.invoke(authorized)
                    self.assertEqual(code, 0 if authorized else 2)
                    self.assertEqual(json.loads(output.splitlines()[-1])['reference'], 'reported validator: passed')

    @unittest.skipUnless(shutil.which('node'), 'node is absent')
    def test_missing_reference_package_is_refused_and_named_without_a_writer_or_ledger(self):
        with patch.dict(os.environ, {'ATPROTO_LEXICON_PACKAGE': str(self.root / 'absent-package')}), \
                patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')):
            code, output = self.invoke(True)
            self.assertEqual(code, 1)
            self.assertIn('reference validator required', output)
            self.assertIn('absent-package', output)
            code, output = self.invoke()
            self.assertEqual(code, 2)
            self.assertIn('unavailable', output)
        self.assertFalse(State(self.state).lexicon_ledger.exists())

    def test_partial_read_failure_or_wrong_did_document_is_unknown_for_the_whole_batch(self):
        for wrong_did in (True, False):
            with self.subTest(wrong_did=wrong_did):
                def fetch(method, url, headers, body):
                    if url == 'https://plc.directory/' + AUTHORITY:
                        response = {'id': 'did:plc:wrong' if wrong_did else AUTHORITY,
                                    'service': [{'id': AUTHORITY + '#atproto_pds', 'serviceEndpoint': 'https://owner.example'}]}
                    elif 'cursor=' not in url:
                        nsid, value = next(iter(self.values().items()))
                        response = {'records': [{'uri': f'at://{AUTHORITY}/{COLLECTION}/{nsid}', 'value': value}], 'cursor': 'next'}
                    else:
                        raise OSError('page two unavailable')
                    return 200, json.dumps(response).encode(), {}
                code, output = self.invoke(fetch=fetch)
                self.assertEqual(code, 2)
                rows = [json.loads(line) for line in output.splitlines()[1:-1]]
                self.assertTrue(all(row['published'].startswith('unknown (') for row in rows))
                self.assertIn('did_document_mismatch' if wrong_did else 'page two unavailable', output)

    def test_offline_published_state_is_unknown_for_every_document(self):
        code, output = self.invoke()
        self.assertEqual(code, 2)
        rows = [json.loads(line) for line in output.splitlines()[1:-1]]
        self.assertTrue(all(row['published'] == 'unknown (offline test)' for row in rows))

    def values(self):
        return {json.loads(p.read_text())['id']: {**json.loads(p.read_text()), '$type': COLLECTION}
                for p in self.directory.rglob('*.json')}

    def test_default_dry_run_lists_exact_files_in_nsid_order_with_canonical_cids_and_no_effects(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')), \
                patch.object(State, 'host', side_effect=AssertionError('host opened')), \
                patch.object(Path, 'write_text', side_effect=AssertionError('file written')), \
                patch.object(State, 'write', side_effect=AssertionError('ledger written')):
            code, output = self.invoke()
        self.assertEqual(code, 2)
        lines = output.splitlines()
        self.assertEqual(lines[0], TXT_CHECK)
        rows = [json.loads(line) for line in lines[1:]]
        self.assertEqual(lines[1:], [canonical(row) for row in rows])
        values = self.values()
        expected = []
        for nsid, value in sorted(values.items()):
            cid, raw = block(from_json(value))
            expected.append({'collection': COLLECTION, 'rkey': nsid, 'cid': str(cid), 'bytes': len(raw),
                             'published': 'unknown (offline test)'})
            self.assertEqual(value['id'], nsid)
        self.assertEqual(rows[:-1], expected)
        reference = (f'unavailable ({self.reference_unavailable})' if self.reference_unavailable
                     else f'{self.reference_validator}: passed')
        self.assertEqual(rows[-1], {'count': len(values), 'did': AUTHORITY, 'reference': reference})
        self.assertEqual({p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)

    def test_exact_command_needs_no_state_or_credential_for_a_dry_run(self):
        output = StringIO()
        with patch('socket.socket', side_effect=AssertionError('socket opened')), \
                patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')):
            self.assertEqual(main(['lexicons'], output, fetch=self.offline), 2)
        reference = (f'unavailable ({self.reference_unavailable})' if self.reference_unavailable
                     else f'{self.reference_validator}: passed')
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1]),
                         {'count': len(list(DIR.rglob('*.json'))), 'did': AUTHORITY,
                          'reference': reference})
        self.assertFalse(parser().parse_args(['lexicons']).authorized)

    @needs_reference
    def test_fake_writer_puts_every_document_once_then_only_a_changed_document_and_never_deletes(self):
        writer = Writer()
        with patch.object(post, 'record_writer', return_value=writer) as factory:
            self.assertEqual(self.invoke(True)[0], 0)
            factory.assert_called_once()
            self.assertEqual(factory.call_args.kwargs['expected_did'], AUTHORITY)
            self.assertEqual(writer.calls, [(COLLECTION, k, v) for k, v in sorted(self.values().items())])
            st = State(self.state)
            self.assertTrue(st.lexicon_ledger.exists())
            self.assertFalse(st.mirror.exists())
            ledger = st.lexicon_ledger.read_bytes()
            writer.calls.clear()
            self.assertEqual(self.invoke(True)[0], 0)
            self.assertEqual(writer.calls, [])
            self.assertEqual(st.lexicon_ledger.read_bytes(), ledger)
            path = self.directory / 'defs.json'
            changed = json.loads(path.read_text())
            changed['description'] = 'Unicode retained: 🪿\n' + 'x' * 4096
            path.write_text(canonical(changed))
            self.invoke(True)
            self.assertEqual(writer.calls, [(COLLECTION, changed['id'], {**changed, '$type': COLLECTION})])
            writer.calls.clear()
            path.unlink()
            retained = st.lexicon_ledger.read_bytes()
            self.invoke(True)
            self.assertEqual(writer.calls, [])
            self.assertEqual(st.lexicon_ledger.read_bytes(), retained)
            self.assertIn(f'{COLLECTION} {changed["id"]}', json.loads(retained))
            # Publication belongs to the account, independent of the selected world.
            self.assertEqual(State(self.state, 'garden').lexicon_ledger, st.lexicon_ledger)

    @needs_reference
    def test_a_maximum_length_nsid_name_keeps_every_document_field_and_dag_cbor_byte(self):
        name = 'a' * 63
        nsid = 'online.fg-goose.gsb.' + name
        value = {'lexicon': 1, 'id': nsid, 'description': '🪿' * 4096,
                 'defs': {'main': {'type': 'token', 'description': 'public token'}}, 'revision': 1}
        (self.directory / (name + '.json')).write_text(canonical(value))
        _, output = self.invoke()
        rows = [json.loads(line) for line in output.splitlines()[1:-1]]
        cid, raw = block(from_json({**value, '$type': COLLECTION}))
        self.assertEqual(next(row for row in rows if row['rkey'] == nsid),
                         {'collection': COLLECTION, 'rkey': nsid, 'cid': str(cid), 'bytes': len(raw),
                          'published': 'unknown (offline test)'})
        writer = Writer()
        with patch.object(post, 'record_writer', return_value=writer):
            self.invoke(True)
        self.assertIn((COLLECTION, nsid, {**value, '$type': COLLECTION}), writer.calls)

    @needs_reference
    def test_each_put_is_the_verbatim_v1_document_in_the_sessions_own_repo(self):
        client = Client()
        self.invoke(True, client=client)
        self.assertEqual(client.calls[0], ('com.atproto.server.createSession', {'identifier': 'owner', 'password': 'fake'}, None))
        self.assertEqual(client.calls[1:], [('com.atproto.repo.putRecord',
                         {'repo': AUTHORITY, 'collection': COLLECTION, 'rkey': k, 'record': v, 'validate': False}, 'jwt')
                         for k, v in sorted(self.values().items())])

    @needs_reference
    def test_wrong_credential_did_aborts_before_any_put_even_when_the_ledger_is_complete(self):
        for complete in (False, True):
            with self.subTest(complete=complete):
                if complete:
                    self.invoke(True, client=Client())
                client = Client('did:plc:anotheraccount')
                before = {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
                with self.assertRaisesRegex(Failure, 'lexicon_authority'):
                    self.invoke(True, client=client)
                self.assertEqual([n for n, _, _ in client.calls], ['com.atproto.server.createSession'])
                self.assertEqual({p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}, before)

    @needs_reference
    def test_configured_authority_is_checked_and_has_its_own_ledger(self):
        self.invoke(True, client=Client())
        old = State(self.state).lexicon_ledger
        other = 'did:plc:otherauthority'
        with (self.state / 'delvetalk.toml').open('a') as f:
            f.write(f'lexicon_authority = "{other}"\n')
        self.assertEqual(Config.load(self.state, environ={}).lexicon_authority, other)
        client = Client(other)
        self.invoke(True, client=client)
        self.assertEqual(len(client.calls), len(self.values()) + 1)
        self.assertTrue(all(body['repo'] == other for _, body, _ in client.calls[1:]))
        self.assertNotEqual(State(self.state).lexicon_ledger, old)

    @needs_reference
    def test_a_failed_write_is_not_remembered_and_retry_writes_only_the_remaining_records(self):
        writer = Writer()
        values = sorted(self.values().items())
        def interrupted(c, k, v):
            if k == values[1][0]:
                raise Failure('test_interrupted')
            writer(c, k, v)
        with patch.object(post, 'record_writer', return_value=interrupted):
            with self.assertRaises(Failure):
                self.invoke(True)
        self.assertEqual(len(json.loads(State(self.state).lexicon_ledger.read_text())), 1)
        writer.calls.clear()
        with patch.object(post, 'record_writer', return_value=writer):
            self.invoke(True)
        self.assertEqual(writer.calls, [(COLLECTION, k, v) for k, v in values[1:]])

    def test_mismatched_id_or_version_is_refused_before_a_writer_is_opened(self):
        path = self.directory / 'defs.json'
        original = json.loads(path.read_text())
        for bad in ({**original, 'id': 'online.fg-goose.gsb.wrong'}, {**original, 'lexicon': True},
                    {**original, 'lexicon': 2}, {**original, '$type': 'wrong'}):
            with self.subTest(bad=bad):
                path.write_text(canonical(bad))
                with patch.object(post, 'record_writer', side_effect=AssertionError('writer opened')):
                    code, output = self.invoke(True)
                    self.assertEqual(code, 1)
                    self.assertIn('lexicon_document', output)


if __name__ == '__main__':
    unittest.main()
