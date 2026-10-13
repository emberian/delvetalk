"""Early paints: a carried/refreshed town through serve and the real model worker.

Refuted by: waiting behind 64 renders consumes an attempt; a valid mock reply
falls back after waiting; or a verifier refusal loses its clause in worker output.
The host tests require the current binary; WorkerVerdicts runs without Lean.
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from deploy import genesis
from tests.host import binary, served
from tests.town import Town
from tests.wire import record
from transport import carry, interpret, model
from transport.config import Config, LIBRARY
from transport.host import HostClient
from transport.state import State


def fixture(directory, request, text):
    Path(directory, model.request_hash(request) + '.json').write_text(json.dumps({
        'model': request['model'], 'content': [{'type': 'text', 'text': text}],
        'usage': {}, 'stop_reason': 'end_turn',
    }))


class WorkerVerdicts(unittest.TestCase):
    def test_command_preserves_the_clause_and_attempt_that_explain_an_exact_or_retrying_paint(self):
        """The v15 logs kept keys alone, so their retrying -> exact pairs cannot name the cause."""
        request = {'model': model.DEFAULT_MODEL, 'system': 'paint', 'user': 'Strokes: carried thing'}
        for verdict in (
            {'status': 'retrying', 'object': 'carried', 'key': 'k', 'clause': 'imagery',
             'detail': 'rain: imagery names state or source words', 'next': 10},
            {'status': 'exact', 'object': 'carried', 'version': 2, 'key': 'k',
             'reason': 'rejected', 'clause': 'imagery', 'detail': 'rain: imagery names state or source words'},
            {'status': 'retrying', 'object': 'carried', 'key': 'k', 'attempts': 1, 'next': 2000},
            {'status': 'exact', 'object': 'carried', 'version': 2, 'key': 'k',
             'reason': 'rejected', 'clause': 'model', 'detail': 'transport'},
        ):
            with self.subTest(verdict=verdict), tempfile.TemporaryDirectory() as d:
                fixture(d, request, 'Like rain.')
                st = State(Path(d, 'state'), config=Config(model_mock=d))
                host = Mock()
                host.send.side_effect = [
                    {'status': 'interpretations', 'pending': []},
                    {'status': 'renders', 'pending': [{'key': 'k', 'request': request}]}, verdict,
                ]
                out = io.StringIO()
                with patch.object(st, 'host', return_value=host):
                    interpret.command(st, types.SimpleNamespace(once=True), out)
                paints = json.loads(out.getvalue())['paints']
                self.assertEqual(paints[verdict['status']], ['k'])
                self.assertEqual(paints.get('verdicts'), [verdict], paints)
                host.close.assert_called_once()

    def test_diagnostics_keep_a_full_paint_detail_but_never_copy_request_or_reply_text(self):
        request = {'model': model.DEFAULT_MODEL, 'system': 'paint', 'user': 'private strokes'}
        # A full-length rejected paint can be the clause's detail. Host additions must not
        # turn the worker's diagnostic into a request/response transcript.
        detail = '"\n<rain>&' + 'x' * 390
        verdict = {'status': 'exact', 'key': 'k', 'clause': 'quotes', 'detail': detail,
                   'request': request, 'raw': 'private reply', 'text': 'private expansion'}
        host = Mock()
        host.send.side_effect = [
            {'status': 'renders', 'pending': [{'key': 'k', 'request': request}]}, verdict,
        ]
        done = interpret.paint(host, lambda req: model.failed('refused'))
        self.assertEqual(done['verdicts'], [{k: verdict[k] for k in ('status', 'key', 'clause', 'detail')}])


class CarriedPaints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        old = Town(os.path.join(cls.tmp.name, 'old'), cleanup=cls.addClassCleanup, furnished=False)
        # An old station body moves to the image's body; refresh restitches its old scene.
        scene = genesis.station_scene()
        body_of = genesis.body_of
        old_body = lambda name: body_of(name) + ('\n# before the carry\n' if name == 'station' else '')
        with patch.object(genesis, 'body_of', side_effect=old_body), \
                patch.object(genesis, 'station_scene', return_value=scene + '\n// before the carry\n'):
            made = genesis.gas_station(old.client, genesis.OPENER)
        assert all(m['status'] in ('created', 'admitted') for m in made), made
        source = 'edition ObjectiveBend 1\nrecord State:\n  head: String\ndef initial() -> State:\n  {head: "a carried thing"}\n'
        cls.objects = [f'paint-carry-{i:02}' for i in range(64)]
        for obj in cls.objects:
            made = old.send(op='world-create', principal=genesis.OPENER, identity='make-' + obj,
                            object=obj, source=source, entry='initial', seed=record())
            assert made['status'] == 'created', made
        assert old.send(op='world-snapshot')['status'] == 'snapshot'
        old.close()
        cls.carried = Path(cls.tmp.name, 'carried')
        cls.carried.mkdir()
        journal = cls.carried / 'town.journal'
        p = subprocess.run([binary(), 'carry', '--from', old.journal, '--out', str(journal),
                            '--reason', 'early paint regression', '--library', LIBRARY,
                            *carry.body_args(LIBRARY)], capture_output=True, text=True, timeout=600)
        assert p.returncode == 0, p.stderr
        report = json.loads(p.stdout)
        assert 'station' in {m['object'] for m in report['moved']}, report
        refreshed = genesis.carried(binary(), str(journal), True)
        assert all(r['status'] in ('current', 'refreshed', 'left') for r in refreshed), refreshed
        assert any(r.get('slot') == 'scene' and r['status'] == 'refreshed' for r in refreshed), refreshed

    def setUp(self):
        d = tempfile.TemporaryDirectory(dir=self.tmp.name)
        self.addCleanup(d.cleanup)
        state = Path(d.name, 'state')
        shutil.copytree(self.carried, state)
        env = patch.dict(os.environ, {'DELVETALK_RENDER_CACHE': str(Path(d.name, 'render-cache'))})
        env.start()
        self.addCleanup(env.stop)
        server = served(str(state), cleanup=self.addCleanup, opener=genesis.OPENER, library=LIBRARY)
        self.host = HostClient(server.root)
        self.addCleanup(self.host.close)
        self.mock_dir = Path(d.name, 'model')
        self.mock_dir.mkdir()
        self.st = State(state, config=Config(model_mock=str(self.mock_dir)))

    def render(self, obj):
        return self.host.send({'op': 'world-render', 'principal': genesis.OPENER, 'object': obj})

    def pending(self):
        return self.host.send({'op': 'world-renders'})['pending']

    def test_a_full_queue_and_a_model_call_past_worker_grace_do_not_spend_attempts(self):
        self.pending()
        queued = [self.render(obj) for obj in self.objects]
        self.assertEqual({r['status'] for r in queued}, {'pending'}, queued)
        self.assertEqual(self.render('station').get('reason'), 'busy')
        pending = self.pending()
        self.assertEqual(len(pending), 64)
        for item in pending:
            fixture(self.mock_dir, item['request'], '[[1]]')
        calls = []

        def ask(request):
            calls.append(request)
            if len(calls) == 1:
                # One serial call crosses both reader patience (3s) and worker grace (10s).
                time.sleep(10.1)
                held = self.render(self.objects[-1])
                self.assertEqual((held['status'], held['reason']), ('exact', 'unattended'), held)
                waiting = self.pending()
                self.assertEqual(len(waiting), 64)
                self.assertEqual({r['attempts'] for r in waiting}, {0})
            return model.ask(request, self.st)

        done = interpret.paint(self.host, ask)
        self.assertEqual(set(done['painted']), {r['key'] for r in queued}, done)
        self.assertFalse(done.get('exact') or done.get('retrying') or done.get('failed'), done)
        self.assertEqual(len(calls), 64)
        self.assertEqual({self.render(obj)['status'] for obj in self.objects}, {'painted'})

    def test_a_clause_refusal_retries_once_without_network_attempts_then_keeps_its_verdict(self):
        self.pending()
        first = self.render('station')
        self.assertEqual(first['status'], 'pending', first)
        item, = self.pending()
        fixture(self.mock_dir, item['request'], 'A station has rung.')
        done = interpret.paint(self.host, lambda req: model.ask(req, self.st))
        self.assertEqual(done.get('retrying'), [first['key']], done)
        retry, = self.pending()
        self.assertEqual(retry['attempts'], 0)
        self.assertIn('The last paint was thrown away whole', retry['request']['user'])
        fixture(self.mock_dir, retry['request'], 'A station has rung.')
        done = interpret.paint(self.host, lambda req: model.ask(req, self.st))
        held = self.render('station')
        self.assertEqual((held['status'], held['reason'], held['clause']),
                         ('exact', 'rejected', 'imagery'), held)
        self.assertEqual(done.get('exact'), [first['key']], done)
        self.assertEqual(done.get('verdicts'), [held], done)
        self.assertEqual(self.pending(), [])

    def test_only_submitted_transport_failures_exhaust_the_three_model_attempts(self):
        self.pending()
        first = self.render('station')
        # No fixture: model.ask returns failed/transport. Each submitted failure,
        # rather than elapsed time or listing the queue, consumes one attempt.
        for tried in (1, 2):
            done = interpret.paint(self.host, lambda req: model.ask(req, self.st))
            self.assertEqual(done.get('retrying'), [first['key']], done)
            self.assertEqual(done['verdicts'][0]['attempts'], tried)
            self.assertNotIn('clause', done['verdicts'][0])
            self.assertEqual(self.pending(), [])  # not yet at the host's next
            time.sleep(2.1)
            item, = self.pending()
            self.assertEqual(item['attempts'], tried)
        done = interpret.paint(self.host, lambda req: model.ask(req, self.st))
        held = self.render('station')
        self.assertEqual((held['status'], held['clause'], held['detail']), ('exact', 'model', 'transport'), held)
        self.assertEqual(done.get('verdicts'), [held], done)
        self.assertEqual(self.pending(), [])


if __name__ == '__main__':
    unittest.main()
