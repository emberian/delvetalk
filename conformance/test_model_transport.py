"""Physical model credential and HTTP custody checks; no network or native build."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import model_service as model

class Transport(unittest.TestCase):
    def test_explicit_account_private_file_and_no_refresh_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokens.toml'
            raw = b'[[tokens]]\nname="fixture"\nkey="synthetic-setup"\naccess_token="synthetic-login"\nrefresh_token="synthetic-refresh"\nexpires_at=9999999999999\n'
            path.write_bytes(raw)
            path.chmod(0o600)
            self.assertEqual(model.configured_credential('fixture', path=path), 'synthetic-login')
            self.assertEqual(path.read_bytes(), raw)
            path.write_bytes(raw.replace(b'9999999999999', b'1'))
            self.assertEqual(model.configured_credential('fixture', path=path), 'synthetic-setup')
            with self.assertRaises(ValueError): model.configured_credential('absent', path=path)
            path.chmod(0o644)
            with self.assertRaises(ValueError): model.configured_credential('fixture', path=path)
            with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'explicit-fixture'}):
                self.assertEqual(model.configured_credential(), 'explicit-fixture')

    def test_malformed_credential_shapes_raise_clean_value_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokens.toml'
            path.write_text('')
            path.chmod(0o600)
            for configuration in (None, [], {'tokens': 'bad'}, {'tokens': {}},
                                  {'tokens': [False]}, {'tokens': [{'name': 'fixture', 'expires_at': 'bad'}]}):
                with self.subTest(configuration=configuration), patch.object(model.tomllib, 'loads', return_value=configuration):
                    with self.assertRaises(ValueError): model.configured_credential('fixture', path=path)

    def test_confirmed_http_refusal_and_uncertain_attempt_never_replay(self):
        for failure, status in ((model.ProviderHTTPError(429, error_type='rate_limit_error'), 'rejected'), (TimeoutError(), 'uncertain')):
            with tempfile.TemporaryDirectory() as directory:
                calls = []
                def provider(body):
                    calls.append(body)
                    raise failure
                service = model.Service(directory, provider)
                job = {'body': {'synthetic': True}}
                receipt = service.request(job)
                self.assertEqual(receipt['status'], status)
                self.assertEqual(service.request(job), receipt)
                self.assertEqual(len(calls), 1)
                if status == 'rejected':
                    self.assertEqual(receipt['httpStatus'], 429)
                    self.assertEqual(receipt['errorType'], 'rate_limit_error')
                self.assertEqual(json.loads(next(Path(directory).glob('*.json')).read_text()), receipt)

    def test_oversized_encoded_frame_is_unsupported_without_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(model.urllib.request, 'build_opener') as opener:
            provider = model.AnthropicMessages('synthetic-key')
            service = model.Service(directory, provider)
            body = {'model': 'claude-haiku-5-5', 'max_tokens': 512, 'stream': False,
                    'system': chr(0) * 12000, 'messages': [{'role': 'user', 'content': 'synthetic'}]}
            receipt = service.request({'body': body})
            self.assertEqual(receipt['status'], 'unsupported')
            self.assertEqual(service.request({'body': body}), receipt)
            opener.assert_not_called()

if __name__ == '__main__': unittest.main()
