"""Receipt-first portal submission; callers own authorization, locks and results."""
from pathlib import Path
import subprocess
import tempfile

import worker
import world
from history import canonical

ROOT = Path(__file__).resolve().parents[1]


def execute(portal, saved, cached_reply, directory, check_pins):
    """Return (receipt, None) or (None, uncertainty type), retaining the exact request.

    Admission history precedes runtime checks. Pin/lookup failures propagate;
    only an attempted process submission can produce an uncertain outcome.
    """
    request = saved['request']
    reply = cached_reply or portal._retained(request)
    if reply is not None:
        return reply, None
    if len(canonical(request)) > world.MAX_EXPANDED_REQUEST_BYTES:
        raise ValueError('Expanded request exceeds the 1 MiB local host envelope')
    check_pins(saved)
    try:
        with tempfile.NamedTemporaryFile('wb', dir=directory) as stream:
            stream.write(canonical(request))
            stream.flush()
            return worker.command([str(ROOT / 'scripts/world.py'), '--profile', portal.profile,
                                   str(portal.database), stream.name], 20), None
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        return None, type(error).__name__
