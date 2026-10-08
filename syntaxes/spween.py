"""Explicit Spween parser/lowering adapters; scene source never selects code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = '95980f7d1e109138496849a444f28c4b9076a4e2'
BRIDGE = ROOT / 'scene/spween-bridge/target/debug/delvetalk-spween'


def parse(source):
    if not BRIDGE.is_file():
        raise ValueError('build the pinned parser: cargo build --locked --manifest-path scene/spween-bridge/Cargo.toml')
    executable_hash = hashlib.sha256(BRIDGE.read_bytes()).hexdigest()
    try:
        result = subprocess.run([str(BRIDGE)], input=json.dumps({'op': 'parse', 'source': source}),
                                text=True, capture_output=True, timeout=15, check=True)
    except (subprocess.SubprocessError, OSError) as error:
        raise ValueError(f'Spween bridge failed: {error}') from error
    document = json.loads(result.stdout)
    if document.get('ok') is not True:
        raise ValueError(f"Spween {document.get('stage', 'parse')}: {document.get('error', 'refused')}")
    if document.get('source') != source:
        raise ValueError('Spween bridge did not preserve exact source')
    if document.get('upstream') != UPSTREAM:
        raise ValueError('Spween bridge reported an unexpected upstream revision')
    document['bridge_binary_sha256'] = executable_hash
    return source_shape(document)


def source_shape(document):
    if not isinstance(document, dict) or document.get('ok') is not True or document.get('upstream') != UPSTREAM:
        raise ValueError('expected pinned parsed Spween document')
    if not isinstance(document.get('source'), str) or not isinstance(document.get('ast'), dict):
        raise ValueError('parsed document requires original source and complete scene AST')
    if not isinstance(document['ast'].get('meta'), dict) or not isinstance(document['ast'].get('passages'), list):
        raise ValueError('Spween AST requires metadata and passages')
    return document


def lower(source):
    parsed = parse(source)
    spec = importlib.util.spec_from_file_location('delvetalk_spween_lowering', ROOT / 'scene/lower.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.lower_document(parsed)
    if result.get('source') != source or result.get('ast') != parsed['ast']:
        raise ValueError('Spween lowering must retain exact source and full parsed AST')
    result['bridge_binary_sha256'] = parsed['bridge_binary_sha256']
    return result


def protocol_shape(document):
    if not isinstance(document, dict) or document.get('profile') != 'spween-scene-i64-v1':
        raise ValueError('expected spween-scene-i64-v1 lowered bundle')
    if document.get('upstream') != UPSTREAM or not isinstance(document.get('source'), str) or not isinstance(document.get('ast'), dict):
        raise ValueError('lowered bundle must preserve pinned upstream, source and AST')
    if not isinstance(document.get('provenance'), dict):
        raise ValueError('lowered bundle requires profile provenance')
    spec = importlib.util.spec_from_file_location('delvetalk_syntax_adapters', ROOT / 'syntaxes/adapters.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.protocol_shape(document.get('protocol'))
    return document
