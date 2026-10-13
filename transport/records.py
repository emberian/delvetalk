"""Digest plans and durable progress for records written through post.record_writer."""
import hashlib
import json

from transport.delve import canonical


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def plan(path, now, fingerprint=digest, delete=True, retain=()):
    """-> (writes, deletes, ledger): changed values and vanished keys in a digest ledger.
    `retain` holds unavailable records; `delete=False` keeps every vanished key indefinitely."""
    ledger = json.loads(path.read_text()) if path.exists() else {}
    held = {f'{c} {k}': v for (c, k), v in now.items()}
    writes = {key: value for key, value in held.items() if ledger.get(key) != fingerprint(value)}
    deletes = [key for key in ledger if key not in held and key not in retain] if delete else []
    return writes, deletes, ledger


def put_records(st, path, writes, deletes, ledger, writer, fingerprint=digest, limit=None, final=()):
    """Write a plan, saving its ledger after each successful record. Ordered `final` keys land only
    after all ordinary writes/deletes, outside `limit`. Failed writes are never remembered."""
    ordinary = {key: value for key, value in writes.items() if key not in final}
    following = [(key, writes[key]) for key in final if key in writes]
    done = []

    def put(key, value):
        collection, rkey = key.split(' ', 1)
        writer(collection, rkey, value)
        if value is None:
            ledger.pop(key, None)
        else:
            ledger[key] = fingerprint(value)
        st.write(path, ledger)
        done.append(key)

    batch = len(ordinary) + len(deletes) if limit is None else limit
    for key, value in list(ordinary.items())[:batch]:
        put(key, value)
    for key in deletes[:max(0, batch - len(done))]:
        put(key, None)
    left = len(ordinary) + len(deletes) - len(done)
    if left == 0:
        for key, value in following:
            put(key, value)
    return {'written': done, 'left': left + (len(following) if left > 0 else 0)}
