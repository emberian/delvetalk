"""Signing keys, did:key, TIDs and commits (atproto.com/specs/cryptography, /repository "Commit Objects").

A key is k256 (secp256k1) or p256. Signatures are ECDSA over sha-256, deterministic
(RFC 6979, so a commit is a function of its content and the key), as 64 raw bytes r||s with s in the low half.
"""
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from transport.atproto.cbor import block, encode, varint

CURVES = {'secp256k1': (ec.SECP256K1, 0xe7, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141),
          'secp256r1': (ec.SECP256R1, 0x1200, 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551)}
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
S32 = '234567abcdefghijklmnopqrstuvwxyz'


def b58encode(raw):
    n, out = int.from_bytes(raw, 'big'), ''
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + out


def b58decode(text):
    n = 0
    for c in text:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return b'\0' * (len(text) - len(text.lstrip('1'))) + raw


def tid(micros, clock_id=0):
    """A TID: 64 bits, the top zero, then microseconds since the epoch (53 bits) and a 10-bit clock id."""
    n, out = (micros << 10) | clock_id, ''
    for _ in range(13):
        out = S32[n & 31] + out
        n >>= 5
    return out


def multikey(public):
    """`z...`: base58btc of the multicodec (secp256k1-pub or p256-pub) and the compressed point."""
    code = CURVES[public.curve.name][1]
    point = public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint)
    return 'z' + b58encode(varint(code) + point)


def public_key(did_key):
    """The public key a `did:key:z...` (or a bare `z...` multikey) names."""
    raw = b58decode(did_key.removeprefix('did:key:').removeprefix('z'))
    for name, (curve, code, _) in CURVES.items():
        if raw.startswith(varint(code)):
            return ec.EllipticCurvePublicKey.from_encoded_point(curve(), raw[len(varint(code)):])
    raise ValueError('not a k256 or p256 did:key')


def verify(public, message, sig):
    """True when `sig` is 64 bytes r||s, low-S, and signs sha-256(message) under `public`."""
    order = CURVES[public.curve.name][2]
    r, s = int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big')
    if len(sig) != 64 or not 0 < s <= order // 2:
        return False
    try:
        public.verify(encode_dss_signature(r, s), message, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


class Key:
    def __init__(self, private):
        if private.curve.name not in CURVES:
            raise ValueError('a repository key is k256 or p256')
        self.private = private
        self.did_key = 'did:key:' + multikey(private.public_key())

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            return cls(serialization.load_pem_private_key(f.read(), None))

    @classmethod
    def generate(cls, curve='secp256k1'):
        return cls(ec.generate_private_key(CURVES[curve][0]()))

    def pem(self):
        return self.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption())

    def sign(self, message):
        r, s = decode_dss_signature(self.private.sign(message, ec.ECDSA(hashes.SHA256(), deterministic_signing=True)))
        order = CURVES[self.private.curve.name][2]
        return r.to_bytes(32, 'big') + min(s, order - s).to_bytes(32, 'big')

    def commit(self, did, data, rev, prev):
        """-> (CID, bytes) of the signed commit {did, version: 3, data, rev, prev, sig}; sig over the unsigned one."""
        unsigned = {'did': did, 'version': 3, 'data': data, 'rev': rev, 'prev': prev}
        return block({**unsigned, 'sig': self.sign(encode(unsigned))})


def derive_key(town_key, did):
    """Derive a hosted k256 key from the town scalar and DID with HKDF-SHA256 and rejection sampling."""
    material = town_key.private.private_numbers().private_value.to_bytes(32, 'big')
    counter = 0
    while True:
        info = b'delvetalk hosted key v1\0' + did.encode() + b'\0' + counter.to_bytes(4, 'big')
        raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(material)
        scalar = int.from_bytes(raw, 'big')
        if 0 < scalar < CURVES['secp256k1'][2]:
            return Key(ec.derive_private_key(scalar, ec.SECP256K1()))
        counter += 1
