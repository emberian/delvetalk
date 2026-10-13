"""Test-local RFC 6455 client; standard library sockets and independent WebSocket framing."""
import base64
import hashlib
import os
import socket

from transport.atproto.cbor import decode, encode

ROUTE = '/xrpc/com.atproto.sync.subscribeRepos'


class Consumer:
    """Test-local client: masked controls, buffered HTTP upgrade, unmasked binary server frames."""
    def __init__(self, address, query=''):
        self.socket = socket.create_connection(address, timeout=10)
        self.socket.settimeout(30)
        self.buffer = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f'GET {ROUTE}{query} HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
                             f'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n').encode())
        while b'\r\n\r\n' not in self.buffer:
            self.buffer.extend(self.socket.recv(65536))
        head, _, tail = self.buffer.partition(b'\r\n\r\n')
        self.buffer = bytearray(tail)
        assert head.startswith(b'HTTP/1.1 101 '), head
        accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        assert b'Sec-WebSocket-Accept: ' + accept in head, head

    def take(self, n):
        while len(self.buffer) < n:
            got = self.socket.recv(65536)
            if not got:
                raise EOFError('closed')
            self.buffer.extend(got)
        out = bytes(self.buffer[:n])
        del self.buffer[:n]
        return out

    def raw(self):
        first, length = self.take(2)
        assert first & 0x80 and not length & 0x80
        length &= 127
        if length >= 126:
            length = int.from_bytes(self.take(2 if length == 126 else 8), 'big')
        return first & 15, self.take(length)

    def event(self):
        op, payload = self.raw()
        assert op == 2, (op, payload)
        for header in ({'op': -1}, *({'op': 1, 't': t} for t in ('#commit', '#sync', '#identity', '#info'))):
            encoded = encode(header)
            if payload.startswith(encoded):
                return header, decode(payload[len(encoded):]), payload
        raise AssertionError('unknown event header')

    def control(self, opcode, payload=b'', masked=True):
        mask = b'abcd'
        wire = bytes([0x80 | opcode, len(payload) | (0x80 if masked else 0)])
        self.socket.sendall(wire + (mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)) if masked else payload))

    def close(self):
        self.socket.close()


