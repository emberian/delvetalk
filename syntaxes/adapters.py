"""Reviewed syntax adapters. Source text is data; no embedded code execution."""
from decimal import Decimal
import json
import re


def json_value(source):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON member: {key}")
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f"non-JSON constant: {value}")
    return json.loads(source, object_pairs_hook=pairs, parse_constant=constant, parse_float=Decimal)


def sexpr(source):
    """Parentheses -> arrays; quoted strings use JSON escapes; #t/#f -> bool."""
    tokens = []
    offset = 0
    pattern = re.compile(r'\s+|;[^\n]*|[()]|"(?:[^"\\]|\\.)*"|[^\s();"]+')
    while offset < len(source):
        token = pattern.match(source, offset)
        if token is None:
            raise ValueError(f"invalid token at character {offset}")
        offset = token.end()
        token = token.group()
        if not token.isspace() and not token.startswith(';'):
            tokens.append(token)
    offset = 0
    def read():
        nonlocal offset
        if offset == len(tokens):
            raise ValueError("unexpected end of S-expression")
        token = tokens[offset]
        offset += 1
        if token == '(':
            items = []
            while offset < len(tokens) and tokens[offset] != ')':
                items.append(read())
            if offset == len(tokens):
                raise ValueError("unclosed S-expression")
            offset += 1
            return items
        if token == ')':
            raise ValueError("unexpected closing parenthesis")
        if token.startswith('"'):
            return json_value(token)
        if token in ('#t', '#f'):
            return token == '#t'
        if re.fullmatch(r'0|[1-9][0-9]*', token):
            return int(token)
        return token
    result = read()
    if offset != len(tokens):
        raise ValueError("expected exactly one S-expression")
    return result


def protocol_markdown(source):
    """One explicit fenced payload; surrounding Markdown remains opaque."""
    blocks, current, marker, tagged = [], [], None, False
    for line in source.splitlines(keepends=True):
        if marker is None:
            match = re.fullmatch(r' {0,3}(`{3,}|~{3,})([^\r\n]*)\r?\n?', line)
            if match:
                marker = match[1]
                tagged = match[2].strip() == 'delvetalk-protocol'
                current = []
        elif re.fullmatch(r' {0,3}' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}[ \t]*\r?\n?', line):
            if tagged:
                blocks.append(''.join(current))
            marker = None
        else:
            current.append(line)
    if marker is not None:
        raise ValueError("unclosed Markdown fence")
    if len(blocks) != 1:
        raise ValueError("expected exactly one delvetalk-protocol fenced JSON block")
    return json_value(blocks[0])


def protocol_shape(value):
    """Structural preflight only. Lean owns protocol installation/admission."""
    if not isinstance(value, dict) or value.get('profile') != 'delvetalk-local-v1':
        raise ValueError("expected delvetalk-local-v1 protocol object")
    if not isinstance(value.get('initial'), dict) or not isinstance(value.get('commands'), dict):
        raise ValueError("protocol needs initial and commands objects")
    for command in value['commands'].values():
        if (isinstance(command, dict) and isinstance(command.get('transition'), dict)
                and command['transition'].get('profile') in (
                    'delvetalk-source-transition-v1', 'delvetalk-source-transition-v2',
                    'delvetalk-source-data-transition-v1',
                    'delvetalk-source-effects-v1', 'delvetalk-source-receive-v1',
                    'delvetalk-source-data-effects-v1', 'delvetalk-source-data-receive-v1')):
            fields = set(command['transition'])
            if (set(command) != {'transition'} or not {'profile', 'package'} <= fields
                    or not fields <= {'profile', 'package', 'inputCodec', 'resultCodec'}):
                raise ValueError('source transition requires an exclusive profile/package descriptor with optional codecs')
            continue  # Lean validates the package, source, typed call and decision.
        if not isinstance(command, dict) or not isinstance(command.get('require'), list) or not isinstance(command.get('set'), dict) or 'result' not in command or not isinstance(command.get('outbox'), list):
            raise ValueError("command needs require array, set object, result, outbox array")
    return value
