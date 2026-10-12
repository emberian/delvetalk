"""ATPROTO L5 finding 3: attacker-selected HTTPS destinations cannot reach internal networks.

Refuted by any private/translated address connecting; a second DNS lookup selecting loopback; a TLS identity or
Host header naming the pinned IP; a redirect being followed; or a response read beyond limit + 1. No network.
"""
import functools
import io
import ipaddress
import socket
import ssl
import unittest
from unittest import mock

from transport import delve

PUBLIC = '8.8.8.8'
PRIVATE = ('127.0.0.1', '10.0.0.5', '169.254.169.254', '::1', 'fe80::1', 'fd00::1', '100.64.0.1',
           '224.0.0.1', 'ff02::1', '240.0.0.1', '0.0.0.0', '::', '2001:db8::1',
           '::ffff:10.0.0.1', '::a00:1', '64:ff9b::a00:1', '2002:0a00:0001::1',
           '::ffff:100.64.0.1', '::6440:1', '64:ff9b::6440:1', '2002:6440:0001::1')
PRIVATE += tuple(str(ipaddress.IPv6Address(prefix + int(ipaddress.IPv4Address(ip))))
                 for ip in PRIVATE if ':' not in ip
                 for prefix in (int(ipaddress.IPv6Address('::ffff:0:0')), 0,
                                int(ipaddress.IPv6Address('64:ff9b::'))))
PRIVATE += tuple('2002:' + f'{int(ipaddress.IPv4Address(ip)) >> 16:04x}:{int(ipaddress.IPv4Address(ip)) & 0xffff:04x}::1'
                 for ip in PRIVATE if ':' not in ip)


def answers(*ips, port=443):
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '',
             (ip, port, 0, 0) if ':' in ip else (ip, port)) for ip in ips]


class ObservedIO(io.BytesIO):
    def __init__(self, raw, reads):
        super().__init__(raw)
        self.reads = reads

    def read(self, size=-1):
        raw = super().read(size)
        self.reads.append((size, len(raw)))
        return raw


class Wire:
    """A socket with real HTTP response parsing and recorded connect, timeout and outbound bytes."""
    def __init__(self, response):
        self.response, self.targets, self.timeouts, self.sent, self.closed = response, [], [], [], False
        self.reads = []

    def connect(self, target):
        self.targets.append(target)

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, raw):
        self.sent.append(raw)

    def makefile(self, mode):
        return ObservedIO(self.response, self.reads)

    def close(self):
        self.closed = True


class PublicTransport(unittest.TestCase):
    def setUp(self):
        self.wire = Wire(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
        self.factory = mock.Mock(return_value=self.wire)
        self.resolve = mock.Mock(return_value=answers(PUBLIC))
        self.context = ssl.create_default_context()
        self.wrap = mock.Mock(return_value=self.wire)
        self.patch_context = mock.patch('transport.delve.ssl.create_default_context', return_value=self.context)
        self.patch_wrap = mock.patch.object(self.context, 'wrap_socket', self.wrap)

    def send(self, url='https://login.example/doc', **kw):
        with self.patch_context, self.patch_wrap:
            return delve.public_transport('GET', url, {}, None, resolve=self.resolve, socket_factory=self.factory, **kw)

    def refused(self, url):
        with self.assertRaises(delve.Failure) as e:
            self.send(url)
        self.assertEqual((e.exception.code, e.exception.detail), ('not_public', urllib_host(url)))
        self.factory.assert_not_called()
        self.assertEqual(self.wire.targets, [])
        self.wrap.assert_not_called()

    def test_private_and_translated_addresses_from_dns_and_literal_urls_never_connect(self):
        for ip in PRIVATE:
            with self.subTest(ip=ip):
                self.resolve.return_value = answers(ip)
                self.refused('https://login.example/doc')
                host = '[' + ip + ']' if ':' in ip else ip
                self.refused('https://' + host + ':8443/doc')

    def test_a_253_character_hostname_connects_but_longer_or_malformed_names_do_not(self):
        host = '.'.join(('a' * 63, 'b' * 63, 'c' * 63, 'd' * 61))
        self.assertEqual(len(host), 253)
        self.assertEqual(self.send('https://' + host + '/doc')[0], 200)
        self.resolve.assert_called_once()
        self.resolve.reset_mock()
        self.factory.reset_mock()
        for bad in (host + 'x', 'a' * 64 + '.example', 'login.example..', '-login.example',
                    'login-.example', 'login_example', '[v1.example]'):
            with self.subTest(host=bad):
                with self.assertRaises(delve.Failure) as e:
                    self.send('https://' + bad + '/doc')
                self.assertEqual(e.exception.code, 'not_public')
        self.resolve.assert_not_called()
        self.factory.assert_not_called()

    def test_a_tls_context_failure_is_a_network_error_before_connecting(self):
        self.patch_context = mock.patch('transport.delve.ssl.create_default_context', side_effect=OSError('CA store'))
        with self.assertRaises(delve.Failure) as e:
            self.send()
        self.assertEqual((e.exception.code, e.exception.detail), ('network_error', 'OSError'))
        self.factory.assert_not_called()

    def test_one_public_and_one_private_answer_refuses_the_whole_destination(self):
        for ips in ((PUBLIC, '10.0.0.5'), ('10.0.0.5', PUBLIC), (PUBLIC, 'fd00::1')):
            with self.subTest(ips=ips):
                self.resolve.return_value = answers(*ips)
                self.refused('https://login.example/doc')

    def test_rebinding_cannot_change_the_pinned_ip_tls_name_or_host_header(self):
        self.resolve.side_effect = [answers(PUBLIC, port=8443), answers('127.0.0.1', port=8443)]
        self.assertEqual(self.send('https://login.example:8443/doc?q=1#fragment', timeout=7), (200, b'{}', {'Content-Length': '2'}))
        self.resolve.assert_called_once_with('login.example', 8443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        self.assertEqual(self.wire.targets, [(PUBLIC, 8443)])
        self.assertEqual(self.wire.timeouts, [7])
        self.wrap.assert_called_once_with(self.wire, server_hostname='login.example')
        self.assertTrue(self.context.check_hostname)
        self.assertEqual(self.context.verify_mode, ssl.CERT_REQUIRED)
        request = b''.join(self.wire.sent)
        self.assertIn(b'GET /doc?q=1 HTTP/1.1\r\n', request)
        self.assertIn(b'Host: login.example:8443\r\n', request)
        self.assertNotIn(PUBLIC.encode(), request)
        self.assertTrue(self.wire.closed)

    def test_a_global_ipv6_address_is_connected_directly_with_its_original_host(self):
        ip = '2606:4700:4700::1111'
        self.resolve.return_value = answers(ip)
        self.assertEqual(self.send()[0], 200)
        self.factory.assert_called_once_with(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.assertEqual(self.wire.targets, [(ip, 443, 0, 0)])

    def test_http_userinfo_invalid_ports_and_scoped_addresses_are_refused_before_dns(self):
        for url in ('http://login.example/doc', 'https://user:pass@login.example/doc', 'https://@login.example/doc',
                    'https://login.example:bad/doc', 'https://login.example:65536/doc', 'https://[fe80::1%25en0]/doc',
                    'https://login.example/\r\nInjected:yes'):
            with self.subTest(url=url), self.assertRaises(delve.Failure) as e:
                self.send(url)
            self.assertEqual(e.exception.code, 'not_public')
        self.resolve.assert_not_called()
        self.factory.assert_not_called()

    def test_a_302_is_returned_without_requesting_its_private_location(self):
        self.wire.response = b'HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1/secret\r\nContent-Length: 0\r\n\r\n'
        status, raw, headers = self.send()
        self.assertEqual((status, raw, headers['Location']), (302, b'', 'https://127.0.0.1/secret'))
        self.resolve.assert_called_once()
        self.assertEqual(len(self.wire.targets), 1)
        self.assertEqual(b''.join(self.wire.sent).count(b'GET '), 1)

    def test_content_length_and_chunked_bodies_preserve_the_limit_plus_one_signal(self):
        for body, size in ((b'abcd', 4), (b'abcde', 5), (b'abcdefghi', 5)):
            for chunked in (False, True):
                with self.subTest(body=body, chunked=chunked):
                    self.wire.response = (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' +
                                          f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n\r\n' if chunked else
                                          b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                    self.wire.reads = []
                    self.assertEqual(self.send(limit=4)[1], body[:size])
                    self.assertTrue(all(0 <= requested <= 5 for requested, _ in self.wire.reads), self.wire.reads)
                    if not chunked:
                        self.assertEqual(sum(got for _, got in self.wire.reads), size)

    def test_dns_connect_tls_and_http_failures_are_network_errors_with_reason_codes(self):
        self.wire.connect = mock.Mock(wraps=self.wire.connect)
        cases = ((self.resolve, socket.gaierror('no DNS')), (self.wire.connect, TimeoutError('timed out')),
                 (self.wrap, ssl.SSLCertVerificationError('wrong certificate')))
        for seam, error in cases:
            with self.subTest(error=type(error).__name__):
                seam.side_effect = error
                with self.assertRaises(delve.Failure) as e:
                    self.send()
                self.assertEqual((e.exception.code, e.exception.detail), ('network_error', type(error).__name__))
                seam.side_effect = None
        self.wire.response = b'not HTTP\r\n'
        with self.assertRaises(delve.Failure) as e:
            self.send()
        self.assertEqual((e.exception.code, e.exception.detail), ('network_error', 'BadStatusLine'))

    def test_an_empty_dns_answer_is_refused_without_connecting(self):
        self.resolve.return_value = []
        self.refused('https://login.example/doc')

    def test_a_did_web_rebinding_uses_one_pinned_fetch_and_refuses_the_next_loopback_answer(self):
        self.wire.response = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'
        self.resolve.side_effect = [answers(PUBLIC), answers('127.0.0.1')]
        transport = functools.partial(delve.public_transport, resolve=self.resolve, socket_factory=self.factory)
        with self.patch_context, self.patch_wrap:
            client = delve.Client(transport)
            self.assertEqual(client.did_document('did:web:login.example'), {})
            self.assertEqual(self.resolve.call_count, 1)
            self.assertEqual(self.wire.targets, [(PUBLIC, 443)])
            with self.assertRaises(delve.Failure) as e:
                client.did_document('did:web:login.example')
        self.assertEqual((e.exception.code, e.exception.detail), ('not_public', 'login.example'))
        self.assertEqual(self.resolve.call_count, 2)
        self.assertEqual(self.wire.targets, [(PUBLIC, 443)])

    def test_did_web_private_dns_and_literal_hosts_never_connect(self):
        for ip in ('127.0.0.1', '10.0.0.5', '169.254.169.254', '100.64.0.1'):
            self.resolve.return_value = answers(ip)
            transport = functools.partial(delve.public_transport, resolve=self.resolve, socket_factory=self.factory)
            for did in ('did:web:login.example', 'did:web:' + ip):
                with self.subTest(did=did, ip=ip), self.assertRaises(delve.Failure) as e:
                    delve.Client(transport).did_document(did)
                self.assertEqual(e.exception.code, 'not_public')
        self.factory.assert_not_called()

    def test_default_client_uses_public_transport_for_documents_and_http_for_xrpc(self):
        with mock.patch('transport.delve.public_transport', return_value=(200, b'{}', {})) as public, \
                mock.patch('transport.delve.http_transport', return_value=(200, b'{}', {})) as ordinary:
            client = delve.Client()
            for did in ('did:web:login.example', 'did:plc:' + 'a' * 24):
                self.assertEqual(client.did_document(did), {})
            self.assertEqual(public.call_count, 2)
            ordinary.assert_not_called()
            client.resolve_handle('someone.example')
            ordinary.assert_called_once()
            self.assertEqual(public.call_count, 2)


def urllib_host(url):
    import urllib.parse
    return urllib.parse.urlsplit(url).hostname


if __name__ == '__main__':
    unittest.main()
