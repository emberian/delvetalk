"""Repository signing keys in each fixture's temporary state."""
import os

from transport.atproto import sign


def write_repo_key(st):
    key = sign.Key.generate()
    st.repo_key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(st.repo_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, 'wb') as f:
        f.write(key.pem())
