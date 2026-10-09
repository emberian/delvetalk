#!/usr/bin/env python3
"""Parse Spween and retain its typed data with ordinary Bend runtime/handler source.

Python serializes parser data and transports native checks. Scene execution,
configuration validation, guards, ordering, entry, navigation and menus are Bend
exports in scene/runtime/SceneRuntime.obend; there is no behavioral generator.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scene.lower import LoweringError, UPSTREAM, BIAS, bridge, tagged_values
from syntaxes import obend_object

PROFILE = 'spween-obend-handlers-i64-v1'
LIBRARY = ROOT / 'protocols/spween-handlers'
RUNTIME = ROOT / 'scene/runtime'
PRELUDE = ROOT / 'world/lib/prelude'
RESERVED = {'Abi', 'Encounter', 'Kernel', 'SceneData', 'SceneModel', 'BaseRuntime', 'SceneRuntime', 'Score', 'DefaultScene', 'Scene'}


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def record(**fields):
    return '{' + ', '.join(key + ': ' + value for key, value in fields.items()) + '}'


def constructor(type_name, tag, **fields):
    return type_name + '.' + tag + '(' + (record(**fields) if fields else '') + ')'


def sequence(type_name, values):
    result = constructor(type_name, 'nil')
    for item in reversed(values):
        result = constructor(type_name, 'cons', head=item, tail=result)
    return result


def value(tagged):
    """Representation mapping only: i64 is its unsigned biased payload."""
    tagged_values(tagged)
    kind = tagged[0]
    if kind == 'null': return constructor('K.Value', 'null')
    if kind == 'int': return constructor('K.Value', 'integer', value=str(int(tagged[1]) + BIAS) + 'n')
    if kind == 'bool': return constructor('K.Value', 'boolean', value=str(tagged[1]).lower())
    return constructor('K.Value', 'string', value=quote(tagged[1]))


def condition(data):
    if data is None: return constructor('D.Condition', 'always')
    def expression(expr):
        tag = expr[0]
        if tag == 'atom': return clause(expr[1])
        names = {'and': 'conjunction', 'or': 'disjunction'}
        return constructor('D.Condition', names[tag], left=expression(expr[1]), right=expression(expr[2]))
    def clause(item):
        kind = item['kind']
        if kind == 'not':
            return constructor('D.Condition', 'negation', condition=clause(item['clause']))
        if kind == 'has':
            return constructor('D.Condition', 'has', category=quote(item['category']), key=quote(item['key']))
        if kind == 'compare':
            return constructor('D.Condition', 'compare', name=quote(item['var']), op=quote(item['op']), value=value(item['value']))
        raise LoweringError('unknown parser condition variant')
    return expression(data['expr'])


def effect(data):
    kind = data['kind']
    if kind == 'set':
        return constructor('D.Effect', 'set', name=quote(data['var']), value=value(data['value']))
    if kind == 'modify':
        tagged_values(['int', data['delta']])
        integer = int(data['delta'])
        return constructor('D.Effect', 'modify', name=quote(data['var']), positive=str(integer >= 0).lower(), magnitude=str(abs(integer)) + 'n')
    if kind == 'call':
        return constructor('D.Effect', 'call', name=quote(data['name']), args=sequence('K.Values', [value(x) for x in data['args']]))
    raise LoweringError('unknown parser effect variant')


def score_source(document):
    """Serialize the parser's exact ordered content tree, without selecting steps."""
    if document.get('ok') is not True or document.get('upstream') != UPSTREAM:
        raise LoweringError('requires a successful pinned Spween parse: ' + str(document.get('error', 'invalid parser document')))
    passages = []
    for passage in document['ast']['passages']:
        content = []
        for item in passage['content']:
            kind = item['kind']
            if kind == 'prose':
                encoded = constructor('D.Content', 'prose', text=quote(item['text']))
            elif kind == 'effect':
                encoded = constructor('D.Content', 'effect', effect=effect(item['effect']))
            elif kind == 'choice':
                target = item['target']
                encoded_target = (constructor('D.Target', 'absent') if target is None else
                                  constructor('D.Target', 'named', name=quote(target['target']), isEnd=str(target['is_end']).lower()))
                choice = record(key=quote('choice-' + str(item['span'][0])), text=quote(item['text']),
                    condition=condition(item['condition']),
                    effects=sequence('D.Effects', [effect(x) for x in item['effects']]), target=encoded_target)
                encoded = constructor('D.Content', 'choice', choice=choice)
            else:
                raise LoweringError('unknown parser content variant')
            content.append(encoded)
        passages.append(record(name=quote(passage['name']), content=sequence('D.Contents', content)))
    scene = record(title=quote(document['ast']['meta'].get('title') or ''),
                   requires=condition(document['ast']['meta'].get('requires')),
                   passages=sequence('D.Passages', passages))
    return ('edition ObjectiveBend 1\nimport ./Kernel.obend as K\nimport ./SceneData.obend as D\n'
            'def scene() -> D.Scene:\n  ' + scene + '\n')


def modules_for(document, handler_source=None, *, handler_modules=None, runtime_source=None, runtime_modules=None, scene_source=None, scene_modules=None):
    if handler_modules is not None:
        if handler_source is not None:
            raise LoweringError('supply handler_source or handler_modules, not both')
        if (not isinstance(handler_modules, list) or not handler_modules
                or any(not isinstance(m, dict) or set(m) != {'name', 'source'}
                       or not isinstance(m['name'], str) or not isinstance(m['source'], str)
                       for m in handler_modules)
                or handler_modules[-1]['name'] != 'Handler'
                or any(m['name'] in RESERVED for m in handler_modules)
                or len({m['name'] for m in handler_modules}) != len(handler_modules)):
            raise LoweringError('ordered distinct handler modules must end in Handler; runtime/data module names are reserved')
    else:
        if handler_source is None:
            handler_source = (LIBRARY / 'Handler.obend').read_text()
        handler_modules = [{'name': 'Handler', 'source': handler_source}]
    if runtime_modules is not None:
        if runtime_source is not None:
            raise LoweringError('supply runtime_source or runtime_modules, not both')
        if (not isinstance(runtime_modules, list) or not runtime_modules
                or any(not isinstance(m, dict) or set(m) != {'name', 'source'}
                       or not isinstance(m['name'], str) or not isinstance(m['source'], str)
                       for m in runtime_modules)
                or runtime_modules[-1]['name'] != 'SceneRuntime'
                or any(m['name'] in RESERVED - {'SceneRuntime'} for m in runtime_modules)
                or len({m['name'] for m in runtime_modules}) != len(runtime_modules)
                or {m['name'] for m in runtime_modules} & {m['name'] for m in handler_modules}):
            raise LoweringError('ordered distinct runtime modules must end in SceneRuntime')
    else:
        runtime_modules = [{'name': 'SceneRuntime', 'source': (RUNTIME / 'DefaultRuntime.obend').read_text() if runtime_source is None else runtime_source}]
    if scene_modules is not None:
        if scene_source is not None:
            raise LoweringError('supply scene_source or scene_modules, not both')
        if (not isinstance(scene_modules, list) or not scene_modules
                or any(not isinstance(m, dict) or set(m) != {'name', 'source'}
                       or not isinstance(m['name'], str) or not isinstance(m['source'], str)
                       for m in scene_modules)
                or scene_modules[-1]['name'] != 'Scene'
                or any(m['name'] in RESERVED - {'Scene'} for m in scene_modules)
                or len({m['name'] for m in scene_modules}) != len(scene_modules)
                or {m['name'] for m in scene_modules} & {m['name'] for m in handler_modules + runtime_modules}):
            raise LoweringError('ordered distinct scene entry modules must end in Scene')
    elif scene_source is not None:
        scene_modules = [{'name': 'Scene', 'source': scene_source}]
    default_scene = (RUNTIME / 'Scene.obend').read_text()
    entry_modules = ([{'name': 'DefaultScene', 'source': default_scene}] + scene_modules
                     if scene_modules is not None else [{'name': 'Scene', 'source': default_scene}])
    return ([{'name': 'Abi', 'source': (PRELUDE / 'Abi.obend').read_text()},
             {'name': 'Encounter', 'source': (PRELUDE / 'Encounter.obend').read_text()},
             {'name': 'Kernel', 'source': (LIBRARY / 'Kernel.obend').read_text()},
             {'name': 'SceneData', 'source': (RUNTIME / 'SceneData.obend').read_text()}]
            + handler_modules
            + [{'name': 'SceneModel', 'source': (RUNTIME / 'SceneModel.obend').read_text()},
               {'name': 'BaseRuntime', 'source': (RUNTIME / 'SceneRuntime.obend').read_text()}]
            + runtime_modules
            + [{'name': 'Score', 'source': score_source(document)}] + entry_modules)


def check_data(modules):
    """Report the selected Bend runtime's configuration check; do not copy it."""
    deadline = time.monotonic() + 30
    artifact = obend_object._native({'op': 'compile', 'modules': modules, 'entry': 'validate',
                                    'limits': obend_object.LIMITS}, deadline)['artifact']
    result = obend_object._native({'op': 'run-data-v1', 'artifact': artifact,
                                  'arguments': [], 'limits': obend_object.LIMITS}, deadline)['value']
    validation = obend_object._data(result)
    if (not isinstance(validation, dict) or set(validation) != {'valid', 'reason'}
            or type(validation['valid']) is not bool or not isinstance(validation['reason'], str)):
        raise LoweringError('scene runtime validation must return valid Bool and reason String')
    if not validation['valid']:
        raise LoweringError(validation['reason'])


def compile_document(document, handler_source=None, *, handler_modules=None, runtime_source=None, runtime_modules=None, scene_source=None, scene_modules=None):
    """Seal selected source modules with typed scene data and native checked ABI."""
    modules = modules_for(document, handler_source, handler_modules=handler_modules, runtime_source=runtime_source, runtime_modules=runtime_modules,
                          scene_source=scene_source, scene_modules=scene_modules)
    check_data(modules)
    protocol = obend_object.lower_data_modules(modules)
    protocol['spweenSource'] = {'profile': PROFILE, 'upstream': UPSTREAM,
                              'source': document['source'], 'ast': document['ast']}
    return {'profile': PROFILE, 'upstream': UPSTREAM, 'source': document['source'],
            'ast': document['ast'], 'protocol': protocol,
            'compilerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def compile_source(source, handler_source=None, *, handler_modules=None, runtime_source=None, runtime_modules=None, scene_source=None, scene_modules=None):
    return compile_document(bridge({'op': 'parse', 'source': source}), handler_source,
                            handler_modules=handler_modules, runtime_source=runtime_source, runtime_modules=runtime_modules,
                          scene_source=scene_source, scene_modules=scene_modules)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('--handler', type=Path, help='explicit Handler.obend module bytes')
    parser.add_argument('--runtime', type=Path, help='explicit SceneRuntime.obend module bytes')
    parser.add_argument('--entry', type=Path, help='explicit final Scene.obend module bytes')
    args = parser.parse_args()
    result = compile_source(args.scene.read_text(), args.handler.read_text() if args.handler else None,
                            runtime_source=args.runtime.read_text() if args.runtime else None,
                            scene_source=args.entry.read_text() if args.entry else None)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__': main()
