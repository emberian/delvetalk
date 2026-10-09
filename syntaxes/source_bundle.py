"""Bind explicit local source bytes into package descriptors; never parse or evaluate."""
from copy import deepcopy
import json
from pathlib import Path


def bind(protocol, modules):
    """Fill only exact package descriptors whose module list is empty."""
    def visit(value):
        if isinstance(value, dict):
            if set(value) == {'modules', 'entry'} and value['modules'] == []:
                return {'modules': deepcopy(modules), 'entry': value['entry']}
            return {key: visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value
    return visit(protocol)


def load(template, sources):
    """Sources are explicit ordered (module name, path) pairs, never import lookups."""
    modules = [{'name': name, 'source': Path(path).read_bytes().decode('utf-8')}
               for name, path in sources]
    return bind(json.loads(Path(template).read_bytes()), modules)
