#!/usr/bin/env python3
"""Compile pinned Spween syntax to ordinary, typed Objective Bend source modules.

No scene or handler execution takes place in this Python compiler. The native
source frontend checks the module package and the receiving host admits turns.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scene.lower import Compiler, LoweringError, UPSTREAM, BIAS, bridge, tagged_values
from syntaxes.obend_object import lower_data_modules

PROFILE = 'spween-obend-handlers-i64-v1'
LIBRARY = ROOT / 'protocols/spween-handlers'


def quote(text):
    return json.dumps(text, ensure_ascii=False)


def value(tagged):
    tagged_values(tagged)
    kind = tagged[0]
    if kind == 'null': return 'K.Value.null()'
    if kind == 'int': return 'K.Value.integer({value: ' + str(int(tagged[1]) + BIAS) + 'n})'
    if kind == 'bool': return 'K.Value.boolean({value: ' + str(tagged[1]).lower() + '})'
    return 'K.Value.string({value: ' + quote(tagged[1]) + '})'


def arguments(values):
    result = 'K.Values.nil()'
    for item in reversed(values):
        result = 'K.Values.cons({head: ' + value(item) + ', tail: ' + result + '})'
    return result


class SourceCompiler:
    def __init__(self, document):
        # Reuse only existing syntax/domain diagnostics, never its transition AST.
        checked = Compiler(document, {}, {})
        self.document = document
        self.passages = checked.passages
        self.names = checked.names
        if len(self.passages) > 32:
            raise LoweringError('source handler profile supports at most 32 passages')
        if sum(len(p['content']) for p in self.passages) > 256:
            raise LoweringError('source handler profile supports at most 256 content items')

    def condition(self, condition, state='state.handler'):
        if condition is None: return 'true'
        def expr(e):
            if e[0] == 'atom': return clause(e[1])
            return '(' + expr(e[1]) + (' && ' if e[0] == 'and' else ' || ') + expr(e[2]) + ')'
        def clause(c):
            if c['kind'] == 'has':
                return f'H.has({state}, {quote(c["category"])}, {quote(c["key"])})'
            if c['kind'] == 'not': return '(' + clause(c['clause']) + ') == false'
            left = f'H.get_var({state}, {quote(c["var"])})'
            right = c['value']
            if c['op'] in ('eq', 'ne'):
                answer = f'K.equal({left}, {value(right)})'
                return answer if c['op'] == 'eq' else '(' + answer + ') == false'
            if right[0] == 'string':
                raise LoweringError('source handler profile does not execute string ordering')
            if right[0] != 'int': return 'false'
            return f'K.order({left}, {int(right[1]) + BIAS}n, {quote(c["op"])})'
        return expr(condition['expr'])

    def effects(self, effects):
        lines = []
        previous = 'step'
        for i, effect in enumerate(effects):
            current = 's' + str(i)
            kind = effect['kind']
            if kind == 'call':
                body = f'H.call({previous}, {quote(effect["name"])}, {arguments(effect["args"])}, context)'
            elif kind == 'set':
                body = f'updated({previous}, H.set_var({previous}.state, {quote(effect["var"])}, {value(effect["value"])}))'
            else:
                delta = int(effect['delta'])
                modified = f'K.modify(H.get_var({previous}.state, {quote(effect["var"])}), {str(delta >= 0).lower()}, {abs(delta)}n)'
                body = f'let change: K.Modified = {modified} in if change.valid then updated({previous}, H.set_var({previous}.state, {quote(effect["var"])}, change.value)) else rejected({previous}, "signed i64 overflow")'
            lines.append(f'let {current}: H.Step = if {previous}.accepted then {body} else {previous} in')
            previous = current
        return ' '.join(lines + [previous])

    def emit(self):
        requirements = self.condition(self.document['ast']['meta'].get('requires'))
        text = '''edition ObjectiveBend 1
import ./Kernel.obend as K
import ./Handler.obend as H
record State:
  handler: H.State
  passage: Nat
  visited: K.Visits
  started: Bool
  ended: Bool
record Result:
  passage: Nat
  ended: Bool
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: Result
  emissions: H.Slots
record Choice:
  choice: Nat
def updated(step: H.Step, state: H.State) -> H.Step:
  {accepted: step.accepted, reason: step.reason, state: state, emissions: step.emissions}
def rejected(step: H.Step, reason: String) -> H.Step:
  {accepted: false, reason: reason, state: step.state, emissions: step.emissions}
def finish(state: State, step: H.Step) -> Decision:
  {accepted: step.accepted, reason: step.reason, state: extend(state, {handler: step.state}), result: {passage: state.passage, ended: state.ended}, emissions: step.emissions}
def refuse(state: State, reason: String) -> Decision:
  finish(state, rejected(H.begin(state.handler), reason))
'''
        actions = []
        choices = []
        for index, passage in enumerate(self.passages):
            entry = [x['effect'] for x in passage['content'] if x['kind'] == 'effect']
            text += f'def enter{index}(state: State, step: H.Step, context: K.Context) -> Decision:\n  let done: H.Step = if K.visited(state.visited, {index}n) then step else {self.effects(entry)} in finish(extend(state, {{passage: {index}n, started: true, ended: false, visited: K.visit(state.visited, {index}n)}}), done)\n'
            local_index = 0
            for item in passage['content']:
                if item['kind'] != 'choice': continue
                condition = self.condition(item.get('condition'))
                guard = f'state.started && state.ended == false && state.passage == {index}n && ({condition})'
                action_index = len(actions)
                actions.append((f'c{action_index}', guard, item['text'], local_index))
                target = item.get('target')
                ending = not target or target['is_end']
                destination = 'finish(extend(state, {ended: true}), done)' if ending else f'enter{self.names[target["target"]]}(state, done, context)'
                body = f'let step: H.Step = H.begin(state.handler) in let done: H.Step = {self.effects(item["effects"])} in {destination}'
                choices.append(f'if input.choice == {local_index}n && ({guard}) then {body} else ')
                local_index += 1
        start = 'enter0(state, H.begin(state.handler), context)' if self.passages else 'finish(extend(state, {started: true, ended: true}), H.begin(state.handler))'
        text += f'def start(state: State, input: {{}}, context: K.Context) -> Decision:\n  if state.started then refuse(state, "scene already started") else {start}\n'
        text += 'def choose(state: State, input: Choice, context: K.Context) -> Decision:\n  ' + ''.join(choices) + 'refuse(state, "choice unavailable")\n'
        title = self.document['ast']['meta'].get('title') or 'Spween scene'
        text += '''record NatField:
  type: String
  minimum: Nat
  maximum: Nat
record Description:
  name: String
  initial: State
  methods: {start: {label: String, fields: {}}, choose: {label: String, fields: {choice: NatField}}}
  panels: {}
'''
        text += f'def describe() -> Description:\n  {{name: {quote(title)}, initial: {{handler: H.initial(), passage: 0n, visited: K.Visits.nil(), started: false, ended: false}}, methods: {{start: {{label: "Start", fields: {{}}}}, choose: {{label: "Choose", fields: {{choice: {{type: "nat", minimum: 0n, maximum: 255n}}}}}}}}, panels: {{}}}}\n'
        text += '''record StartAction:
  visible: Bool
  text: String
  command: String
  input: {}
record ChoiceAction:
  visible: Bool
  text: String
  command: String
  input: Choice
'''
        action_type = ', '.join(['start: StartAction'] + [key + ': ChoiceAction' for key, _, _, _ in actions])
        text += f'record View:\n  title: String\n  prose: String\n  actions: {{{action_type}}}\n  children: K.Children\n'
        prose = '""'
        for index, passage in reversed(list(enumerate(self.passages))):
            content = '\n\n'.join(x['text'] for x in passage['content'] if x['kind'] == 'prose')
            prose = f'if state.passage == {index}n then {quote(content)} else {prose}'
        text += f'def requirements(state: State) -> Bool:\n  {requirements}\n'
        descriptions = ['start: {visible: state.started == false, text: "Start", command: "start", input: {}}']
        descriptions += [f'{key}: {{visible: {guard}, text: {quote(label)}, command: "choose", input: {{choice: {index}n}}}}' for key, guard, label, index in actions]
        text += f'def view(state: State, panel: String) -> View:\n  {{title: {quote(title)}, prose: if state.started == false then "Start this shared scene." else if state.ended then "The scene has ended." else {prose}, actions: {{{", ".join(descriptions)}}}, children: K.Children.nil()}}\n'
        return text


def compile_document(document, handler_source=None, *, handler_modules=None):
    """Return retained source/AST plus the genuinely native-checked typed protocol.

    The explicitly supplied handler bytes are the entire binding. No imports are
    resolved from a filesystem, network, shared registry, or ambient object name.
    """
    if handler_modules is not None:
        if handler_source is not None:
            raise LoweringError('supply handler_source or handler_modules, not both')
        if (not isinstance(handler_modules, list) or not handler_modules
                or any(not isinstance(m, dict) or set(m) != {'name', 'source'}
                       or not isinstance(m['name'], str) or not isinstance(m['source'], str)
                       for m in handler_modules)
                or handler_modules[-1]['name'] != 'Handler'
                or any(m['name'] in ('Kernel', 'Scene') for m in handler_modules)
                or len({m['name'] for m in handler_modules}) != len(handler_modules)):
            raise LoweringError('ordered distinct handler modules must end in Handler; Kernel/Scene are reserved')
    else:
        if handler_source is None:
            handler_source = (LIBRARY / 'Handler.obend').read_text()
        handler_modules = [{'name': 'Handler', 'source': handler_source}]
    modules = ([{'name': 'Kernel', 'source': (LIBRARY / 'Kernel.obend').read_text()}]
               + handler_modules + [{'name': 'Scene', 'source': SourceCompiler(document).emit()}])
    protocol = lower_data_modules(modules)
    protocol['spweenSource'] = {'profile': PROFILE, 'upstream': UPSTREAM,
                              'source': document['source'], 'ast': document['ast']}
    return {'profile': PROFILE, 'upstream': UPSTREAM, 'source': document['source'],
            'ast': document['ast'], 'protocol': protocol,
            'compilerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def compile_source(source, handler_source=None, *, handler_modules=None):
    return compile_document(bridge({'op': 'parse', 'source': source}), handler_source, handler_modules=handler_modules)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('--handler', type=Path, help='explicit Handler.obend module bytes')
    args = parser.parse_args()
    result = compile_source(args.scene.read_text(), args.handler.read_text() if args.handler else None)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__': main()
