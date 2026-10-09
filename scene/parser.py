"""Physical transport for the pinned Rust Spween parser and reference oracle."""
from pathlib import Path
import json
import hashlib
import sys

UPSTREAM = "95980f7d1e109138496849a444f28c4b9076a4e2"
BIAS = 1 << 63
ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scene/spween-bridge/target/debug/delvetalk-spween"
sys.path.insert(0, str(ROOT / 'scripts'))
import process_custody

class LoweringError(ValueError):
    pass

def tagged_values(x):
    """Only AST value positions call this; arbitrary prose is never interpreted."""
    if not isinstance(x, list) or not x:
        raise LoweringError("expected tagged Spween value")
    kind = x[0]
    if kind == "null" and len(x) == 1:
        return x
    if len(x) != 2:
        raise LoweringError("invalid tagged Spween value")
    value = x[1]
    if kind == "bool" and type(value) is bool:
        return x
    if kind == "string" and isinstance(value, str):
        return x
    if kind == "int" and isinstance(value, str):
        try:
            integer = int(value)
        except ValueError:
            raise LoweringError("invalid signed decimal integer") from None
        if str(integer) != value or not -BIAS <= integer < BIAS:
            raise LoweringError("integer must be canonical signed i64")
        return x
    if kind == "float":
        raise LoweringError("source scene data does not execute Float values; full AST is retained by parsing")
    raise LoweringError("invalid or unsupported tagged Spween value")


def bridge(request):
    if not BRIDGE.is_file():
        raise LoweringError("build the pinned Rust Spween bridge before parsing")
    pin = hashlib.sha256(BRIDGE.read_bytes()).hexdigest()
    result = process_custody.run_native([str(BRIDGE)],
        input=(json.dumps(request) + "\n").encode("utf-8"), timeout=30, cpu_seconds=30,
        stdout_limit=8 * 1024 * 1024, stderr_limit=1024 * 1024)
    result.check_returncode()
    document = json.loads(result.stdout)
    if hashlib.sha256(BRIDGE.read_bytes()).hexdigest() != pin:
        raise LoweringError("Spween bridge changed during the request")
    return document


def source_shape(document):
    if not isinstance(document, dict) or document.get('ok') is not True or document.get('upstream') != UPSTREAM:
        raise LoweringError('expected pinned parsed Spween document')
    if not isinstance(document.get('source'), str) or not isinstance(document.get('ast'), dict):
        raise LoweringError('parsed document requires original source and complete scene AST')
    if not isinstance(document['ast'].get('meta'), dict) or not isinstance(document['ast'].get('passages'), list):
        raise LoweringError('Spween AST requires metadata and passages')
    return document


def parse(source):
    pin = hashlib.sha256(BRIDGE.read_bytes()).hexdigest()
    document = source_shape(bridge({'op': 'parse', 'source': source}))
    if document['source'] != source:
        raise LoweringError('Spween bridge did not preserve exact source')
    if hashlib.sha256(BRIDGE.read_bytes()).hexdigest() != pin:
        raise LoweringError('Spween bridge changed during parsing')
    document['bridge_binary_sha256'] = pin
    return document
