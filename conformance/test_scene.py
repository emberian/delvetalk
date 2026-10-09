#!/usr/bin/env python3
"""Ordinary source scene receiving behavior against the pinned Rust oracle."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
parser = load('scene_parser', 'scene/parser.py')
room = load('scene_room', 'scene/room.py')
world = load('scene_world', 'scripts/world.py')
source_object = load('scene_source_object', 'scripts/source_object.py')
def scene(body):
    return '---\nid: test\ntitle: Test\nweight: 1\ncooldown: 0\n---\n\n' + body

class SceneHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.serial = 0
    def install(self, source):
        artifact = room.compile_artifact(source)
        response = world.exchange(self.db, {'op': 'create', 'object': 'scene', 'principal': 'owner',
            'intent': 'create', 'protocol': artifact['protocol'], 'law': {
                'profile': 'delvetalk-scoped-law', 'read': 'public',
                'invoke': {'start': ['player'], 'choose': ['player']}, 'reprogram': [], 'law': []}}, profile='compiled')
        self.assertEqual(response['kind'], 'committed', response)
        self.root = response['data']['root']
        return artifact
    def invoke(self, command, choice=None, **changes):
        self.serial += 1
        request = {'op': 'invoke', 'object': 'scene', 'principal': 'player',
            'intent': str(self.serial), 'expected': self.root, 'command': command,
            'input': {} if choice is None else {'choice': choice}}
        request.update(changes)
        response = world.exchange(self.db, request, profile='compiled')
        if response['kind'] == 'committed': self.root = response['data']['root']
        return response, request
    def model(self): return source_object.plain(source_object.state_data(self.root))
    def variables(self):
        xs = self.model()['handler']['variables']; result = {}
        while xs['variant'] == 'cons':
            head = xs['payload']['head']; v = head['value']; k = v['variant']; p = v['payload']
            result[head['name']] = (['null'] if k == 'null' else ['int', str(p['value']-parser.BIAS)]
                if k == 'integer' else ['bool', p['value']] if k == 'boolean' else ['string', p['value']])
            xs = xs['payload']['tail']
        return result
    def compare(self, snapshot):
        model = self.model(); actual = self.variables()
        for name, value in snapshot['vars'].items(): self.assertEqual(actual[name], value)
        self.assertEqual(model['ended'], snapshot['state']['kind'] == 'ended')
        if not model['ended']: self.assertEqual(model['passage'], snapshot['state']['index'])
        view = room.inspect_object(self.root, 'scene')
        self.assertEqual([a['text'] for a in view['data']['actions'].values()],
            [c['text'] for c in snapshot['choices'] if c['available']])
    def replay(self, source, actions):
        oracle = parser.bridge({'op':'replay', 'source':source, 'state':{},
            'actions':[{'choose':i} for i in actions]})
        self.assertTrue(oracle['ok'], oracle)
        self.install(source)
        self.assertEqual(self.invoke('start')[0]['kind'], 'committed')
        self.compare(oracle['trace'][0]['snapshot'])
        for choice, step in zip(actions, oracle['trace'][1:]):
            response, _ = self.invoke('choose', choice)
            self.assertEqual(response['kind'] == 'committed', step['ok'], (response,step))
            self.compare(step['snapshot'])

class SceneTests(SceneHarness):
    def test_branching_reentry_signed_values_and_source_handler(self):
        self.replay((ROOT/'scene/examples/door.scene').read_text(), [0,0,0,0,0,1])
        self.assertEqual(self.variables()['tokens'], ['int','0'])
    def test_ordered_set_modify_and_guard(self):
        self.replay(scene('=== intro\n~ score = -2\n~ score += 3\nHello.\n* [Finish] { score == 1 }\n  ~ score -= 4\n  -> END\n'), [0])
        self.assertEqual(self.variables()['score'], ['int','-3'])
    def test_entry_effect_runs_once_on_reentry(self):
        self.replay(scene('=== a\n~ visits += 1\nA.\n* [Next]\n  -> b\n=== b\nB.\n* [Back]\n  -> a\n'),[0,0])
        self.assertEqual(self.variables()['visits'], ['int','1'])
    def test_unknown_handler_refuses_atomically(self):
        self.install(scene('=== a\n~ missing\nA.\n'))
        before = self.root
        response,_=self.invoke('start')
        self.assertEqual(response['kind'],'refused',response)
        self.assertEqual(self.root,before)
    def test_exact_retry_and_stale_root(self):
        self.install(scene('=== a\nA.\n* [Finish]\n  -> END\n'))
        original=self.root
        response,request=self.invoke('start')
        retry=world.exchange(self.db,request,profile='compiled')
        self.assertEqual(retry,response)
        stale,_=self.invoke('choose',0,expected=original)
        self.assertEqual(stale['kind'],'refused')
        self.assertIn('stale',str(stale))
    def test_mixed_scalar_guards_match_rust(self):
        self.replay(scene('=== a\n~ flag = true\n~ word = "rain"\n~ n = -1\nA.\n* [Stay] { flag == 1 && word == "rain" && n < 0 }\n  -> a\n* [Leave] { absent == null }\n  -> END\n'), [0, 1])

    def test_requirements_follow_source_handler_lifecycle(self):
        source = scene('=== a\n~ score = 1\nA.\n* [Spend]\n  ~ score -= 1\n  -> END\n').replace('cooldown: 0', 'cooldown: 0\nrequires:\n  min: {score: 1}')
        self.install(source)
        modules = self.root['protocol']['sourcePackages']['resident']['modules']
        def eligible():
            return source_object.plain(source_object.evaluate(modules, 'requirements', [source_object.state_data(self.root)]))
        self.assertFalse(eligible())
        self.assertEqual(self.invoke('start')[0]['kind'], 'committed')
        self.assertTrue(eligible())
        self.assertEqual(self.invoke('choose', 0)[0]['kind'], 'committed')
        self.assertFalse(eligible())

    def test_implicit_end_and_restart_refusal(self):
        self.install(scene('=== a\nA.\n* [Finish]\n'))
        self.assertEqual(self.invoke('start')[0]['kind'], 'committed')
        self.assertEqual(self.invoke('choose', 0)[0]['kind'], 'committed')
        self.assertTrue(self.model()['ended'])
        before = self.root
        self.assertEqual(self.invoke('start')[0]['kind'], 'refused')
        self.assertEqual(self.root, before)

    def test_selected_runtime_controls_constructor_initial_state(self):
        handlers = load('custom_scene_handlers', 'scene/handlers.py')
        runtime = '''edition ObjectiveBend 1
import ./SceneModel.obend as M
import ./SceneData.obend as D
import ./BaseRuntime.obend as Base
extension Custom(self: M.Behavior, super: M.Behavior) -> M.Behavior:
  extend(super, {describe: fn(scene: D.Scene) -> M.Description: extend(super.describe(scene), {initial: extend(super.describe(scene).initial, {started: true, ended: true})})})
def behavior() -> M.Behavior:
  fix(Custom, Base.behavior())
'''
        bundle = handlers.compile_source(scene('=== a\nA.\n'), runtime_source=runtime)
        protocol = bundle['protocol']
        model = source_object.plain(source_object.state_data({'protocol': protocol, 'state': protocol['initial']}))
        self.assertTrue(model['started'])
        self.assertTrue(model['ended'])

    def test_handler_cli_retains_exact_utf8_and_crlf(self):
        source = scene('=== a\nA moth’s room.\n').replace('\n', '\r\n').encode('utf-8')
        path = Path(self.tmp.name) / 'exact.scene'
        path.write_bytes(source)
        result = subprocess.run([sys.executable, str(ROOT / 'scene/handlers.py'), str(path)], capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)['source'].encode('utf-8'), source)

if __name__=='__main__': unittest.main()
