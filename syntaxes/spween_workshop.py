"""Explicit scene + ordered Bend module fences; source text never selects Python."""
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SYNTAX = 'spween-handler-workshop@1'
HEADER = 'spween handler workshop 1'
MODULE_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')


def parse_source(source):
    """Keep fence payloads byte-exact under UTF-8, including CRLF and final LF."""
    if not isinstance(source, str):
        raise ValueError('workshop source must be text')
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].rstrip('\r\n') != HEADER:
        raise ValueError('expected ' + HEADER)
    scene, modules, names = None, [], set()
    kind, name, payload = None, None, []
    for line in lines[1:]:
        marker = line.rstrip('\r\n')
        if kind is not None:
            if marker == '```':
                text = ''.join(payload)
                if not text:
                    raise ValueError('empty source block')
                if kind == 'spween':
                    scene = text
                else:
                    modules.append({'name': name, 'source': text})
                kind, name, payload = None, None, []
            elif marker.startswith('```'):
                raise ValueError('nested or malformed source fence')
            else:
                payload.append(line)
            continue
        if marker == '```spween':
            if scene is not None:
                raise ValueError('exactly one Spween scene is required')
            kind = 'spween'
        elif marker.startswith('```obend '):
            name = marker[len('```obend '):]
            if not MODULE_NAME.fullmatch(name) or name in names or name in ('Kernel', 'Scene'):
                raise ValueError('module name must be distinct and cannot replace Kernel or Scene')
            names.add(name)
            kind = 'obend'
        elif marker.startswith('```'):
            raise ValueError('only spween and named obend source fences are supported')
        # All remaining surrounding prose is retained opaque authoring data.
    if kind is not None:
        raise ValueError('unclosed source fence')
    if scene is None or not modules or modules[-1]['name'] != 'Handler':
        raise ValueError('one scene and ordered modules ending in Handler are required')
    if len(modules) > 62:
        raise ValueError('at most 62 authored modules may accompany the generated kernel and scene')
    return {'scene': scene, 'modules': modules}


def lower(source):
    material = parse_source(source)
    spec = importlib.util.spec_from_file_location('spween_workshop_compiler', ROOT / 'scene/handlers.py')
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    bundle = compiler.compile_source(material['scene'], handler_modules=material['modules'])
    protocol = bundle['protocol']
    # Exact document custody belongs to the translation envelope; extracted text
    # stays with the program too, independently of the generated source modules.
    protocol['spweenWorkshop'] = {'syntax': SYNTAX, 'scene': material['scene'],
                                 'modules': material['modules']}
    return protocol
