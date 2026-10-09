"""Exact object-local source table framing; native code resolves executable packages.

No imports, paths, fetching, evaluation or authority decisions belong here.
"""
import copy

TABLE = 'delvetalk-source-package-table-v1'
REF = 'delvetalk-source-package-ref-v1'
NAME = 'resident'


def table(modules):
    if not isinstance(modules, list) or not 1 <= len(modules) <= 64:
        raise ValueError('source table requires 1..64 ordered modules')
    total = 0
    for module in modules:
        if (not isinstance(module, dict) or set(module) != {'name', 'source'}
                or not isinstance(module['name'], str) or not 1 <= len(module['name']) <= 128
                or not isinstance(module['source'], str)):
            raise ValueError('source table requires exact name/source module records')
        size = len(module['source'].encode('utf-8'))
        if size > 512 * 1024:
            raise ValueError('source table module exceeds 512 KiB')
        total += size
    if total > 1024 * 1024:
        raise ValueError('source table exceeds 1 MiB aggregate source')
    return {'format': TABLE, 'modules': copy.deepcopy(modules)}


def selector(entry, *, name=NAME):
    if (not isinstance(name, str) or not 1 <= len(name.encode('utf-8')) <= 128
            or not isinstance(entry, str) or not entry):
        raise ValueError('source package selector requires explicit name and entry')
    return {'format': REF, 'name': name, 'entry': entry}


def validate_selector(value):
    if (not isinstance(value, dict) or set(value) != {'format', 'name', 'entry'}
            or value != selector(value.get('entry'), name=value.get('name'))):
        raise ValueError('invalid object-local source package selector')
    return value


def validate_tables(protocol):
    tables = protocol.get('sourcePackages', {})
    if not isinstance(tables, dict) or len(tables) > 64:
        raise ValueError('sourcePackages requires bounded object-local tables')
    for name, value in tables.items():
        selector('entry', name=name)
        if not isinstance(value, dict) or set(value) != {'format', 'modules'} or value != table(value.get('modules')):
            raise ValueError('invalid exact source package table')
    return tables
