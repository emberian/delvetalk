"""Small explicit fixture notation; this parser never evaluates a protocol."""
import re

MAGIC = 'examples DelveTalk 1'
TOKEN = re.compile(r'[^\s:]+\Z')
MAX_BYTES = 1024 * 1024


def parse(source):
    if not isinstance(source, str) or len(source.encode('utf-8')) > MAX_BYTES:
        raise ValueError('examples exceed 1 MiB')
    lines = source.split('\n')
    if not lines or lines[0] != MAGIC:
        raise ValueError('expected ' + MAGIC)
    cases, case, step, principal, root = [], None, None, None, 'current'
    offer = None
    call_input = None
    offset = 1

    def token(value):
        if not TOKEN.fullmatch(value):
            raise ValueError('expected one nonempty token')
        return value

    def value(text, kind):
        nonlocal offset
        if text.startswith('<<'):
            if kind != 'String':
                raise ValueError('multiline values must be strings')
            marker = text[2:]
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', marker):
                raise ValueError('invalid multiline delimiter')
            content = []
            while offset < len(lines) and lines[offset] != marker:
                content.append(lines[offset])
                offset += 1
            if offset == len(lines):
                raise ValueError('unclosed multiline value')
            offset += 1
            return '\n'.join(content)
        if kind == 'String':
            return text
        if kind == 'Nat' and re.fullmatch(r'0|[1-9][0-9]*', text) and len(text) <= 4096:
            return int(text)
        if kind == 'Bool' and text in ('true', 'false'):
            return text == 'true'
        raise ValueError('invalid ' + kind + ' literal')

    def literal(text):
        match = re.fullmatch(r'([^\s:]+)(?: \((String|Nat|Bool)\))?:(?: (.*))?', text)
        if not match:
            raise ValueError('expected NAME [(String|Nat|Bool)]: VALUE')
        return match[1], value(match[3] if match[3] is not None else '', match[2] or 'String')

    def finish_case():
        if step is not None or principal is not None:
            raise ValueError('unfinished example step')
        if case is not None and ('law' not in case or not case['steps']):
            raise ValueError('case requires law and at least one step')

    while offset < len(lines):
        line = lines[offset]
        offset += 1
        if not line:
            continue
        if line.startswith('case '):
            finish_case()
            name = line[5:]
            if not name or any(item['name'] == name for item in cases):
                raise ValueError('empty or duplicate case name')
            if len(cases) >= 64:
                raise ValueError('too many cases')
            case = {'name': name, 'steps': []}
            cases.append(case)
            root = 'current'
        elif case is None:
            raise ValueError('expected case')
        elif line.startswith('fixture '):
            if step is not None or principal is not None or case['steps']:
                raise ValueError('fixtures belong before steps')
            name = token(line[8:])
            fixtures = case.setdefault('fixtures', [])
            if name == 'candidate' or '/' in name or name in fixtures or len(fixtures) >= 7:
                raise ValueError('fixtures require unique names and at most seven peers')
            fixtures.append(name)
        elif line == 'law' or line.startswith('law '):
            if 'law' in case or step is not None or principal is not None or case['steps']:
                raise ValueError('law must appear once before steps')
            case['law'] = [token(item) for item in line[4:].split(' ')] if line != 'law' else []
            if len(set(case['law'])) != len(case['law']):
                raise ValueError('duplicate law identity')
        elif line.startswith('as '):
            if 'law' not in case or step is not None or principal is not None:
                raise ValueError('as requires a completed previous step and a law')
            principal = token(line[3:])
            root = 'current'
        elif line.startswith('observe '):
            if 'law' not in case or step is not None or principal is not None:
                raise ValueError('observe requires a law and a completed previous step')
            step = {'observe': token(line[8:]), 'view': {'actions': {}}}
            offer = None
        elif line.startswith('at '):
            if principal is None or step is not None or line[3:] not in ('initial', 'current'):
                raise ValueError('at initial|current belongs between as and send')
            root = line[3:]
        elif line.startswith('send '):
            if principal is None or step is not None:
                raise ValueError('send requires as')
            command = token(line[5:])
            target, command = command.split('/', 1) if '/' in command else ('candidate', command)
            if target != 'candidate' and target not in case.get('fixtures', []):
                raise ValueError('send target requires a declared fixture')
            step = {'principal': principal, 'command': token(command), 'input': {}, 'root': root}
            if target != 'candidate':
                step['object'] = target
        elif line == 'transaction':
            if principal is None or step is not None:
                raise ValueError('transaction requires as')
            step = {'principal': principal, 'calls': [], 'root': root}
            call_input = None
        elif line.startswith('call '):
            if step is None or 'calls' not in step or len(step['calls']) >= 16:
                raise ValueError('call requires a transaction with at most sixteen calls')
            parts = token(line[5:]).split('/', 1)
            if len(parts) != 2 or not parts[1] or parts[0] not in ['candidate'] + case.get('fixtures', []):
                raise ValueError('call requires a declared OBJECT/COMMAND')
            call_input = {}
            step['calls'].append({'object': parts[0], 'command': parts[1], 'input': call_input})
        elif line == 'from previous':
            if step is None or 'calls' not in step or len(step['calls']) < 2 or call_input is None or call_input:
                raise ValueError('from previous requires an empty call after an earlier call')
            call = step['calls'][-1]
            del call['input']
            call['inputFrom'] = len(step['calls']) - 2
            call_input = None
        elif line.startswith('  '):
            if step is None:
                raise ValueError('input fields belong after send')
            if 'observe' in step:
                if line.startswith('    '):
                    if offer is None:
                        raise ValueError('view action input requires offer')
                    name, item = literal(line[4:])
                    if name in offer['input']:
                        raise ValueError('duplicate action input field')
                    offer['input'][name] = item
                elif line.startswith('  offer '):
                    match = re.fullmatch(r'  offer ([^\s:]+) -> ([^\s:]+):(?: (.*))?', line)
                    if not match or match[1] in step['view']['actions']:
                        raise ValueError('expected unique offer NAME -> COMMAND: TEXT')
                    offer = {'text': value(match[3] or '', 'String'), 'command': match[2], 'input': {}}
                    step['view']['actions'][match[1]] = offer
                else:
                    name, item = literal(line[2:])
                    if name not in ('title', 'prose') or name in step['view'] or not isinstance(item, str):
                        raise ValueError('view requires one String title and prose')
                    step['view'][name] = item
                    offer = None
                continue
            name, item = literal(line[2:])
            fields = call_input if 'calls' in step else step['input']
            if fields is None:
                raise ValueError('transaction fields require a preceding call')
            if name in fields:
                raise ValueError('duplicate input field')
            fields[name] = item
        elif line.startswith('expect '):
            if step is None:
                raise ValueError('expect requires send')
            if 'observe' in step:
                if line != 'expect view' or set(step['view']) != {'title', 'prose', 'actions'}:
                    raise ValueError('observe requires title, prose and expect view')
            elif 'calls' in step and not step['calls']:
                raise ValueError('transaction requires at least one call')
            elif line == 'expect committed':
                step['kind'] = 'committed'
            else:
                name, item = literal(line[7:])
                if name == 'result':
                    step.update(kind='committed', result=item)
                elif name == 'refusal' and isinstance(item, str):
                    step.update(kind='refused', error=item)
                else:
                    raise ValueError('expect result, refusal or committed')
            case['steps'].append(step)
            if sum(len(item['steps']) for item in cases) > 256:
                raise ValueError('too many steps')
            step, principal = None, None
        else:
            raise ValueError('unknown examples clause')
    finish_case()
    if not cases:
        raise ValueError('at least one case required')
    return cases


def load(source, json_loader):
    """The explicit first-line version opts in; legacy JSON stays unchanged."""
    if source.split('\n', 1)[0] == MAGIC:
        return parse(source)
    return json_loader(source)
