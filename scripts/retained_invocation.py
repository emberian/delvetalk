"""Durable custody for one exact native invocation; no world policy or refresh."""
import fcntl
import os
from pathlib import Path
import tempfile

import world


def submit(database, attempt, *, identity, input_factory=None, source=None):
    database, attempt = Path(database).resolve(), Path(attempt).resolve()
    protected = {database, Path(str(database) + '.lock')}
    if protected & {attempt, Path(str(attempt) + '.lock')}:
        raise ValueError('invocation attempt must be separate from world custody')
    attempt.parent.mkdir(parents=True, exist_ok=True)
    with open(str(attempt) + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if attempt.exists():
            retained = world.wire_loads(attempt.read_text())
            request = retained['request']
            selected = {key: value for key, value in request.items()
                        if key != 'expected' and (key != 'input' or 'input' in identity)}
            if (retained.get('profile') != 'compiled' or retained.get('database') != str(database)
                    or retained.get('source') != source or selected != identity):
                raise ValueError('invocation attempt is bound to different custody or explicit inputs')
        else:
            root = world.exchange(database, {'op': 'inspect', 'object': identity['object'],
                'principal': identity['principal']}, profile='compiled')
            request = {**identity, 'expected': root}
            if 'input' not in request:
                request['input'] = input_factory()
            retained = {'profile': 'compiled', 'database': str(database), 'request': request}
            if source is not None:
                retained['source'] = source
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=attempt.parent,
                        prefix=attempt.name + '.', delete=False) as handle:
                    temporary = handle.name
                    handle.write(world.wire_dumps(retained) + '\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, attempt)
                temporary = None
            finally:
                if temporary is not None:
                    os.unlink(temporary)
        # Reestablish durability even after a crash between rename and directory
        # sync. Only then may the native receiver see this exact request.
        descriptor = os.open(attempt, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        descriptor = os.open(attempt.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return world.exchange(database, request, profile='compiled')
